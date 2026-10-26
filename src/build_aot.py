#!/usr/bin/env python3
"""
AOT-compiles every corpus module with WasmEdge's wasmedgec (instruction counting enabled)
and writes the WasmEdge AOT timing plan. Compilation happens outside every timed region.
"""

import csv
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLAN = PROJECT_ROOT / "data" / "timing_plan.csv"
AOT_DIR = PROJECT_ROOT / "kernels" / "build_aot"
AOT_PLAN = PROJECT_ROOT / "data" / "timing_plan_wasmedge_aot.csv"
WASMEDGEC = "/opt/homebrew/bin/wasmedgec"


def compile_aot(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([WASMEDGEC, "--optimize", "3", "--enable-instruction-count", str(source), str(target)],
                   check=True, capture_output=True)


def main() -> None:
    with PLAN.open() as handle:
        rows = list(csv.DictReader(handle))
    with AOT_PLAN.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["kernel", "group", "opt_level", "path", "reps"])
        for row in rows:
            source = Path(row["path"])
            target = AOT_DIR / f"{source.stem}.dylib"
            if not target.exists():
                compile_aot(source, target)
            writer.writerow([row["kernel"], row["group"], row["opt_level"], str(target), row["reps"]])
    print("aot plan written:", AOT_PLAN, "modules:", len(rows))


if __name__ == "__main__":
    main()
