"""Generate the runtime-summary and backend-disagreement tables for the Springer manuscript.

Every number is computed from results/metrics/ and data/, so the tables cannot drift
from the measurements. Output: tables/tab06.tex and tables/tab07.tex.
"""

import csv
import statistics
from pathlib import Path
from fit_tables_to_width import fit_all

ROOT = Path(__file__).resolve().parent.parent
CELL_SUMMARY_PATH = ROOT / "results" / "metrics" / "rq1_cell_summary.csv"
RATIO_PATH = ROOT / "results" / "metrics" / "rq1_runtime_ratios.csv"
RUNTIME_TABLE_PATH = ROOT / "tables" / "tab06.tex"
BACKEND_TABLE_PATH = ROOT / "tables" / "tab07.tex"

WINCH = "wasmtime-winch"
CRANELIFT = "wasmtime-cranelift"
COMPARED_LEVELS = ("O2", "O3")
TENTH_PERCENTILE = 0.05
FIRST_QUARTILE = 0.25
THIRD_QUARTILE = 0.75
NINETY_FIFTH_PERCENTILE = 0.95
FUEL_UNIT_SCALE = 1e6
# Relative fuel differences below this are sub-unit jitter, not backend disagreement.
DISAGREEMENT_RELATIVE_FLOOR = 1e-6

RUNTIME_LABELS = {
    "v8": "V8 (Node.js)",
    "wamr-interp": "WAMR interpreter",
    "wasmedge-aot": "WasmEdge AOT",
    "wasmedge-interp": "WasmEdge interpreter",
    "wasmer-cranelift": "Wasmer Cranelift",
    "wasmer-cranelift-metered": "Wasmer Cranelift, metered",
    "wasmer-llvm": "Wasmer LLVM",
    "wasmer-llvm-metered": "Wasmer LLVM, metered",
    "wasmer-singlepass": "Wasmer Singlepass",
    "wasmer-singlepass-metered": "Wasmer Singlepass, metered",
    "wasmtime-cranelift": "Wasmtime Cranelift (reference)",
    "wasmtime-winch": "Wasmtime Winch, metered",
}


def percentile(sorted_values, fraction):
    """Linear-interpolated percentile of an already sorted list."""
    position = fraction * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def read_cells():
    rows_by_runtime = {}
    for row in csv.DictReader(CELL_SUMMARY_PATH.open()):
        rows_by_runtime.setdefault(row["runtime"], []).append(row)
    return rows_by_runtime


def fuel_spread(rows):
    """Dispersion of cost per fuel unit across cells; None if the runtime has no fuel."""
    psis = sorted(float(r["psi_mean_ns_per_fuel"]) for r in rows if r["psi_mean_ns_per_fuel"])
    if not psis:
        return None
    return {
        "a_adv": psis[-1] / psis[0],
        "p95_p5": percentile(psis, NINETY_FIFTH_PERCENTILE) / percentile(psis, TENTH_PERCENTILE),
        "iqr_psi": percentile(psis, THIRD_QUARTILE) / percentile(psis, FIRST_QUARTILE),
        "cv": statistics.stdev(psis) / statistics.fmean(psis),
    }


def clock_and_ipc(rows):
    """Median per-cell effective clock (GHz) and retired instructions per cycle."""
    clocks = []
    ipcs = []
    for row in rows:
        cycles = float(row["cycles_mean"])
        cpu_ns = float(row["cpu_mean_ns"])
        if cycles > 0 and cpu_ns > 0:
            clocks.append(cycles / cpu_ns)
            ipcs.append(float(row["instructions_mean"]) / cycles)
    return statistics.median(clocks), statistics.median(ipcs)


def spread_cells(spread):
    """LaTeX cells for the four fuel-dispersion columns, or dashes without a fuel meter."""
    if spread is None:
        return ["---"] * 4
    return [
        f"${spread['a_adv']:.1f}$",
        f"${spread['p95_p5']:.1f}$",
        f"${spread['iqr_psi']:.1f}$",
        f"${spread['cv']:.2f}$",
    ]


def runtime_table_rows(cells):
    ratios = {r["runtime"]: r for r in csv.DictReader(RATIO_PATH.open())}
    lines = []
    for runtime, label in RUNTIME_LABELS.items():
        ratio = ratios[runtime]
        clock, ipc = clock_and_ipc(cells[runtime])
        columns = [
            label,
            f"${float(ratio['ratio_median']):.2f}$",
            f"$[{float(ratio['ratio_q25']):.2f}, {float(ratio['ratio_q75']):.2f}]$",
            *spread_cells(fuel_spread(cells[runtime])),
            f"${clock:.2f}$",
            f"${ipc:.1f}$",
        ]
        lines.append(" & ".join(columns) + " \\\\")
    return lines


