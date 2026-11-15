"""Part B error analysis: which transistor model causes the gate-level error?

Ablation: for each of the 4 models (nmos_on, nmos_off, pmos_on, pmos_off),
replace the ML currents of every device using that model by SPICE's exact
per-device currents (BSIM4 diagnostics), recompute the KCL-closed leakage,
and measure the remaining gate error. The drop in error = that model's share.
Also records where gate devices sit relative to the training distribution.

Outputs: outputs/part_b/error_attribution.csv, outputs/part_b/operating_point_coverage.csv
Run:     python -m layer2.scripts.error_attribution
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common_scripts.circuits import GATE_INPUTS, gate_devices
from common_scripts.config import load_config, general_path, layer_path
from common_scripts.gate_ml import (device_table, kcl_closed_rail_current, oracle_device_currents,
                                predict_device_currents)
from common_scripts.transistor_model import TERMINALS
from layer2.scripts.generate_corners import load_corners

OUT = layer_path(2, "outputs")
CASES = ["nmos_on", "nmos_off", "pmos_on", "pmos_off"]


def stats(pred, ref):
    e = np.abs(pred / ref - 1) * 100
    return float(np.median(e)), float(np.percentile(e, 95)), float(np.mean(e))


def main() -> None:
    cfg = load_config()
    corners = load_corners()
    rows, cov = [], []
    for gate in cfg["part_b"]["gates"]:
        sp = pd.read_csv(layer_path(2, "data", "raw", f"part_b_spice_{gate}.csv"), dtype={"inputs": str})
        sims = sp.merge(corners, on="corner_id").reset_index(drop=True)
        ins = GATE_INPUTS[gate]
        for k, n in enumerate(ins):
            sims[f"in_{n}"] = sims.inputs.str[k].astype(int)
        devs, _ = gate_devices(gate, ins, "y")
        tab = device_table(sims, devs, ins)
        ml = predict_device_currents(tab)
        orc = oracle_device_currents(tab, sims)
        t = np.where(orc.type == "nmos", 1, -1)
        m = np.where(t * orc.vd >= t * orc.vs, 1, -1)
        orc["ich_d"] = t * m * np.array([sims.at[i, f"d_{d}_id"] for i, d in zip(orc.sim_idx, orc.device)])
        ref = sims.i_vdd.to_numpy()
        variants = {"all ML": ml}
        for c in CASES:
            v = ml.copy()
            sel = v.case == c
            v.loc[sel, TERMINALS + ["ich_d"]] = orc.loc[sel, TERMINALS + ["ich_d"]].to_numpy()
            variants[f"{c} -> SPICE"] = v
        for name, v in variants.items():
            leak = kcl_closed_rail_current(v, ins).reindex(sims.index).to_numpy()
            for inp, idx in sims.groupby("inputs").groups.items():
                md, p95, mean = stats(leak[idx], ref[idx])
                rows.append({"gate": gate.upper(), "inputs": inp, "variant": name,
                             "median_err_pct": md, "p95_err_pct": p95, "mean_err_pct": mean})
        # operating-point coverage: distance of (vd, vs) from the nearest rail corner
        tab["vd_n"], tab["vs_n"] = tab.vd / tab.vdd, tab.vs / tab.vdd
        tab["gate"] = gate.upper()
        cov.append(tab[["gate", "device", "case", "vd_n", "vs_n"]])
    res = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT / "error_attribution.csv", index=False)
    piv = res.pivot_table(index=["gate", "inputs"], columns="variant", values="mean_err_pct", sort=False)
    piv = piv[["all ML"] + [f"{c} -> SPICE" for c in CASES]]
    with pd.option_context("display.width", 200, "display.float_format", "{:.2f}".format):
        print("MEAN gate error (%) when one model is replaced by exact SPICE currents\n", piv.to_string())

    # training-set density near each gate operating point (fraction of the case's 10k samples
    # whose (vd, vs) lie within +/-2 % of VDD of the gate device's (vd, vs))
    c = pd.concat(cov, ignore_index=True)
    out = []
    for case in CASES:
        tr = pd.read_csv(layer_path(1, "data", "processed", f"{case}.csv"))
        tvd, tvs = (tr.vd / tr.vdd).to_numpy(), (tr.vs / tr.vdd).to_numpy()
        g = c[c.case == case]
        pts = g[["vd_n", "vs_n"]].drop_duplicates().round(3).drop_duplicates()
        n_near = [int(np.sum((np.abs(tvd - a) < 0.02) & (np.abs(tvs - b) < 0.02))) for a, b in pts.to_numpy()]
        out.append({"case": case, "gate_device_instances": len(g),
                    "median_training_samples_within_2pct": float(np.median(n_near)),
                    "min_training_samples_within_2pct": int(np.min(n_near))})
    pd.DataFrame(out).to_csv(OUT / "operating_point_coverage.csv", index=False)
    print("\n", pd.DataFrame(out).to_string(index=False))


if __name__ == "__main__":
    main()
