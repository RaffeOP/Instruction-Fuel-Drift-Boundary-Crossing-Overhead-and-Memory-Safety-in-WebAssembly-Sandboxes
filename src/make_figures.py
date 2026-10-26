#!/usr/bin/env python3
"""Generates figures/fig01.pdf to fig08.pdf from the measured outputs (vector PDF, Type 42 fonts)."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from parametric_stats_engine import clopper_pearson_ci

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIG_DIR = PROJECT_ROOT / "figures"
DATA = PROJECT_ROOT / "data"
METRICS = PROJECT_ROOT / "results" / "metrics"
OPT_LEVELS = ["O0", "O2", "O3", "Oz"]
CONFIG_ORDER = [
    "default_2gib_guard", "reduced_64kib_guard", "zero_guard", "zero_guard_explicit_checks",
    "no_growth_reservation", "zero_guard_no_growth_reservation",
]
CONFIG_LABELS = {
    "default_2gib_guard": "2 GiB guard (default)",
    "reduced_64kib_guard": "64 KiB guard",
    "zero_guard": "zero guard",
    "zero_guard_explicit_checks": "zero guard, explicit checks",
    "no_growth_reservation": "no growth reservation",
    "zero_guard_no_growth_reservation": "zero guard, no growth reserve",
}
DPI = 300
TEXT_SIZE = 8
plt.rcParams.update({
    "pdf.fonttype": 42, "ps.fonttype": 42, "font.size": TEXT_SIZE,
    "axes.titlesize": TEXT_SIZE, "axes.labelsize": TEXT_SIZE, "legend.fontsize": TEXT_SIZE - 1,
    "xtick.labelsize": TEXT_SIZE - 1, "ytick.labelsize": TEXT_SIZE - 1, "figure.dpi": DPI,
})


def save(fig, name: str) -> None:
    fig.savefig(FIG_DIR / name, format="pdf", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def fig01_psi_heatmap(cells: pd.DataFrame) -> None:
    subset = cells[(cells["runtime"] == "wasmtime-cranelift")]
    table = subset.pivot(index="kernel", columns="opt_level", values="psi_mean_ns_per_fuel")[OPT_LEVELS]
    fig, ax = plt.subplots(figsize=(3.5, 6.0))
    image = ax.imshow(np.log10(table.to_numpy()), cmap="viridis", aspect="auto")
    ax.set_xticks(range(len(OPT_LEVELS)), OPT_LEVELS)
    ax.set_yticks(range(len(table.index)), table.index, fontsize=4)
    ax.set_xlabel("Frontend optimization level")
    ax.set_title("Mean ns per fuel unit, Wasmtime Cranelift")
    colorbar = fig.colorbar(image, ax=ax)
    colorbar.set_label(r"$\log_{10}\,\psi$")
    save(fig, "fig01.pdf")


def fig02_psi_by_opt(cells: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(3.5, 2.8))
    positions = []
    labels = []
    data = []
    for index, runtime in enumerate(["wasmtime-cranelift", "wasmtime-winch"]):
        for opt_index, opt in enumerate(OPT_LEVELS):
            values = cells[(cells["runtime"] == runtime) & (cells["opt_level"] == opt)]["psi_mean_ns_per_fuel"]
            data.append(values.dropna().to_numpy())
            positions.append(opt_index * 3 + index)
            labels.append(f"{opt}\n{runtime.replace('wasmtime-', '')}" if index == 0 else "")
    boxes = ax.boxplot(data, positions=positions, widths=0.7, showfliers=False, patch_artist=True)
    for position, box in zip(positions, boxes["boxes"]):
        box.set_facecolor("0.85" if position % 3 == 0 else "C1")
    ax.set_xticks([opt_index * 3 + 0.5 for opt_index in range(len(OPT_LEVELS))], OPT_LEVELS)
    ax.legend(handles=[Patch(facecolor="0.85", label="Cranelift"), Patch(facecolor="C1", label="Winch")],
              frameon=False, fontsize=7, loc="upper right")
    ax.set_yscale("log")
    ax.set_xlabel("Frontend optimization level")
    ax.set_ylabel(r"$\psi$ (ns per fuel unit)")
    save(fig, "fig02.pdf")


def fig03_fuel_vs_time(cells: pd.DataFrame) -> None:
    subset = cells[cells["runtime"] == "wasmtime-cranelift"]
    fig, ax = plt.subplots(figsize=(3.5, 2.8))
    for opt in OPT_LEVELS:
        part = subset[subset["opt_level"] == opt]
        ax.scatter(part["fuel"], part["cpu_mean_ns"] / 1e6, s=6, label=opt)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Metered fuel units per call")
    ax.set_ylabel("Mean on-CPU time (ms)")
    ax.legend(title="Opt level", frameon=False)
    save(fig, "fig03.pdf")


def fig04_runtime_ratios(cells: pd.DataFrame) -> None:
    reference = cells[cells["runtime"] == "wasmtime-cranelift"].set_index(["opt_level", "kernel"])["cpu_median_ns"]
    runtimes = ["v8", "wasmer-cranelift", "wasmer-llvm", "wasmer-singlepass", "wasmer-cranelift-metered",
                "wasmer-llvm-metered", "wasmer-singlepass-metered", "wasmtime-winch", "wasmedge-aot", "wamr-interp", "wasmedge-interp"]
    data = []
    for runtime in runtimes:
        other = cells[cells["runtime"] == runtime].set_index(["opt_level", "kernel"])["cpu_median_ns"]
        data.append((other / reference).dropna().to_numpy())
    fig, ax = plt.subplots(figsize=(3.5, 3.0))
    ax.boxplot(data, tick_labels=[r.replace("wasmer-", "w-").replace("-interp", "") for r in runtimes],
               showfliers=False)
    ax.set_yscale("log")
    ax.axhline(1.0, color="0.5", linewidth=0.8, linestyle="--")
    for divider in (4.5, 7.5):
        ax.axvline(divider, color="0.6", linewidth=0.6, linestyle=":")
    ax.set_ylabel("Median time ratio vs Wasmtime Cranelift")
    plt.setp(ax.get_xticklabels(), rotation=35, ha="right")
    save(fig, "fig04.pdf")


def fig06_host_latency() -> None:
    rows = pd.read_csv(DATA / "rq3_host_call_latency.csv")
    summary = rows.groupby(["side", "payload_bytes"])["per_call_ns"].median().unstack("side")
    fig, ax = plt.subplots(figsize=(3.5, 2.8))
    ax.plot(summary.index, summary["wasm"] / 1e3, marker="o", ms=3, label="Host-call (wasm)")
    ax.plot(summary.index, summary["native"] / 1e3, marker="s", ms=3, label="Native baseline")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Payload size (bytes)")
    ax.set_ylabel(r"Median per-call time ($\mu$s)")
    ax.legend(frameon=False)
    save(fig, "fig06.pdf")


def fig08_calibwasm() -> None:
    static = pd.read_csv(METRICS / "rq5_calibwasm_loo.csv")
    static = static[static["lambda"] != "fuel-only baseline"].astype({"lambda": float})
    dynamic = pd.read_csv(METRICS / "rq5_dynamic_loo.csv")
    dynamic = dynamic[dynamic["model"] == "dynamic opcode classes"]
    shared = [0.01, 0.1, 1.0, 10.0]
    static = static.set_index("lambda").loc[shared]
    dynamic = dynamic.set_index("lambda").loc[shared]
    baseline = float(static["cv_uncalibrated"].iloc[0])
    positions = range(len(shared))
    width = 0.38
    fig, ax = plt.subplots(figsize=(3.5, 2.6))
    ax.bar([p - width / 2 for p in positions], static["cv_calibrated_loo"], width, label="static classes", color="C0")
    ax.bar([p + width / 2 for p in positions], dynamic["cv_psi"], width, label="dynamic classes", color="C1")
    ax.axhline(baseline, color="0.3", linestyle="--", linewidth=0.8, label="uncalibrated fuel")
    ax.set_xticks(list(positions), [f"{v:g}" for v in shared])
    ax.set_xlabel(r"ridge strength $\lambda$")
    ax.set_ylabel(r"CV of $\psi$ across cells")
    ax.legend(frameon=False, fontsize=6)
    save(fig, "fig08.pdf")


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    cells = pd.read_csv(METRICS / "rq1_cell_summary.csv")
    fig01_psi_heatmap(cells)
    fig02_psi_by_opt(cells)
    fig03_fuel_vs_time(cells)
    fig04_runtime_ratios(cells)
    fig06_host_latency()
    fig08_calibwasm()
    print("wrote fig01.pdf to fig08.pdf in", FIG_DIR)


if __name__ == "__main__":
    main()
