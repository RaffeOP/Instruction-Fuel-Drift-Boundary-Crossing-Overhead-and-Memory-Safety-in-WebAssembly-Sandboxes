#!/usr/bin/env python3
"""
RQ5 extension: loop-nest-weighted static opcode calibration.

Each instruction in the functions reachable from run() is weighted by gamma**d, where d is the
number of enclosing wasm `loop` blocks at that instruction. Weighted class counts become the
design matrix; ridge-NNLS weights are fitted with leave-one-cell-out (LOO) validation, exactly as
in fuel_metering_evaluator.py. Target is the per-cell mean on-CPU time of Wasmtime Cranelift.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import subprocess
from scipy.optimize import nnls

import opcode_profile as bc

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
METRICS = PROJECT_ROOT / "results" / "metrics"
GAMMAS = (1.0, 2.0, 4.0, 8.0)
LAMBDAS = (0.01, 0.1, 1.0, 10.0)
CLASSES = [name for name, _ in bc.OPCODE_CLASSES] + ["other"]


def weighted_profile(wasm_path: Path, gamma: float) -> np.ndarray:
    wat = subprocess.run([bc.WASM2WAT, str(wasm_path)], capture_output=True, text=True, check=True).stdout
    bodies, name_to_index, exports = bc.parse_functions(wat)
    entry = bc.resolve(exports["run"], name_to_index)
    counts = np.zeros(len(CLASSES))
    for index in bc.reachable_from(entry, bodies, name_to_index):
        stack = []
        for line in bodies.get(index, []):
            first = line.split(" ")[0]
            if first in ("block", "loop", "if"):
                stack.append(first)
                continue
            if first == "end":
                if stack:
                    stack.pop()
                continue
            match = bc.MNEMONIC.match(line)
            if not match:
                continue
            depth = sum(1 for kind in stack if kind == "loop")
            counts[CLASSES.index(bc.classify(match.group(1)))] += gamma ** depth
    return counts


def cell_table() -> pd.DataFrame:
    runs = pd.read_csv(DATA / "rq1_wasmtime-cranelift.csv")
    cells = runs.groupby(["opt_level", "kernel"]).agg(
        cpu_mean_ns=("cpu_ns", "mean"), fuel=("fuel", "first")).reset_index()
    return cells


def ridge_nonnegative(design: np.ndarray, target: np.ndarray, lam: float) -> np.ndarray:
    root = np.sqrt(lam)
    augmented = np.vstack([design, root * np.eye(design.shape[1])])
    rhs = np.concatenate([target, root * np.ones(design.shape[1])])
    return nnls(augmented, rhs)[0]


def loo_predict(design: np.ndarray, time_ns: np.ndarray, lam: float) -> np.ndarray:
    scale_x = float(design.sum(axis=1).mean())
    scale_t = float(time_ns.mean())
    dn = design / scale_x
    tn = time_ns / scale_t
    pred = np.zeros_like(tn)
    for i in range(len(tn)):
        keep = np.arange(len(tn)) != i
        pred[i] = dn[i] @ ridge_nonnegative(dn[keep], tn[keep], lam)
    return np.maximum(pred * scale_t, 1e-9)


def cv(values: np.ndarray) -> float:
    return float(np.std(values, ddof=1) / np.mean(values))


def main() -> None:
    manifest = pd.read_csv(DATA / "corpus_manifest.csv")
    cells = cell_table()
    cells = cells.merge(manifest[["kernel", "opt_level", "path"]], on=["kernel", "opt_level"])
    cells = cells.sort_values(["opt_level", "kernel"]).reset_index(drop=True)
    time_ns = cells["cpu_mean_ns"].to_numpy(float)
    fuel = cells["fuel"].to_numpy(float)
    psi = time_ns / fuel
    rows = [{"model": "uncalibrated fuel", "gamma": np.nan, "lambda": np.nan, "cv_psi": cv(psi)}]
    rows.append({"model": "fuel-only LOO scale", "gamma": np.nan, "lambda": np.nan,
                 "cv_psi": cv(time_ns / np.array([(time_ns[np.arange(len(time_ns)) != i] @ fuel[np.arange(len(time_ns)) != i])
                                                  / (fuel[np.arange(len(time_ns)) != i] @ fuel[np.arange(len(time_ns)) != i])
                                                  * fuel[i] for i in range(len(time_ns))]))})
    for gamma in GAMMAS:
        design = np.vstack([weighted_profile(Path(p), gamma) for p in cells["path"]])
        for lam in LAMBDAS:
            pred = loo_predict(design, time_ns, lam)
            rows.append({"model": "loop-weighted static opcodes", "gamma": gamma, "lambda": lam,
                         "cv_psi": cv(time_ns / pred)})
        print("gamma", gamma, "done", flush=True)
    out = pd.DataFrame(rows)
    out["cv_change_pct"] = 100 * (cv(psi) - out["cv_psi"]) / cv(psi)
    METRICS.mkdir(parents=True, exist_ok=True)
    out.to_csv(METRICS / "rq5_loop_weighted_loo.csv", index=False)
    print(out.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
