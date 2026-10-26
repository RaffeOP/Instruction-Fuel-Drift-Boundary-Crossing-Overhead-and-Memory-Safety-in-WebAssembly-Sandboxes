"""Generate the RQ4 recycling-slope table and the RQ5 linear-recalibration bound table.

Reads data/rq4_*.csv, data/dynamic_opcode_mix.csv, data/opcode_mix_*.csv and
results/metrics/rq1_cell_summary.csv, rq5_*.csv. Writes tables/tab08.tex and tables/tab09.tex.
"""

import csv
import statistics
from collections import defaultdict
from pathlib import Path
from fit_tables_to_width import fit_all

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
METRICS = ROOT / "results" / "metrics"
RECYCLING_TABLE_PATH = ROOT / "tables" / "tab08.tex"
BOUND_TABLE_PATH = ROOT / "tables" / "tab09.tex"

Z_95 = 1.96
T_95_FOUR_DF = 2.776
OPCODE_LEVELS = ("O0", "O2", "O3", "Oz")
EXCLUDED_AGGREGATE_CLASS = "memory_ops"
DYNAMIC_META_COLUMNS = ("kernel", "group", "opt_level", "reps", "dynamic_total", "result")
STATIC_META_COLUMNS = ("kernel", "group", "opt_level")
LIFECYCLE_STEP = 1000


def ols_slope(xs, ys):
    """Return the OLS slope and its standard error."""
    count = len(xs)
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    residual_ss = sum((y - intercept - slope * x) ** 2 for x, y in zip(xs, ys))
    return slope, (residual_ss / (count - 2) / sxx) ** 0.5


def grouped_series(path, key_fn, value_column):
    """Map each series key to its (lifecycle, value) lists."""
    series = defaultdict(lambda: ([], []))
    for row in csv.DictReader(path.open()):
        key = key_fn(row)
        series[key][0].append(float(row["lifecycle"]))
        series[key][1].append(float(row[value_column]))
    return series


def lifecycles_per_series(series):
    return int(max(max(xs) for xs, _ in series.values())) + LIFECYCLE_STEP


def recycling_rows():
    """Return one row per recycling condition with slope, interval, and run count."""
    python_series = grouped_series(DATA / "rq4_multitenant_rss_uss.csv",
                                   lambda r: r["condition"], "uss_bytes")
    dirty_series = grouped_series(DATA / "rq4_dirty_pages_control.csv",
                                  lambda r: str(r["dirty_pages"]), "internal")
    allocator_series = grouped_series(DATA / "rq4_allocation_strategy_uss.csv",
                                      lambda r: (r["condition"], r["repeat"]),
                                      "private_anonymous_bytes")
    rows = []
    for label, condition in (("Python, default reservation", "on_demand_default"),
                             ("Python, no growth reservation", "no_growth_reservation")):
        rows.append(single_run_row(label, python_series[condition], 1))
    for label, condition in (("Rust, zero dirty pages", "0"), ("Rust, four dirty pages", "4")):
        rows.append(single_run_row(label, dirty_series[condition], 1))
    rows.append(repeated_row("Rust, on-demand allocation", allocator_series, "on_demand"))
    rows.append(repeated_row("Rust, pooled allocation", allocator_series, "pooled"))
    return rows


def single_run_row(label, series, repeats):
    slope, standard_error = ols_slope(*series)
    half_width = Z_95 * standard_error
    lifecycles = lifecycles_per_series({"only": series})
    return {"label": label, "repeats": repeats, "lifecycles": lifecycles,
            "slope": slope, "low": slope - half_width, "high": slope + half_width}


def repeated_row(label, allocator_series, allocator):
    slopes = []
    lifecycles = 0
    for (condition, _), series in allocator_series.items():
        if condition != allocator:
            continue
        slopes.append(ols_slope(*series)[0])
        lifecycles = lifecycles_per_series({"only": series})
    mean = statistics.fmean(slopes)
    half_width = T_95_FOUR_DF * statistics.stdev(slopes) / len(slopes) ** 0.5
    return {"label": label, "repeats": len(slopes), "lifecycles": lifecycles * len(slopes),
            "slope": mean, "low": mean - half_width, "high": mean + half_width}


