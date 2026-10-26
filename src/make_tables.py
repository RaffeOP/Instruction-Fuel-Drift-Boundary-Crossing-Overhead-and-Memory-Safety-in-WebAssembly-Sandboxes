#!/usr/bin/env python3
"""Generates tables/tab01.tex to tab05.tex (booktabs) from the measured outputs."""

import re
from pathlib import Path

import numpy as np
import pandas as pd

from host_call_benchmarker import affine_fit
from parametric_stats_engine import clopper_pearson_ci
from recycling_auditor import ols_slope, tail_fit
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TABLE_DIR = PROJECT_ROOT / "tables"
DATA = PROJECT_ROOT / "data"
METRICS = PROJECT_ROOT / "results" / "metrics"
CONFIG_ORDER = [
    "default_2gib_guard", "reduced_64kib_guard", "zero_guard", "zero_guard_explicit_checks",
    "no_growth_reservation", "zero_guard_no_growth_reservation",
]
RUNTIME_LABELS = {
    "wasmtime-cranelift": "Wasmtime 50.0.0 Cranelift", "wasmtime-winch": "Wasmtime 50.0.0 Winch",
    "wasmer-singlepass": "Wasmer 7.5.0 Singlepass", "wasmer-cranelift": "Wasmer 7.5.0 Cranelift",
    "wasmer-llvm": "Wasmer 7.5.0 LLVM (LLVM 22.1)",
    "wasmer-singlepass-metered": "Wasmer 7.5.0 Singlepass, metered",
    "wasmer-cranelift-metered": "Wasmer 7.5.0 Cranelift, metered",
    "wasmer-llvm-metered": "Wasmer 7.5.0 LLVM, metered",
    "wasmedge-aot": "WasmEdge 0.18.0 AOT", "wasmedge-interp": "WasmEdge 0.18.0 interpreter",
    "wamr-interp": "WAMR (iwasm 2.4.5) interpreter", "v8": "V8 14.6 (Node.js 26.11.1)",
}
FUEL_METER = {"wasmtime-cranelift": "Wasm fuel", "wasmtime-winch": "Wasm fuel",
              "wasmer-singlepass-metered": "Operator count", "wasmer-cranelift-metered": "Operator count",
              "wasmer-llvm-metered": "Operator count", "wasmedge-aot": "Instruction count",
              "wasmedge-interp": "Instruction count"}
HOST_LOAD_CUTOFF = 4.0
SMALL_PAYLOAD_MAX_BYTES = 16384


def latex_escape(text: str) -> str:
    return text.replace("_", r"\_")


def write_table(name: str, caption: str, label: str, column_spec: str, header: list, rows: list,
                wide: bool = False) -> None:
    """Writes one booktabs table. Wide tables span both columns; narrow ones are scaled to one column."""
    environment = "table*" if wide else "table"
    tabular = [r"\begin{tabular}{" + column_spec + "}", r"\toprule", " & ".join(header) + r" \\", r"\midrule"]
    tabular += [" & ".join(row) + r" \\" for row in rows]
    tabular += [r"\bottomrule", r"\end{tabular}"]
    if not wide:
        tabular = [r"\resizebox{\columnwidth}{!}{%"] + tabular + ["}"]
    lines = [rf"\begin{{{environment}}}[t]", r"\centering", rf"\caption{{{caption}}}", rf"\label{{{label}}}"]
    lines += tabular + [rf"\end{{{environment}}}", ""]
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    (TABLE_DIR / name).write_text("\n".join(lines))


def tab01_campaign() -> None:
    cells = pd.read_csv(METRICS / "rq1_cell_summary.csv")
    rows = []
    for runtime, label in RUNTIME_LABELS.items():
        subset = cells[cells["runtime"] == runtime]
        timed = pd.read_csv(DATA / f"rq1_{runtime}.csv")
        ratio = timed["wall_ns"] / timed["cpu_ns"]
        rows.append([label, FUEL_METER.get(runtime, "none"), str(int(subset["replicates"].iloc[0])),
                     f"{int(subset['replicates'].sum()):,}", f"{ratio.median():.3f} ({ratio.quantile(0.95):.3f})"])
    rq2 = pd.read_csv(DATA / "rq2_boundary_conformance.csv")
    rq3 = pd.read_csv(DATA / "rq3_host_call_latency.csv")
    rq4 = pd.read_csv(DATA / "rq4_multitenant_rss_uss.csv")
    rows.append(["RQ2 linear-memory probes (6 configurations)", "n/a", "100", f"{len(rq2):,}", "n/a"])
    rows.append(["RQ3 host-call samples (wasm and native)", "n/a", "926", f"{len(rq3):,}", "n/a"])
    rows.append([f"RQ4 sandbox lifecycles (2 conditions, {len(rq4)} checkpoints each)", "n/a",
                 "1 per lifecycle", "240,000", "n/a"])
    write_table("tab01.tex",
                "Measurement campaign. Each timed runtime covers 200 cells (50 kernels at four optimization levels). "
                "The wall-to-CPU ratio compares a replicate's elapsed time with its thread CPU time; a value near 1 "
                "means the timed thread was not time-shared (median, with the 95th percentile in parentheses). "
                "Each replicate waited until the 1-minute load was at most 4 (per-replicate gate, applied to WasmEdge "
                "AOT, V8, and the host-call sweep; per-step gate elsewhere).",
                "tab:campaign", "lrrrr",
                ["Experiment or runtime", "Fuel meter", "Replicates", "Runs", "Wall/CPU (p95)"], rows, wide=True)


