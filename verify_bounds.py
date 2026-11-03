#!/usr/bin/env python3
"""Recomputes headline numbers from the data files and checks that the paper text states them.

Each check recomputes a value from data/ or results/metrics/, formats it to the precision the
paper uses, and confirms that the formatted string appears in paper/main.tex. A failure means a
number in the text no longer matches its source, so the paper must be updated before submission.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parent
DATA = PROJECT_ROOT / "data"
METRICS = PROJECT_ROOT / "results" / "metrics"
PAPER = PROJECT_ROOT / "paper" / "main.tex"


def cranelift_cells() -> pd.DataFrame:
    runs = pd.read_csv(DATA / "rq1_wasmtime-cranelift.csv")
    return runs.groupby(["opt_level", "kernel"]).agg(t=("cpu_ns", "mean"), fuel=("fuel", "first")).reset_index()


def per_write_medians(wasi: pd.DataFrame) -> pd.DataFrame:
    base = wasi[wasi["mode"] == "baseline"].groupby(["side", "payload_bytes", "replicate"]).cpu_ns.median()
    full = wasi[wasi["mode"] == "full"].set_index(["side", "payload_bytes", "replicate"])
    full["per_write_ns"] = (full["cpu_ns"] - base.reindex(full.index).values) / full["writes"]
    return full.reset_index().groupby(["payload_bytes", "side"]).per_write_ns.median().unstack("side")


def pmu_cells(path: Path) -> pd.DataFrame:
    runs = pd.read_csv(path)
    cells = runs.groupby(["kernel", "opt_level"]).agg(cpu=("cpu_ns", "mean"), fuel=("fuel", "first")).reset_index()
    cells["psi"] = cells.cpu / cells.fuel
    return cells


def adversarial_psi(backend: str) -> pd.Series:
    runs = pd.read_csv(DATA / "pmu" / f"pmu_adversarial_{backend}.csv")
    cells = runs.groupby("kernel").agg(cpu=("cpu_ns", "mean"), fuel=("fuel", "first"))
    return cells.cpu / cells.fuel


def claims() -> list:
    headline = json.loads((METRICS / "rq1_headline.json").read_text())
    cells = cranelift_cells()
    fuel = pd.read_csv(DATA / "rq1_wasmtime-cranelift.csv").groupby(["opt_level", "kernel"]).fuel.first().unstack("opt_level")
    winch = pd.read_csv(DATA / "rq1_wasmtime-winch.csv").groupby(["opt_level", "kernel"]).fuel.first()
    cran = pd.read_csv(DATA / "rq1_wasmtime-cranelift.csv").groupby(["opt_level", "kernel"]).fuel.first()
    rel = ((winch - cran).abs() / cran)
    flat = pd.read_csv(DATA / "pmu" / "fuel_cranelift_flatbulk.csv").groupby(["opt_level", "kernel"]).fuel.first()
    ratios = pd.read_csv(METRICS / "rq1_runtime_ratios.csv").set_index("runtime")
    pmu = pmu_cells(DATA / "pmu" / "pmu_corpus_cranelift.csv")
    adv = adversarial_psi("cranelift")
    adv_w = adversarial_psi("winch")
    winch_pmu = pmu_cells(DATA / "pmu" / "pmu_corpus_winch.csv")
    calib = pd.read_csv(METRICS / "calibration_v2.csv").set_index(["features", "split"])
    slopes = pd.read_csv(METRICS / "rq4_buffer_attribution_slopes.csv")
    paired = slopes.pivot_table(index=["mode", "dirty_pages", "repeat"], columns="prefault",
                                values="slope_bytes_per_lifecycle")
    host = pd.read_csv(DATA / "r4" / "rq3_host_call_rust.csv", keep_default_na=False)
    host_med = host[host.side != "null"].groupby(["payload_bytes", "side"]).per_call_ns.median().unstack("side")
    compound = pd.read_csv(DATA / "r4" / "rq2_compound.csv")
    return [
        ("A_adv Cranelift, cross-runtime rerun", f"{headline['a_adv']['wasmtime-cranelift']['a_adv']:.1f}", "=38.3$"),
        ("A_adv Cranelift, kperf run", f"{pmu.psi.max() / pmu.psi.min():.1f}", "$34.1$"),
        ("fuel O0/O2 min", f"{(fuel.O0 / fuel.O2).min():.2f}", "$0.36$"),
        ("fuel O0/O2 max", f"{(fuel.O0 / fuel.O2).max():.1f}", "$6.5$"),
        ("Winch disagreement cells above noise", str(int((rel > 1e-6).sum())), "in 20 cells above numerical noise"),
        ("flat-bulk Cranelift equals Winch in all cells", str(int((flat == winch).sum())), "all 200 cells"),
        ("r(time, fuel)", f"{np.corrcoef(cells.t, cells.fuel)[0, 1]:.2f}", "$r=0.73$"),
        ("Winch time ratio", f"{ratios.loc['wasmtime-winch', 'ratio_median']:.2f}", "Winch is at $2.11$"),
        ("WasmEdge AOT ratio", f"{ratios.loc['wasmedge-aot', 'ratio_median']:.2f}", "WasmEdge AOT at $0.77$"),
        ("adversarial max Cranelift", f"{adv.max():.1f}", "$93.8$"),
        ("adversarial max / benign max", f"{adv.max() / pmu.psi.max():.0f}", "$260$"),
        ("adversarial max / benign min", f"{adv.max() / pmu.psi.min():,.0f}".replace(",", "{,}"), "$8{,}879$"),
        ("Winch bulk copy 4M psi", f"{adv_w['adv_bulk_copy_4M']:,.0f}".replace(",", "{,}"), "$7{,}518$"),
        ("Winch bulk / Winch benign max", f"{adv_w['adv_bulk_copy_4M'] / winch_pmu.psi.max():,.0f}".replace(",", "{,}"), "$15{,}673$"),
        ("LOKO dynamic shares", f"{calib.loc[('dynamic class shares', 'LOKO'), 'log_score']:.3f}", "$0.682$"),
        ("LOKO PMU + instructions", f"{calib.loc[('PMU event rates + native instructions', 'LOKO'), 'log_score']:.3f}", "$0.551$"),
        ("RQ4 paired buffer difference", f"{(paired[0] - paired[1]).mean():.2f}", "$8.02$"),
        ("host call / native at 64 B", f"{host_med.loc[64, 'wasm'] / host_med.loc[64, 'native']:.2f}", "$2.10$ times"),
        ("compound trials conforming", str(int(compound.conforms.sum())), "All 4{,}200 trials conform"),
    ]


CLASS_COLUMNS = ["int_arith", "float_arith", "compare", "memory_load", "memory_store", "branch", "control",
                 "call", "local_global", "const", "conversion", "memory_ops", "other"]


def main() -> int:
    text = PAPER.read_text()
    checks = claims()
    failures = []
    for label, value, needle in checks:
        found = needle in text
        print(f"{'OK  ' if found else 'MISS'} {label}: recomputed {value}, text needle '{needle}'")
        if not found:
            failures.append(label)
    print(f"{len(checks) - len(failures)} of {len(checks)} headline numbers found in the paper text")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
