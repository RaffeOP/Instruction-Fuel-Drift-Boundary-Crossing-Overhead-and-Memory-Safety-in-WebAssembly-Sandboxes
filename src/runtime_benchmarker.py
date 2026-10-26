#!/usr/bin/env python3
"""
In-process Wasmtime sweep: fuel consumed, per-thread CPU time, and wall time
per kernel invocation, across frontend optimization level and Wasmtime backend.

Hardware PMU counters (kperf) require root on macOS and are unavailable in this
workspace, so the hardware-cost proxy is per-thread on-CPU time in nanoseconds.
Results are appended row by row so an interrupted sweep resumes where it stopped.
"""

import argparse
import csv
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Set, Tuple

import wasmtime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODULE_DIR = PROJECT_ROOT / "kernels" / "build_wasm"
DEFAULT_OUT = PROJECT_ROOT / "data" / "rq1_fuel_timing.csv"

OPT_LEVELS = ("O0", "O2", "O3", "Oz")
BACKENDS = ("cranelift",)
KERNEL_REPS: Dict[str, int] = {
    "gemm": 2,
    "jacobi2d": 10,
    "floyd": 1,
    "trisolv": 50,
    "atax": 20,
    "seidel2d": 5,
    "covariance": 2,
    "crc32": 2,
    "collatz": 1,
    "divrem": 5,
    "cachethrash": 2,
}
FUEL_BUDGET = 1 << 60
WARMUP_CALLS = 2
REPLICATES = 300
RANDOM_SEED = 20261022
CSV_FIELDS = (
    "opt_level", "backend", "kernel", "replicate", "fuel",
    "cpu_ns", "wall_ns", "checksum",
)


@dataclass(frozen=True)
class CellKey:
    opt_level: str
    backend: str
    kernel: str
    replicate: int


def build_store(backend: str) -> wasmtime.Store:
    config = wasmtime.Config()
    config.consume_fuel = True
    config.strategy = backend
    engine = wasmtime.Engine(config)
    return wasmtime.Store(engine)


def load_instance(store: wasmtime.Store, opt_level: str):
    module_path = MODULE_DIR / f"kernels-{opt_level}.wasm"
    module = wasmtime.Module.from_file(store.engine, str(module_path))
    return wasmtime.Instance(store, module, [])


def invoke_kernel(store: wasmtime.Store, kernel_fn, reps: int) -> Tuple[int, int, int, int]:
    """Returns (fuel, cpu_ns, wall_ns, checksum) for one kernel invocation."""
    store.set_fuel(FUEL_BUDGET)
    cpu_start = time.thread_time_ns()
    wall_start = time.perf_counter_ns()
    checksum = kernel_fn(store, reps)
    wall_ns = time.perf_counter_ns() - wall_start
    cpu_ns = time.thread_time_ns() - cpu_start
    fuel = FUEL_BUDGET - store.get_fuel()
    return fuel, cpu_ns, wall_ns, int(checksum)


def completed_keys(out_path: Path) -> Set[CellKey]:
    if not out_path.exists():
        return set()
    with out_path.open(newline="") as handle:
        rows = csv.DictReader(handle)
        return {
            CellKey(r["opt_level"], r["backend"], r["kernel"], int(r["replicate"]))
            for r in rows
        }


def planned_cells(replicate: int) -> List[CellKey]:
    cells = [
        CellKey(opt, backend, kernel, replicate)
        for opt in OPT_LEVELS
        for backend in BACKENDS
        for kernel in KERNEL_REPS
    ]
    random.Random(RANDOM_SEED + replicate).shuffle(cells)
    return cells


def iter_pending(done: Set[CellKey]) -> Iterator[CellKey]:
    for replicate in range(REPLICATES):
        for cell in planned_cells(replicate):
            if cell not in done:
                yield cell


def open_writer(out_path: Path):
    is_new = not out_path.exists()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    handle = out_path.open("a", newline="")
    writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
    if is_new:
        writer.writeheader()
    return handle, writer


def run_sweep(out_path: Path) -> None:
    done = completed_keys(out_path)
    handle, writer = open_writer(out_path)
    stores: Dict[Tuple[str, str], Tuple[wasmtime.Store, object]] = {}
    try:
        for cell in iter_pending(done):
            key = (cell.opt_level, cell.backend)
            if key not in stores:
                store = build_store(cell.backend)
                stores[key] = (store, load_instance(store, cell.opt_level))
            store, instance = stores[key]
            kernel_fn = instance.exports(store)[cell.kernel]
            if cell.replicate == 0:
                for _ in range(WARMUP_CALLS):
                    invoke_kernel(store, kernel_fn, KERNEL_REPS[cell.kernel])
            fuel, cpu_ns, wall_ns, checksum = invoke_kernel(
                store, kernel_fn, KERNEL_REPS[cell.kernel]
            )
            writer.writerow({
                "opt_level": cell.opt_level,
                "backend": cell.backend,
                "kernel": cell.kernel,
                "replicate": cell.replicate,
                "fuel": fuel,
                "cpu_ns": cpu_ns,
                "wall_ns": wall_ns,
                "checksum": checksum,
            })
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        handle.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


if __name__ == "__main__":
    started = time.time()
    run_sweep(parse_args().out)
    print(f"sweep finished in {time.time() - started:.1f}s")
