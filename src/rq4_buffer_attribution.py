#!/usr/bin/env python3
"""
RQ4 attribution test: is the per-lifecycle growth the harness's own latency buffer?

The recycling child records one u64 latency per lifecycle into a buffer reserved up front.
Reserved pages become private dirty memory only when first written, so an unfaulted buffer
adds 8 bytes per lifecycle to the measured series. This script runs the child with and
without --prefault (every buffer page written before the first checkpoint), for both
allocation strategies, and fits the OLS slope of private anonymous memory per repeat.

Writes data/rq4_buffer_attribution.csv (checkpoints) and
results/metrics/rq4_buffer_attribution_slopes.csv (one slope per repeat).
"""

import csv
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RECYCLE_BIN = PROJECT_ROOT / "rust_harness" / "target" / "release" / "recycle"
MODULE_PATH = PROJECT_ROOT / "kernels" / "build_wasm" / "lifecycle.wasm"
OUT = PROJECT_ROOT / "data" / "rq4_buffer_attribution.csv"
SLOPES = PROJECT_ROOT / "results" / "metrics" / "rq4_buffer_attribution_slopes.csv"
LIFECYCLES = 120_000
STRIDE = 1_000
REPEATS = 5
MODES = ("on-demand", "pooled")
DIRTY_PAGES = (0, 4)
SCRATCH_LATENCY = Path("/dev/null")


def run_child(mode: str, prefault: bool, dirty: int) -> list:
    command = [str(RECYCLE_BIN), "--mode", mode, "--lifecycles", str(LIFECYCLES),
               "--checkpoint-stride", str(STRIDE), "--module", str(MODULE_PATH),
               "--latency-out", str(SCRATCH_LATENCY), "--dirty-pages", str(dirty),
               "--prefault", "1" if prefault else "0"]
    child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    rows = []
    for line in child.stdout:
        if not line.startswith("CHECKPOINT"):
            continue
        _, lifecycle, internal, footprint = line.split()
        rows.append((int(lifecycle), int(internal), int(footprint)))
        child.stdin.write("\n")
        child.stdin.flush()
    child.stdin.close()
    if child.wait() != 0:
        raise RuntimeError(f"recycle child failed: {command}")
    return rows


def main() -> None:
    SLOPES.parent.mkdir(parents=True, exist_ok=True)
    records, slopes = [], []
    for mode in MODES:
        for dirty in DIRTY_PAGES:
            for prefault in (False, True):
                for repeat in range(REPEATS):
                    rows = run_child(mode, prefault, dirty)
                    for lifecycle, internal, footprint in rows:
                        records.append({"mode": mode, "dirty_pages": dirty, "prefault": int(prefault), "repeat": repeat,
                                        "lifecycle": lifecycle, "private_anonymous_bytes": internal,
                                        "phys_footprint_bytes": footprint})
                    x = np.array([r[0] for r in rows], float)
                    y = np.array([r[1] for r in rows], float)
                    fit = stats.linregress(x, y)
                    slopes.append({"mode": mode, "dirty_pages": dirty, "prefault": int(prefault), "repeat": repeat,
                                   "slope_bytes_per_lifecycle": fit.slope,
                                   "total_growth_bytes": y[-1] - y[0]})
                    print(mode, dirty, prefault, repeat, round(fit.slope, 3), flush=True)
    pd.DataFrame(records).to_csv(OUT, index=False)
    frame = pd.DataFrame(slopes)
    frame.to_csv(SLOPES, index=False)
    summary = frame.groupby(["mode", "dirty_pages", "prefault"])["slope_bytes_per_lifecycle"].agg(["mean", "std", "count"])
    print(summary.round(3).to_string())


if __name__ == "__main__":
    main()
