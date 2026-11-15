"""Part B step 5: compare ML vs SPICE gate leakage (deliverables 6 and 7).

Metrics per gate / input case (see common/metrics.py for definitions):
SPICE median, ML median, bias = median(ML/SPICE - 1), median / P95 / mean /
max relative error, R2 on log10. Gate leakage is always > 0 here, so no
sample is excluded by the floor (n_below_floor is reported anyway).

Outputs (outputs/part_b/)
  gate_results_table.csv       18 cases + overall (deliverable 6)
  gate_parity.png              ML vs SPICE, log axes, all simulations (deliverable 7)
  gate_error_by_case.png       median and P95 error per case
  gate_error_vs_corner.png     relative error vs temperature / VDD / widths
  gate_worst_cases.csv         20 largest errors with their corner conditions

Run:  python -m layer2.scripts.compare_gate_results
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common_scripts.config import general_path, layer_path
from common_scripts.metrics import error_stats
from common_scripts.plotting import GRID, INK, INK_2, REF_LINE, SERIES, apply_style, plt, save

OUT = layer_path(2, "outputs")
GATES = ["inv", "nand2", "nor2", "and2", "or2"]
GATE_COLOR = {g: SERIES[i] for i, g in enumerate(GATES)}


def results_table(res: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (gate, inputs), g in res.groupby(["gate", "inputs"], sort=False):
        s = error_stats(g.ml_leak, g.spice_leak, floor=0)
        rows.append({"gate": gate.upper(), "inputs": inputs, "n": s["n"],
                     "spice_median_A": g.spice_leak.median(), "ml_median_A": g.ml_leak.median(),
                     "bias_pct": s["bias_pct"], "median_err_pct": s["median_err_pct"],
                     "p95_err_pct": s["p95_err_pct"], "mean_err_pct": s["mean_err_pct"],
                     "max_err_pct": s["max_err_pct"], "r2_log10": s["r2_log10"],
                     "sign_errors": s["sign_errors"]})
    t = pd.DataFrame(rows)
    order = {g: i for i, g in enumerate(GATES)}
    t = t.sort_values(["gate", "inputs"], key=lambda c: c.map(lambda v: order.get(str(v).lower(), v)))
    s = error_stats(res.ml_leak, res.spice_leak, floor=0)
    t.loc[len(t)] = {"gate": "ALL", "inputs": "-", "n": s["n"], "spice_median_A": res.spice_leak.median(),
                     "ml_median_A": res.ml_leak.median(), "bias_pct": s["bias_pct"],
                     "median_err_pct": s["median_err_pct"], "p95_err_pct": s["p95_err_pct"],
                     "mean_err_pct": s["mean_err_pct"], "max_err_pct": s["max_err_pct"],
                     "r2_log10": s["r2_log10"], "sign_errors": s["sign_errors"]}
    return t.reset_index(drop=True)


def parity(res: pd.DataFrame, overall: pd.Series) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 6.0))
    lo = min(res.spice_leak.min(), res.ml_leak.min()) / 2
    hi = max(res.spice_leak.max(), res.ml_leak.max()) * 2
    x = np.array([lo, hi])
    ax.fill_between(x, x * 0.95, x * 1.05, color=GRID, alpha=0.8, lw=0, label="±5 %")
    ax.plot(x, x, color=INK_2, lw=1, ls="--")
    for g in GATES:
        d = res[res.gate == g]
        ax.scatter(d.spice_leak, d.ml_leak, s=9, alpha=0.6, color=GATE_COLOR[g], linewidths=0,
                   label=f"{g.upper()} (n={len(d)})")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("SPICE leakage  I_VDD  (A)")
    ax.set_ylabel("ML leakage  (A)")
    ax.set_title("Gate leakage: ML vs SPICE (all gates, inputs, 200 corners)", loc="left")
    ax.text(0.98, 0.03, f"median error {overall.median_err_pct:.2f} %\nP95 error {overall.p95_err_pct:.2f} %\n"
            f"mean error {overall.mean_err_pct:.2f} %", transform=ax.transAxes, ha="right", va="bottom",
            color=INK, fontsize=9)
    ax.legend(loc="upper left", markerscale=1.8)
    save(fig, OUT / "gate_parity.png")


def by_case(t: pd.DataFrame) -> None:
    t = t[t.gate != "ALL"].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(10, 3.8))
    x = np.arange(len(t))
    cols = [GATE_COLOR[g.lower()] for g in t.gate]
    for i in x:
        ax.plot([i, i], [t.median_err_pct[i], t.p95_err_pct[i]], color=GRID, lw=3, solid_capstyle="round")
    ax.scatter(x, t.median_err_pct, s=40, color=cols, zorder=3, label="median")
    ax.scatter(x, t.p95_err_pct, s=40, facecolors="none", edgecolors=cols, lw=1.8, zorder=3, label="P95")
    ax.set_xticks(x, [f"{g}\n{i}" for g, i in zip(t.gate, t.inputs)], fontsize=8)
    ax.set_ylabel("relative error (%)")
    ax.set_title("Gate leakage error per gate / input case (filled = median, open = P95)", loc="left")
    ax.grid(axis="x", visible=False)
    save(fig, OUT / "gate_error_by_case.png")


def vs_corner(res: pd.DataFrame) -> None:
    res = res.assign(err=np.abs(res.ml_leak / res.spice_leak - 1) * 100)
    fig, axes = plt.subplots(1, 4, figsize=(15, 3.6), sharey=True)
    for ax, (col, lab, sc) in zip(axes, [("temp", "Temperature (°C)", 1), ("vdd", "VDD (V)", 1),
                                         ("n_vth0", "NMOS vth0 (V)", 1), ("wn", "NMOS width (nm)", 1e9)]):
        for g in GATES:
            d = res[res.gate == g]
            ax.scatter(d[col] * sc, d.err, s=5, alpha=0.4, color=GATE_COLOR[g], linewidths=0,
                       label=g.upper())
        ax.set_yscale("log")
        ax.set_xlabel(lab)
    axes[0].set_ylabel("relative error (%)")
    axes[-1].legend(loc="lower right", markerscale=2, fontsize=7.5)
    fig.suptitle("Gate leakage error vs corner conditions", fontsize=12, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout()
    save(fig, OUT / "gate_error_vs_corner.png")


def main() -> None:
    apply_style()
    res = pd.read_csv(layer_path(2, "data", "results", "part_b_results.csv"), dtype={"inputs": str})
    t = results_table(res)
    OUT.mkdir(parents=True, exist_ok=True)
    t.to_csv(OUT / "gate_results_table.csv", index=False)
    with pd.option_context("display.width", 220, "display.float_format", "{:.4g}".format):
        print(t.to_string(index=False))
    parity(res, t.iloc[-1])
    by_case(t)
    vs_corner(res)
    res["err_pct"] = np.abs(res.ml_leak / res.spice_leak - 1) * 100
    cols = ["gate", "inputs", "corner_id", "spice_leak", "ml_leak", "err_pct", "vdd", "temp", "wn", "wp",
            "n_vth0", "p_vth0"]
    res.sort_values("err_pct", ascending=False)[cols].head(20).to_csv(OUT / "gate_worst_cases.csv", index=False)
    print(f"\noutputs -> {OUT}")


if __name__ == "__main__":
    main()