def write_recycling_table(rows):
    body = "\n".join(
        f"{row['label']} & {row['repeats']} & {row['lifecycles']:,} & {row['slope']:.2f} & "
        f"$[{row['low']:.2f}, {row['high']:.2f}]$ \\\\"
        for row in rows
    )
    total = sum(row["lifecycles"] for row in rows)
    RECYCLING_TABLE_PATH.write_text(
        "\\begin{table}[t]\n"
        "\\caption{Recycling growth slopes for the six RQ4 conditions. Each slope is the OLS slope of "
        "private memory against recycled lifecycle count, in bytes per lifecycle. Single-run conditions "
        "report a 95\\% interval from the OLS standard error. Rust allocator conditions report the mean of "
        "five repeat slopes with a 95\\% $t$ interval on the repeat mean. The six conditions together "
        f"comprise {total:,} recycled lifecycles.}}\\label{{tab:rq4_slopes}}\n"
        "\\begin{tabular}{lrrrr}\n"
        "\\toprule\n"
        "Condition & Repeats & Lifecycles & Slope (B/lifecycle) & 95\\% interval \\\\\n"
        "\\midrule\n"
        f"{body}\n"
        "\\bottomrule\n"
        "\\end{tabular}\n"
        "\\end{table}\n"
    )


def read_cranelift_fuel_psi():
    psi = {}
    for row in csv.DictReader((METRICS / "rq1_cell_summary.csv").open()):
        if row["runtime"] == "wasmtime-cranelift":
            psi[(row["opt_level"], row["kernel"])] = float(row["psi_mean_ns_per_fuel"])
    return psi


def class_share_fit(rows, class_names, total_fn, psi):
    """Least-squares fit of cost per fuel on class shares, with an intercept."""
    targets = []
    shares = []
    for row in rows:
        key = (row["opt_level"], row["kernel"])
        if key not in psi:
            continue
        total = total_fn(row)
        shares.append([1.0] + [float(row[name]) / total for name in class_names])
        targets.append(psi[key])
    design = np.array(shares)
    target = np.array(targets)
    coefficients, *_ = np.linalg.lstsq(design, target, rcond=None)
    residual = target - design @ coefficients
    r_squared = 1 - float((residual ** 2).sum()) / float(((target - target.mean()) ** 2).sum())
    coefficient_of_variation = target.std(ddof=1) / target.mean()
    return {"r2": r_squared, "cv": coefficient_of_variation,
            "bound": coefficient_of_variation * (1 - r_squared) ** 0.5, "n": len(target)}


def dynamic_fit(psi):
    rows = list(csv.DictReader((DATA / "dynamic_opcode_mix.csv").open()))
    names = [c for c in rows[0] if c not in DYNAMIC_META_COLUMNS and c != EXCLUDED_AGGREGATE_CLASS]
    return class_share_fit(rows, names, lambda r: float(r["dynamic_total"]), psi)


def static_fit(psi):
    rows = []
    for level in OPCODE_LEVELS:
        for row in csv.DictReader((DATA / f"opcode_mix_{level}.csv").open()):
            row["opt_level"] = level
            rows.append(row)
    names = [c for c in rows[0] if c not in STATIC_META_COLUMNS and c != EXCLUDED_AGGREGATE_CLASS]
    for row in rows:
        row["_total"] = sum(float(row[c]) for c in names)
    return class_share_fit(rows, names, lambda r: r["_total"], psi)


def best_loo_cv(model_name):
    """Lowest leave-one-cell-out CV over the ridge-strength grid for one model."""
    values = [
        float(row["cv_psi"])
        for row in csv.DictReader((METRICS / "rq5_dynamic_loo.csv").open())
        if row["model"] == model_name
    ]
    return min(values)


