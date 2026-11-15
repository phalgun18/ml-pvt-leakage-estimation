"""Extra figures used only by the technical report (outputs/report/).

  partc_accuracy_ladder.png   spec method vs loading-aware, ML vs perfect-gate ceiling
  gate_error_attribution.png  gate error when one transistor model is replaced by exact SPICE
  partc_error_vs_corner.png   CLA spec-method error vs temperature and NMOS oxide thickness
  gate_error_vs_vdd.png       gate ML error vs VDD and PMOS oxide thickness

Run:  python -m report.report_figures
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common_scripts.config import REPO_ROOT, general_path, layer_path
from common_scripts.plotting import GRID, INK, INK_2, REF_LINE, SERIES, apply_style, plt, save

REPORT_DIR = REPO_ROOT / "report"
OUT = REPORT_DIR.joinpath("figures")


def acc(pred, ref):
    return 100 - np.mean(np.abs(pred / ref - 1)) * 100


def ladder(c: pd.DataFrame) -> dict:
    vals = {
        "Spec method\nML gate predictions": acc(c.ml_leak, c.spice_leak),
        "Spec method\nperfect SPICE gates\n(ceiling)": acc(c.spice_gate_sum, c.spice_leak),
        "+ loading gate tunnelling\nML gate predictions": acc(c.ml_leak_loaded, c.spice_leak),
        "+ loading gate tunnelling\nperfect SPICE gates\n(ceiling)": acc(c.spice_gate_sum_loaded, c.spice_leak),
    }
    fig, ax = plt.subplots(figsize=(8.6, 3.9))
    cols = [SERIES[0], "#9ec5f4", SERIES[1], "#f4b79e"]
    x = np.arange(len(vals))
    bars = ax.bar(x, list(vals.values()), color=cols, width=0.62, edgecolor="none")
    for b, v in zip(bars, vals.values()):
        ax.text(b.get_x() + b.get_width() / 2, v + 1.2, f"{v:.2f} %", ha="center", va="bottom",
                color=INK, fontsize=10, fontweight="bold")
    ax.axhline(99, color=REF_LINE, ls="--", lw=1)
    ax.text(-0.42, 100.2, "99 % target", color=INK_2, fontsize=8, ha="left", va="bottom")
    ax.set_xticks(x, list(vals.keys()), fontsize=8.5)
    ax.set_ylim(0, 112)
    ax.set_ylabel("mean accuracy (%)")
    ax.grid(axis="x", visible=False)
    ax.set_title("3-bit CLA: mean accuracy vs full-netlist SPICE (12,800 simulations)", loc="left")
    save(fig, OUT / "partc_accuracy_ladder.png")
    return vals


def attribution() -> None:
    a = pd.read_csv(layer_path(2, "outputs", "error_attribution.csv"), dtype={"inputs": str})
    piv = a.pivot_table(index=["gate", "inputs"], columns="variant", values="mean_err_pct", sort=False)
    order = ["all ML", "nmos_on -> SPICE", "nmos_off -> SPICE", "pmos_on -> SPICE", "pmos_off -> SPICE"]
    labels = ["all ML", "NMOS ON exact", "NMOS OFF exact", "PMOS ON exact", "PMOS OFF exact"]
    piv = piv[order]
    fig, ax = plt.subplots(figsize=(10, 3.9))
    x = np.arange(len(piv))
    w = 0.16
    cols = [INK_2, SERIES[0], "#9ec5f4", SERIES[1], "#f4b79e"]
    for j, (col, lab) in enumerate(zip(order, labels)):
        ax.bar(x + (j - 2) * w, piv[col].to_numpy(), width=w * 0.92, color=cols[j], label=lab, edgecolor="none")
    ax.set_xticks(x, [f"{g}\n{i}" for g, i in piv.index], fontsize=7.5)
    ax.set_ylabel("mean gate error (%)")
    ax.grid(axis="x", visible=False)
    ax.legend(ncols=5, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.2))
    ax.set_title("Error attribution: gate error when one transistor model is replaced by exact SPICE currents",
                 loc="left", fontsize=10)
    save(fig, OUT / "gate_error_attribution.png")


def partc_vs_corner(c: pd.DataFrame) -> None:
    c = c.assign(es=np.abs(c.ml_leak / c.spice_leak - 1) * 100,
                 el=np.abs(c.ml_leak_loaded / c.spice_leak - 1) * 100)
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), sharey=True)
    for ax, col, lab, sc in ((axes[0], "temp", "Temperature (°C)", 1), (axes[1], "n_toxe", "NMOS toxe (nm)", 1e9)):
        ax.scatter(c[col] * sc, c.es, s=3, alpha=0.25, color=SERIES[0], linewidths=0, label="spec method")
        ax.scatter(c[col] * sc, c.el, s=3, alpha=0.25, color=SERIES[1], linewidths=0, label="+ loading")
        ax.set_xlabel(lab)
        ax.set_yscale("log")
    axes[0].set_ylabel("CLA relative error (%)")
    axes[0].legend(markerscale=4, loc="lower left")
    fig.suptitle("CLA error vs corner: the missing loading current is gate tunnelling "
                 "(large for thin oxide, small share at high T)", fontsize=11, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout()
    save(fig, OUT / "partc_error_vs_corner.png")


def gate_vs_vdd() -> None:
    r = pd.read_csv(layer_path(2, "data", "results", "part_b_results.csv"), dtype={"inputs": str})
    r["e"] = np.abs(r.ml_leak / r.spice_leak - 1) * 100
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), sharey=True)
    for ax, col, lab, sc in ((axes[0], "vdd", "VDD (V)", 1), (axes[1], "p_toxe", "PMOS toxe (nm)", 1e9),
                             (axes[2], "temp", "Temperature (°C)", 1)):
        ax.scatter(r[col] * sc, r.e, s=4, alpha=0.3, color=SERIES[0], linewidths=0)
        bins = np.linspace((r[col] * sc).min(), (r[col] * sc).max(), 9)
        idx = np.digitize(r[col] * sc, bins)
        bx = [(r[col] * sc)[idx == k].mean() for k in range(1, 9)]
        by = [r.e[idx == k].mean() for k in range(1, 9)]
        ax.plot(bx, by, color=INK, lw=2, label="binned mean")
        ax.set_xlabel(lab)
        ax.set_yscale("log")
    axes[0].set_ylabel("gate relative error (%)")
    axes[0].legend(loc="lower left")
    fig.suptitle("Gate ML error vs corner conditions (all 3,600 gate simulations)", fontsize=11,
                 fontweight="bold", x=0.01, ha="left")
    fig.tight_layout()
    save(fig, OUT / "gate_error_vs_vdd.png")


def main() -> None:
    apply_style()
    OUT.mkdir(parents=True, exist_ok=True)
    c = pd.read_csv(layer_path(3, "data", "results", "part_c_results.csv"))
    print(ladder(c))
    attribution()
    partc_vs_corner(c)
    gate_vs_vdd()
    print(f"figures -> {OUT}")


if __name__ == "__main__":
    main()
