#!/usr/bin/env python3
"""
Round-4 calibration analysis (RQ5), addressing three review points:

1. Leakage. Leave-one-cell-out (LOCO) keeps the same kernel at its other optimization
   levels in the training set. We add leave-one-kernel-out (LOKO), which holds out all four
   builds of a kernel at once, and report both.
2. Metric. Cost per fuel unit is a product of factors (Eq. psi_factor), so the target is
   y = log(mu_psi) and the score is the root-mean-square residual of y. Proposition 1(i)
   holds for any target vector: with an in-sample least-squares fit the RMS residual equals
   sd(y) * sqrt(1 - R^2) * sqrt((n-1)/n), the bound, and out-of-sample rows are scored by the
   same quantity. exp(RMS) is the typical factor by which a calibrated budget misses.
   The round-3 score, the coefficient of variation of mu_psi / exp(prediction), is kept.
3. Features. Besides static and dynamic opcode-class shares, the design can include
   log microarchitectural event rates per fuel unit from the kperf campaign (L1D load misses,
   branch mispredictions, L1D and L2 TLB misses) and log native instructions per fuel unit.

Ridge strength is chosen inside each training fold by an inner leave-one-kernel-out search,
so no reported score uses the held-out cell to pick lambda.

Outputs results/metrics/calibration_v2.csv and, when PMU data exist,
results/metrics/calibration_v2_adversarial.csv (corpus-trained model scored on the
adversarial family).
"""

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
METRICS = PROJECT_ROOT / "results" / "metrics"
PMU_CORPUS = DATA / "pmu" / "pmu_corpus_cranelift.csv"
PMU_ADVERSARIAL = DATA / "pmu" / "pmu_adversarial_cranelift.csv"
LAMBDA_GRID = (1e-4, 1e-3, 1e-2, 1e-1, 1.0, 10.0, 100.0)
CLASS_COLUMNS = ["int_arith", "float_arith", "compare", "memory_load", "memory_store", "branch",
                 "control", "call", "local_global", "const", "conversion", "memory_ops", "other"]
PMU_EVENTS = ["l1d_miss_ld", "branch_mispred", "l1d_tlb_miss", "l2_tlb_miss"]
RATE_FLOOR = 1e-6


def shares(frame: pd.DataFrame) -> pd.DataFrame:
    counts = frame[CLASS_COLUMNS].to_numpy(float)
    return pd.DataFrame(counts / counts.sum(axis=1, keepdims=True), columns=[f"share_{c}" for c in CLASS_COLUMNS])


def static_counts() -> pd.DataFrame:
    frames = []
    for opt in ("O0", "O2", "O3", "Oz"):
        frame = pd.read_csv(DATA / f"opcode_mix_{opt}.csv")
        frame["opt_level"] = opt
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def pmu_rates(path: Path) -> pd.DataFrame:
    """Per-cell event counts per fuel unit and the cell's mean psi from a kperf run."""
    runs = pd.read_csv(path)
    cells = runs.groupby(["kernel", "opt_level"], sort=False)
    table = cells[["cpu_ns", "fuel", "instructions"] + PMU_EVENTS].mean().reset_index()
    for event in PMU_EVENTS:
        table[f"rate_{event}"] = np.log(table[event] / table["fuel"] + RATE_FLOOR)
    table["log_ins_per_fuel"] = np.log(table["instructions"] / table["fuel"])
    table["psi_pmu"] = table["cpu_ns"] / table["fuel"]
    return table


def corpus_table() -> pd.DataFrame:
    runs = pd.read_csv(DATA / "rq1_wasmtime-cranelift.csv")
    cells = runs.groupby(["kernel", "opt_level"]).agg(cpu_ns=("cpu_ns", "mean"), fuel=("fuel", "first")).reset_index()
    cells["psi"] = cells["cpu_ns"] / cells["fuel"]
    dynamic = pd.read_csv(DATA / "dynamic_opcode_mix.csv")
    dynamic = pd.concat([dynamic[["kernel", "opt_level"]], shares(dynamic)], axis=1)
    static = static_counts()
    static = pd.concat([static[["kernel", "opt_level"]], shares(static).add_prefix("static_")], axis=1)
    table = cells.merge(dynamic, on=["kernel", "opt_level"]).merge(static, on=["kernel", "opt_level"])
    if PMU_CORPUS.exists():
        # The gated kperf campaign supersedes the round-3 timing: same modules and fuel, logged load.
        table = table.merge(pmu_rates(PMU_CORPUS).drop(columns=["cpu_ns", "fuel", "instructions"]), on=["kernel", "opt_level"])
        table["psi"] = table["psi_pmu"]
    return table.sort_values(["kernel", "opt_level"]).reset_index(drop=True)


def standardize(train: np.ndarray, test: np.ndarray) -> tuple:
    mean = train.mean(axis=0)
    scale = train.std(axis=0)
    scale[scale == 0] = 1.0
    return (train - mean) / scale, (test - mean) / scale


def ridge_fit_predict(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray, lam: float) -> np.ndarray:
    """Ridge with an unpenalized intercept on standardized features."""
    if x_train.shape[1] == 0:
        return np.full(len(x_test), y_train.mean())
    xs_train, xs_test = standardize(x_train, x_test)
    y_mean = y_train.mean()
    gram = xs_train.T @ xs_train + lam * np.eye(xs_train.shape[1])
    weights = np.linalg.solve(gram, xs_train.T @ (y_train - y_mean))
    return xs_test @ weights + y_mean


