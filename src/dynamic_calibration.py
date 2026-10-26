#!/usr/bin/env python3
"""Leave-one-cell-out calibration of cost per fuel unit with dynamic opcode-class counts.

Compares four predictors of each cell's mean CPU time: the uncalibrated fuel scale, a
static opcode-class design (from the disassembly profile), and a dynamic opcode-class design
(from executed counts). Dispersion is the coefficient of variation of time / prediction across
the 200 cells, the same metric as the static calibration in loop_weighted_calibration.py.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from loop_weighted_calibration import cell_table, cv, loo_predict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
METRICS = PROJECT_ROOT / "results" / "metrics"
LAMBDAS = (0.01, 0.1, 1.0, 10.0, 100.0)
CLASS_COLUMNS = ["int_arith", "float_arith", "compare", "memory_load", "memory_store", "branch",
                 "control", "call", "local_global", "const", "conversion", "memory_ops", "other"]


def load_design(path: Path, cells: pd.DataFrame) -> np.ndarray:
    table = pd.read_csv(path)
    merged = cells[["kernel", "opt_level"]].merge(table, on=["kernel", "opt_level"], how="left")
    if merged[CLASS_COLUMNS].isna().any().any():
        raise ValueError(f"missing opcode rows in {path.name}")
    return merged[CLASS_COLUMNS].to_numpy(float)


def static_table() -> pd.DataFrame:
    frames = []
    for opt in ("O0", "O2", "O3", "Oz"):
        frame = pd.read_csv(DATA / f"opcode_mix_{opt}.csv")
        frame["opt_level"] = opt
        frames.append(frame.rename(columns={"kernel": "kernel"}))
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    cells = cell_table().sort_values(["opt_level", "kernel"]).reset_index(drop=True)
    time_ns = cells["cpu_mean_ns"].to_numpy(float)
    fuel = cells["fuel"].to_numpy(float)
    dynamic = pd.read_csv(DATA / "dynamic_opcode_mix.csv").rename(columns={"group": "_g"})
    dynamic_design = cells[["kernel", "opt_level"]].merge(dynamic, on=["kernel", "opt_level"])[CLASS_COLUMNS].to_numpy(float)
    static_frame = static_table()
    static_design = cells[["kernel", "opt_level"]].merge(static_frame, on=["kernel", "opt_level"])[CLASS_COLUMNS].to_numpy(float)
    dynamic_total = dynamic_design.sum(axis=1)
    rows = [
        {"model": "uncalibrated fuel", "lambda": np.nan, "cv_psi": cv(time_ns / fuel)},
        {"model": "static opcode classes", "lambda": np.nan, "cv_psi": np.nan},
    ]
    static_rows = []
    for lam in LAMBDAS:
        pred = loo_predict(static_design, time_ns, lam)
        static_rows.append({"model": "static opcode classes", "lambda": lam, "cv_psi": cv(time_ns / pred)})
    rows = [rows[0]] + static_rows
    for lam in LAMBDAS:
        pred = loo_predict(dynamic_design, time_ns, lam)
        rows.append({"model": "dynamic opcode classes", "lambda": lam, "cv_psi": cv(time_ns / pred)})
    out = pd.DataFrame(rows)
    baseline = cv(time_ns / fuel)
    out["cv_change_pct"] = 100 * (baseline - out["cv_psi"]) / baseline
    METRICS.mkdir(parents=True, exist_ok=True)
    out.to_csv(METRICS / "rq5_dynamic_loo.csv", index=False)
    r_total = np.corrcoef(dynamic_total, fuel)[0, 1]
    r_time_dynamic = np.corrcoef(time_ns, dynamic_total)[0, 1]
    print(out.round(4).to_string(index=False))
    print(f"r(dynamic total, wasmtime fuel) = {r_total:.4f}")
    print(f"r(time, dynamic total) = {r_time_dynamic:.4f}")
    print(f"median dynamic total / fuel = {np.median(dynamic_total / fuel):.4f}")


if __name__ == "__main__":
    main()