def tab02_anova_by_group() -> None:
    anova = pd.read_csv(METRICS / "rq1_anova.csv")
    rows = []
    for group, subset in anova.groupby("group"):
        rows.append([group, str(len(subset)), str(int((subset["p_value"] < 0.05).sum())),
                     f"{subset['f_w'].median():.1f}", f"{subset['partial_eta_sq'].median():.3f}",
                     f"{subset['partial_eta_sq'].min():.3f}"])
    write_table("tab02.tex",
                "Log-transformed Welch ANOVA of on-CPU time across frontend optimization levels "
                "(Wasmtime Cranelift, 100 replicates per cell), summarized by kernel group.",
                "tab:anova", "lrrrrr",
                ["Group", "Kernels", r"$p<0.05$", r"median $F_W$", r"median $\eta_p^2$", r"min $\eta_p^2$"], rows)


def tab03_boundary() -> None:
    rq2 = pd.read_csv(DATA / "rq2_boundary_conformance.csv")
    rows = []
    for config in CONFIG_ORDER:
        subset = rq2[rq2["config"] == config]
        ok = int(subset["outcome"].isin(["spec_return", "graceful_trap"]).sum())
        rate, lower, upper = clopper_pearson_ci(ok, len(subset))
        rows.append([latex_escape(config), str(len(subset)), str(ok), f"{rate:.3f}", f"[{lower:.4f}, {upper:.3f}]"])
    write_table("tab03.tex",
                r"Trap-conformance rate $\tau_{\mathrm{trap}}$ per memory configuration (8 probes, 100 trials each), "
                r"with exact 95\% Clopper--Pearson intervals.",
                "tab:boundary", "lrrrl",
                ["Configuration", "Trials", "Conforming", r"$\tau_{\mathrm{trap}}$", "95\\% CI"], rows)


def tab04_host_fit() -> None:
    rq3 = pd.read_csv(DATA / "rq3_host_call_latency.csv")
    rows = []
    for label, frame in (("all samples", rq3), (f"load $<{HOST_LOAD_CUTOFF:g}$", rq3[rq3["loadavg_1m"] < HOST_LOAD_CUTOFF])):
        for side in ("wasm", "native"):
            subset = frame[frame["side"] == side]
            fit = affine_fit(subset["payload_bytes"].to_numpy(float), subset["per_call_ns"].to_numpy(float))
            rows.append([label, side, str(len(subset)), f"{fit['alpha_ns']:.0f} $\\pm$ {fit['alpha_ci_half']:.0f}",
                         f"{fit['beta_ns_per_byte']:.4f} $\\pm$ {fit['beta_ci_half']:.4f}", f"{fit['r_squared']:.3f}"])
    small = rq3[rq3["payload_bytes"] <= SMALL_PAYLOAD_MAX_BYTES]
    for side, label in (("wasm", "Wasm host call"), ("native", "Native baseline")):
        subset = small[small["side"] == side]
        fit = affine_fit(subset["payload_bytes"].to_numpy(float), subset["per_call_ns"].to_numpy(float))
        rows.append(["Small payloads ($64$\\,B to $16$\\,KiB)", label, str(len(subset)),
                     f"{fit['alpha_ns']:.0f} $\\pm$ {fit['alpha_ci_half']:.0f}",
                     f"{fit['beta_ns_per_byte']:.4f} $\\pm$ {fit['beta_ci_half']:.4f}", f"{fit['r_squared']:.3f}"])
    wasi = wasi_per_write()
    for side, label in (("preview1", "WASI Preview 1"), ("preview2", "WASI Preview 2")):
        subset = wasi[wasi["side"] == side]
        fit = affine_fit(subset["payload_bytes"].to_numpy(float), subset["per_write_ns"].to_numpy(float))
        rows.append(["WASI write, all sizes", label, str(len(subset)), f"{fit['alpha_ns']:.0f} $\\pm$ {fit['alpha_ci_half']:.0f}",
                     f"{fit['beta_ns_per_byte']:.4f} $\\pm$ {fit['beta_ci_half']:.4f}", f"{fit['r_squared']:.3f}"])
    write_table("tab04.tex",
                r"Affine fits $T(s)=\alpha+\beta s$ with OLS 95\% half-widths. Host rows: per-call latency of the "
                r"Wasmtime host-function boundary and the native copy-and-validate baseline, 64\,B to 16\,MiB. WASI rows: "
                r"per-write cost of a stdout write to \texttt{/dev/null} (instantiation subtracted), 64\,B to 16\,MiB payloads. "
                r"Host rows were sampled under a per-sample load gate of 4 (1-minute load median 3.4, maximum 5.5); the load-filtered rows drop the 13 wasm and 3 native samples above 4.",
                "tab:hostfit", "llrrrr",
                ["Sample", "Side", "n", r"$\alpha$ (ns)", r"$\beta$ (ns/B)", r"$R^2$"], rows, wide=True)


