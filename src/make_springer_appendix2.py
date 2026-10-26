"""Generate the data appendices of the journal manuscript from raw measurements.

Writes tables/tab15.tex (every cell), tab16.tex (RQ2 probe outcomes), tab17.tex (RQ3 host-call and
WASI sweeps), and tab18.tex (per-kernel Welch ANOVA). Every value is computed from data/ and
results/metrics/.
"""

import csv
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from fit_tables_to_width import fit_all

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
METRICS = ROOT / "results" / "metrics"
TABLE_DIR = ROOT / "tables"
OPT_LEVELS = ("O0", "O2", "O3", "Oz")
CRANELIFT = "wasmtime-cranelift"
WINCH = "wasmtime-winch"
NANOSECONDS_PER_MILLISECOND = 1e6
NANOSECONDS_PER_MICROSECOND = 1e3
FUEL_UNIT_SCALE = 1e6
PAYLOAD_LABELS = {64: "64\\,B", 1024: "1\\,KiB", 16384: "16\\,KiB", 262144: "256\\,KiB",
                  1048576: "1\\,MiB", 4194304: "4\\,MiB", 16777216: "16\\,MiB"}


def write(name, text):
    (TABLE_DIR / name).write_text(text)


def cell_table():
    rows = list(csv.DictReader((METRICS / "rq1_cell_summary.csv").open()))
    cranelift = {}
    winch = {}
    for row in rows:
        key = (row["opt_level"], row["kernel"])
        if row["runtime"] == CRANELIFT:
            cranelift[key] = row
        elif row["runtime"] == WINCH:
            winch[key] = row
    lines = []
    for key in sorted(cranelift, key=lambda k: (k[1], OPT_LEVELS.index(k[0]))):
        row = cranelift[key]
        fuel = float(row["fuel"])
        winch_diff = (float(winch[key]["fuel"]) - fuel) / fuel * 100
        kernel = row["kernel"].replace("_", "\\_")
        lines.append(
            f"\\texttt{{{kernel}}} ({key[0]}) & {fuel / FUEL_UNIT_SCALE:,.1f} & "
            f"{float(row['cpu_median_ns']) / NANOSECONDS_PER_MILLISECOND:.2f} & "
            f"{float(row['psi_mean_ns_per_fuel']):.3f} & {float(row['cycles_per_fuel']):.2f} & "
            f"{winch_diff:+.2f}\\% \\\\"
        )
    write("tab15.tex",
        "{\\scriptsize\\setlength{\\tabcolsep}{2pt}%\n\\begin{longtable}{lrrrrr}\n"
        "\\caption{Every measured cell under Wasmtime Cranelift, with the Winch fuel difference. Fuel is in "
        "millions of units, CPU time is the per-cell median of thread CPU time in milliseconds, $\\mu_\\psi$ is "
        "the cost per fuel unit in nanoseconds, and the last column gives $(F_{\\mathrm{Winch}}-F_{\\mathrm{Cranelift}})"
        "/F_{\\mathrm{Cranelift}}$.}\\label{tab:all_cells}\\\\\n"
        "\\toprule\n"
        "Kernel (level) & Fuel (M) & CPU (ms) & $\\mu_\\psi$ (ns) & Cycles/fuel & Winch diff.\\\\\n"
        "\\midrule\n\\endfirsthead\n"
        "\\toprule\n"
        "Kernel (level) & Fuel (M) & CPU (ms) & $\\mu_\\psi$ (ns) & Cycles/fuel & Winch diff.\\\\\n"
        "\\midrule\n\\endhead\n"
        "\\midrule\n\\multicolumn{6}{r}{Continued on next page}\\\\\n\\endfoot\n"
        "\\bottomrule\n\\endlastfoot\n"
        + "\n".join(lines) + "\n\\end{longtable}\n}\n")


def rq2_table():
    counts = defaultdict(Counter)
    outcomes = set()
    for row in csv.DictReader((DATA / "rq2_boundary_conformance.csv").open()):
        counts[(row["config"], row["probe"])][row["outcome"]] += 1
        outcomes.add(row["outcome"])
    ordered = sorted(outcomes)
    outcome_labels = {"spec_return": "Spec.\\ return", "graceful_trap": "Graceful"}
    header = " & ".join(["Probe", "Trials"] + [outcome_labels.get(o, o) for o in ordered])
    lines = []
    for config in sorted({config for config, _ in counts}):
        label = config.replace("_", "\\_\\allowbreak ")
        lines.append(f"\\multicolumn{{{2 + len(ordered)}}}{{l}}{{\\texttt{{{label}}}}} \\\\")
        for probe in sorted(p for c, p in counts if c == config):
            total = sum(counts[(config, probe)].values())
            cells = " & ".join(f"{counts[(config, probe)][o]:,}" for o in ordered)
            probe_label = probe.replace("_", "\\_\\allowbreak ")
            lines.append(f"\\quad \\texttt{{{probe_label}}} & {total:,} & {cells} \\\\")
        lines.append("\\midrule")
    columns = "l" + "r" * (1 + len(ordered))
    write("tab16.tex",
        "{\\scriptsize\\setlength{\\tabcolsep}{3pt}%\n\\begin{longtable}{" + columns + "}\n"
        "\\caption{Linear-memory probe outcomes for every configuration and probe. Each probe row covers the "
        "100 trials of one probe under one guard configuration. A specified return and a graceful trap both "
        "conform to the specification.}\\label{tab:rq2_outcomes}\\\\\n"
        "\\toprule\n"
        f"{header} \\\\\n"
        "\\midrule\n\\endfirsthead\n"
        "\\toprule\n"
        f"{header} \\\\\n"
        "\\midrule\n\\endhead\n"
        "\\midrule\n\\multicolumn{" + str(2 + len(ordered)) + "}{r}{Continued on next page}\\\\\n\\endfoot\n"
        "\\bottomrule\n\\endlastfoot\n"
        + "\n".join(lines[:-1]) + "\n\\end{longtable}\n}\n")


