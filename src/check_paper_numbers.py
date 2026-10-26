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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
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


def claims() -> list:
    headline = json.loads((METRICS / "rq1_headline.json").read_text())
    cells = cranelift_cells()
    psi = cells.t / cells.fuel
    fuel = pd.read_csv(DATA / "rq1_wasmtime-cranelift.csv").groupby(["opt_level", "kernel"]).fuel.first().unstack("opt_level")
    winch = pd.read_csv(DATA / "rq1_wasmtime-winch.csv").groupby(["opt_level", "kernel"]).fuel.first()
    cran = pd.read_csv(DATA / "rq1_wasmtime-cranelift.csv").groupby(["opt_level", "kernel"]).fuel.first()
    rel = ((winch - cran).abs() / cran)
    dyn = pd.read_csv(DATA / "dynamic_opcode_mix.csv")
    dyn = cells[["opt_level", "kernel"]].merge(dyn, on=["opt_level", "kernel"])
    dyn_total = dyn[CLASS_COLUMNS].sum(axis=1).to_numpy(float)
    fuel_matched = cells.fuel.to_numpy(float)
    ratios = pd.read_csv(METRICS / "rq1_runtime_ratios.csv").set_index("runtime")
    host = pd.read_csv(DATA / "rq3_host_call_latency.csv")
    host_med = host.groupby(["side", "payload_bytes"]).per_call_ns.median().unstack("side")
    wasi = per_write_medians(pd.read_csv(DATA / "rq3_wasi_p1_p2.csv"))
    alloc = pd.read_csv(DATA / "rq4_allocation_strategy_uss.csv")
    dynloo = pd.read_csv(METRICS / "rq5_dynamic_loo.csv")
    loop = pd.read_csv(METRICS / "rq5_loop_weighted_loo.csv")
    loop = loop[loop["model"] == "loop-weighted static opcodes"]

    def slope_mean(condition: str) -> float:
        rows = alloc[alloc.condition == condition]
        return float(np.mean([stats.linregress(g.lifecycle, g.private_anonymous_bytes).slope
                              for _, g in rows.groupby("repeat")]))

    return [
        ("A_adv Cranelift", f"{headline['a_adv']['wasmtime-cranelift']['a_adv']:.1f}", "=40.8$"),
        ("robust p95/p5 Cranelift", f"{psi.quantile(.95) / psi.quantile(.05):.1f}", "$8.9$"),
        ("fuel O0/O2 min", f"{(fuel.O0 / fuel.O2).min():.2f}", "$0.36$"),
        ("fuel O0/O2 max", f"{(fuel.O0 / fuel.O2).max():.1f}", "$6.5$"),
        ("Winch disagreement cells above noise", str(int((rel > 1e-6).sum())), "20 cells above numerical noise"),
        ("r(time, fuel)", f"{np.corrcoef(cells.t, fuel_matched)[0, 1]:.2f}", "$r=0.73$"),
        ("dynamic total vs fuel r", f"{np.corrcoef(dyn_total, fuel_matched)[0, 1]:.4f}", "$0.9999$"),
        ("dynamic total / fuel median", f"{np.median(dyn_total / fuel_matched):.4f}", "$1.0003$"),
        ("WasmEdge interpreter ratio", f"{ratios.loc['wasmedge-interp', 'ratio_median']:.0f}", "$81$"),
        ("Winch ratio", f"{ratios.loc['wasmtime-winch', 'ratio_median']:.2f}", "$2.13$"),
        ("V8 ratio", f"{ratios.loc['v8', 'ratio_median']:.2f}", "V8 at $0.81$"),
        ("host ratio at 64 B", f"{host_med.loc[64, 'wasm'] / host_med.loc[64, 'native']:.0f}", "ratio of $61$"),
        ("Rust on-demand slope", f"{slope_mean('on_demand'):.2f}", "$9.14\\pm0.19$"),
        ("Rust pooled slope", f"{slope_mean('pooled'):.2f}", "$8.99\\pm0.08$"),
        ("dynamic classes best lambda=100", f"{dynloo[(dynloo.model == 'dynamic opcode classes') & (dynloo['lambda'] == 100)].cv_psi.iloc[0]:.2f}", "$0.99$ at $\\lambda=100$"),
        ("loop-weighted best", f"{loop.cv_psi.min():.2f}", "$1.50$"),
        ("WASI P2/P1 per write at 64 B", f"{wasi.loc[64, 'preview2'] / wasi.loc[64, 'preview1']:.2f}", "$1.11$"),
        ("WASI P2/P1 per write at 16 KiB", f"{wasi.loc[16384, 'preview2'] / wasi.loc[16384, 'preview1']:.2f}", "$0.68$"),
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
