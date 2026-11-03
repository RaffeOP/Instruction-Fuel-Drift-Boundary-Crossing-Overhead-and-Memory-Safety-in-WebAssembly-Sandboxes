#!/usr/bin/env python3
"""
Load telemetry for every timed experiment of the gated reruns (Appendix D, Table 13).

* kperf and pmu_bench runs record the 1-minute load immediately before every replicate.
* The cross-runtime runners print one time-stamped line per finished cell; a cell's window runs
  from the previous line to its own, and it is assigned the maximum of the 2-second load samples
  inside that window (or the nearest earlier sample for windows shorter than the sampling period).
* host_bench and wasi_bench record the load before every sample.

Writes tables/tab13.tex and results/metrics/load_summary.csv.
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
R4 = DATA / "r4"
LOGS = ROOT / "results" / "logs" / "r4"
TABLES = ROOT / "tables"
METRICS = ROOT / "results" / "metrics"
GATE = 3.0
PER_REPLICATE = [
    ("Wasmtime Cranelift, kperf corpus", DATA / "pmu" / "pmu_corpus_cranelift.csv", "load1"),
    ("Wasmtime Winch, kperf corpus", DATA / "pmu" / "pmu_corpus_winch.csv", "load1"),
    ("Adversarial search, Cranelift", DATA / "pmu" / "pmu_adversarial_cranelift.csv", "load1"),
    ("Adversarial search, Winch", DATA / "pmu" / "pmu_adversarial_winch.csv", "load1"),
    ("Serverless kernels, Cranelift", R4 / "serverless_cranelift.csv", "load1"),
    ("Serverless kernels, Winch", R4 / "serverless_winch.csv", "load1"),
    ("Host-call boundary (Rust)", R4 / "rq3_host_call_rust.csv", "loadavg_1m"),
    ("WASI Preview 1 / Preview 2", R4 / "rq3_wasi_p1_p2.csv", "loadavg_1m"),
]
RUNNERS = ["wasmtime-cranelift", "wasmtime-winch", "wasmer-cranelift", "wasmer-llvm", "wasmer-singlepass",
           "wasmer-cranelift-metered", "wasmer-llvm-metered", "wasmer-singlepass-metered", "wamr-interp",
           "wasmedge-aot", "v8", "wasmedge-interp"]


def describe(label: str, values: pd.Series, unit: str) -> dict:
    return {"experiment": label, "unit": unit, "n": int(len(values)), "median": float(values.median()),
            "p95": float(values.quantile(0.95)), "max": float(values.max()), "above_gate": float((values > GATE).mean())}


def cell_window_loads(runner: str, samples: pd.DataFrame) -> pd.Series:
    log = LOGS / f"{runner}.err"
    stamps = []
    start = None
    for line in log.read_text().splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2 and parts[0].isdigit() and parts[1].startswith("done"):
            stamps.append(int(parts[0]))
    campaign = (LOGS / "campaign.log").read_text().splitlines() if (LOGS / "campaign.log").exists() else []
    for line in campaign:
        fields = line.split()
        if len(fields) >= 3 and fields[1] == "START" and fields[2] == runner:
            start = int(fields[0])
    loads = []
    previous = start if start is not None else (stamps[0] if stamps else 0)
    times = samples["unix_time"].to_numpy()
    values = samples["load1"].to_numpy()
    for stamp in stamps:
        inside = values[(times > previous) & (times <= stamp)]
        if len(inside) == 0:
            earlier = values[times <= stamp]
            inside = earlier[-1:] if len(earlier) else values[:1]
        loads.append(inside.max())
        previous = stamp
    return pd.Series(loads, dtype=float)


def step_window_loads(runner: str, samples: pd.DataFrame) -> pd.Series:
    """For runners that print no per-cell lines, the load samples between step start and end."""
    start = end = None
    for line in (LOGS / "campaign.log").read_text().splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[2] == runner:
            if fields[1] == "START":
                start = int(fields[0])
            elif fields[1] == "DONE":
                end = int(fields[0])
    inside = samples[(samples.unix_time >= start) & (samples.unix_time <= end)]
    return inside["load1"].astype(float)


def main() -> None:
    has_step_log = (LOGS / "campaign.log").exists()
    rows = []
    for label, path, column in PER_REPLICATE:
        if path.exists():
            rows.append(describe(label, pd.read_csv(path, keep_default_na=False)[column].astype(float), "replicate"))
    samples = pd.read_csv(R4 / "load_samples.csv")
    for runner in RUNNERS:
        if not (LOGS / f"{runner}.err").exists():
            continue
        loads = cell_window_loads(runner, samples)
        if len(loads) == 200:
            rows.append(describe(f"{runner}, cell windows", loads, "cell"))
        elif len(loads) == 0 and has_step_log:
            rows.append(describe(f"{runner}, step window", step_window_loads(runner, samples), "2-s sample"))
    frame = pd.DataFrame(rows)
    frame.to_csv(METRICS / "load_summary.csv", index=False)
    body = "\n".join(
        f"{r.experiment} & {r.unit} & {r.n:,} & {r.median:.2f} & {r.p95:.2f} & {r.max:.2f} & {100 * r.above_gate:.1f}\\% \\\\"
        for r in frame.itertuples())
    caption = ("One-minute load during the gated reruns. Replicate rows use the load recorded immediately before each "
               "replicate or sample; cell rows assign each cell the highest 2-second load sample inside its execution window. "
               "The admission gate is 3.0 on the 8-core machine, applied before each cell (kperf harness) or each step "
               "(cross-runtime runners); the last column is the share above it. The V8 runner prints no per-cell lines, so "
               "it has no cell-window row.")
    (TABLES / "tab13.tex").write_text(
        "\\begin{table}[t]\n" f"\\caption{{{caption}}}\\label{{tab:load}}\n"
        "\\footnotesize\n\\setlength{\\tabcolsep}{4pt}%\n\\begin{adjustbox}{max width=\\textwidth}%\n"
        "\\begin{tabular}{llrrrrr}\n\\toprule\nExperiment & Unit & $n$ & Median & P95 & Max & $>3.0$ \\\\\n\\midrule\n"
        f"{body}\n\\bottomrule\n\\end{{tabular}}%\n\\end{{adjustbox}}\n\\end{{table}}\n")
    print(frame.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
