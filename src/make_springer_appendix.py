"""Generate the appendix tables for the Springer manuscript from the measured data.

Writes tables/tab10.tex (per-kernel cost per fuel unit), tab11.tex (per-runtime time ratio by
optimization level), tab12.tex (corpus summary), tab13.tex (load telemetry), and tab14.tex
(dynamic operator-class shares). Every value is computed from data/ and results/metrics/.
"""

import csv
import statistics
from collections import defaultdict
from pathlib import Path
from fit_tables_to_width import fit_all

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
METRICS = ROOT / "results" / "metrics"
TABLE_DIR = ROOT / "tables"
OPT_LEVELS = ("O0", "O2", "O3", "Oz")
CRANELIFT = "wasmtime-cranelift"
RUNTIME_ORDER = (
    "v8", "wamr-interp", "wasmedge-aot", "wasmedge-interp", "wasmer-cranelift",
    "wasmer-cranelift-metered", "wasmer-llvm", "wasmer-llvm-metered", "wasmer-singlepass",
    "wasmer-singlepass-metered", "wasmtime-cranelift", "wasmtime-winch",
)
RUNTIME_LABELS = {
    "v8": "V8 (Node.js)", "wamr-interp": "WAMR interpreter", "wasmedge-aot": "WasmEdge AOT",
    "wasmedge-interp": "WasmEdge interpreter", "wasmer-cranelift": "Wasmer Cranelift",
    "wasmer-cranelift-metered": "Wasmer Cranelift, metered", "wasmer-llvm": "Wasmer LLVM",
    "wasmer-llvm-metered": "Wasmer LLVM, metered", "wasmer-singlepass": "Wasmer Singlepass",
    "wasmer-singlepass-metered": "Wasmer Singlepass, metered",
    "wasmtime-cranelift": "Wasmtime Cranelift (reference)", "wasmtime-winch": "Wasmtime Winch, metered",
}
KERNELS_PER_BLOCK = 25
LOAD_GATE = 4.0
PERCENTILE_95 = 0.95
MILLISECONDS_PER_KIB = 1024


def write_table(name, text):
    (TABLE_DIR / name).write_text(text)


def cell_rows():
    return list(csv.DictReader((METRICS / "rq1_cell_summary.csv").open()))


def kernel_psi_table(cells):
    groups = {}
    psi = {}
    for row in cells:
        if row["runtime"] == CRANELIFT:
            psi[(row["kernel"], row["opt_level"])] = float(row["psi_mean_ns_per_fuel"])
            groups[row["kernel"]] = row["group"]
    kernels = sorted(groups, key=lambda k: (groups[k], k))
    blocks = [kernels[i:i + KERNELS_PER_BLOCK] for i in range(0, len(kernels), KERNELS_PER_BLOCK)]
    lines = []
    for index in range(KERNELS_PER_BLOCK):
        cells_in_row = []
        for block in blocks:
            if index >= len(block):
                cells_in_row.extend(["", "", "", "", ""])
                continue
            kernel = block[index]
            values = [f"{psi[(kernel, level)]:.3f}" for level in OPT_LEVELS]
            cells_in_row.append(kernel.replace("_", "\\_"))
            cells_in_row.extend(values)
        lines.append(" & ".join(cells_in_row) + " \\\\")
    header = " & ".join(["Kernel", "O0", "O2", "O3", "Oz"] * len(blocks))
    write_table("tab10.tex",
        "\\begin{table}[t]\n"
        "\\caption{Cost per fuel unit $\\mu_\\psi$ in nanoseconds for every kernel under Wasmtime Cranelift, "
        "at each frontend optimization level. Each entry is the mean over the timed replicates of that cell.}"
        "\\label{tab:per_kernel_psi}\n"
        "\\footnotesize\n\\setlength{\\tabcolsep}{3pt}%\n"
        "\\begin{tabular}{" + "l" + "r" * 4 + ("|l" + "r" * 4) * (len(blocks) - 1) + "}\n"
        "\\toprule\n" + header + " \\\\\n\\midrule\n" + "\n".join(lines) + "\n\\bottomrule\n\\end{tabular}\n"
        "\\end{table}\n")
    return psi


def ratio_by_level_table(cells):
    cpu = {}
    for row in cells:
        cpu[(row["runtime"], row["opt_level"], row["kernel"])] = float(row["cpu_median_ns"])
    kernels = {k for (_, _, k) in cpu}
    lines = []
    for runtime in RUNTIME_ORDER:
        medians = []
        for level in OPT_LEVELS:
            ratios = [cpu[(runtime, level, k)] / cpu[(CRANELIFT, level, k)] for k in kernels]
            medians.append(statistics.median(ratios))
        values = " & ".join(f"${value:.2f}\\times$" for value in medians)
        lines.append(f"{RUNTIME_LABELS[runtime]} & {values} \\\\")
    write_table("tab11.tex",
        "\\begin{table}[t]\n"
        "\\caption{Median per-kernel time ratio relative to Wasmtime Cranelift at each optimization level "
        "(median over the 50 kernels of the per-kernel ratio of median CPU time). Pooling the four levels "
        "reproduces the statistic in Table~\\ref{tab:runtime_summary}.}\\label{tab:ratio_by_level}\n"
        "\\footnotesize\n\\setlength{\\tabcolsep}{5pt}%\n"
        "\\begin{tabular}{lrrrr}\n\\toprule\n"
        "Runtime & \\texttt{-O0} & \\texttt{-O2} & \\texttt{-O3} & \\texttt{-Oz} \\\\\n\\midrule\n"
        + "\n".join(lines) + "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n")


