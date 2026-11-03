#!/usr/bin/env python3
"""
RQ4 long run: 10^6 lifecycles per allocator with a prefaulted latency buffer, to test whether
the residual MALLOC_SMALL growth keeps accumulating or levels off.
Writes data/rq4_long_run.csv.
"""

import subprocess
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RECYCLE_BIN = PROJECT_ROOT / "rust_harness" / "target" / "release" / "recycle"
MODULE_PATH = PROJECT_ROOT / "kernels" / "build_wasm" / "lifecycle.wasm"
OUT = PROJECT_ROOT / "data" / "rq4_long_run.csv"
LIFECYCLES = 1_000_000
STRIDE = 10_000
REPEATS = 3


def run(mode: str, repeat: int) -> list:
    command = [str(RECYCLE_BIN), "--mode", mode, "--lifecycles", str(LIFECYCLES), "--checkpoint-stride", str(STRIDE),
               "--module", str(MODULE_PATH), "--latency-out", "/dev/null", "--dirty-pages", "4", "--prefault", "1"]
    child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    rows = []
    for line in child.stdout:
        if line.startswith("CHECKPOINT"):
            _, lifecycle, internal, footprint = line.split()
            rows.append({"mode": mode, "repeat": repeat, "lifecycle": int(lifecycle),
                         "private_anonymous_bytes": int(internal), "phys_footprint_bytes": int(footprint)})
            child.stdin.write("\n")
            child.stdin.flush()
    child.stdin.close()
    if child.wait() != 0:
        raise RuntimeError(f"child failed for {mode}")
    return rows


def main() -> None:
    rows = []
    for mode in ("on-demand", "pooled"):
        for repeat in range(REPEATS):
            rows += run(mode, repeat)
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT, index=False)
    for (mode, repeat), g in frame.groupby(["mode", "repeat"]):
        y = g.set_index("lifecycle")["private_anonymous_bytes"]
        base = y.iloc[0]
        marks = {k: int((y.loc[k] - base) / 1024) for k in (100_000, 250_000, 500_000, 750_000, 990_000)}
        print(mode, repeat, "growth KiB at", marks)


if __name__ == "__main__":
    main()
