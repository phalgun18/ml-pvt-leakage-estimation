"""Part A step 1c: data check of the four SPICE datasets (deliverable 3).

Checks per case (nothing is silently dropped - all findings are reported):
  * completeness: rows vs. samples drawn, logged simulation failures
  * missing values, duplicate input rows
  * ranges: every input within its spec range; vg/vb equal the case values
  * KCL: |id+ig+is+ib| <= abs_tol + rel_tol * max(|id|,|ig|,|is|,|ib|)
  * resolution: count of currents below the numeric floors
    (|I| < 1e-15 A, where ngspice round-off dominates for terminals at ~VDD)
Plots (outputs/part_a/):
  trend_off_current_vs_temp.png, trend_off_current_vs_vth0.png,
  trend_gate_current_vs_toxe.png, kcl_residuals.png
Tables: outputs/part_a/data_check.csv, data_check.json

Run:  python -m layer1.scripts.validate_data
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from common_scripts.config import load_config, general_path, layer_path, vdd_range, width_range
from common_scripts.model_card import nominal_params
from common_scripts.plotting import DEVICE_COLOR, INK, INK_2, REF_LINE, apply_style, plt, save
from layer1.scripts.generate_samples import INPUT_COLS

CUR = ["id", "ig", "is", "ib"]
OUT = layer_path(1, "outputs")
RES_FLOOR = 1e-15


def load_case(case: str) -> pd.DataFrame:
    return pd.read_csv(layer_path(1, "data", "processed", f"{case}.csv"))


def decomposition_check(case: str) -> dict:
    """Terminal currents vs. sum of BSIM4 components (justifies the model form)."""
    from common_scripts.transistor_model import (COMPONENTS, components_from_spice,
                                             compose_terminals, sign_agreement)
    cfg = load_config()
    dev, lmin = cfg["part_a"]["cases"][case]["device"], cfg["technology"]["lmin"]
    raw = pd.read_csv(layer_path(1, "data", "raw", f"{case}_spice_raw.csv"))
    comp = components_from_spice(raw, dev)
    rec = compose_terminals({c: comp[c].to_numpy() for c in COMPONENTS}, raw, dev, lmin)
    out = {f"decomp_max_abs_resid_{k}_A": float(np.abs(rec[k] - raw[k]).max()) for k in CUR}
    out.update({f"sign_rule_{c}": v for c, v in sign_agreement(raw, dev, lmin).items()})
    return out


def check_case(case: str, df: pd.DataFrame) -> dict:
    cfg = load_config()
    c = cfg["part_a"]["cases"][case]
    tech, met = cfg["technology"], cfg["metrics"]
    nom = nominal_params()[c["device"]]
    tol = tech["process_tolerance"]
    eps = 1e-9

    fail_log = layer_path(1, "logs", f"part_a_{case}_failures.csv")
    n_fail_log = len(pd.read_csv(fail_log)) if fail_log.exists() else 0

    rng = {"vdd": vdd_range(), "temp": (tech["temp_min_c"], tech["temp_max_c"]), "w": width_range()}
    for p in tech["process_params"]:
        rng[p] = tuple(sorted((nom[p] * (1 - tol), nom[p] * (1 + tol))))
    out_of_range = {k: int(((df[k] < lo * (1 - eps) - eps * abs(lo)) |
                            (df[k] > hi * (1 + eps) + eps * abs(hi))).sum()) for k, (lo, hi) in rng.items()}
    # Vd, Vs in [0, VDD]; VG/VB fixed by case
    out_of_range["vd"] = int(((df.vd < 0) | (df.vd > df.vdd * (1 + eps))).sum())
    out_of_range["vs"] = int(((df.vs < 0) | (df.vs > df.vdd * (1 + eps))).sum())
    exp_vg = df.vdd if c["vg"] == "vdd" else 0.0
    exp_vb = df.vdd if c["vb"] == "vdd" else 0.0
    out_of_range["vg_case"] = int((np.abs(df.vg - exp_vg) > 1e-9).sum())
    out_of_range["vb_case"] = int((np.abs(df.vb - exp_vb) > 1e-9).sum())

    I = df[CUR].to_numpy()
    ksum = I.sum(axis=1)
    kmax = np.abs(I).max(axis=1)
    ktol = met["kcl_abs_tol_a"] + met["kcl_rel_tol"] * kmax
    viol = np.abs(ksum) > ktol
    df["kcl_sum"] = ksum
    df["kcl_rel"] = np.abs(ksum) / np.maximum(kmax, 1e-300)

    return {
        "case": case,
        "rows": len(df),
        "failed_simulations_logged": n_fail_log,
        "missing_values": int(df[INPUT_COLS + CUR].isna().sum().sum()),
        "duplicate_input_rows": int(df.duplicated(subset=INPUT_COLS).sum()),
        "out_of_range_total": int(sum(out_of_range.values())),
        "out_of_range": out_of_range,
        "kcl_abs_tol_A": met["kcl_abs_tol_a"], "kcl_rel_tol": met["kcl_rel_tol"],
        "kcl_violations": int(viol.sum()),
        "kcl_max_abs_sum_A": float(np.abs(ksum).max()),
        "kcl_median_abs_sum_A": float(np.median(np.abs(ksum))),
        "kcl_max_rel": float(df.kcl_rel.max()),
        **{f"n_abs_{k}_below_1e-15": int((np.abs(df[k]) < RES_FLOOR).sum()) for k in CUR},
        **{f"median_abs_{k}_A": float(np.median(np.abs(df[k]))) for k in CUR},
    }


def binned_median(x, y, bins=12):
    edges = np.linspace(x.min(), x.max(), bins + 1)
    idx = np.clip(np.digitize(x, edges) - 1, 0, bins - 1)
    cx, cy = [], []
    for b in range(bins):
        m = idx == b
        if m.sum() >= 10:
            cx.append(x[m].mean())
            cy.append(np.median(y[m]))
    return np.array(cx), np.array(cy)


def trend_plot(data, xcol, ycol, xlabel, ylabel, title, note, fname, xscale=1.0):
    """Faint: all samples. Solid: samples at the textbook bias (``sel`` mask). Line: binned median of sel."""
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, (case, df, sel, dev) in zip(axes, data):
        x = df[xcol].to_numpy() * xscale
        y = np.abs(df[ycol].to_numpy()) / (df["w"].to_numpy() * 1e6)   # A per um of width
        ok = y > 0
        ax.scatter(x[ok & ~sel], y[ok & ~sel], s=4, alpha=0.08, color=REF_LINE, linewidths=0,
                   label="all other samples")
        ax.scatter(x[ok & sel], y[ok & sel], s=9, alpha=0.6, color=DEVICE_COLOR[dev], linewidths=0,
                   label=f"textbook bias (n={int((ok & sel).sum())})")
        bx, by = binned_median(x[ok & sel], y[ok & sel], bins=10)
        ax.plot(bx, by, color=INK, lw=2, label="binned median")
        ax.set_yscale("log")
        ax.set_title(case.replace("_", " ").upper())
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.legend(loc="best", markerscale=2)
    fig.suptitle(title, fontsize=12, fontweight="bold", x=0.01, ha="left")
    fig.text(0.01, -0.03, note, fontsize=8, color=INK_2, ha="left")
    fig.tight_layout()
    save(fig, OUT / fname)


def main() -> None:
    apply_style()
    cfg = load_config()
    data, rows = {}, []
    for case in cfg["part_a"]["cases"]:
        df = load_case(case)
        rows.append({**check_case(case, df), **decomposition_check(case)})
        data[case] = df
    summary = pd.DataFrame([{k: v for k, v in r.items() if k != "out_of_range"} for r in rows])
    OUT.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUT / "data_check.csv", index=False)
    (OUT / "data_check.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    with pd.option_context("display.width", 200, "display.max_columns", 50):
        print(summary.T.to_string())

    # ---- trend plots. Highlighted subset = textbook bias: source within 5 % of its rail
    #      (NMOS Vs ~ 0, PMOS Vs ~ VDD) so Vgs ~ 0 for OFF, |Vgs| ~ VDD for ON; OFF also |Vds| > 0.3 V.
    def at_rail(df, dev):
        return (df.vs < 0.05 * df.vdd) if dev == "nmos" else (df.vs > 0.95 * df.vdd)

    def sel(case, off):
        df, dev = data[case], cfg["part_a"]["cases"][case]["device"]
        m = at_rail(df, dev)
        if off:
            m &= np.abs(df.vd - df.vs) > 0.3
        return (case, df, m.to_numpy(), dev)

    off = [sel("nmos_off", True), sel("pmos_off", True)]
    note = ("|ID| per um of width. Highlighted: source within 5 % of its rail (Vgs ~ 0) and |Vds| > 0.3 V, "
            "i.e. the textbook OFF-current bias. Grey: all other samples (source bias adds body effect and Vgs < 0).")
    trend_plot(off, "temp", "id", "Temperature (°C)", "|ID| / W  (A/µm)",
               "OFF current vs temperature", note, "trend_off_current_vs_temp.png")
    trend_plot(off, "vth0", "id", "vth0 (V)", "|ID| / W  (A/µm)",
               "OFF current vs vth0", note + "\nPMOS vth0 is negative: further right = smaller |vth0|.",
               "trend_off_current_vs_vth0.png")
    on = [sel("nmos_on", False), sel("pmos_on", False)]
    trend_plot(on, "toxe", "ig", "toxe (nm)", "|IG| / W  (A/µm)",
               "Gate tunnelling current vs oxide thickness",
               "ON devices. Highlighted: source within 5 % of its rail, so |Vgs| ~ VDD (full oxide field). "
               "Grey floor near 5e-16 A: simulator round-off (gate node at VDD).",
               "trend_gate_current_vs_toxe.png", xscale=1e9)

    # ---- KCL residual distribution
    fig, ax = plt.subplots(figsize=(7, 3.6))
    for i, case in enumerate(cfg["part_a"]["cases"]):
        r = np.abs(data[case][CUR].sum(axis=1)).to_numpy()
        r = np.maximum(r, 1e-30)
        ax.hist(np.log10(r), bins=60, histtype="step", lw=2,
                color=["#2a78d6", "#1baf7a", "#eb6834", "#eda100"][i], label=case)
    ax.axvline(np.log10(cfg["metrics"]["kcl_abs_tol_a"]), color=REF_LINE, ls="--", lw=1.2)
    ax.text(np.log10(cfg["metrics"]["kcl_abs_tol_a"]), ax.get_ylim()[1] * 0.95, " abs tol 1e-15 A",
            color=INK_2, fontsize=8, va="top")
    ax.set_xlabel("log10 |id + ig + is + ib|  (A)")
    ax.set_ylabel("samples")
    ax.set_title("KCL residual per sample", loc="left")
    ax.legend()
    save(fig, OUT / "kcl_residuals.png")
    print(f"\nplots + tables -> {OUT}")


if __name__ == "__main__":
    main()
