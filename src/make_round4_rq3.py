#!/usr/bin/env python3
"""
RQ3 analysis for the round-4 revision: the host-call boundary under a Rust embedder and the
WASI Preview 1 versus Preview 2 write cost, both from the gated rerun in data/r4/.

Host call:
  * the transition cost is measured directly by the `null` side (an import call that does no
    host work), not inferred from a regression intercept;
  * the boundary overhead at each size is the difference of the host-call and native medians;
  * affine fits T(s) = alpha + beta*s are reported separately for small (<= 16 KiB) and large
    (>= 256 KiB) payloads, with OLS 95% intervals and R^2.
WASI:
  * the per-write cost of each replicate is (T_full - median T_baseline) / writes;
  * the P2/P1 ratio at each size has a 95% interval from Welch's t on log per-write costs, and a
    difference is reported only where that interval excludes 1.

Writes tables/tab04.tex, tables/tab17.tex, figures/fig06.pdf, results/metrics/rq3_round4.json.
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
SMALL_MAX = 16384
LARGE_MIN = 262144
CONFIDENCE = 0.95


def size_label(n: int) -> str:
    for unit, scale in (("MiB", 1 << 20), ("KiB", 1 << 10)):
        if n >= scale:
            return f"{n // scale}\\,{unit}"
    return f"{n}\\,B"


def affine(sizes: np.ndarray, times: np.ndarray) -> dict:
    fit = stats.linregress(sizes, times)
    t_crit = stats.t.ppf(0.5 + CONFIDENCE / 2, len(sizes) - 2)
    return {"alpha": fit.intercept, "alpha_half": t_crit * fit.intercept_stderr,
            "beta": fit.slope, "beta_half": t_crit * fit.stderr, "r2": fit.rvalue ** 2, "n": len(sizes)}


def mean_interval(values: pd.Series) -> tuple:
    half = stats.t.ppf(0.5 + CONFIDENCE / 2, len(values) - 1) * values.std(ddof=1) / np.sqrt(len(values))
    return float(values.mean()), float(half)


def host_analysis() -> dict:
    host = pd.read_csv(R4 / "rq3_host_call_rust.csv", keep_default_na=False)  # side "null" is a label, not NaN
    null = host[host.side == "null"]["per_call_ns"]
    medians = host[host.side != "null"].groupby(["payload_bytes", "side"])["per_call_ns"].median().unstack("side")
    medians["overhead"] = medians["wasm"] - medians["native"]
    medians["ratio"] = medians["wasm"] / medians["native"]
    fits = {}
    for side in ("wasm", "native"):
        part = host[host.side == side]
        for label, mask in (("small", part.payload_bytes <= SMALL_MAX), ("large", part.payload_bytes >= LARGE_MIN)):
            sub = part[mask]
            fits[f"{side}_{label}"] = affine(sub.payload_bytes.to_numpy(float), sub.per_call_ns.to_numpy(float))
    transition, transition_half = mean_interval(null)
    return {"medians": medians, "fits": fits, "transition_ns": transition, "transition_half": transition_half,
            "transition_median": float(null.median()), "load_max": float(host.loadavg_1m.max()),
            "load_median": float(host.loadavg_1m.median())}


def wasi_analysis() -> pd.DataFrame:
    wasi = pd.read_csv(R4 / "rq3_wasi_p1_p2.csv")
    base = wasi[wasi["mode"] == "baseline"].groupby(["side", "payload_bytes"])["cpu_ns"].median()
    full = wasi[wasi["mode"] == "full"].copy()
    full["per_write_ns"] = (full["cpu_ns"] - base.reindex(list(zip(full.side, full.payload_bytes))).values) / full["writes"]
    rows = []
    for size, part in full.groupby("payload_bytes"):
        p1 = np.log(part[part.side == "preview1"]["per_write_ns"].clip(lower=1e-3))
        p2 = np.log(part[part.side == "preview2"]["per_write_ns"].clip(lower=1e-3))
        test = stats.ttest_ind(p2, p1, equal_var=False)
        dof = test.df
        se = np.sqrt(p2.var(ddof=1) / len(p2) + p1.var(ddof=1) / len(p1))
        diff = p2.mean() - p1.mean()
        half = stats.t.ppf(0.5 + CONFIDENCE / 2, dof) * se
        rows.append({"payload_bytes": size, "p1_median_ns": float(np.exp(p1).median()),
                     "p2_median_ns": float(np.exp(p2).median()), "ratio": float(np.exp(diff)),
                     "ratio_low": float(np.exp(diff - half)), "ratio_high": float(np.exp(diff + half)),
                     "p_value": float(test.pvalue)})
    frame = pd.DataFrame(rows)
    frame.attrs["load_max"] = float(wasi["loadavg_1m"].max())
    frame.attrs["load_median"] = float(wasi["loadavg_1m"].median())
    frame.attrs["fits"] = {side: affine(full[full.side == side].payload_bytes.to_numpy(float),
                                        full[full.side == side].per_write_ns.to_numpy(float))
                           for side in ("preview1", "preview2")}
    return frame


def latex_table(caption: str, label: str, spec: str, header: str, rows: list) -> str:
    return ("\\begin{table}[t]\n" f"\\caption{{{caption}}}\\label{{{label}}}\n"
            "\\footnotesize\n\\setlength{\\tabcolsep}{4pt}%\n\\begin{adjustbox}{max width=\\textwidth}%\n"
            f"\\begin{{tabular}}{{{spec}}}\n\\toprule\n{header} \\\\\n\\midrule\n" + "\n".join(rows) +
            "\n\\bottomrule\n\\end{tabular}%\n\\end{adjustbox}\n\\end{table}\n")


def write_fit_table(host: dict, wasi: pd.DataFrame) -> None:
    rows = [f"Host-call transition (null import) & --- & ${host['transition_ns']:.1f} \\pm {host['transition_half']:.1f}$ & --- & --- \\\\"]
    names = {"wasm": "Host call", "native": "Native baseline"}
    for side in ("wasm", "native"):
        for label, text in (("small", "64\\,B--16\\,KiB"), ("large", "256\\,KiB--16\\,MiB")):
            fit = host["fits"][f"{side}_{label}"]
            rows.append(f"{names[side]}, {text} & {fit['n']} & ${fit['alpha']:.0f} \\pm {fit['alpha_half']:.0f}$ & "
                        f"${fit['beta']:.4f} \\pm {fit['beta_half']:.4f}$ & {fit['r2']:.3f} \\\\")
    for side, name in (("preview1", "WASI Preview 1 write"), ("preview2", "WASI Preview 2 write")):
        fit = wasi.attrs["fits"][side]
        rows.append(f"{name}, 64\\,B--16\\,MiB & {fit['n']} & ${fit['alpha']:.0f} \\pm {fit['alpha_half']:.0f}$ & "
                    f"${fit['beta']:.4f} \\pm {fit['beta_half']:.4f}$ & {fit['r2']:.3f} \\\\")
    caption = ("RQ3 cost models from the gated rerun, Wasmtime 50.0.0 embedded in Rust. The transition row is the mean "
               "per-call cost of an import that does no host work, with a 95\\% $t$ interval over replicates. The other rows "
               "are OLS fits $T(s)=\\alpha+\\beta s$ in ns and ns per byte with 95\\% half-widths, fitted separately below "
               "and above the cache-capacity range because one line does not fit both. WASI rows are per-write costs to "
               "\\texttt{/dev/null} with instantiation subtracted.")
    header = "Model & $n$ & $\\alpha$ (ns) & $\\beta$ (ns/B) & $R^2$"
    (TABLES / "tab04.tex").write_text(latex_table(caption, "tab:hostfit", "lrrrr", header, rows))


def write_sweep_table(host: dict, wasi: pd.DataFrame) -> None:
    rows = []
    medians = host["medians"]
    wasi_by_size = wasi.set_index("payload_bytes")
    for size, row in medians.iterrows():
        cells = [size_label(int(size)), f"{row['wasm']:,.0f}", f"{row['native']:,.0f}", f"{row['overhead']:,.0f}", f"{row['ratio']:.2f}"]
        if size in wasi_by_size.index:
            w = wasi_by_size.loc[size]
            cells += [f"{w['p1_median_ns']:,.0f}", f"{w['p2_median_ns']:,.0f}", f"{w['ratio']:.2f} [{w['ratio_low']:.2f}, {w['ratio_high']:.2f}]"]
        else:
            cells += ["---", "---", "---"]
        rows.append(" & ".join(cells) + " \\\\")
    caption = ("Per-size medians of the RQ3 sweeps in ns per call or per write. Overhead is the host-call median minus the "
               "native median. The WASI ratio is Preview 2 over Preview 1 per-write cost with a 95\\% interval from Welch's "
               "$t$ on log costs; WASI was swept at seven of the ten host-call sizes.")
    header = ("Payload & Host call & Native & Overhead & Ratio & WASI P1 & WASI P2 & P2/P1 [95\\% CI]")
    (TABLES / "tab17.tex").write_text(latex_table(caption, "tab:rq3_sweep", "lrrrrrrr", header, rows))


def write_figure(host: dict, wasi: pd.DataFrame) -> None:
    matplotlib.rcParams.update({"pdf.fonttype": 42, "ps.fonttype": 42, "font.size": 7, "axes.spines.top": False,
                                "axes.spines.right": False, "axes.grid": True, "grid.color": "#e4e3df",
                                "grid.linewidth": 0.5, "legend.frameon": False})
    medians = host["medians"]
    figure, (left, right) = plt.subplots(1, 2, figsize=(6.6, 2.5))
    left.plot(medians.index, medians["wasm"], color="#2a78d6", marker="o", markersize=4, linewidth=1.4, label="host call (Rust embedder)")
    left.plot(medians.index, medians["native"], color="#eb6834", marker="s", markersize=4, linewidth=1.4, label="native copy-and-validate")
    left.axhline(host["transition_ns"], color="#52514e", linestyle=":", linewidth=1, label="null import (transition)")
    left.set_xscale("log", base=2)
    left.set_yscale("log")
    left.set_xlabel("Payload (bytes)")
    left.set_ylabel("Median per call (ns)")
    left.set_title("(a) Host-call boundary", loc="left")
    left.legend(fontsize=6, loc="upper left")
    right.errorbar(wasi.payload_bytes, wasi.ratio, yerr=[wasi.ratio - wasi.ratio_low, wasi.ratio_high - wasi.ratio],
                   color="#2a78d6", marker="o", markersize=4, linewidth=1.2, capsize=2)
    right.axhline(1.0, color="#52514e", linestyle=":", linewidth=1)
    right.set_xscale("log", base=2)
    right.set_xlabel("Payload (bytes)")
    right.set_ylabel("Preview 2 / Preview 1 per write")
    right.set_title("(b) WASI write cost ratio, 95% CI", loc="left")
    figure.tight_layout()
    figure.savefig(FIGURES / "fig06.pdf", dpi=300)
    plt.close(figure)


def main() -> None:
    host = host_analysis()
    wasi = wasi_analysis()
    write_fit_table(host, wasi)
    write_sweep_table(host, wasi)
    write_figure(host, wasi)
    summary = {"transition_ns": host["transition_ns"], "transition_half": host["transition_half"],
               "host_load_median": host["load_median"], "host_load_max": host["load_max"],
               "wasi_load_median": wasi.attrs["load_median"], "wasi_load_max": wasi.attrs["load_max"],
               "host_medians": host["medians"].reset_index().to_dict(orient="records"),
               "host_fits": host["fits"], "wasi": wasi.to_dict(orient="records"), "wasi_fits": wasi.attrs["fits"]}
    (METRICS / "rq3_round4.json").write_text(json.dumps(summary, indent=2, default=float))
    print(json.dumps(summary, indent=1, default=float)[:3000])


if __name__ == "__main__":
    main()
