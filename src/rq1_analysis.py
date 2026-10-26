#!/usr/bin/env python3
"""
RQ1 and RQ5 analysis over the 50-kernel corpus and every timing sweep that completed.

Cost measures:
  cpu_ns  per-thread on-CPU time of one timed run(reps) call (hardware PMU counters are not accessible).
  fuel    Wasmtime fuel (Cranelift and Winch) or WasmEdge instruction count (interpreter and AOT).
          Wasmer, WAMR, and V8 expose no comparable meter and are timing-only.

Outputs under results/metrics/: per-cell summaries, checksum agreement, per-runtime
A_adv, runtime time ratios, per-kernel Welch ANOVA, and CalibWasm leave-one-cell-out.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import nnls

from parametric_stats_engine import compute_log_welch_anova

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
METRICS = PROJECT_ROOT / "results" / "metrics"
RUN_FILES = {
    "wasmtime-cranelift": "rq1_wasmtime-cranelift.csv",
    "wasmtime-winch": "rq1_wasmtime-winch.csv",
    "wasmer-singlepass": "rq1_wasmer-singlepass.csv",
    "wasmer-cranelift": "rq1_wasmer-cranelift.csv",
    "wasmer-llvm": "rq1_wasmer-llvm.csv",
    "wasmedge-aot": "rq1_wasmedge-aot.csv",
    "wasmedge-interp": "rq1_wasmedge-interp.csv",
    "wasmedge-aot": "rq1_wasmedge-aot.csv",
    "wasmer-cranelift-metered": "rq1_wasmer-cranelift-metered.csv",
    "wasmer-llvm-metered": "rq1_wasmer-llvm-metered.csv",
    "wasmer-singlepass-metered": "rq1_wasmer-singlepass-metered.csv",
    "wamr-interp": "rq1_wamr-interp.csv",
    "v8": "rq1_v8.csv",
}
FUEL_RUNTIMES = ("wasmtime-cranelift", "wasmtime-winch", "wasmedge-aot", "wasmedge-interp",
                 "wasmer-cranelift-metered", "wasmer-llvm-metered", "wasmer-singlepass-metered")
REFERENCE_RUNTIME = "wasmtime-cranelift"
OPT_LEVELS = ("O0", "O2", "O3", "Oz")
OPCODE_CLASSES = (
    "int_arith", "float_arith", "compare", "memory_load", "memory_store",
    "branch", "control", "call", "local_global", "const", "conversion", "memory_ops", "other",
)
NS_PER_MS = 1e6
CALIBWASM_LAMBDAS = (0.01, 0.1, 1.0, 10.0)


def load_runs() -> pd.DataFrame:
    frames = []
    for runtime, filename in RUN_FILES.items():
        path = DATA / filename
        if path.exists():
            frame = pd.read_csv(path)
            if len(frame):
                frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def cell_summary(runs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (runtime, opt, kernel), group in runs.groupby(["runtime", "opt_level", "kernel"]):
        fuel = group["fuel"].dropna()
        row = {
            "runtime": runtime, "opt_level": opt, "kernel": kernel, "group": group["group"].iloc[0],
            "replicates": len(group), "cpu_mean_ns": group["cpu_ns"].mean(),
            "cpu_median_ns": group["cpu_ns"].median(), "cpu_sd_ns": group["cpu_ns"].std(),
            "cycles_mean": group["cycles"].mean() if "cycles" in group else np.nan,
            "instructions_mean": group["instructions"].mean() if "instructions" in group else np.nan,
            "wall_median_ns": group["wall_ns"].median(), "checksum": group["checksum"].iloc[0],
            "fuel": float(fuel.iloc[0]) if len(fuel) else np.nan,
        }
        if len(fuel):
            row["psi_mean_ns_per_fuel"] = float((group["cpu_ns"] / group["fuel"]).mean())
            if "cycles" in group:
                row["cycles_per_fuel"] = float((group["cycles"] / group["fuel"]).mean())
        rows.append(row)
    return pd.DataFrame(rows)


def checksum_agreement(cells: pd.DataFrame) -> dict:
    per_cell = cells.groupby(["opt_level", "kernel"])["checksum"].nunique()
    return {"cells": int(len(per_cell)), "cells_with_disagreement": int((per_cell > 1).sum())}


def a_adv_by_runtime(cells: pd.DataFrame) -> dict:
    result = {}
    for runtime in FUEL_RUNTIMES:
        subset = cells[(cells["runtime"] == runtime) & cells["psi_mean_ns_per_fuel"].notna()]
        if len(subset):
            psi = subset["psi_mean_ns_per_fuel"]
            result[runtime] = {"cells": int(len(psi)), "a_adv": float(psi.max() / psi.min()),
                               "psi_cv": float(psi.std(ddof=1) / psi.mean())}
    return result


def runtime_time_ratios(cells: pd.DataFrame) -> pd.DataFrame:
    reference = cells[cells["runtime"] == REFERENCE_RUNTIME].set_index(["opt_level", "kernel"])["cpu_median_ns"]
    rows = []
    for runtime in cells["runtime"].unique():
        other = cells[cells["runtime"] == runtime].set_index(["opt_level", "kernel"])["cpu_median_ns"]
        ratio = (other / reference).dropna()
        rows.append({"runtime": runtime, "cells": int(len(ratio)),
                     "ratio_median": float(ratio.median()), "ratio_q25": float(ratio.quantile(0.25)),
                     "ratio_q75": float(ratio.quantile(0.75))})
    return pd.DataFrame(rows)


def per_kernel_anova(runs: pd.DataFrame) -> pd.DataFrame:
    reference = runs[runs["runtime"] == REFERENCE_RUNTIME]
    rows = []
    for kernel, group in reference.groupby("kernel"):
        result = compute_log_welch_anova(group, "opt_level", "cpu_ns")
        rows.append({"kernel": kernel, "group": group["group"].iloc[0], "f_w": result.f_stat,
                     "df_between": result.df_between, "df_within": result.df_within,
                     "p_value": result.p_value, "partial_eta_sq": result.partial_eta_sq})
    return pd.DataFrame(rows)


def opcode_design(cells: pd.DataFrame) -> np.ndarray:
    tables = {opt: pd.read_csv(DATA / f"opcode_mix_{opt}.csv").set_index("kernel") for opt in OPT_LEVELS}
    rows = []
    for _, cell in cells.iterrows():
        counts = tables[cell["opt_level"]].loc[cell["kernel"], list(OPCODE_CLASSES)]
        rows.append(counts.to_numpy(dtype=np.float64))
    return np.vstack(rows)


def fit_ridge_nonnegative(design: np.ndarray, target: np.ndarray, lam: float) -> np.ndarray:
    root = np.sqrt(lam)
    augmented_design = np.vstack([design, root * np.eye(design.shape[1])])
    augmented_target = np.concatenate([target, root * np.ones(design.shape[1])])
    weights, _ = nnls(augmented_design, augmented_target)
    return weights


def cv_of(values: np.ndarray) -> float:
    return float(np.std(values, ddof=1) / np.mean(values))


def calibwasm_leave_one_out(design: np.ndarray, time_ns: np.ndarray, fuel: np.ndarray, lam: float):
    scale_x = float(design.sum(axis=1).mean())
    scale_t = float(time_ns.mean())
    design_n = design / scale_x
    target_n = time_ns / scale_t
    predicted_n = np.zeros_like(target_n)
    for held_out in range(len(target_n)):
        keep = np.arange(len(target_n)) != held_out
        weights = fit_ridge_nonnegative(design_n[keep], target_n[keep], lam)
        predicted_n[held_out] = design_n[held_out] @ weights
    predicted_ns = np.maximum(predicted_n * scale_t, 1e-9)
    psi_uncal = time_ns / fuel
    psi_cal = time_ns / predicted_ns
    return cv_of(psi_uncal), cv_of(psi_cal), predicted_ns


def fuel_only_leave_one_out(time_ns: np.ndarray, fuel: np.ndarray) -> np.ndarray:
    """Predicts each cell's time as one global scale times its fuel, fitted without that cell."""
    predicted = np.zeros_like(time_ns)
    for held_out in range(len(time_ns)):
        keep = np.arange(len(time_ns)) != held_out
        scale = float(time_ns[keep] @ fuel[keep]) / float(fuel[keep] @ fuel[keep])
        predicted[held_out] = scale * fuel[held_out]
    return predicted


