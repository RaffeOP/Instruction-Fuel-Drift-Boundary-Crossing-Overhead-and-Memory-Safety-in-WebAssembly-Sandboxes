#!/usr/bin/env python3
"""
RQ4 attribution of the residual (post-prefault) growth to virtual-memory regions.

Runs the recycling child with a prefaulted latency buffer and, while the child is paused at
selected checkpoints, records `vmmap --summary` for it. The per-region dirty sizes at each
checkpoint show which allocator regions account for the stepwise growth.

Writes data/rq4_region_profile.csv.
"""

import re
import subprocess
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RECYCLE_BIN = PROJECT_ROOT / "rust_harness" / "target" / "release" / "recycle"
MODULE_PATH = PROJECT_ROOT / "kernels" / "build_wasm" / "lifecycle.wasm"
OUT = PROJECT_ROOT / "data" / "rq4_region_profile.csv"
LIFECYCLES = 120_000
STRIDE = 1_000
SNAPSHOTS = {0, 1_000, 5_000, 20_000, 60_000, 119_000}
ROW = re.compile(r"^(?P<name>[A-Za-z_][\w .()/-]*?)\s{2,}(?P<vsize>[\d.]+[KMG]?)\s+(?P<resident>[\d.]+[KMG]?)\s+(?P<dirty>[\d.]+[KMG]?)\s+(?P<swapped>[\d.]+[KMG]?)")
UNITS = {"K": 1 << 10, "M": 1 << 20, "G": 1 << 30}


def to_bytes(text: str) -> float:
    if text[-1] in UNITS:
        return float(text[:-1]) * UNITS[text[-1]]
    return float(text)


def region_dirty(pid: int) -> dict:
    output = subprocess.run(["vmmap", "--summary", str(pid)], capture_output=True, text=True).stdout
    regions = {}
    in_table = False
    for line in output.splitlines():
        if line.startswith("REGION TYPE"):
            in_table = True
            continue
        if in_table and line.startswith("==="):
            continue
        if in_table and not line.strip():
            break
        match = ROW.match(line) if in_table else None
        if match:
            regions[match["name"].strip()] = to_bytes(match["dirty"])
    return regions


def profile(mode: str) -> list:
    command = [str(RECYCLE_BIN), "--mode", mode, "--lifecycles", str(LIFECYCLES), "--checkpoint-stride", str(STRIDE),
               "--module", str(MODULE_PATH), "--latency-out", "/dev/null", "--dirty-pages", "4", "--prefault", "1"]
    child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    rows = []
    for line in child.stdout:
        if not line.startswith("CHECKPOINT"):
            continue
        _, lifecycle, internal, _ = line.split()
        if int(lifecycle) in SNAPSHOTS:
            for region, dirty in region_dirty(child.pid).items():
                rows.append({"mode": mode, "lifecycle": int(lifecycle), "region": region, "dirty_bytes": dirty,
                             "private_anonymous_bytes": int(internal)})
        child.stdin.write("\n")
        child.stdin.flush()
    child.stdin.close()
    child.wait()
    return rows


def main() -> None:
    frame = pd.DataFrame(profile("on-demand") + profile("pooled"))
    frame.to_csv(OUT, index=False)
    pivot = frame.pivot_table(index=["mode", "region"], columns="lifecycle", values="dirty_bytes")
    changed = pivot[(pivot.max(axis=1) - pivot.min(axis=1)) > 0]
    print((changed / 1024).round(1).to_string())


if __name__ == "__main__":
    main()
