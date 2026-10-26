#!/usr/bin/env python3
"""
RQ4 multi-tenant sandbox recycling auditor.

Repeatedly instantiates a Wasmtime sandbox that dirties a fixed number of
linear-memory pages, drops it, and records the process Unique Set Size (USS)
at fixed checkpoints. The leak slope gamma_leak is the OLS slope of USS against
recycled lifecycle count; its 95% interval is a parametric t-interval.
Lifecycle latencies are summarized with a generalized Pareto fit to the upper
tail (peaks over threshold).

Scope: the Python bindings expose no pooling-allocator switch, so the two
conditions compare the default on-demand reservation with a configuration that
reserves no growth headroom. The pooling allocator is not evaluated here.
"""

import argparse
import csv
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np
import psutil
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = PROJECT_ROOT / "kernels" / "build_wasm" / "lifecycle.wasm"
DEFAULT_OUT = PROJECT_ROOT / "data" / "rq4_multitenant_rss_uss.csv"
LIFECYCLES = 120_000
CHECKPOINT_STRIDE = 1_000
PAGES_PER_SANDBOX = 4
WASM_PAGE_BYTES = 65536
CONFIDENCE = 0.95
TAIL_QUANTILE = 0.95
CSV_FIELDS = ("condition", "lifecycle", "uss_bytes", "latency_ns")


@dataclass(frozen=True)
class Condition:
    name: str
    reservation_for_growth: int | None


CONDITIONS: List[Condition] = [
    Condition("on_demand_default", None),
    Condition("no_growth_reservation", 0),
]


def build_module(condition: Condition):
    import wasmtime

    config = wasmtime.Config()
    if condition.reservation_for_growth is not None:
        config.memory_reservation_for_growth = condition.reservation_for_growth
    engine = wasmtime.Engine(config)
    module = wasmtime.Module.from_file(engine, str(MODULE_PATH))
    return engine, module


def one_lifecycle(engine, module) -> int:
    import wasmtime

    store = wasmtime.Store(engine)
    instance = wasmtime.Instance(store, module, [])
    dirty = instance.exports(store)["dirty"]
    result = dirty(store, PAGES_PER_SANDBOX)
    if int(result) < 0:
        raise RuntimeError("linear-memory growth failed during lifecycle")
    return int(result)


def uss_bytes(process: psutil.Process) -> int:
    return int(process.memory_full_info().uss)


def run_condition(condition: Condition, writer, process: psutil.Process) -> np.ndarray:
    engine, module = build_module(condition)
    latencies = np.empty(LIFECYCLES, dtype=np.float64)
    for lifecycle in range(LIFECYCLES):
        start = time.perf_counter_ns()
        one_lifecycle(engine, module)
        latencies[lifecycle] = time.perf_counter_ns() - start
        if lifecycle % CHECKPOINT_STRIDE == 0:
            writer.writerow({
                "condition": condition.name, "lifecycle": lifecycle,
                "uss_bytes": uss_bytes(process), "latency_ns": int(latencies[lifecycle]),
            })
    return latencies


def ols_slope(x: np.ndarray, y: np.ndarray):
    x_centered = x - x.mean()
    slope = float(x_centered @ (y - y.mean()) / (x_centered @ x_centered))
    intercept = float(y.mean() - slope * x.mean())
    residuals = y - (intercept + slope * x)
    degrees = len(x) - 2
    sigma_sq = float(residuals @ residuals) / degrees
    slope_se = float(np.sqrt(sigma_sq / (x_centered @ x_centered)))
    t_crit = stats.t.ppf(1.0 - (1.0 - CONFIDENCE) / 2.0, degrees)
    if slope_se == 0.0:
        # A perfect linear fit has zero residuals: the slope is exact and its p-value is zero.
        p_value = 0.0 if slope != 0.0 else 1.0
    else:
        p_value = float(2.0 * stats.t.sf(abs(slope / slope_se), degrees))
    return slope, slope - t_crit * slope_se, slope + t_crit * slope_se, p_value


def tail_fit(latencies: np.ndarray) -> dict:
    threshold = float(np.quantile(latencies, TAIL_QUANTILE))
    exceedances = latencies[latencies > threshold] - threshold
    shape, _, scale = stats.genpareto.fit(exceedances, floc=0.0)
    return {"threshold_ns": threshold, "shape_xi": float(shape),
            "scale_sigma_ns": float(scale), "exceedances": int(len(exceedances))}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    process = psutil.Process()
    with arguments.out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for condition in CONDITIONS:
            latencies = run_condition(condition, writer, process)
            np.save(DEFAULT_OUT.parent / f"rq4_latency_{condition.name}.npy", latencies)
            print(condition.name, "tail", tail_fit(latencies))
    print("recycling sweep written to", arguments.out)
