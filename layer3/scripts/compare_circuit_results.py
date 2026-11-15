"""Part C step 8: hierarchical ML vs full-netlist SPICE for the 3-bit CLA.

Outputs (outputs/part_c/)
  circuit_results_table.csv    overall metrics (same columns as the gate table) for:
                                 ML vs SPICE (the deliverable, spec method),
                                 loading-aware ML vs SPICE (improvement),
                                 ML vs sum of isolated-gate SPICE (pure ML error),
                                 sum of isolated-gate SPICE vs full SPICE (loading error)
  circuit_results_by_vector.csv the same metrics per input vector (64 rows)
  circuit_parity.png           ML vs SPICE leakage, log axes (deliverable 8)
  circuit_error_breakdown.png  error distributions of the three comparisons
  circuit_vs_gate_accuracy.csv Part C vs Part B summary
  rail_deviation.json          how far CLA gate outputs (= next gates' inputs) sit from 0 / VDD

Run:  python -m layer3.scripts.compare_circuit_results
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common_scripts.config import general_path, layer_path
from common_scripts.metrics import error_stats
from common_scripts.plotting import GRID, INK, INK_2, REF_LINE, SERIES, apply_style, plt, save

OUT = layer_path(3, "outputs")


def row(name, pred, ref):
    s = error_stats(np.asarray(pred), np.asarray(ref), floor=0)
    return {"comparison": name, "n": s["n"], "spice_median_A": float(np.median(ref)),
            "ml_median_A": float(np.median(pred)), "bias_pct": s["bias_pct"],
            "median_err_pct": s["median_err_pct"], "p95_err_pct": s["p95_err_pct"],
            "mean_err_pct": s["mean_err_pct"], "max_err_pct": s["max_err_pct"],
            "mean_accuracy_pct": 100 - s["mean_err_pct"], "r2_log10": s["r2_log10"],
            "sign_errors": s["sign_errors"]}


def main() -> None:
    apply_style()
    res = pd.read_csv(layer_path(3, "data", "results", "part_c_results.csv"))
    OUT.mkdir(parents=True, exist_ok=True)
    t = pd.DataFrame([
        row("ML (hierarchical) vs SPICE full netlist", res.ml_leak, res.spice_leak),
        row("ML (hierarchical) vs sum of isolated-gate SPICE [pure ML error]", res.ml_leak, res.spice_gate_sum),
        row("sum of isolated-gate SPICE vs SPICE full netlist [hierarchy/loading error]",
            res.spice_gate_sum, res.spice_leak),
        row("ML loading-aware (gates + driven-input currents) vs SPICE full netlist",
            res.ml_leak_loaded, res.spice_leak),
        row("isolated-gate SPICE + driven-input currents vs SPICE full netlist [check of the loading model]",
            res.spice_gate_sum_loaded, res.spice_leak),
    ])
    t.to_csv(OUT / "circuit_results_table.csv", index=False)
    by_vec = pd.DataFrame([{"vector": v, **{k: x for k, x in row("ML vs SPICE", g.ml_leak, g.spice_leak).items()
                                             if k != "comparison"}}
                           for v, g in res.groupby("vector", sort=False)])
    by_vec.to_csv(OUT / "circuit_results_by_vector.csv", index=False)
    with pd.option_context("display.width", 250, "display.float_format", "{:.4g}".format,
                           "display.max_colwidth", 80):
        print(t.T.to_string())
        print("\nper-vector mean error: min %.2f %%, max %.2f %%"
              % (by_vec.mean_err_pct.min(), by_vec.mean_err_pct.max()))

    gate = pd.read_csv(layer_path(2, "outputs", "gate_results_table.csv"))
    ga = gate[gate.gate == "ALL"].iloc[0]
    ca, cl = t.iloc[0], t.iloc[3]          # spec method, loading-aware
    lv = [{"level": "Part B gates (3,600 sims)", "median_err_pct": ga.median_err_pct,
           "p95_err_pct": ga.p95_err_pct, "mean_err_pct": ga.mean_err_pct,
           "mean_accuracy_pct": 100 - ga.mean_err_pct, "bias_pct": ga.bias_pct}]
    for name, r in ((f"Part C CLA, spec method ({int(ca.n)} sims)", ca),
                    (f"Part C CLA, loading-aware ({int(cl.n)} sims)", cl)):
        lv.append({"level": name, "median_err_pct": r.median_err_pct, "p95_err_pct": r.p95_err_pct,
                   "mean_err_pct": r.mean_err_pct, "mean_accuracy_pct": r.mean_accuracy_pct,
                   "bias_pct": r.bias_pct})
    pd.DataFrame(lv).to_csv(OUT / "circuit_vs_gate_accuracy.csv", index=False)

    # spec assumption check: every gate input at exactly 0 or VDD
    import json
    from common_scripts.cla import INPUTS, cla3_gates, evaluate
    sm = pd.read_csv(layer_path(3, "data", "raw", "part_c_spice_summary.csv")).merge(
        res[["corner_id", "vdd"]].drop_duplicates(), on="corner_id")
    gates = cla3_gates()
    devs = []
    for _, r in sm.iterrows():
        val = evaluate(gates, {n: int(r[f"in_{n}"]) for n in INPUTS})
        devs.extend(abs(r[f"v_{g.out}"] - r.vdd * val[g.out]) for g in gates)
    devs = np.array(devs)
    rail = {"n_gate_outputs": int(len(devs)), "median_uV": float(np.median(devs) * 1e6),
            "p99_uV": float(np.percentile(devs, 99) * 1e6), "max_uV": float(devs.max() * 1e6),
            "max_pct_of_vdd": float(devs.max() / sm.vdd.min() * 100)}
    (OUT / "rail_deviation.json").write_text(json.dumps(rail, indent=2), encoding="utf-8")
    print("rail deviation:", rail)

    # parity: two panels on identical axes
    lo = min(res.spice_leak.min(), res.ml_leak.min(), res.ml_leak_loaded.min()) / 1.5
    hi = max(res.spice_leak.max(), res.ml_leak.max(), res.ml_leak_loaded.max()) * 1.5
    x = np.array([lo, hi])
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.6), sharex=True, sharey=True)
    panels = ((axes[0], "ml_leak", ca, "Spec method: sum of 39 gate leakages", SERIES[0]),
              (axes[1], "ml_leak_loaded", cl, "Loading-aware: + currents into gate inputs driven high",
               SERIES[1]))
    for ax, col, r, title, c in panels:
        ax.fill_between(x, x * 0.95, x * 1.05, color=GRID, alpha=0.8, lw=0, label="±5 %")
        ax.plot(x, x, color=INK_2, lw=1, ls="--")
        ax.scatter(res.spice_leak, res[col], s=4, alpha=0.35, color=c, linewidths=0,
                   label=f"{len(res)} sims (64 vectors x 200 corners)")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlim(lo, hi)
        ax.set_ylim(lo, hi)
        ax.set_xlabel("SPICE leakage, full CLA netlist (A)")
        ax.set_title(title, loc="left", fontsize=10)
        ax.text(0.98, 0.03, f"median error {r.median_err_pct:.2f} %\nP95 error {r.p95_err_pct:.2f} %\n"
                f"mean accuracy {r.mean_accuracy_pct:.2f} %", transform=ax.transAxes, ha="right",
                va="bottom", color=INK, fontsize=9)
        ax.legend(loc="upper left", markerscale=2)
    axes[0].set_ylabel("ML leakage (A)")
    fig.suptitle("3-bit CLA: hierarchical ML vs SPICE", fontsize=12, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout()
    save(fig, OUT / "circuit_parity.png")

    # error breakdown (signed, full range, log counts)
    fig, ax = plt.subplots(figsize=(9, 3.8))
    comps = [("spec method ML vs full netlist", res.ml_leak / res.spice_leak - 1, SERIES[0]),
             ("isolated-gate SPICE sum vs full netlist (loading error)",
              res.spice_gate_sum / res.spice_leak - 1, SERIES[2]),
             ("ML vs isolated-gate SPICE sum (pure ML error)", res.ml_leak / res.spice_gate_sum - 1, SERIES[3]),
             ("loading-aware ML vs full netlist", res.ml_leak_loaded / res.spice_leak - 1, SERIES[1])]
    bins = np.linspace(-85, 15, 201)
    for name, e, col in comps:
        ax.hist(e * 100, bins=bins, histtype="step", lw=2, color=col, label=name)
    ax.axvline(0, color=REF_LINE, lw=1)
    ax.set_yscale("log")
    ax.set_xlabel("signed relative error (%)")
    ax.set_ylabel("simulations (log)")
    ax.set_title("Where the CLA error comes from", loc="left")
    ax.legend(loc="upper left", fontsize=8)
    save(fig, OUT / "circuit_error_breakdown.png")
    print(f"\noutputs -> {OUT}")


if __name__ == "__main__":
    main()