def tab05_recycling_and_calibwasm() -> None:
    rq4 = pd.read_csv(DATA / "rq4_multitenant_rss_uss.csv")
    rows = []
    alloc = pd.read_csv(DATA / "rq4_allocation_strategy_uss.csv")
    for condition in ["on_demand", "pooled"]:
        sl = [stats.linregress(g.lifecycle, g.private_anonymous_bytes).slope for _, g in alloc[alloc.condition == condition].groupby("repeat")]
        sl = np.array(sl)
        half = stats.t.ppf(0.975, len(sl) - 1) * sl.std(ddof=1) / np.sqrt(len(sl))
        rows.append([f"RQ4 Rust child {condition.replace('_', chr(92) + '_')}", f"{sl.mean():.2f} $\\pm$ {half:.2f} B/lc", "n/a", "n/a"])
    for dp, g in pd.read_csv(DATA / "rq4_dirty_pages_control.csv").groupby("dirty_pages"):
        slope = stats.linregress(g.lifecycle, g.internal).slope
        rows.append([f"RQ4 control, {dp} dirty pages per sandbox", f"{slope:.2f} B/lc", "n/a", "n/a"])
    for condition in rq4["condition"].unique():
        subset = rq4[rq4["condition"] == condition]
        slope, lower, upper, p_value = ols_slope(subset["lifecycle"].to_numpy(float), subset["uss_bytes"].to_numpy(float))
        tail = tail_fit(np.load(DATA / f"rq4_latency_{condition}.npy"))
        rows.append([f"RQ4 {latex_escape(condition)}", f"{slope:.3f} [{lower:.3f}, {upper:.3f}] B/lc",
                     f"{p_value:.2e}", f"{tail['shape_xi']:.3f}"])
    calib = pd.read_csv(METRICS / "rq5_calibwasm_loo.csv")
    for _, row in calib.iterrows():
        if row["lambda"] == "fuel-only baseline":
            label = "RQ5 fuel-only baseline"
        else:
            label = f"RQ5 CalibWasm $\\lambda={float(row['lambda']):g}$"
        rows.append([label, f"CV {row['cv_uncalibrated']:.3f} $\\to$ {row['cv_calibrated_loo']:.3f}", "n/a",
                     f"{row['cv_change_pct']:.1f}\\%"])
    dynamic = pd.read_csv(METRICS / "rq5_dynamic_loo.csv")
    for _, row in dynamic[dynamic["model"] == "dynamic opcode classes"].iterrows():
        rows.append([f"RQ5 dynamic classes $\\lambda={float(row['lambda']):g}$",
                     f"CV {dynamic.loc[0, 'cv_psi']:.3f} $\\to$ {row['cv_psi']:.3f}", "n/a",
                     f"{row['cv_change_pct']:.1f}\\%"])
    write_table("tab05.tex",
                r"Recycling leak slope (OLS over 1{,}000-lifecycle checkpoints, 95\% CI; last column is the GPD "
                r"shape $\xi$) and leave-one-cell-out calibration of cost per fuel unit, with static opcode-class "
                r"counts (CalibWasm) and dynamically executed class counts. Negative change means dispersion increased.",
                "tab:rq5", "lrrr", ["Analysis", "Estimate", "$p$", r"$\xi$ / change"], rows, wide=True)


def wasi_per_write() -> pd.DataFrame:
    data = pd.read_csv(DATA / "rq3_wasi_p1_p2.csv")
    base = data[data["mode"] == "baseline"].groupby(["side", "payload_bytes", "replicate"]).cpu_ns.median()
    full = data[data["mode"] == "full"].set_index(["side", "payload_bytes", "replicate"])
    full["per_write_ns"] = (full["cpu_ns"] - base.reindex(full.index).values) / full["writes"]
    return full.reset_index()


def main() -> None:
    tab01_campaign()
    tab02_anova_by_group()
    tab03_boundary()
    tab04_host_fit()
    tab05_recycling_and_calibwasm()
    print("wrote tab01.tex to tab05.tex in", TABLE_DIR)


if __name__ == "__main__":
    main()
