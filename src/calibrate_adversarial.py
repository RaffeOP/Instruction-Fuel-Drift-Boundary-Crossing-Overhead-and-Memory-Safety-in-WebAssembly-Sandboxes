#!/usr/bin/env python3
"""
Calibrates reps for the adversarial plan so one timed call takes about TARGET_NS of CPU,
the same target the corpus plan uses. Reads a probe run made with reps=1 and writes
data/adversarial_plan.csv.

Usage: calibrate_adversarial.py PROBE.csv
"""

import csv
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UNCALIBRATED = PROJECT_ROOT / "data" / "adversarial_plan_uncalibrated.csv"
CALIBRATED = PROJECT_ROOT / "data" / "adversarial_plan.csv"
TARGET_NS = 20_000_000


def main(probe_path: str) -> None:
    probe = pd.read_csv(probe_path)
    per_rep = probe.groupby("kernel")["cpu_ns"].median() / probe.groupby("kernel")["reps"].first()
    with UNCALIBRATED.open() as source, CALIBRATED.open("w", newline="") as target:
        reader = csv.DictReader(source)
        writer = csv.DictWriter(target, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            row["reps"] = max(1, round(TARGET_NS / per_rep[row["kernel"]]))
            writer.writerow(row)
    print(f"wrote {CALIBRATED}")


if __name__ == "__main__":
    main(sys.argv[1])
