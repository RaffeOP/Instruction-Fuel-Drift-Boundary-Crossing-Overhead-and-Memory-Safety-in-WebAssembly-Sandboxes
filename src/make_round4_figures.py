#!/usr/bin/env python3
"""
Figures added in the round-4 revision. All are vector PDFs with Type 42 fonts.

  figures/fig09.pdf  microarchitectural attribution of cost per fuel unit (Cranelift corpus)
  figures/fig10.pdf  adversarial worst-case search against the corpus range
  figures/fig07.pdf  RQ4 recycling: latency-buffer artefact and the 10^6-lifecycle plateau

The categorical palette is the validated reference instance (blue, orange, aqua); every
series also has its own marker shape, so group identity never rests on color alone.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
METRICS = ROOT / "results" / "metrics"
FIGURES = ROOT / "figures"
GROUP_STYLE = {
    "polybench": {"color": "#2a78d6", "marker": "o", "label": "PolyBench"},
    "integer": {"color": "#eb6834", "marker": "s", "label": "Integer/crypto"},
    "memory": {"color": "#1baf7a", "marker": "^", "label": "Linear-memory"},
}
INK = "#52514e"
GRID = "#e4e3df"
KIB = 1024


def configure() -> None:
    matplotlib.rcParams.update({
        "pdf.fonttype": 42, "ps.fonttype": 42, "font.size": 7,
        "axes.edgecolor": INK, "axes.labelcolor": "#0b0b0b", "xtick.color": INK, "ytick.color": INK,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
    })


def corpus_cells() -> pd.DataFrame:
    return pd.read_csv(METRICS / "pmu_cell_summary_cranelift.csv")


def plot_attribution() -> None:
    cells = corpus_cells()
    cells["cpi"] = 1.0 / cells["ipc"]
    figure, (left, right) = plt.subplots(1, 2, figsize=(6.6, 2.6))
    for group, style in GROUP_STYLE.items():
        part = cells[cells["group"] == group]
        left.scatter(part["cpi"], part["psi"], s=14, color=style["color"], marker=style["marker"],
                     edgecolor="white", linewidth=0.5, label=style["label"])
        right.scatter(part["r_l1d_miss_ld"] * 1e3 + 1e-3, part["psi"], s=14, color=style["color"],
                      marker=style["marker"], edgecolor="white", linewidth=0.5, label=style["label"])
    for axis in (left, right):
        axis.set_yscale("log")
        axis.set_ylabel(r"$\mu_\psi$ (ns per fuel unit)")
    left.set_xscale("log")
    left.set_xlabel("Cycles per retired native instruction (CPI)")
    left.set_title("(a) Cost per fuel unit tracks CPI", loc="left")
    right.set_xscale("log")
    right.set_xlabel(r"Retired L1D load misses per $10^3$ fuel units")
    right.set_title("(b) Against the L1D load-miss rate", loc="left")
    left.legend(loc="upper left")
    figure.tight_layout()
    figure.savefig(FIGURES / "fig09.pdf", dpi=300)
    plt.close(figure)


def adversarial_cells(path: Path) -> pd.DataFrame:
    runs = pd.read_csv(path)
    cells = runs.groupby(["kernel", "group"], sort=False).agg(cpu=("cpu_ns", "mean"), fuel=("fuel", "first")).reset_index()
    cells["psi"] = cells["cpu"] / cells["fuel"]
    return cells


def working_set(kernel: str) -> float:
    token = kernel.split("_")[3]
    scale = {"K": KIB, "M": KIB ** 2, "G": KIB ** 3}[token[-1]]
    return float(token[:-1]) * scale


def plot_adversarial() -> None:
    cells = adversarial_cells(DATA / "pmu" / "pmu_adversarial_cranelift.csv")
    corpus = corpus_cells()
    lo, hi = corpus["psi"].min(), corpus["psi"].max()
    figure, (left, right) = plt.subplots(1, 2, figsize=(6.6, 2.7), gridspec_kw={"width_ratios": [1.15, 1]})
    chase = cells[cells["group"] == "adv_chase"].copy()
    chase["unroll"] = chase["kernel"].str.extract(r"_u(\d+)$").fillna("1").astype(int)
    chase["stride"] = chase["kernel"].str.extract(r"_s(\d+)_").astype(int)
    chase["bytes"] = chase["kernel"].map(working_set)
    series = [
        ("128 B stride", chase[(chase.stride == 128) & (chase.unroll == 1)], "#2a78d6", "o"),
        ("16 KiB stride", chase[(chase.stride == 16384) & (chase.unroll == 1)], "#eb6834", "s"),
    ]
    for label, part, color, marker in series:
        part = part.sort_values("bytes")
        left.plot(part["bytes"], part["psi"], color=color, marker=marker, markersize=4, linewidth=1.2, label=label)
    for unroll, marker in ((4, "v"), (16, "D"), (64, "*")):
        part = chase[(chase.unroll == unroll)].sort_values("bytes")
        left.plot(part["bytes"], part["psi"], color="#1baf7a", marker=marker, markersize=5, linewidth=0.8,
                  linestyle=":", label=f"128 B, {unroll} nested loads")
    left.axhspan(lo, hi, color=GRID, alpha=0.8, zorder=0)
    left.text(2.0 ** 25, lo * 1.3, "benign corpus range", color=INK, fontsize=6)
    left.set_xscale("log", base=2)
    left.set_yscale("log")
    left.set_xlabel("Pointer-chase working set (bytes)")
    left.set_ylabel(r"$\mu_\psi$ (ns per fuel unit)")
    left.set_title("(a) Dependent-load chase", loc="left")
    left.legend(loc="upper left", fontsize=5.5)
    winch = adversarial_cells(DATA / "pmu" / "pmu_adversarial_winch.csv").set_index("kernel")
    others = cells[cells["group"] != "adv_chase"].set_index("kernel")
    order = winch.loc[others.index, "psi"].sort_values().index
    positions = np.arange(len(order))
    bar = 0.38
    right.barh(positions - bar / 2, others.loc[order, "psi"], height=bar, color="#2a78d6", label="Cranelift")
    right.barh(positions + bar / 2, winch.loc[order, "psi"], height=bar, color="#eb6834", label="Winch")
    right.set_yticks(positions, [k.replace("adv_", "") for k in order], fontsize=5.5)
    right.axvspan(lo, hi, color=GRID, alpha=0.8, zorder=0)
    right.set_xscale("log")
    right.set_xlabel(r"$\mu_\psi$ (ns per fuel unit)")
    right.set_title("(b) Other operator families", loc="left")
    right.grid(axis="y", visible=False)
    right.legend(loc="lower right", fontsize=6)
    figure.tight_layout()
    figure.savefig(FIGURES / "fig10.pdf", dpi=300)
    plt.close(figure)


def plot_recycling() -> None:
    attribution = pd.read_csv(DATA / "rq4_buffer_attribution.csv")
    long_run = pd.read_csv(DATA / "rq4_long_run.csv")
    figure, (left, right) = plt.subplots(1, 2, figsize=(6.6, 2.5))
    styles = {("on-demand", 0): ("#2a78d6", "o", "on-demand, buffer faulted in loop"),
              ("on-demand", 1): ("#2a78d6", "o", "on-demand, buffer prefaulted"),
              ("pooled", 0): ("#eb6834", "s", "pooled, buffer faulted in loop"),
              ("pooled", 1): ("#eb6834", "s", "pooled, buffer prefaulted")}
    subset = attribution[attribution["dirty_pages"] == 4]
    for (mode, prefault), part in subset.groupby(["mode", "prefault"]):
        color, marker, label = styles[(mode, prefault)]
        mean = part.groupby("lifecycle")["private_anonymous_bytes"].mean()
        growth = (mean - mean.iloc[0]) / KIB
        left.plot(growth.index, growth.values, color=color, linewidth=1.4 if prefault else 0.9,
                  linestyle="-" if prefault else "--", label=label)
    left.set_xlabel("Recycled lifecycles")
    left.set_ylabel("Private anonymous growth (KiB)")
    left.set_title("(a) 120,000 lifecycles, 4 dirty pages", loc="left")
    left.legend(fontsize=5.5, loc="upper left")
    for (mode, repeat), part in long_run.groupby(["mode", "repeat"]):
        color = "#2a78d6" if mode == "on-demand" else "#eb6834"
        growth = (part["private_anonymous_bytes"] - part["private_anonymous_bytes"].iloc[0]) / KIB
        right.plot(part["lifecycle"], growth, color=color, linewidth=0.9,
                   label=mode if repeat == 0 else None)
    right.set_xlabel("Recycled lifecycles")
    right.set_ylabel("Private anonymous growth (KiB)")
    right.set_title(r"(b) $10^6$ lifecycles, prefaulted buffer", loc="left")
    right.legend(fontsize=6, loc="lower right")
    figure.tight_layout()
    figure.savefig(FIGURES / "fig07.pdf", dpi=300)
    plt.close(figure)


def main() -> None:
    configure()
    FIGURES.mkdir(exist_ok=True)
    plot_attribution()
    plot_recycling()
    if (DATA / "pmu" / "pmu_adversarial_cranelift.csv").exists():
        plot_adversarial()


if __name__ == "__main__":
    main()
