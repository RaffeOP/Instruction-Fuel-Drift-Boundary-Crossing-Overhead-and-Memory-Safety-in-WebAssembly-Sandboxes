#!/usr/bin/env python3
"""
RQ4 allocation-strategy comparison: on-demand versus pooling allocation.

Each condition runs in a fresh child process (rust_harness recycle binary). At every
checkpoint the child pauses and this parent samples the child's unique set size (USS)
with psutil, then acknowledges. Lifecycle latencies are written by the child, so no
measurement is taken while USS is being sampled.
"""

import argparse
import csv
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RECYCLE_BIN = PROJECT_ROOT / "rust_harness" / "target" / "release" / "recycle"
MODULE_PATH = PROJECT_ROOT / "kernels" / "build_wasm" / "lifecycle.wasm"
DATA = PROJECT_ROOT / "data"
DEFAULT_OUT = DATA / "rq4_allocation_strategy_uss.csv"
LIFECYCLES = 120_000
CHECKPOINT_STRIDE = 1_000
CSV_FIELDS = ("condition", "repeat", "lifecycle", "private_anonymous_bytes", "phys_footprint_bytes")


@dataclass(frozen=True)
class Condition:
    name: str
    mode: str


CONDITIONS = (Condition("on_demand", "on-demand"), Condition("pooled", "pooled"))
REPEATS = 5


def run_condition(condition: Condition, repeat: int, lifecycles: int, stride: int, writer) -> np.ndarray:
    latency_path = DATA / f"rq4_latency_{condition.name}_r{repeat}.bin"
    command = [str(RECYCLE_BIN), "--mode", condition.mode, "--lifecycles", str(lifecycles),
               "--checkpoint-stride", str(stride), "--module", str(MODULE_PATH),
               "--latency-out", str(latency_path)]
    child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    for line in child.stdout:
        line = line.strip()
        if not line.startswith("CHECKPOINT"):
            continue
        _, lifecycle_text, internal_text, footprint_text = line.split()
        writer.writerow({"condition": condition.name, "repeat": repeat, "lifecycle": int(lifecycle_text),
                         "private_anonymous_bytes": int(internal_text),
                         "phys_footprint_bytes": int(footprint_text)})
        child.stdin.write("\n")
        child.stdin.flush()
    child.stdin.close()
    if child.wait() != 0:
        raise RuntimeError(f"{condition.name} child exited with status {child.returncode}")
    raw = np.fromfile(latency_path, dtype="<u8").astype(np.float64)
    if len(raw) != lifecycles:
        raise RuntimeError(f"{condition.name}: expected {lifecycles} latencies, got {len(raw)}")
    return raw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lifecycles", type=int, default=LIFECYCLES)
    parser.add_argument("--stride", type=int, default=CHECKPOINT_STRIDE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    with arguments.out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for condition in CONDITIONS:
            for repeat in range(arguments.repeats):
                latencies = run_condition(condition, repeat, arguments.lifecycles, arguments.stride, writer)
                np.save(DATA / f"rq4_latency_{condition.name}_r{repeat}.npy", latencies)
                print(condition.name, repeat, "median ns", float(np.median(latencies)),
                      "p99 ns", float(np.quantile(latencies, 0.99)), flush=True)
    print("written", arguments.out)


if __name__ == "__main__":
    main()
