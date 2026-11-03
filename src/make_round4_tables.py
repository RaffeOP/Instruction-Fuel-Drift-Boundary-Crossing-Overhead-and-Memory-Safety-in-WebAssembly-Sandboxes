#!/usr/bin/env python3
"""
LaTeX tables added or replaced in the round-4 revision.

  tables/tab05.tex  RQ5 calibration: feature sets x {in-sample, LOCO, LOKO}, additive and
                    multiplicative scores (replaces the mixed RQ4/RQ5 table)
  tables/tab08.tex  RQ4 attribution: slopes with and without a prefaulted latency buffer,
                    plus the 10^6-lifecycle plateau
  tables/tab09.tex  Proposition 1 bound against the out-of-sample additive score
  tables/tab20.tex  kperf counter validation against known-count microbenchmarks
  tables/tab21.tex  microarchitectural attribution of log cost per fuel unit
  tables/tab22.tex  adversarial worst-case search
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
METRICS = ROOT / "results" / "metrics"
TABLES = ROOT / "tables"
KIB = 1024


def latex_sci(value: float) -> str:
    mantissa, exponent = f"{value:.1e}".split("e")
    return f"{mantissa}\\times10^{{{int(exponent)}}}"


def t_interval(values: pd.Series) -> tuple:
    mean = float(values.mean())
    half = float(stats.t.ppf(0.975, len(values) - 1) * values.std(ddof=1) / np.sqrt(len(values)))
    return mean, half


def table(caption: str, label: str, spec: str, header: str, rows: list) -> str:
    body = "\n".join(rows)
    return (
        "\\begin{table}[t]\n"
        f"\\caption{{{caption}}}\\label{{{label}}}\n"
        "\\footnotesize\n\\setlength{\\tabcolsep}{4pt}%\n"
        "\\begin{adjustbox}{max width=\\textwidth}%\n"
        f"\\begin{{tabular}}{{{spec}}}\n\\toprule\n{header} \\\\\n\\midrule\n{body}\n"
        "\\bottomrule\n\\end{tabular}%\n\\end{adjustbox}\n\\end{table}\n"
    )


def rq4_table() -> None:
    slopes = pd.read_csv(METRICS / "rq4_buffer_attribution_slopes.csv")
    rows = []
    for (mode, dirty), part in slopes.groupby(["mode", "dirty_pages"]):
        cells = []
        for prefault in (0, 1):
            values = part[part.prefault == prefault]
            mean, half = t_interval(values["slope_bytes_per_lifecycle"])
            growth = values["total_growth_bytes"].mean() / KIB
            cells.append(f"${mean:.2f} \\pm {half:.2f}$ & {growth:,.0f}")
        rows.append(f"{mode} & {dirty} & " + " & ".join(cells) + " \\\\")
    long_run = pd.read_csv(DATA / "rq4_long_run.csv")
    rows.append("\\midrule")
    for mode, part in long_run.groupby("mode"):
        plateau, tail = [], []
        for _, run in part.groupby("repeat"):
            series = run.set_index("lifecycle")["private_anonymous_bytes"]
            plateau.append((series.loc[100_000] - series.iloc[0]) / KIB)
            late = series[series.index >= 100_000]
            tail.append(stats.linregress(late.index, late.values).slope)
        rows.append(f"{mode}, $10^6$ lifecycles & 4 & \\multicolumn{{2}}{{c}}{{---}} & "
                    f"${np.mean(tail):.3f}$ (after $10^5$) & {np.mean(plateau):,.0f} (at $10^5$) \\\\")
    caption = ("RQ4 attribution of recycling growth in the Rust child. Slopes are OLS slopes of private anonymous "
               "memory against lifecycle count (bytes per lifecycle), mean of five independent processes with a 95\\% "
               "$t$ interval; growth is the total over 120,000 lifecycles in KiB. In the \\emph{faulted in loop} columns the "
               "8-byte latency record of each lifecycle is the first write to its buffer page, as in the original harness; "
               "in the \\emph{prefaulted} columns every buffer page is written before the first checkpoint. The last rows "
               "run $10^6$ lifecycles with a prefaulted buffer (three processes per allocator) and report the slope after "
               "lifecycle $10^5$ and the growth reached by then.")
    header = ("Allocator & Dirty pages & \\multicolumn{2}{c}{Buffer faulted in loop} & \\multicolumn{2}{c}{Buffer prefaulted} \\\\\n"
              "\\cmidrule(lr){3-4}\\cmidrule(lr){5-6}\n & & Slope & Growth & Slope & Growth")
    (TABLES / "tab08.tex").write_text(table(caption, "tab:rq4_slopes", "llrrrr", header, rows))


def validation_table() -> None:
    frame = pd.read_csv(DATA / "pmu" / "counter_validation.csv")
    frame = frame[frame["event"] != "cycles_per_load"]
    rows = []
    for _, row in frame.iterrows():
        test = row["test"].replace("_", "\\_")
        event = row["event"].replace("_", "\\_")
        ratio = f"{row['ratio']:.4f}" if row["expected"] > 1 else "---"
        rows.append(f"\\texttt{{{test}}} & \\texttt{{{event}}} & {row['expected']:,.0f} & {row['measured']:,.0f} & {ratio} \\\\")
    caption = ("Validation of the kperf counters on native microbenchmarks with known counts. The fixed loop retires "
               "exactly four instructions per iteration; the branch loop has one data-dependent branch per element on "
               "constant or uniformly random bits (half of the random branches are expected to mispredict); the pointer "
               "chase follows one random cycle with one pointer per 128-byte line, resident in a 16\\,KiB set or spread "
               "over 256\\,MiB. Rows with an expected count near zero show the residual count.")
    header = "Test & Event & Expected & Measured & Ratio"
    (TABLES / "tab20.tex").write_text(table(caption, "tab:pmu_validation", "llrrr", header, rows))


def attribution_table() -> None:
    cells = pd.read_csv(METRICS / "pmu_cell_summary_cranelift.csv")
    log_psi = np.log(cells["psi"])
    log_ipf = np.log(cells["ins_per_fuel"])
    log_cpi = np.log(1.0 / cells["ipc"])
    rate_columns = ["r_l1d_miss_ld", "r_branch_mispred", "r_l1d_tlb_miss", "r_l2_tlb_miss"]

    def r2(columns: list) -> float:
        design = np.column_stack([np.ones(len(cells))] + columns)
        coef, *_ = np.linalg.lstsq(design, log_psi, rcond=None)
        residual = log_psi - design @ coef
        return float(1 - (residual ** 2).sum() / ((log_psi - log_psi.mean()) ** 2).sum())

    rates = [cells[c] for c in rate_columns]
    rows = [
        f"Variance of $\\log\\mu_\\psi$ & {log_psi.var():.3f} \\\\",
        f"\\quad share from $\\log$(native instructions per fuel unit) & {log_ipf.var() / log_psi.var():.2f} \\\\",
        f"\\quad share from $\\log$ CPI & {log_cpi.var() / log_psi.var():.2f} \\\\",
        f"\\quad share from twice their covariance & {2 * np.cov(log_ipf, log_cpi)[0, 1] / log_psi.var():.2f} \\\\",
        "\\midrule",
        f"$R^2$, native instructions per fuel unit & {r2([log_ipf]):.2f} \\\\",
        f"$R^2$, four event rates per fuel unit & {r2(rates):.2f} \\\\",
        f"$R^2$, both & {r2([log_ipf] + rates):.2f} \\\\",
        "\\midrule",
    ]
    names = {"r_l1d_miss_ld": "L1D load misses per fuel unit", "r_branch_mispred": "branch mispredictions per fuel unit",
             "r_l1d_tlb_miss": "L1D TLB misses per fuel unit", "r_l2_tlb_miss": "L2 TLB misses per fuel unit",
             "wait_share": "share of cycles waiting on an L1D miss", "ipc": "retired instructions per cycle",
             "mem_share": "memory-operator share of fuel", "miss_per_memop": "L1D misses per Wasm load"}
    for column, name in names.items():
        rho, p_value = stats.spearmanr(cells[column], cells["psi"], nan_policy="omit")
        rows.append(f"Spearman $\\rho$ with $\\mu_\\psi$: {name} & ${rho:+.2f}$ ($p={latex_sci(p_value)}$) \\\\")
    caption = ("Microarchitectural attribution of the cost per fuel unit over the 200 Wasmtime Cranelift cells of the "
               "gated kperf campaign. Because $\\mu_\\psi = (\\text{native instructions per fuel unit})\\times"
               "\\mathrm{CPI}/f_{\\mathrm{eff}}$ and $f_{\\mathrm{eff}}$ is nearly constant, $\\mathrm{Var}(\\log\\mu_\\psi)$ "
               "splits into the two factors and their covariance. $R^2$ values are in-sample least-squares fits of "
               "$\\log\\mu_\\psi$ with an intercept.")
    (TABLES / "tab21.tex").write_text(table(caption, "tab:attribution", "lr", "Quantity & Value", rows))


def adversarial_table() -> None:
    path = DATA / "pmu" / "pmu_adversarial_cranelift.csv"
    winch_path = DATA / "pmu" / "pmu_adversarial_winch.csv"
    if not path.exists():
        return
    corpus = pd.read_csv(METRICS / "pmu_cell_summary_cranelift.csv")
    lo, hi = corpus["psi"].min(), corpus["psi"].max()

    def summarize(file: Path) -> pd.DataFrame:
        runs = pd.read_csv(file)
        grouped = runs.groupby("kernel", sort=False)
        out = grouped.agg(group=("group", "first"), fuel=("fuel", "first"), reps=("reps", "first"),
                          cpu=("cpu_ns", "mean"), cycles=("cycles", "mean"), l1d=("l1d_miss_ld", "mean"),
                          tlb=("l2_tlb_miss", "mean"), wait=("l1d_miss_wait_cycles", "mean"))
        out["psi"] = out["cpu"] / out["fuel"]
        out["psi_ci"] = grouped.apply(lambda g: stats.t.ppf(0.975, len(g) - 1) * (g.cpu_ns / g.fuel).std(ddof=1) / np.sqrt(len(g)))
        return out

    cran = summarize(path)
    winch = summarize(winch_path) if winch_path.exists() else None
    rows = []
    for kernel, row in cran.iterrows():
        fuel_per_rep = row["fuel"] / row["reps"]
        name = kernel.replace("adv_", "").replace("_", "\\_")
        winch_psi = f"{winch.loc[kernel, 'psi']:.3f}" if winch is not None else "---"
        rows.append(f"\\texttt{{{name}}} & {fuel_per_rep:,.0f} & ${row['psi']:.3f} \\pm {row['psi_ci']:.3f}$ & "
                    f"{row['psi'] / hi:.2f} & {row['l1d'] / row['fuel']:.3f} & {row['wait'] / row['cycles']:.2f} & {winch_psi} \\\\")
    caption = (f"Adversarial worst-case search under Wasmtime (Cranelift, 30 replicates per kernel, gated). Fuel is per "
               f"repetition of the kernel body; $\\mu_\\psi$ is in ns per fuel unit with a 95\\% $t$ interval. The ratio "
               f"column divides by the largest corpus cell, ${hi:.3f}$\\,ns (the smallest is ${lo:.4f}$\\,ns). The miss "
               f"column is retired L1D load misses per fuel unit; the wait column is the share of cycles spent waiting "
               f"on an L1D miss. The last column is $\\mu_\\psi$ under Winch. Chase kernels are named by stride, "
               f"working set, and, for \\texttt{{\\_uN}}, the number of loads nested in one expression.")
    header = "Kernel & Fuel/rep & $\\mu_\\psi$ (ns) & $\\div$ corpus max & L1D miss/fuel & Wait share & Winch $\\mu_\\psi$"
    (TABLES / "tab22.tex").write_text(table(caption, "tab:adversarial", "lrrrrrr", header, rows))


def calibration_tables() -> None:
    frame = pd.read_csv(METRICS / "calibration_v2.csv")
    cv_psi, sd_log = map(float, (METRICS / "calibration_v2_cv.txt").read_text().split())
    rows = []
    for features, part in frame.groupby("features", sort=False):
        scores = {row["split"]: row for _, row in part.iterrows()}
        insample, loco, loko = scores["in-sample OLS"], scores["LOCO"], scores["LOKO"]
        rows.append(f"{features} & {insample['r2']:.3f} & {insample['log_score']:.3f} & {loco['log_score']:.3f} & "
                    f"{loko['log_score']:.3f} & {np.exp(loko['log_score']):.2f} & {loko['multiplicative_score']:.3f} \\\\")
    caption = ("RQ5 calibration of the cost per fuel unit on the 200 Cranelift cells of the gated campaign. The target is "
               "$y=\\log\\mu_\\psi$ (standard deviation " + f"{sd_log:.3f}" + "), and the score is the RMS residual of $y$, "
               "the quantity Proposition~\\ref{prop:linear_bound} bounds: the in-sample column equals the bound "
               "$\\mathrm{sd}(y)\\sqrt{1-R^2}\\sqrt{(n-1)/n}$. LOCO holds out one cell; LOKO holds out all four builds of a "
               "kernel. Ridge strength is chosen inside each training fold by leave-one-kernel-out search. "
               "$e^{\\mathrm{RMS}}$ is the typical factor by which a LOKO-calibrated budget misses. The last column is the score "
               "used in an earlier version of this study, the coefficient of variation of $\\mu_\\psi/\\hat\\mu_\\psi$ (uncalibrated: " + f"{cv_psi:.3f}" + "). "
               "PMU features are the logarithms of L1D load misses, branch mispredictions, and L1D and L2 TLB misses per fuel "
               "unit; native instructions is the logarithm of retired native instructions per fuel unit.")
    header = (" & & \\multicolumn{3}{c}{RMS residual of $\\log\\mu_\\psi$} & \\multicolumn{2}{c}{LOKO} \\\\\n"
              "\\cmidrule(lr){3-5}\\cmidrule(lr){6-7}\n"
              "Features & $R^2$ & In-sample & LOCO & LOKO & $e^{\\mathrm{RMS}}$ & CV")
    (TABLES / "tab05.tex").write_text(table(caption, "tab:rq5", "lrrrrrr", header, rows))


def rq2_extension_table() -> None:
    compound = pd.read_csv(DATA / "r4" / "rq2_compound.csv")
    pooling = pd.read_csv(DATA / "r4" / "rq2_pooling.csv").iloc[0]
    rows = []
    for config, part in compound.groupby("config", sort=False):
        trials, conform = len(part), int(part["conforms"].sum())
        lower = stats.beta.ppf(0.025, conform, trials - conform + 1) if conform else 0.0
        rows.append(f"\\texttt{{{config.replace('_', '\\_')}}} & {trials} & {part['steps'].sum():,} & "
                    f"{part['traps_expected'].sum():,} & {conform} & {lower:.4f} \\\\")
    rows.append("\\midrule")
    rows.append(f"Pooling, {int(pooling['threads'])} threads, {int(pooling['slots'])} slots & {int(pooling['attempts']):,} & "
                f"\\multicolumn{{4}}{{l}}{{{int(pooling['admitted'])} admitted, {int(pooling['refused_cleanly'])} refused with an error, "
                f"{int(pooling['dirty_slot'])} dirty slots, {int(pooling['pattern_lost'])} lost patterns, "
                f"{int(pooling['other_errors'])} other errors}} \\\\")
    caption = ("Compound and concurrent linear-memory trials. Each compound trial is a seeded sequence of 40 operations on "
               "one instance (grows including past the declared maximum of 1{,}024 pages, loads and stores near the end and at "
               "high addresses, and \\texttt{memory.fill} and \\texttt{memory.copy} straddling the end), checked step by "
               "step against a shadow copy of memory; the same 600 sequences run under every configuration. Must-fail steps are "
               "those the specification requires to trap or, for grows, to return $-1$. The lower bound is the exact 95\\% "
               "Clopper--Pearson bound on trial conformance. The pooling row counts instantiation attempts by eight threads that "
               "each try to hold 16 tenants on a 64-slot pool.")
    header = "Configuration & Trials & Steps & Must-fail steps & Conforming & Lower bound"
    (TABLES / "tab23.tex").write_text(table(caption, "tab:rq2_compound", "lrrrrr", header, rows))


def serverless_table() -> None:
    corpus = pd.read_csv(METRICS / "rq1_cell_summary.csv")
    rows = []
    cells = {}
    for backend, runtime in (("cranelift", "wasmtime-cranelift"), ("winch", "wasmtime-winch")):
        runs = pd.read_csv(DATA / "r4" / f"serverless_{backend}.csv")
        grouped = runs.groupby(["kernel", "opt_level"]).agg(cpu=("cpu_ns", "mean"), fuel=("fuel", "first"))
        reference = corpus[corpus.runtime == runtime]["psi_mean_ns_per_fuel"].dropna()
        cells[backend] = (grouped["cpu"] / grouped["fuel"], reference)
    for kernel in sorted(cells["cranelift"][0].index.get_level_values(0).unique()):
        entries = []
        for backend in ("cranelift", "winch"):
            psi, _ = cells[backend]
            entries += [f"{psi.loc[(kernel, level)]:.4f}" for level in ("O0", "O2", "O3", "Oz")]
        rows.append(f"\\texttt{{{kernel.replace('sl_', '').replace('_', '\\_')}}} & " + " & ".join(entries) + " \\\\")
    notes = []
    for backend, name in (("cranelift", "Cranelift"), ("winch", "Winch")):
        psi, reference = cells[backend]
        low = stats.percentileofscore(reference, psi.min())
        high = stats.percentileofscore(reference, psi.max())
        notes.append(f"under {name} they lie between percentiles {low:.0f} and {high:.0f} of the 200 corpus cells")
    caption = ("Cost per fuel unit $\\mu_\\psi$ (ns) of the five serverless-style kernels at the four optimization levels, "
               "100 gated replicates per cell. The kernels are JSON request parsing, Base64 encode and decode, HTTP request "
               "routing against a 64-route table, LZ77 compression with decompression, and HMAC-SHA256 verification of "
               "JWT-sized tokens; " + "; ".join(notes) + ".")
    header = (" & \\multicolumn{4}{c}{Cranelift} & \\multicolumn{4}{c}{Winch} \\\\\n\\cmidrule(lr){2-5}\\cmidrule(lr){6-9}\n"
              "Kernel & -O0 & -O2 & -O3 & -Oz & -O0 & -O2 & -O3 & -Oz")
    (TABLES / "tab25.tex").write_text(table(caption, "tab:serverless", "lrrrrrrrr", header, rows))


def main() -> None:
    serverless_table()
    rq2_extension_table()
    rq4_table()
    validation_table()
    attribution_table()
    adversarial_table()
    if (METRICS / "calibration_v2.csv").exists():
        calibration_tables()


if __name__ == "__main__":
    main()
