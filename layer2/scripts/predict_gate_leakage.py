"""Part B step 4: ML leakage prediction for every gate / input / corner.

Uses ONLY the four Part-A transistor models plus the SPICE-recorded internal
node and output voltages (spec step 4). No gate-level model is trained.

Outputs
  data/results/part_b_results.csv            one row per (gate, inputs, corner):
        corner + inputs, SPICE leakage, ML leakage (ml_leak = KCL-closed, final;
        ml_leak_direct = plain sum at the VDD rail), SPICE node voltages
        (which are also the voltages fed to the ML), oracle leakage
  data/results/part_b_device_predictions.csv per-device terminal voltages, state, ML currents
  outputs/part_b/oracle_check.csv            formula check vs SPICE

Run:  python -m layer2.scripts.predict_gate_leakage
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common_scripts.circuits import GATE_INPUTS, gate_devices
from common_scripts.config import load_config, general_path, layer_path
from common_scripts.gate_ml import (device_table, kcl_closed_rail_current, oracle_device_currents,
                                predict_device_currents, rail_current)
from layer2.scripts.generate_corners import load_corners

OUT = layer_path(2, "outputs")
RES = layer_path(2, "data", "results")


def main() -> None:
    cfg = load_config()
    corners = load_corners()
    all_rows, all_dev, oracle_rows = [], [], []
    for gate in cfg["part_b"]["gates"]:
        sp = pd.read_csv(layer_path(2, "data", "raw", f"part_b_spice_{gate}.csv"), dtype={"inputs": str})
        sims = sp.merge(corners, on="corner_id", how="left").reset_index(drop=True)
        ins = GATE_INPUTS[gate]
        for k, n in enumerate(ins):
            sims[f"in_{n}"] = sims["inputs"].str[k].astype(int)
        devs, internal = gate_devices(gate, ins, "y")

        tab = device_table(sims, devs, ins)
        ml = predict_device_currents(tab)
        sims["ml_leak_direct"] = rail_current(ml, "vdd").reindex(sims.index).to_numpy()
        sims["ml_leak"] = kcl_closed_rail_current(ml, ins).reindex(sims.index).to_numpy()
        # ML current drawn from each input (gate tunnelling into the input node); used by
        # the loading-aware hierarchical CLA estimate in Part C
        for n in ins:
            sims[f"ml_in_{n}"] = rail_current(ml, n).reindex(sims.index).to_numpy()
        orc = oracle_device_currents(tab, sims)
        sims["oracle_leak"] = rail_current(orc, "vdd").reindex(sims.index).to_numpy()
        sims["spice_leak"] = sims["i_vdd"]

        rel = np.abs(sims.oracle_leak / sims.spice_leak - 1)
        oracle_rows.append({"gate": gate, "n": len(sims), "oracle_max_rel_diff": rel.max(),
                            "oracle_median_rel_diff": rel.median()})
        ml["gate"], ml["corner_id"] = gate, sims.loc[ml.sim_idx, "corner_id"].to_numpy()
        ml["inputs"] = sims.loc[ml.sim_idx, "inputs"].to_numpy()
        all_dev.append(ml.drop(columns=["sim_idx"]))

        keep = (["corner_id", "gate", "inputs", "expected_out", "vdd", "temp", "wn", "wp"]
                + [c for c in corners.columns if c[:2] in ("n_", "p_")]
                + ["spice_leak", "ml_leak", "ml_leak_direct", "oracle_leak", "i_gnd"]
                + [c for c in sims.columns if c.startswith(("i_in_", "ml_in_", "v_"))])
        all_rows.append(sims[keep])
        print(f"[{gate}] sims={len(sims)}  oracle max rel diff={rel.max():.2e}")

    res = pd.concat(all_rows, ignore_index=True)
    res["case"] = res.gate.str.upper() + " " + res.inputs
    RES.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    res.to_csv(RES / "part_b_results.csv", index=False, float_format="%.10g")
    pd.concat(all_dev, ignore_index=True).to_csv(RES / "part_b_device_predictions.csv",
                                                 index=False, float_format="%.10g")
    pd.DataFrame(oracle_rows).to_csv(OUT / "oracle_check.csv", index=False)
    fails = layer_path(2, "logs", "part_b_failures.csv")
    nf = len(pd.read_csv(fails)) if fails.exists() else 0
    print(f"rows: {len(res)} (+ {nf} SPICE non-convergent, excluded, see logs/part_b_failures.csv)")


if __name__ == "__main__":
    main()
