"""Part A step 3: plots for the chosen models on the TEST set.

  outputs/part_a/parity_<case>.png       predicted vs SPICE |I| (log-log), one panel per terminal
  outputs/part_a/error_cdf_test.png      cumulative distribution of relative error
  outputs/part_a/model_comparison.png    validation P95 error per case x model type

Log axes need |I| > 0: points are plotted at |I|; samples where predicted and
SPICE signs differ are drawn in red; samples below the 1e-15 A evaluation
floor are drawn faint grey (excluded from % metrics, see metrics.py).

Run:  python -m layer1.scripts.plot_results
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common_scripts.config import load_config, general_path, layer_path
from common_scripts.plotting import DEVICE_COLOR, GRID, INK_2, REF_LINE, SERIES, apply_style, plt, save
from common_scripts.transistor_model import TERMINALS

OUT = layer_path(1, "outputs")
FLOOR = 1e-15
SIGN_ERR = "#e34948"


def parity(case: str, dev: str, metrics: pd.DataFrame) -> None:
    df = pd.read_csv(OUT / f"predictions_test_{case}.csv")
    fig, axes = plt.subplots(2, 2, figsize=(9, 8.2))
    for ax, k in zip(axes.flat, TERMINALS):
        ref, pred = df[k].to_numpy(), df[f"{k}_pred"].to_numpy()
        a_ref, a_pred = np.abs(ref), np.maximum(np.abs(pred), 1e-40)
        ok = a_ref >= FLOOR
        sign_bad = ok & (np.sign(ref) != np.sign(pred))
        good = ok & ~sign_bad
        if (~ok).any():
            ax.scatter(np.maximum(a_ref[~ok], 1e-40), a_pred[~ok], s=5, color=REF_LINE, alpha=0.25,
                       linewidths=0, label=f"|I| < 1e-15 A (n={int((~ok).sum())})")
        ax.scatter(a_ref[good], a_pred[good], s=6, color=DEVICE_COLOR[dev], alpha=0.5, linewidths=0,
                   label=f"evaluated (n={int(good.sum())})")
        if sign_bad.any():
            ax.scatter(a_ref[sign_bad], a_pred[sign_bad], s=14, color=SIGN_ERR, linewidths=0,
                       label=f"sign mismatch (n={int(sign_bad.sum())})")
        if ok.any():
            lo = max(min(a_ref[ok].min(), a_pred[ok].min()) / 3, 1e-20)
            hi = max(a_ref.max(), a_pred.max()) * 3
            ax.plot([lo, hi], [lo, hi], color=INK_2, lw=1, ls="--")
            ax.set_xlim(lo, hi)
            ax.set_ylim(lo, hi)
        ax.set_xscale("log")
        ax.set_yscale("log")
        m = metrics[(metrics.case == case) & (metrics.terminal == k)].iloc[0]
        txt = ("no samples above floor" if np.isnan(m.median_err_pct) else
               f"median {m.median_err_pct:.2f} %   P95 {m.p95_err_pct:.2f} %")
        ax.set_title(f"{k.upper()}   ({txt})", fontsize=9.5, loc="left")
        ax.set_xlabel("SPICE |I|  (A)")
        ax.set_ylabel("ML |I|  (A)")
        ax.legend(loc="upper left", fontsize=7.5, markerscale=1.5)
    fig.suptitle(f"{case.replace('_', ' ').upper()}: ML vs SPICE on the test set "
                 f"({metrics[metrics.case == case].model.iloc[0]})",
                 fontsize=12, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout()
    save(fig, OUT / f"parity_{case}.png")


def error_cdf(cases, metrics) -> None:
    fig, axes = plt.subplots(1, 4, figsize=(14, 3.6), sharey=True)
    for ax, k in zip(axes, TERMINALS):
        for i, case in enumerate(cases):
            df = pd.read_csv(OUT / f"predictions_test_{case}.csv")
            ok = np.abs(df[k]) >= FLOOR
            if not ok.any():
                continue
            e = np.sort(np.abs(df[f"{k}_pred"][ok] - df[k][ok]) / np.abs(df[k][ok]) * 100)
            ax.plot(np.maximum(e, 1e-4), np.linspace(0, 1, len(e)), color=SERIES[i], lw=2, label=case)
        ax.axvline(1, color=REF_LINE, ls="--", lw=1)
        ax.set_xscale("log")
        ax.set_title(k.upper(), loc="left")
        ax.set_xlabel("relative error (%)")
    axes[0].set_ylabel("fraction of test samples")
    axes[-1].legend(loc="lower right")
    fig.suptitle("Test-set relative error, cumulative (|I_SPICE| >= 1e-15 A; dashed = 1 %)",
                 fontsize=12, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout()
    save(fig, OUT / "error_cdf_test.png")


def comparison_plot() -> None:
    s = pd.read_csv(OUT / "model_comparison_table.csv")
    cases = list(dict.fromkeys(s.case))
    models = ["poly_ridge", "rf", "hgb", "mlp"]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    width = 0.2
    for j, m in enumerate(models):
        vals = [s[(s.case == c) & (s.model == m)].p95_err_pct_mean.squeeze() for c in cases]
        x = np.arange(len(cases)) + (j - 1.5) * width
        ax.bar(x, vals, width=width * 0.9, color=SERIES[j], label=m, edgecolor="none")
    ax.set_yscale("log")
    from matplotlib.ticker import FixedLocator, NullLocator, ScalarFormatter
    ax.yaxis.set_major_locator(FixedLocator([1, 2, 5, 10, 20, 50]))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_major_formatter(ScalarFormatter())
    ax.set_xticks(np.arange(len(cases)), [c.replace("_", " ").upper() for c in cases])
    ax.set_ylabel("validation P95 rel. error (%)\nmean over terminals")
    ax.grid(axis="x", visible=False)
    ax.legend(ncols=4, loc="upper center", bbox_to_anchor=(0.5, 1.13))
    ax.set_title("Model comparison (lower is better)", loc="left", pad=28)
    save(fig, OUT / "model_comparison.png")


def main() -> None:
    apply_style()
    cfg = load_config()
    metrics = pd.read_csv(OUT / "test_metrics.csv")
    cases = list(cfg["part_a"]["cases"])
    for case in cases:
        parity(case, cfg["part_a"]["cases"][case]["device"], metrics)
    error_cdf(cases, metrics)
    comparison_plot()
    print(f"plots -> {OUT}")


if __name__ == "__main__":
    main()