def host_medians():
    medians = defaultdict(list)
    for row in csv.DictReader((DATA / "rq3_host_call_latency.csv").open()):
        medians[(row["side"], int(row["payload_bytes"]))].append(float(row["per_call_ns"]))
    return {key: statistics.median(values) for key, values in medians.items()}


def wasi_per_write_medians():
    """Median over replicates of (full minus baseline CPU time) divided by writes, in nanoseconds."""
    runs = defaultdict(dict)
    for row in csv.DictReader((DATA / "rq3_wasi_p1_p2.csv").open()):
        key = (row["side"], int(row["payload_bytes"]), int(row["replicate"]))
        runs[key][row["mode"]] = (float(row["cpu_ns"]), int(row["writes"]))
    per_write = defaultdict(list)
    for (side, size, _), modes in runs.items():
        if "full" in modes and "baseline" in modes:
            full_cpu, writes = modes["full"]
            baseline_cpu, _ = modes["baseline"]
            per_write[(side, size)].append((full_cpu - baseline_cpu) / writes)
    return {key: statistics.median(values) for key, values in per_write.items()}


def rq3_table():
    host = host_medians()
    wasi = wasi_per_write_medians()
    lines = []
    for size in sorted(PAYLOAD_LABELS):
        wasm_us = host[("wasm", size)] / NANOSECONDS_PER_MICROSECOND
        native_us = host[("native", size)] / NANOSECONDS_PER_MICROSECOND
        p1 = wasi[("preview1", size)] / NANOSECONDS_PER_MICROSECOND
        p2 = wasi[("preview2", size)] / NANOSECONDS_PER_MICROSECOND
        lines.append(
            f"{PAYLOAD_LABELS[size]} & {wasm_us:,.3f} & {native_us:,.3f} & {wasm_us / native_us:.1f} & "
            f"{p1:.3f} & {p2:.3f} & {p2 / p1:.2f} \\\\"
        )
    write("tab17.tex",
        "\\begin{table}[t]\n"
        "\\caption{Host-call and WASI costs by payload size. Host-call entries are medians of the per-call "
        "time, in microseconds, for the wasm boundary and for the native copy-and-validate. WASI entries are "
        "the median over replicates of the full-minus-baseline CPU time per write, in microseconds, for "
        "Preview 1 and Preview 2. The last column is the Preview 2 to Preview 1 ratio.}\\label{tab:rq3_sweep}\n"
        "\\footnotesize\n\\setlength{\\tabcolsep}{4pt}%\n"
        "\\begin{tabular}{lrrrrrr}\n\\toprule\n"
        "Payload & Host call ($\\mu$s) & Native ($\\mu$s) & Ratio & P1 write ($\\mu$s) & P2 write ($\\mu$s) & P2/P1 \\\\\n"
        "\\midrule\n" + "\n".join(lines) + "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n")


def format_p_value(p_value):
    """Scientific notation for a p-value, with an explicit bound for values that underflow."""
    if p_value == 0:
        return "$<10^{-300}$"
    mantissa, exponent = f"{p_value:.2e}".split("e")
    return f"${mantissa}\\times10^{{{int(exponent)}}}$"


def anova_table():
    lines = []
    for row in csv.DictReader((METRICS / "rq1_anova.csv").open()):
        kernel = row["kernel"].replace("_", "\\_")
        p_value = float(row["p_value"])
        p_text = format_p_value(p_value)
        lines.append(
            f"\\texttt{{{kernel}}} & {row['group']} & {float(row['f_w']):,.1f} & "
            f"{float(row['df_within']):.1f} & {p_text} & {float(row['partial_eta_sq']):.3f} \\\\"
        )
    write("tab18.tex",
        "{\\scriptsize\\setlength{\\tabcolsep}{4pt}%\n\\begin{longtable}{llrrp{2.0cm}r}\n"
        "\\caption{Welch's heteroscedastic ANOVA of log-transformed CPU time across the four frontend levels, "
        "for each kernel under Wasmtime Cranelift. Degrees of freedom between groups are 3 for every kernel. "
        "The within-group degrees of freedom are fractional because of the Welch correction.}"
        "\\label{tab:per_kernel_anova}\\\\\n"
        "\\toprule\n"
        "Kernel & Group & $F_W$ & $\\mathrm{df}$ & $p$ & $\\eta_p^2$ \\\\\n"
        "\\midrule\n\\endfirsthead\n"
        "\\toprule\n"
        "Kernel & Group & $F_W$ & $\\mathrm{df}$ & $p$ & $\\eta_p^2$ \\\\\n"
        "\\midrule\n\\endhead\n"
        "\\midrule\n\\multicolumn{6}{r}{Continued on next page}\\\\\n\\endfoot\n"
        "\\bottomrule\n\\endlastfoot\n"
        + "\n".join(lines) + "\n\\end{longtable}\n}\n")


def main():
    cell_table()
    rq2_table()
    rq3_table()
    anova_table()
    print("wrote tab15 to tab18 in", TABLE_DIR)


if __name__ == "__main__":
    main()
    fit_all()
