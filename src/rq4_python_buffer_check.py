#!/usr/bin/env python3
"""
RQ4 check of the Python recycling harness.

The round-3 Python harness filled an np.empty latency array one entry per lifecycle, so its
unique set size grew by up to 8 bytes per lifecycle as the array's pages were first written.
Its two conditions ran in one process, the second after the first had already raised the
process's allocator high-water mark. This script runs each condition in a fresh process,
with the latency array either faulted in the loop (round-3 behaviour) or prefaulted.

Writes results/metrics/rq4_python_buffer_check.csv.
Usage: rq4_python_buffer_check.py            (driver)
       rq4_python_buffer_check.py CHILD NAME PREFAULT   (one condition, prints the slope)
"""

import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recycling_auditor import CHECKPOINT_STRIDE, CONDITIONS, LIFECYCLES, build_module, ols_slope, one_lifecycle  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "results" / "metrics" / "rq4_python_buffer_check.csv"
REPEATS = 3


def child(name: str, prefault: bool) -> None:
    condition = next(c for c in CONDITIONS if c.name == name)
    engine, module = build_module(condition)
    process = psutil.Process()
    latencies = np.ones(LIFECYCLES) if prefault else np.empty(LIFECYCLES)
    xs, ys = [], []
    for lifecycle in range(LIFECYCLES):
        start = time.perf_counter_ns()
        one_lifecycle(engine, module)
        latencies[lifecycle] = time.perf_counter_ns() - start
        if lifecycle % CHECKPOINT_STRIDE == 0:
            xs.append(lifecycle)
            ys.append(process.memory_full_info().uss)
    slope, low, high, _ = ols_slope(np.array(xs, float), np.array(ys, float))
    print(f"{slope} {low} {high}")


def main() -> None:
    rows = []
    for condition in CONDITIONS:
        for prefault in (0, 1):
            for repeat in range(REPEATS):
                output = subprocess.run([sys.executable, __file__, "CHILD", condition.name, str(prefault)],
                                        capture_output=True, text=True, check=True).stdout.split()
                slope, low, high = map(float, output)
                rows.append({"condition": condition.name, "prefault": prefault, "repeat": repeat,
                             "slope": slope, "ci_low": low, "ci_high": high})
                print(condition.name, prefault, repeat, round(slope, 3), flush=True)
    frame = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUT, index=False)
    print(frame.groupby(["condition", "prefault"])["slope"].agg(["mean", "std"]).round(3))


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "CHILD":
        child(sys.argv[2], sys.argv[3] == "1")
    else:
        main()
