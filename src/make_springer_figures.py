"""Generate the Springer-version recycling figure: all six RQ4 conditions, growth and slopes.

Writes figures/fig07.pdf as vector PDF with Type 42 fonts. Panel (a) plots USS growth
from the first checkpoint for every condition; panel (b) plots each condition's slope with its
95% interval, using the same computation as tables/tab08.tex.
"""

import csv
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from make_springer_rq_tables import recycling_rows  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FIG_DIR = ROOT / "figures"
DPI = 300
BYTES_PER_KIB = 1e3
PYTHON_STYLE = {"marker": "o", "color": "#1f4e79"}
RUST_STYLE = {"marker": "s", "color": "#b5562a"}
DIRTY_STYLE = {"marker": "^", "color": "#4d7d3a"}
SLOPE_LABEL_ROTATION = 35


def configure_matplotlib():
    matplotlib.rcParams["pdf.fonttype"] = 42
    matplotlib.rcParams["ps.fonttype"] = 42
    matplotlib.rcParams["font.size"] = 7


def growth_series():
    """Return (label, style, lifecycles, growth in KiB) for every RQ4 condition."""
    series = []
    python = defaultdict(lambda: ([], []))
    for row in csv.DictReader((DATA / "rq4_multitenant_rss_uss.csv").open()):
        python[row["condition"]][0].append(int(row["lifecycle"]))
        python[row["condition"]][1].append(float(row["uss_bytes"]))
    for condition, (xs, ys) in python.items():
        series.append((f"Python, {condition.replace('_', ' ')}", PYTHON_STYLE, xs, growth(ys)))
    dirty = defaultdict(lambda: ([], []))
    for row in csv.DictReader((DATA / "rq4_dirty_pages_control.csv").open()):
        dirty[row["dirty_pages"]][0].append(int(row["lifecycle"]))
        dirty[row["dirty_pages"]][1].append(float(row["internal"]))
    for pages, (xs, ys) in dirty.items():
        series.append((f"Rust, {pages} dirty pages", DIRTY_STYLE, xs, growth(ys)))
    series.extend(rust_allocator_series())
    return series


def rust_allocator_series():
    by_allocator = defaultdict(lambda: defaultdict(list))
    for row in csv.DictReader((DATA / "rq4_allocation_strategy_uss.csv").open()):
        by_allocator[row["condition"]][int(row["lifecycle"])].append(float(row["private_anonymous_bytes"]))
    result = []
    for allocator, checkpoints in by_allocator.items():
        xs = sorted(checkpoints)
        ys = [statistics.fmean(checkpoints[x]) for x in xs]
        result.append((f"Rust, {allocator.replace('_', ' ')}", RUST_STYLE, xs, growth(ys)))
    return result


def growth(values):
    return [(value - values[0]) / BYTES_PER_KIB for value in values]


def plot_growth(axis, series):
    for label, style, xs, ys in series:
        axis.plot(xs, ys, linestyle="none", markersize=2, label=label, **style)
    axis.set_xlabel("Recycled sandbox lifecycles")
    axis.set_ylabel("USS growth from first checkpoint (KiB)")
    axis.legend(frameon=False, fontsize=5)


def plot_slopes(axis, rows):
    labels = [row["label"] for row in rows]
    positions = list(range(len(rows)))
    slopes = [row["slope"] for row in rows]
    errors = [[row["slope"] - row["low"] for row in rows], [row["high"] - row["slope"] for row in rows]]
    axis.errorbar(positions, slopes, yerr=errors, fmt="o", color="#222222", capsize=2, markersize=3)
    axis.set_xticks(positions)
    axis.set_xticklabels(labels, rotation=SLOPE_LABEL_ROTATION, ha="right", fontsize=5)
    axis.set_ylabel("Slope (bytes per lifecycle)")


def build_figure():
    figure, (growth_axis, slope_axis) = plt.subplots(1, 2, figsize=(7.0, 2.9))
    plot_growth(growth_axis, growth_series())
    plot_slopes(slope_axis, recycling_rows())
    growth_axis.set_title("(a) Growth trajectories", fontsize=7)
    slope_axis.set_title("(b) Slopes with 95% intervals", fontsize=7)
    figure.tight_layout()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIG_DIR / "fig07.pdf", format="pdf", dpi=DPI, bbox_inches="tight")
    plt.close(figure)


def main():
    configure_matplotlib()
    build_figure()
    print("wrote", FIG_DIR / "fig07.pdf")


if __name__ == "__main__":
    main()