def run_calibwasm(cells: pd.DataFrame) -> pd.DataFrame:
    reference = cells[(cells["runtime"] == REFERENCE_RUNTIME)].reset_index(drop=True)
    design = opcode_design(reference)
    time_ns = reference["cpu_mean_ns"].to_numpy(dtype=np.float64)
    fuel = reference["fuel"].to_numpy(dtype=np.float64)
    rows = []
    for lam in CALIBWASM_LAMBDAS:
        cv_uncal, cv_cal, _ = calibwasm_leave_one_out(design, time_ns, fuel, lam)
        rows.append({"lambda": lam, "cv_uncalibrated": cv_uncal, "cv_calibrated_loo": cv_cal,
                     "cv_change_pct": 100.0 * (cv_uncal - cv_cal) / cv_uncal})
    fuel_only = fuel_only_leave_one_out(time_ns, fuel)
    rows.append({"lambda": "fuel-only baseline", "cv_uncalibrated": cv_of(time_ns / fuel),
                 "cv_calibrated_loo": cv_of(time_ns / fuel_only),
                 "cv_change_pct": 100.0 * (cv_of(time_ns / fuel) - cv_of(time_ns / fuel_only)) / cv_of(time_ns / fuel)})
    return pd.DataFrame(rows)


def main() -> None:
    METRICS.mkdir(parents=True, exist_ok=True)
    runs = load_runs()
    cells = cell_summary(runs)
    cells.to_csv(METRICS / "rq1_cell_summary.csv", index=False)
    summary = {
        "runtimes": sorted(runs["runtime"].unique().tolist()),
        "runs": int(len(runs)),
        "checksum_agreement": checksum_agreement(cells),
        "a_adv": a_adv_by_runtime(cells),
    }
    runtime_time_ratios(cells).to_csv(METRICS / "rq1_runtime_ratios.csv", index=False)
    anova = per_kernel_anova(runs)
    anova.to_csv(METRICS / "rq1_anova.csv", index=False)
    run_calibwasm(cells).to_csv(METRICS / "rq5_calibwasm_loo.csv", index=False)
    (METRICS / "rq1_headline.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
