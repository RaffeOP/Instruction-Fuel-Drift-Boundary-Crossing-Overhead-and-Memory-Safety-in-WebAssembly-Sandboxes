#!/usr/bin/env python3
"""
Separates one-time work (array initialization, allocation, cleanup) from per-repetition kernel work.

For each module, the timed run(reps) call is measured at reps in {1, 2, 4} on fresh instances.
Fuel F(k) and on-CPU time C(k) are fitted as a + b*k. The intercept a is the per-call fixed cost
(initialization and cleanup) and b the per-repetition kernel cost. Fresh instances avoid cross-call
state; the first call's allocation effects are included in the intercept.
"""

import csv
import statistics
import time
from pathlib import Path

import numpy as np
import wasmtime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = PROJECT_ROOT / "data" / "corpus_manifest.csv"
OUT = PROJECT_ROOT / "data" / "init_share_cranelift_O2.csv"
REPS = (1, 2, 4)
FUEL_BUDGET = 1 << 62
SAMPLES = 5


def fresh(path: str):
    config = wasmtime.Config()
    config.consume_fuel = True
    config.strategy = "cranelift"
    engine = wasmtime.Engine(config)
    module = wasmtime.Module.from_file(engine, path)
    store = wasmtime.Store(engine)
    store.set_wasi(wasmtime.WasiConfig())
    linker = wasmtime.Linker(engine)
    linker.define_wasi()
    store.set_fuel(FUEL_BUDGET)
    instance = linker.instantiate(store, module)
    return store, instance.exports(store)


def measure(path: str, reps: int):
    store, exports = fresh(path)
    store.set_fuel(FUEL_BUDGET)
    start = time.thread_time_ns()
    exports["run"](store, reps)
    cpu = time.thread_time_ns() - start
    fuel = FUEL_BUDGET - store.get_fuel()
    return fuel, cpu


def main() -> None:
    rows = [r for r in csv.DictReader(MANIFEST.open()) if r["opt_level"] == "O2"]
    out = []
    for row in rows:
        fuel_points, cpu_points = [], []
        for reps in REPS:
            f_samples, c_samples = [], []
            for _ in range(SAMPLES):
                f, c = measure(row["path"], reps)
                f_samples.append(f)
                c_samples.append(c)
            fuel_points.append(statistics.median(f_samples))
            cpu_points.append(statistics.median(c_samples))
        x = np.array(REPS, dtype=float)
        fb, fa = np.polyfit(x, np.array(fuel_points), 1)
        cb, ca = np.polyfit(x, np.array(cpu_points), 1)
        out.append({"kernel": row["kernel"], "group": row["group"],
                    "fuel_fixed": fa, "fuel_per_rep": fb,
                    "fixed_share_fuel": fa / (fa + fb),
                    "cpu_fixed_ns": ca, "cpu_per_rep_ns": cb,
                    "fixed_share_cpu": ca / (ca + cb)})
        print(row["kernel"], round(fa / (fa + fb), 4), round(ca / (ca + cb), 4), flush=True)
    with OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(out[0].keys()))
        writer.writeheader()
        writer.writerows(out)
    print("written", OUT)


if __name__ == "__main__":
    main()