def corpus_table():
    rows = list(csv.DictReader((DATA / "corpus_manifest.csv").open()))
    sizes = defaultdict(list)
    kernels = defaultdict(set)
    for row in rows:
        sizes[(row["group"], row["opt_level"])].append(int(row["wasm_bytes"]) / MILLISECONDS_PER_KIB)
        kernels[row["group"]].add(row["kernel"])
    groups = ("polybench", "integer", "memory")
    labels = {"polybench": "PolyBench/C numerical", "integer": "Integer and cryptographic",
              "memory": "Linear-memory behavior"}
    lines = []
    for group in groups:
        medians = " & ".join(f"{statistics.median(sizes[(group, level)]):.1f}" for level in OPT_LEVELS)
        lines.append(f"{labels[group]} & {len(kernels[group])} & {len(kernels[group]) * len(OPT_LEVELS)} & {medians} \\\\")
    write_table("tab12.tex",
        "\\begin{table}[t]\n"
        "\\caption{Corpus summary. Each kernel is compiled at four frontend optimization levels, giving "
        "200 modules. Median module size is in kibibytes of \\texttt{wasm32-wasip1} output.}"
        "\\label{tab:corpus}\n"
        "\\footnotesize\n\\setlength{\\tabcolsep}{5pt}%\n"
        "\\begin{tabular}{lrrrrrr}\n\\toprule\n"
        "Group & Kernels & Modules & \\texttt{-O0} KiB & \\texttt{-O2} KiB & \\texttt{-O3} KiB & \\texttt{-Oz} KiB \\\\\n"
        "\\midrule\n" + "\n".join(lines) + "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n")


def load_table():
    loads = []
    stamps = []
    for row in csv.DictReader((DATA / "load_log.csv").open()):
        loads.append(float(row["load1"]))
        stamps.append(int(row["timestamp"]))
    ordered = sorted(loads)
    p95 = ordered[int(PERCENTILE_95 * (len(ordered) - 1))]
    above = sum(1 for value in loads if value > LOAD_GATE) / len(loads)
    span_hours = (max(stamps) - min(stamps)) / 3600
    write_table("tab13.tex",
        "\\begin{table}[t]\n"
        "\\caption{Load telemetry sampled during the campaign. The 1-minute load average is read at a fixed "
        "interval. The admission gate for each replicate is a load of at most 4. This table reports the "
        "whole sampled series, not the load at each replicate's start, which the per-replicate log does not "
        "record.}\\label{tab:load}\n"
        "\\begin{tabular}{lr}\n\\toprule\n"
        "Quantity & Value \\\\\n\\midrule\n"
        f"Samples & {len(loads):,} \\\\\n"
        f"Span (hours) & {span_hours:.1f} \\\\\n"
        f"Median 1-minute load & {statistics.median(loads):.2f} \\\\\n"
        f"95th percentile & {p95:.2f} \\\\\n"
        f"Maximum & {max(loads):.2f} \\\\\n"
        f"Share of samples above the gate of {LOAD_GATE:.0f} & {100 * above:.1f}\\% \\\\\n"
        "\\bottomrule\n\\end{tabular}\n\\end{table}\n")


def opcode_share_table():
    rows = list(csv.DictReader((DATA / "dynamic_opcode_mix.csv").open()))
    meta = {"kernel", "group", "opt_level", "reps", "dynamic_total", "result"}
    classes = [c for c in rows[0] if c not in meta]
    shares = defaultdict(list)
    for row in rows:
        total = float(row["dynamic_total"])
        for name in classes:
            shares[name].append(100 * float(row[name]) / total)
    lines = []
    for name in classes:
        values = shares[name]
        label = name.replace("_", "\\_")
        lines.append(f"\\texttt{{{label}}} & {statistics.median(values):.2f} & {min(values):.2f} & {max(values):.2f} \\\\")
    write_table("tab14.tex",
        "\\begin{table}[t]\n"
        "\\caption{Dynamic operator-class shares across the 200 cells, in percent of executed operations. "
        "Shares are computed from the instrumented counts in \\texttt{dynamic\\_opcode\\_mix.csv}.}"
        "\\label{tab:opcode_shares}\n"
        "\\footnotesize\n\\setlength{\\tabcolsep}{6pt}%\n"
        "\\begin{tabular}{lrrr}\n\\toprule\n"
        "Operator class & Median (\\%) & Minimum (\\%) & Maximum (\\%) \\\\\n\\midrule\n"
        + "\n".join(lines) + "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n")


def main():
    cells = cell_rows()
    kernel_psi_table(cells)
    ratio_by_level_table(cells)
    corpus_table()
    load_table()
    opcode_share_table()
    print("wrote tab10 to tab14 in", TABLE_DIR)


if __name__ == "__main__":
    main()
    fit_all()