def write_bound_table(psi):
    static = static_fit(psi)
    dynamic = dynamic_fit(psi)
    body = "\n".join([
        f"Static class counts & {static['n']} & {static['r2']:.3f} & {static['bound']:.3f} & "
        f"{best_loo_cv('static opcode classes'):.3f} \\\\",
        f"Dynamic class counts & {dynamic['n']} & {dynamic['r2']:.3f} & {dynamic['bound']:.3f} & "
        f"{best_loo_cv('dynamic opcode classes'):.3f} \\\\",
    ])
    BOUND_TABLE_PATH.write_text(
        "\\begin{table}[t]\n"
        "\\caption{Linear recalibration bound on the 200 Cranelift cells. $R^2$ is the in-sample coefficient "
        "of determination of a least-squares fit of $\\mu_\\psi$ on the operator-class shares, with an "
        "intercept. The in-sample bound is $\\mathrm{CV}(\\mu_\\psi)\\sqrt{1-R^2}$ with "
        "$\\mathrm{CV}(\\mu_\\psi)=0.983$, the smallest residual coefficient of variation any such fit can "
        "reach (Proposition~\\ref{prop:linear_bound}). The last column is the lowest leave-one-cell-out CV from "
        "Table~\\ref{tab:rq5}. That score is multiplicative, CV of time divided by prediction, so the in-sample "
        "bound does not apply to it.}\\label{tab:rq5_bound}\n"
        "\\begin{tabular}{lrrrr}\n"
        "\\toprule\n"
        "Class counts & Cells & $R^2$ & In-sample bound & Best LOO CV \\\\\n"
        "\\midrule\n"
        f"{body}\n"
        "\\bottomrule\n"
        "\\end{tabular}\n"
        "\\end{table}\n"
    )


LATENCY_TABLE_PATH = ROOT / "tables" / "tab19.tex"
NANOSECONDS_PER_MICROSECOND = 1e3
PERCENTILES = (50, 95, 99)


def latency_series(name):
    return np.load(DATA / f"rq4_latency_{name}.npy").astype(float) / NANOSECONDS_PER_MICROSECOND


def percentile_profile(values):
    return [float(np.percentile(values, q)) for q in PERCENTILES]


def latency_rows(recycling):
    slopes = {row["label"]: row["slope"] for row in recycling}
    rows = []
    for label, name in (("Python, default reservation", "on_demand_default"),
                        ("Python, no growth reservation", "no_growth_reservation")):
        median, p95, p99 = percentile_profile(latency_series(name))
        rows.append((label, 1, median, median, median, p95, p99, slopes[label]))
    for label, allocator in (("Rust, on-demand allocation", "on_demand"),
                             ("Rust, pooled allocation", "pooled")):
        profiles = np.array([percentile_profile(latency_series(f"{allocator}_r{r}")) for r in range(5)])
        medians = profiles[:, 0]
        rows.append((label, 5, float(np.median(medians)), float(medians.min()), float(medians.max()),
                     float(np.median(profiles[:, 1])), float(np.median(profiles[:, 2])), slopes[label]))
    return rows


def range_text(repeats, low, high):
    if repeats == 1:
        return "---"
    return f"{low:.1f}--{high:.1f}"


def write_latency_table(recycling):
    body = "\n".join(
        f"{label} & {repeats} & {median:.1f} & {range_text(repeats, low, high)} & {p95:.1f} & {p99:.1f} & {slope:.2f} \\\\"
        for label, repeats, median, low, high, p95, p99, slope in latency_rows(recycling)
    )
    LATENCY_TABLE_PATH.write_text(
        "\\begin{table}[t]\n"
        "\\caption{Lifecycle latency and memory growth by harness and allocator. Latencies are in microseconds, "
        "computed over the 120,000 lifecycles of each series. For the Rust allocators, the median column is the "
        "median of the five per-repeat medians, the range column gives the smallest and largest repeat median, "
        "and the percentile columns are medians of the per-repeat values. The slope is the USS growth rate from "
        "Table~\\ref{tab:rq4_slopes}.}\\label{tab:rq4_latency}\n"
        "\\footnotesize\n\\setlength{\\tabcolsep}{4pt}%\n"
        "\\begin{tabular}{lrrrrrr}\n\\toprule\n"
        "Condition & Repeats & Median & Repeat range & 95th & 99th & Slope (B/lifecycle) \\\\\n"
        "\\midrule\n" + body + "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n"
    )


def main():
    write_recycling_table(recycling_rows())
    write_bound_table(read_cranelift_fuel_psi())
    write_latency_table(recycling_rows())
    print(f"wrote {RECYCLING_TABLE_PATH} and {BOUND_TABLE_PATH}")


if __name__ == "__main__":
    main()
    fit_all()
