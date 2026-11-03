#!/usr/bin/env python3
"""
Analysis of the DualGate quota experiment (rust_harness/src/bin/quota_bench.rs).

Inputs (data/r4/):
  quota_enforce_cranelift.csv   corpus, serverless, and adversarial cells under Cranelift
  quota_enforce_winch.csv       adversarial cells under Winch
  quota_probe_cranelift.csv     the single 256 MiB memory.copy preemption probe
  quota_overhead_cranelift.csv  fuel-only versus fuel+epoch timing of the corpus
  quota_tick_*.csv              tick-length sensitivity on a subset

Overshoot is CPU at stop divided by the budget, minus one. Fuel-only runs stopped by the safety
cap are censored: their true overshoot is at least the cap.

Writes tables/tab24.tex, figures/fig11.pdf, results/metrics/quota_summary.json.
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
R4 = ROOT / "data" / "r4"
TABLES = ROOT / "tables"
FIGURES = ROOT / "figures"
METRICS = ROOT / "results" / "metrics"
POLICIES = ("fuel", "time", "dual")
POLICY_LABEL = {"fuel": "Fuel only", "time": "CPU-time gate", "dual": "DualGate (fuel + CPU time)"}


def family(group: str) -> str:
    if group.startswith("adv"):
        return "adversarial"
    if group == "serverless":
        return "serverless"
    return "corpus"


def load_enforce() -> pd.DataFrame:
    frames = []
    for name in ("quota_enforce_cranelift.csv", "quota_enforce_winch.csv"):
        path = R4 / name
        if path.exists():
            frames.append(pd.read_csv(path))
    data = pd.concat(frames, ignore_index=True)
    data["family"] = data["group"].map(family)
    return data


def summarize(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (backend, fam, policy), part in data.groupby(["backend", "family", "policy"], sort=False):
        over = part["overshoot"]
        rows.append({"backend": backend, "family": fam, "policy": policy, "runs": len(part),
                     "median": over.median(), "p99": over.quantile(0.99), "max": over.max(),
                     "censored": int((part["stop"] == "cap").sum()),
                     "under_budget": float((over < -0.05).mean())})
    return pd.DataFrame(rows)


def overhead_summary() -> dict:
    path = R4 / "quota_overhead_cranelift.csv"
    if not path.exists():
        return {}
    data = pd.read_csv(path)
    log_ratio = np.log(data["ratio"])
    half = stats.t.ppf(0.975, len(log_ratio) - 1) * log_ratio.std(ddof=1) / np.sqrt(len(log_ratio))
    return {"cells": len(data), "geomean": float(np.exp(log_ratio.mean())),
            "ci_low": float(np.exp(log_ratio.mean() - half)), "ci_high": float(np.exp(log_ratio.mean() + half)),
            "median": float(data["ratio"].median()), "p95": float(data["ratio"].quantile(0.95)),
            "max": float(data["ratio"].max())}


def write_table(summary: pd.DataFrame, overhead: dict, probe: dict) -> None:
    rows = []
    for _, r in summary.iterrows():
        censored = f" ({r['censored']} at cap)" if r["censored"] else ""
        rows.append(f"{r['backend'].capitalize()} & {r['family']} & {POLICY_LABEL[r['policy']]} & {r['runs']} & "
                    f"{100 * r['median']:+.1f}\\% & {100 * r['p99']:+.1f}\\% & {100 * r['max']:+.1f}\\%{censored} \\\\")
    note = ""
    if overhead:
        note += (f" Enabling epoch interruption costs a geometric-mean factor of {overhead['geomean']:.4f} "
                 f"(95\\% CI {overhead['ci_low']:.4f}--{overhead['ci_high']:.4f}) in CPU time over {overhead['cells']} corpus cells.")
    if probe:
        note += (f" A single 256\\,MiB \\texttt{{memory.copy}} cannot be interrupted mid-operation; under the CPU-time gate "
                 f"the probe overshoots by up to {100 * probe['max']:.0f}\\%.")
    caption = ("CPU overshoot of a 20\\,ms budget per call under three policies, as (CPU at stop $-$ budget)/budget; "
               "negative values mean the call was stopped early. Fuel-only converts the budget to fuel at the benign median "
               "cost per fuel unit; its runs are stopped by a safety cap at 50 times the budget, so its maxima are censored "
               "where marked. The CPU-time gate checks the guest thread's CPU time at every 1\\,ms epoch; DualGate applies both "
               "limits." + note)
    header = "Backend & Kernels & Policy & Runs & Median & 99th pct. & Maximum"
    body = "\n".join(rows)
    (TABLES / "tab24.tex").write_text(
        "\\begin{table}[t]\n" f"\\caption{{{caption}}}\\label{{tab:quota}}\n"
        "\\footnotesize\n\\setlength{\\tabcolsep}{4pt}%\n\\begin{adjustbox}{max width=\\textwidth}%\n"
        f"\\begin{{tabular}}{{lllrrrr}}\n\\toprule\n{header} \\\\\n\\midrule\n{body}\n"
        "\\bottomrule\n\\end{tabular}%\n\\end{adjustbox}\n\\end{table}\n")


def write_figure(data: pd.DataFrame) -> None:
    matplotlib.rcParams.update({"pdf.fonttype": 42, "ps.fonttype": 42, "font.size": 7, "axes.spines.top": False,
                                "axes.spines.right": False, "axes.grid": True, "grid.color": "#e4e3df",
                                "grid.linewidth": 0.5, "legend.frameon": False})
    colors = {"fuel": "#eb6834", "time": "#2a78d6", "dual": "#1baf7a"}
    markers = {"fuel": "s", "time": "o", "dual": "^"}
    cran = data[data["backend"] == "cranelift"]
    families = [f for f in ("corpus", "serverless", "adversarial") if f in set(cran["family"])]
    figure, axes = plt.subplots(1, len(families), figsize=(6.6, 2.4), sharey=True)
    for axis, fam in zip(np.atleast_1d(axes), families):
        part = cran[cran["family"] == fam]
        for offset, policy in enumerate(POLICIES):
            values = np.sort(part[part["policy"] == policy]["overshoot"].to_numpy() + 1.0)
            quantiles = np.arange(1, len(values) + 1) / len(values)
            axis.plot(values, quantiles, color=colors[policy], linewidth=1.3, label=POLICY_LABEL[policy],
                      marker=markers[policy], markevery=max(1, len(values) // 8), markersize=3)
        axis.axvline(1.0, color="#52514e", linestyle=":", linewidth=1)
        axis.set_xscale("log")
        axis.set_xlabel("CPU at stop / budget")
        axis.set_title(f"{fam} (Cranelift)", loc="left")
    np.atleast_1d(axes)[0].set_ylabel("Fraction of runs")
    np.atleast_1d(axes)[0].legend(fontsize=5.5, loc="lower right")
    figure.tight_layout()
    figure.savefig(FIGURES / "fig11.pdf", dpi=300)
    plt.close(figure)


def main() -> None:
    data = load_enforce()
    summary = summarize(data)
    overhead = overhead_summary()
    probe_path = R4 / "quota_probe_cranelift.csv"
    probe = {}
    if probe_path.exists():
        p = pd.read_csv(probe_path)
        gated = p[p["policy"] != "fuel"]["overshoot"]
        probe = {"max": float(gated.max()), "median": float(gated.median())}
    ticks = {}
    for path in sorted(R4.glob("quota_tick_*.csv")):
        t = pd.read_csv(path)
        t = t[t["policy"] == "time"]
        ticks[path.stem] = {"median": float(t["overshoot"].median()), "p99": float(t["overshoot"].quantile(0.99)),
                            "max": float(t["overshoot"].max())}
    write_table(summary, overhead, probe)
    write_figure(data)
    result = {"summary": summary.to_dict(orient="records"), "overhead": overhead, "probe": probe, "ticks": ticks}
    (METRICS / "quota_summary.json").write_text(json.dumps(result, indent=2, default=float))
    print(summary.round(4).to_string(index=False))
    print(json.dumps({"overhead": overhead, "probe": probe, "ticks": ticks}, indent=1))


if __name__ == "__main__":
    main()
