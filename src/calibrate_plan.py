#!/usr/bin/env python3
"""
Builds the shared timing plan: one row per module with the reps per timed call.

reps is chosen once, with Wasmtime Cranelift, so that one run(reps) call takes
about TARGET_CALL_NS. Every runtime uses the same plan, so timed calls do the
same work across runtimes. Calibration uses the median of CALIBRATION_SAMPLES.
"""

import csv
import statistics
import time
from pathlib import Path

import wasmtime

from validate_corpus import instantiate

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = PROJECT_ROOT / "data" / "corpus_manifest.csv"
PLAN = PROJECT_ROOT / "data" / "timing_plan.csv"
TARGET_CALL_NS = 20_000_000
CALIBRATION_SAMPLES = 3
MIN_REPS = 1
MAX_REPS = 1_000_000


def time_one_call(store, run, reps: int) -> int:
    start = time.perf_counter_ns()
    run(store, reps)
    return time.perf_counter_ns() - start


def calibrate(path: Path) -> int:
    store, exports = instantiate(path)
    run = exports["run"]
    run(store, 1)
    per_rep = statistics.median(time_one_call(store, run, 1) for _ in range(CALIBRATION_SAMPLES))
    per_rep = max(per_rep, 1)
    return max(MIN_REPS, min(MAX_REPS, round(TARGET_CALL_NS / per_rep)))


def main() -> None:
    with MANIFEST.open() as handle:
        rows = list(csv.DictReader(handle))
    with PLAN.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["kernel", "group", "opt_level", "path", "reps"])
        for row in rows:
            reps = calibrate(Path(row["path"]))
            writer.writerow([row["kernel"], row["group"], row["opt_level"], row["path"], reps])
    print("plan written:", PLAN, "cells:", len(rows))


if __name__ == "__main__":
    main()
