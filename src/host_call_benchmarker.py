#!/usr/bin/env python3
"""
RQ3 host-call boundary benchmark.

Measures the per-call latency of a guest-to-host call that copies a payload out
of linear memory and validates it as UTF-8, against the same copy-and-validate
work performed natively. Fits the affine model T(s) = alpha + beta * s by OLS
for each side and reports the inflation ratio Lambda(s) = T_wasm / T_native.

Scope: this measures the Wasmtime host-function boundary on Apple M3. The
WASI Preview 1 versus Preview 2 comparison is a separate benchmark
(rust_harness/src/bin/wasi_bench.rs) and is not part of this fit.
"""

import argparse
import csv
import os
import random
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = PROJECT_ROOT / "kernels" / "build_wasm" / "host_boundary.wasm"
DEFAULT_OUT = PROJECT_ROOT / "data" / "rq3_host_call_latency.csv"
PAYLOAD_BYTES = (64, 1024, 16384, 262144, 1048576, 4194304, 16777216)
REPLICATES = 926
TARGET_BYTES_PER_SAMPLE = 200_000_000
MIN_CALLS = 4
MAX_CALLS = 20000
CONFIDENCE = 0.95
LOAD_GATE = 4.0
GATE_POLL_SECONDS = 5
RANDOM_SEED = 20261022
CSV_FIELDS = ("side", "payload_bytes", "replicate", "calls", "per_call_ns", "loadavg_1m")


class HostBoundary:
    """Holds the host-side state the imported function needs."""

    def __init__(self) -> None:
        self.store = None
        self.memory = None
        self.accepted = 0

    def consume(self, pointer: int, length: int) -> int:
        payload = self.memory.read(self.store, pointer, pointer + length)
        payload.decode("utf-8")
        self.accepted += 1
        return 1


def instantiate(boundary: HostBoundary):
    import wasmtime

    engine = wasmtime.Engine(wasmtime.Config())
    store = wasmtime.Store(engine)
    module = wasmtime.Module.from_file(engine, str(MODULE_PATH))
    host_type = wasmtime.FuncType([wasmtime.ValType.i32(), wasmtime.ValType.i32()],
                                  [wasmtime.ValType.i32()])
    host_func = wasmtime.Func(store, host_type, lambda p, n: boundary.consume(p, n))
    instance = wasmtime.Instance(store, module, [host_func])
    exports = instance.exports(store)
    boundary.store = store
    boundary.memory = exports["memory"]
    return store, exports


def calls_for(payload_bytes: int) -> int:
    return max(MIN_CALLS, min(MAX_CALLS, TARGET_BYTES_PER_SAMPLE // payload_bytes))


def time_wasm(boundary: HostBoundary, exports, store, payload_bytes: int) -> float:
    calls = calls_for(payload_bytes)
    start = time.perf_counter_ns()
    exports["run"](store, calls, payload_bytes)
    return (time.perf_counter_ns() - start) / calls


def time_native(payload: bytes, payload_bytes: int) -> float:
    calls = calls_for(payload_bytes)
    start = time.perf_counter_ns()
    for _ in range(calls):
        bytes(payload[:payload_bytes]).decode("utf-8")
    return (time.perf_counter_ns() - start) / calls


def wait_for_quiet() -> None:
    """Blocks until the 1-minute load average is at most LOAD_GATE; called before each sample."""
    while os.getloadavg()[0] > LOAD_GATE:
        time.sleep(GATE_POLL_SECONDS)


def run_sweep(out_path: Path) -> None:
    boundary = HostBoundary()
    store, exports = instantiate(boundary)
    exports["fill"](store, max(PAYLOAD_BYTES))
    native_payload = b"A" * max(PAYLOAD_BYTES)
    plan: List[Tuple[str, int, int]] = []
    for replicate in range(REPLICATES):
        for size in PAYLOAD_BYTES:
            plan.append(("wasm", size, replicate))
            plan.append(("native", size, replicate))
    random.Random(RANDOM_SEED).shuffle(plan)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for side, size, replicate in plan:
            wait_for_quiet()
            if side == "wasm":
                per_call = time_wasm(boundary, exports, store, size)
            else:
                per_call = time_native(native_payload, size)
            writer.writerow({
                "side": side, "payload_bytes": size, "replicate": replicate,
                "calls": calls_for(size), "per_call_ns": f"{per_call:.1f}",
                "loadavg_1m": f"{os.getloadavg()[0]:.2f}",
            })


def load_rows(out_path: Path) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    sides: Dict[str, Tuple[List[float], List[float]]] = {"wasm": ([], []), "native": ([], [])}
    with out_path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            sizes, times = sides[row["side"]]
            sizes.append(float(row["payload_bytes"]))
            times.append(float(row["per_call_ns"]))
    return {side: (np.array(s), np.array(t)) for side, (s, t) in sides.items()}


def affine_fit(sizes: np.ndarray, per_call: np.ndarray) -> Dict[str, float]:
    design = np.column_stack([np.ones_like(sizes), sizes])
    coefficients, _, _, _ = np.linalg.lstsq(design, per_call, rcond=None)
    residuals = per_call - design @ coefficients
    degrees = len(per_call) - 2
    sigma_sq = float(residuals @ residuals) / degrees
    covariance = sigma_sq * np.linalg.inv(design.T @ design)
    t_crit = stats.t.ppf(1.0 - (1.0 - CONFIDENCE) / 2.0, degrees)
    ss_total = float(np.sum((per_call - per_call.mean()) ** 2))
    r_squared = 1.0 - float(residuals @ residuals) / ss_total
    return {
        "alpha_ns": float(coefficients[0]),
        "alpha_ci_half": float(t_crit * np.sqrt(covariance[0, 0])),
        "beta_ns_per_byte": float(coefficients[1]),
        "beta_ci_half": float(t_crit * np.sqrt(covariance[1, 1])),
        "r_squared": r_squared,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--fit-only", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    if not arguments.fit_only:
        run_sweep(arguments.out)
    for side, (sizes, per_call) in load_rows(arguments.out).items():
        fit = affine_fit(sizes, per_call)
        print(side, {k: round(v, 4) for k, v in fit.items()})
