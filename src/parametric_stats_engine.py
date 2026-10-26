#!/usr/bin/env python3
"""
Parametric Statistical Engine for Trajectory 3 (WebAssembly Cloud Sandboxing).
Strictly implements Log-Transformed Welch's Heteroscedastic ANOVA,
Clopper-Pearson Exact Binomial Confidence Intervals, Affine OLS Host-Call Decomposition,
Generalized Pareto Distribution (GPD) Extreme-Value Tail Modeling, and Ridge Fuel Calibration.
Zero non-parametric tests are used.
Principal Investigator: Devarsh Patel (24BCT0267), VIT Vellore.
Target: Springer Nature journal (manuscript in paper/main.tex)
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
from scipy import stats

@dataclass
class WelchAnovaResult:
    metric_name: str
    f_stat: float
    df_between: float
    df_within: float
    p_value: float
    partial_eta_sq: float

def _log_group_moments(df: pd.DataFrame, group_col: str, value_col: str) -> tuple:
    """Returns the cleaned frame and per-group size, mean, and variance of the log values."""
    clean = df[[group_col, value_col]].dropna()
    clean = clean[clean[value_col] > 0].copy()
    clean["log_val"] = np.log(clean[value_col].to_numpy(dtype=np.float64))
    groups = [g["log_val"].to_numpy() for _, g in clean.groupby(group_col)]
    n_i = np.array([len(g) for g in groups], dtype=np.float64)
    means = np.array([np.mean(g) for g in groups], dtype=np.float64)
    vars_i = np.array([np.var(g, ddof=1) for g in groups], dtype=np.float64)
    return clean, n_i, means, vars_i


def compute_log_welch_anova(
    df: pd.DataFrame, group_col: str, value_col: str
) -> WelchAnovaResult:
    """Computes Welch's heteroscedastic one-way ANOVA on log-transformed positive telemetry."""
    clean, n_i, means, vars_i = _log_group_moments(df, group_col, value_col)
    k = len(n_i)

    w_i = n_i / vars_i
    w_sum = np.sum(w_i)
    mean_weighted = np.sum(w_i * means) / w_sum

    numerator = np.sum(w_i * (means - mean_weighted) ** 2) / (k - 1.0)
    lambda_term = (3.0 / (k**2 - 1.0)) * np.sum(
        ((1.0 - (w_i / w_sum)) ** 2) / (n_i - 1.0)
    )

    f_stat = float(numerator / (1.0 + (2.0 * (k - 2.0) / 3.0) * lambda_term))
    df1 = float(k - 1.0)
    df2 = float(1.0 / lambda_term)
    p_val = float(stats.f.sf(f_stat, df1, df2))

    # Parametric effect size: Partial Eta-Squared from standard SS decomposition on log scale
    grand_mean = float(np.mean(clean["log_val"]))
    ss_between = float(np.sum(n_i * (means - grand_mean) ** 2))
    ss_within = float(np.sum((n_i - 1.0) * vars_i))
    partial_eta_sq = ss_between / (ss_between + ss_within)

    return WelchAnovaResult(
        metric_name=value_col,
        f_stat=f_stat,
        df_between=df1,
        df_within=df2,
        p_value=p_val,
        partial_eta_sq=partial_eta_sq,
    )

def clopper_pearson_ci(
    successes: int, trials: int, alpha: float = 0.05
) -> Tuple[float, float, float]:
    """Exact parametric Clopper-Pearson confidence interval via Beta distribution quantiles."""
    if trials <= 0:
        raise ValueError("Total trials must be strictly positive.")
    rate = successes / float(trials)
    lower = (
        0.0
        if successes == 0
        else float(stats.beta.ppf(alpha / 2.0, successes, trials - successes + 1))
    )
    upper = (
        1.0
        if successes == trials
        else float(stats.beta.ppf(1.0 - alpha / 2.0, successes + 1, trials - successes))
    )
    return rate, lower, upper

def fit_affine_wasi_overhead(
    payload_bytes: np.ndarray, latency_ns: np.ndarray
) -> Dict[str, float]:
    """Fits T_WASM(s) = alpha_0 + beta_1 * s via parametric OLS with 95% confidence intervals."""
    res = stats.linregress(payload_bytes, latency_ns)
    n = len(payload_bytes)
    t_crit = float(stats.t.ppf(0.975, df=n - 2))
    return {
        "alpha_0_fixed_ns": float(res.intercept),
        "alpha_0_ci95_ns": float(t_crit * res.intercept_stderr),
        "beta_1_ns_per_byte": float(res.slope),
        "beta_1_ci95_ns_per_byte": float(t_crit * res.stderr),
        "r_squared": float(res.rvalue**2),
        "p_value": float(res.pvalue),
    }

def fit_gpd_tail_latency(
    latencies_ns: np.ndarray, threshold_quantile: float = 0.95
) -> Dict[str, float]:
    """Fits a parametric Generalized Pareto Distribution (GPD) to tail latencies above quantile u."""
    u = float(np.quantile(latencies_ns, threshold_quantile))
    exceedances = latencies_ns[latencies_ns > u] - u
    shape_xi, loc, scale_sigma = stats.genpareto.fit(exceedances, floc=0.0)

    # Parametric p99 and p99.9 quantile estimator from GPD fit
    n_total = float(len(latencies_ns))
    n_u = float(len(exceedances))
    zeta_u = n_u / n_total

    def gpd_quantile(p: float) -> float:
        if abs(shape_xi) < 1e-8:
            return u + scale_sigma * np.log(zeta_u / (1.0 - p))
        return u + (scale_sigma / shape_xi) * (
            ((1.0 - p) / zeta_u) ** (-shape_xi) - 1.0
        )

    return {
        "threshold_u_ns": u,
        "gpd_shape_xi": float(shape_xi),
        "gpd_scale_sigma": float(scale_sigma),
        "parametric_p99_ns": float(gpd_quantile(0.99)),
        "parametric_p999_ns": float(gpd_quantile(0.999)),
    }

def fit_calibwasm_ridge_weights(
    opcode_matrix: np.ndarray, hw_cycles: np.ndarray, ridge_lambda: float = 10.0
) -> Tuple[np.ndarray, float, float]:
    """
    Learns CalibWasm non-negative opcode weights w via Ridge regression centered at w_0 = 1:
    min_{w >= 0} ||X w - c_hw||_2^2 + lambda ||w - 1||_2^2
    Returns (weights, uncalibrated_cv, calibrated_cv).
    """
    n_samples, n_features = opcode_matrix.shape
    uncalibrated_fuel = np.sum(opcode_matrix, axis=1)
    psi_uncal = hw_cycles / np.maximum(uncalibrated_fuel, 1.0)
    cv_uncal = float(np.std(psi_uncal, ddof=1) / np.mean(psi_uncal))

    # Closed-form Ridge solution around prior w_0 = 1, projected onto positive orthant
    xtx = opcode_matrix.T @ opcode_matrix
    prior_one = np.ones(n_features, dtype=np.float64)
    rhs = opcode_matrix.T @ hw_cycles + ridge_lambda * prior_one
    w_hat = np.linalg.solve(xtx + ridge_lambda * np.eye(n_features), rhs)
    w_hat = np.maximum(w_hat, 1e-3)

    # Normalize so mean weight equals 1.0 fuel unit
    w_hat = w_hat / np.mean(w_hat)
    calibrated_fuel = opcode_matrix @ w_hat
    psi_cal = hw_cycles / np.maximum(calibrated_fuel, 1.0)
    cv_cal = float(np.std(psi_cal, ddof=1) / np.mean(psi_cal))

    return w_hat, cv_uncal, cv_cal