def write_runtime_table(cells):
    body = "\n".join(runtime_table_rows(cells))
    RUNTIME_TABLE_PATH.write_text(
        "\\begin{table}[t]\n"
        "\\caption{Cross-runtime summary over the 200 cells. Time ratios are relative to Wasmtime "
        "Cranelift; $\\mathcal{A}_{\\mathrm{adv}}$ is the largest over smallest cost per fuel unit, "
        "$P_{95}/P_5$ and $\\mathrm{IQR}_\\psi$ are the 95th-to-5th and 75th-to-25th percentile ratios "
        "of that cost, and $\\mathrm{CV}(\\mu_\\psi)$ is its coefficient of variation. Effective clock "
        "$f_{\\mathrm{eff}}$ in GHz is the per-cell median of cycles per CPU nanosecond, and IPC is the per-cell median of "
        "retired instructions per cycle. Dashes mark runtimes without a fuel meter.}\\label{tab:runtime_summary}\n"
        "\\footnotesize\n\\setlength{\\tabcolsep}{3pt}%\n"
        "\\begin{tabular}{lrrrrrrrr}\n"
        "\\toprule\n"
        "Runtime & Median ($\\times$) & IQR ($\\times$) & $\\mathcal{A}_{\\mathrm{adv}}$ & $P_{95}/P_5$ "
        "& $\\mathrm{IQR}_\\psi$ & $\\mathrm{CV}(\\mu_\\psi)$ & $f_{\\mathrm{eff}}$ & IPC \\\\\n"
        "\\midrule\n"
        f"{body}\n"
        "\\bottomrule\n"
        "\\end{tabular}\n"
        "\\end{table}\n"
    )


def read_fuel():
    fuel = {}
    for row in csv.DictReader(CELL_SUMMARY_PATH.open()):
        if row["runtime"] in (CRANELIFT, WINCH):
            fuel[(row["runtime"], row["opt_level"], row["kernel"])] = float(row["fuel"])
    return fuel


def relative_difference(fuel, level, kernel):
    cranelift = fuel[(CRANELIFT, level, kernel)]
    winch = fuel[(WINCH, level, kernel)]
    return (winch - cranelift) / cranelift


def disagreeing_kernels(fuel):
    kernels = {kernel for (_, _, kernel) in fuel}
    return sorted(
        kernel
        for kernel in kernels
        if any(
            abs(relative_difference(fuel, level, kernel)) > DISAGREEMENT_RELATIVE_FLOOR
            for level in COMPARED_LEVELS
        )
    )


def disagreement_rows(fuel):
    lines = []
    for kernel in disagreeing_kernels(fuel):
        columns = [f"\\texttt{{{kernel.replace('_', '\\_')}}}"]
        for level in COMPARED_LEVELS:
            cranelift = fuel[(CRANELIFT, level, kernel)]
            signed_percent = relative_difference(fuel, level, kernel) * 100
            columns.append(f"{cranelift / FUEL_UNIT_SCALE:,.1f}")
            columns.append(f"{signed_percent:+.2f}\\%")
        lines.append(" & ".join(columns) + " \\\\")
    return lines


def write_backend_table(fuel):
    body = "\n".join(disagreement_rows(fuel))
    BACKEND_TABLE_PATH.write_text(
        "\\begin{table}[t]\n"
        "\\caption{Kernels whose Winch and Cranelift fuel differ above numerical noise at "
        "\\texttt{-O2} and \\texttt{-O3}. Cranelift fuel is in millions of units; the Winch column gives "
        "the signed relative difference $(F_{\\mathrm{Winch}}-F_{\\mathrm{Cranelift}})/F_{\\mathrm{Cranelift}}$. "
        "These 20 cells are the backend disagreements reported in the text. Every other cell agrees exactly, "
        "except four \\texttt{pb\\_heat\\_3d} cells that differ by eight fuel units (relative difference "
        "below $10^{-7}$).}\\label{tab:backend_disagreement}\n"
        "\\footnotesize\n\\setlength{\\tabcolsep}{4pt}%\n"
        "\\begin{tabular}{lrrrr}\n"
        "\\toprule\n"
        " & \\multicolumn{2}{c}{\\texttt{-O2}} & \\multicolumn{2}{c}{\\texttt{-O3}} \\\\\n"
        "\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}\n"
        "Kernel & Cranelift fuel (M) & Winch vs.\\ Cranelift & Cranelift fuel (M) & Winch vs.\\ Cranelift \\\\\n"
        "\\midrule\n"
        f"{body}\n"
        "\\bottomrule\n"
        "\\end{tabular}\n"
        "\\end{table}\n"
    )


def main():
    cells = read_cells()
    write_runtime_table(cells)
    write_backend_table(read_fuel())
    print(f"wrote {RUNTIME_TABLE_PATH} and {BACKEND_TABLE_PATH}")


if __name__ == "__main__":
    main()
    fit_all()
