"""
RQ1 and RQ5 evaluator: fuel metering divergence, adversarial amplification,
per-kernel Welch ANOVA, and CalibWasm opcode-class calibration.

Hardware cost is per-thread on-CPU time (cpu_ns), since PMU counters are not
accessible on this host. psi = cpu_ns / fuel is the cost of one fuel unit.
CalibWasm is evaluated by leave-one-cell-out prediction: each (opt, kernel)
cell's calibrated fuel is predicted from weights fitted on all other cells.
"""

from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import nnls

from parametric_stats_engine import compute_log_welch_anova

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TELEMETRY_PATH = PROJECT_ROOT / "data" / "rq1_fuel_timing.csv"
ENGINE_PATH = PROJECT_ROOT / "data" / "rq1_v8_timing.csv"
OPCODE_PATH_TEMPLATE = PROJECT_ROOT / "data" / "opcode_mix_{opt}.csv"
METRICS_DIR = PROJECT_ROOT / "results" / "metrics"
OPT_LEVELS = ("O0", "O2", "O3", "Oz")
LAMBDA_GRID = (0.01, 0.1, 1.0, 10.0)
OPCODE_CLASSES = (
    "int_arith", "float_arith", "compare", "memory_load", "memory_store",
    "branch", "control", "call", "local_global", "const", "other",
)
NS_PER_MS = 1e6


def load_wasmtime_rows() -> pd.DataFrame:
    frame = pd.read_csv(TELEMETRY_PATH)
    frame["psi"] = frame["cpu_ns"] / frame["fuel"].clip(lower=1)
    return frame


def fuel_is_deterministic(frame: pd.DataFrame) -> bool:
    spread = frame.groupby(["opt_level", "kernel"])["fuel"].nunique()
    return bool((spread == 1).all())


def summarize_cells(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = frame.groupby(["opt_level", "kernel"])
    summary = grouped.agg(
        fuel=("fuel", "first"),
        cpu_mean_ns=("cpu_ns", "mean"),
        cpu_sd_ns=("cpu_ns", "std"),
        psi_mean=("psi", "mean"),
        psi_sd=("psi", "std"),
        replicates=("replicate", "count"),
    ).reset_index()
    summary["psi_cv_replicates"] = summary["psi_sd"] / summary["psi_mean"]
    return summary


def adversarial_amplification(cells: pd.DataFrame) -> float:
    return float(cells["psi_mean"].max() / cells["psi_mean"].min())


def cv_of(values: np.ndarray) -> float:
    return float(np.std(values, ddof=1) / np.mean(values))


def per_kernel_anova(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for kernel, group in frame.groupby("kernel"):
        result = compute_log_welch_anova(group, "opt_level", "cpu_ns")
        rows.append({
            "kernel": kernel,
            "f_w": result.f_stat,
            "df_between": result.df_between,
            "df_within": result.df_within,
            "p_value": result.p_value,
            "partial_eta_sq": result.partial_eta_sq,
        })
    return pd.DataFrame(rows)


def load_opcode_matrix(cells: pd.DataFrame) -> np.ndarray:
    tables = {opt: pd.read_csv(OPCODE_PATH_TEMPLATE.with_name(
        OPCODE_PATH_TEMPLATE.name.format(opt=opt))).set_index("kernel")
        for opt in OPT_LEVELS}
    rows = []
    for _, cell in cells.iterrows():
        counts = tables[cell["opt_level"]].loc[cell["kernel"], list(OPCODE_CLASSES)]
        rows.append(counts.to_numpy(dtype=np.float64))
    return np.vstack(rows)


def fit_ridge_nonnegative(design: np.ndarray, target: np.ndarray, lam: float) -> np.ndarray:
    """min ||X u - t||^2 + lam ||u - 1||^2 subject to u >= 0 (dimensionless, normalized)."""
    root = np.sqrt(lam)
    augmented_design = np.vstack([design, root * np.eye(design.shape[1])])
    augmented_target = np.concatenate([target, root * np.ones(design.shape[1])])
    weights, _ = nnls(augmented_design, augmented_target)
    return weights


def calibwasm_leave_one_out(design: np.ndarray, time_ns: np.ndarray,
                            fuel: np.ndarray, lam: float) -> Tuple[np.ndarray, float, float]:
    """Predicts each cell's time from weights fitted on all other cells."""
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
    return psi_cal, cv_of(psi_uncal), cv_of(psi_cal)


def run_calibwasm(cells: pd.DataFrame) -> pd.DataFrame:
    design = load_opcode_matrix(cells)
    time_ns = cells["cpu_mean_ns"].to_numpy(dtype=np.float64)
    fuel = cells["fuel"].to_numpy(dtype=np.float64)
    rows = []
    for lam in LAMBDA_GRID:
        _, cv_uncal, cv_cal = calibwasm_leave_one_out(design, time_ns, fuel, lam)
        rows.append({
            "lambda": lam,
            "cv_uncalibrated": cv_uncal,
            "cv_calibrated_loo": cv_cal,
            "cv_reduction_pct": 100.0 * (cv_uncal - cv_cal) / cv_uncal,
        })
    return pd.DataFrame(rows)


def main() -> None:
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    frame = load_wasmtime_rows()
    cells = summarize_cells(frame)
    cells.to_csv(METRICS_DIR / "rq1_cell_summary.csv", index=False)
    anova = per_kernel_anova(frame)
    anova.to_csv(METRICS_DIR / "rq1_anova.csv", index=False)
    calib = run_calibwasm(cells)
    calib.to_csv(METRICS_DIR / "rq5_calibwasm_loo.csv", index=False)
    headline = {
        "fuel_deterministic_per_cell": fuel_is_deterministic(frame),
        "a_adv_all_cells": adversarial_amplification(cells),
        "cv_psi_uncal_cells": cv_of(cells["psi_mean"].to_numpy()),
        "cells": int(len(cells)),
        "rows": int(len(frame)),
    }
    print(headline)
    print(anova.to_string(index=False))
    print(calib.to_string(index=False))


if __name__ == "__main__":
    main()