def pick_lambda(x: np.ndarray, y: np.ndarray, groups: np.ndarray) -> float:
    """Inner leave-one-group-out search for the ridge strength."""
    best_lambda, best_error = LAMBDA_GRID[0], np.inf
    for lam in LAMBDA_GRID:
        error = 0.0
        for group in np.unique(groups):
            held = groups == group
            prediction = ridge_fit_predict(x[~held], y[~held], x[held], lam)
            error += float(((y[held] - prediction) ** 2).sum())
        if error < best_error:
            best_lambda, best_error = lam, error
    return best_lambda


def cross_validate(x: np.ndarray, y: np.ndarray, outer: np.ndarray, inner: np.ndarray) -> np.ndarray:
    prediction = np.zeros_like(y)
    for fold in np.unique(outer):
        held = outer == fold
        lam = pick_lambda(x[~held], y[~held], inner[~held]) if x.shape[1] else 0.0
        prediction[held] = ridge_fit_predict(x[~held], y[~held], x[held], lam)
    return prediction


def log_score(y: np.ndarray, prediction: np.ndarray) -> float:
    """RMS residual of log mu_psi, the quantity Proposition 1 bounds for this target."""
    return float(np.sqrt(np.mean((y - prediction) ** 2)))


def multiplicative_score(y: np.ndarray, prediction: np.ndarray) -> float:
    """Round-3 score: CV of mu_psi divided by its calibrated prediction."""
    ratio = np.exp(y - prediction)
    return float(np.std(ratio, ddof=1) / np.mean(ratio))


def in_sample(x: np.ndarray, y: np.ndarray) -> tuple:
    design = np.column_stack([np.ones(len(y)), x])
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    fitted = design @ coef
    r2 = 1 - ((y - fitted) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return fitted, float(r2)


def feature_sets(table: pd.DataFrame) -> dict:
    dynamic = [c for c in table.columns if c.startswith("share_")]
    static = [c for c in table.columns if c.startswith("static_share_")]
    sets = {"fuel only (intercept)": [], "static class shares": static, "dynamic class shares": dynamic}
    rates = [f"rate_{e}" for e in PMU_EVENTS if f"rate_{e}" in table.columns]
    if rates:
        sets["PMU event rates"] = rates
        sets["PMU event rates + native instructions"] = rates + ["log_ins_per_fuel"]
        sets["dynamic shares + PMU rates + instructions"] = dynamic + rates + ["log_ins_per_fuel"]
    return sets


def evaluate(table: pd.DataFrame) -> pd.DataFrame:
    y = np.log(table["psi"].to_numpy(float))
    kernels = table["kernel"].to_numpy()
    cells = np.arange(len(table))
    rows = []
    for name, columns in feature_sets(table).items():
        x = table[columns].to_numpy(float)
        fitted, r2 = in_sample(x, y)
        rows.append({"features": name, "split": "in-sample OLS", "r2": r2,
                     "log_score": log_score(y, fitted), "multiplicative_score": multiplicative_score(y, fitted)})
        for split, outer in (("LOCO", cells), ("LOKO", kernels)):
            prediction = cross_validate(x, y, outer, kernels)
            rows.append({"features": name, "split": split, "r2": np.nan,
                         "log_score": log_score(y, prediction),
                         "multiplicative_score": multiplicative_score(y, prediction)})
    result = pd.DataFrame(rows)
    psi = np.exp(y)
    result.attrs["cv_psi"] = float(np.std(psi, ddof=1) / np.mean(psi))
    result.attrs["sd_log_psi"] = float(np.std(y, ddof=1))
    return result


def score_adversarial(table: pd.DataFrame) -> pd.DataFrame:
    """Trains on the corpus and predicts psi for the adversarial family (pure extrapolation)."""
    adversarial = pmu_rates(PMU_ADVERSARIAL)
    features = [f"rate_{e}" for e in PMU_EVENTS] + ["log_ins_per_fuel"]
    x_train = table[features].to_numpy(float)
    y_train = np.log(table["psi"].to_numpy(float))
    lam = pick_lambda(x_train, y_train, table["kernel"].to_numpy())
    predicted = ridge_fit_predict(x_train, y_train, adversarial[features].to_numpy(float), lam)
    adversarial["psi_predicted"] = np.exp(predicted)
    adversarial["lambda"] = lam
    return adversarial[["kernel", "psi_pmu", "psi_predicted", "lambda"] + features]


def main() -> None:
    METRICS.mkdir(parents=True, exist_ok=True)
    table = corpus_table()
    result = evaluate(table)
    result.to_csv(METRICS / "calibration_v2.csv", index=False)
    (METRICS / "calibration_v2_cv.txt").write_text(f"{result.attrs['cv_psi']:.4f} {result.attrs['sd_log_psi']:.4f}\n")
    print(f"cells={len(table)} CV(mu_psi)={result.attrs['cv_psi']:.3f} sd(log mu_psi)={result.attrs['sd_log_psi']:.3f}")
    print(result.round(3).to_string(index=False))
    if PMU_CORPUS.exists() and PMU_ADVERSARIAL.exists():
        adversarial = score_adversarial(table)
        adversarial.to_csv(METRICS / "calibration_v2_adversarial.csv", index=False)
        print(adversarial.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
