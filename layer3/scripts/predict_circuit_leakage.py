"""Part C step 7: hierarchical ML leakage of the 3-bit CLA.

For each corner and input vector: logic-simulate the CLA, read every gate's
input bits (in the gate's own input order), take that gate's ML leakage from
the Part-B gate models (which call the transistor models) at the same corner,
and sum over the 39 gates. As the spec states, gate inputs are assumed to be
exactly 0 / VDD and inter-gate loading is ignored.

Loading-aware variant (ml_leak_loaded, reported alongside, NOT the spec method):
  in the real circuit, gate-tunnelling current into an input held at logic 1 is
  supplied by the DRIVING gate from VDD, whereas in the isolated Part-B gate it
  came from the ideal input source (outside I_VDD). ml_leak_loaded adds, for every
  gate input at logic 1 that is driven by another gate (not a primary input), the
  ML input current of that gate (from the same Part-B transistor-model evaluation).
  spice_gate_sum_loaded is the same construction with the SPICE gate results.

Also recorded (diagnostic, NOT the ML prediction):
  spice_gate_sum = sum of the isolated-gate SPICE leakages from Part B.
  ML vs spice_gate_sum isolates the ML error; spice_gate_sum vs the full
  netlist isolates the hierarchy / loading error.

Output: data/results/part_c_results.csv
Run:    python -m layer3.scripts.predict_circuit_leakage
"""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from common_scripts.cla import INPUTS, cla3_gates, evaluate, vector_label, vectors
from common_scripts.config import load_config, general_path, layer_path
from layer2.scripts.generate_corners import load_corners


def main() -> None:
    cfg = load_config()
    gates = cla3_gates()
    pb = pd.read_csv(layer_path(2, "data", "results", "part_b_results.csv"), dtype={"inputs": str})
    ml = pb.set_index(["gate", "inputs", "corner_id"])["ml_leak"].to_dict()
    sg = pb.set_index(["gate", "inputs", "corner_id"])["spice_leak"].to_dict()
    pbi = pb.set_index(["gate", "inputs", "corner_id"])
    ml_in = {n: pbi[f"ml_in_{n}"].to_dict() for n in ("a", "b")}
    sp_in = {n: pbi[f"i_in_{n}"].to_dict() for n in ("a", "b")}
    sp = pd.read_csv(layer_path(3, "data", "raw", "part_c_spice_summary.csv"))
    sp_leak = sp.set_index(["corner_id", "vector"])["i_vdd"].to_dict()
    corners = load_corners()

    rows = []
    for v in vectors(cfg["part_c"]["cin"]):
        val = evaluate(gates, v)
        calls = [(g.type, "".join(str(val[i]) for i in g.ins)) for g in gates]
        # (gate type, input bits, Part-B input name) for inputs at 1 driven by another gate
        loads = [(g.type, b, "ab"[k]) for g, (_, b) in zip(gates, calls)
                 for k, node in enumerate(g.ins) if val[node] == 1 and node not in INPUTS]
        mix = Counter(f"{t}_{b}" for t, b in calls)
        for cid in corners.corner_id:
            key = (int(cid), vector_label(v))
            rows.append({"corner_id": int(cid), "vector": vector_label(v),
                         **{f"in_{n}": v[n] for n in INPUTS},
                         "spice_leak": sp_leak.get(key, np.nan),
                         "ml_leak": sum(ml[(t, b, cid)] for t, b in calls),
                         "spice_gate_sum": sum(sg[(t, b, cid)] for t, b in calls),
                         "ml_load": sum(ml_in[n][(t, b, cid)] for t, b, n in loads),
                         "spice_load": sum(sp_in[n][(t, b, cid)] for t, b, n in loads),
                         "n_loaded_inputs": len(loads),
                         "gate_calls": ";".join(f"{k}x{n}" for k, n in sorted(mix.items()))})
    res = pd.DataFrame(rows).merge(corners, on="corner_id", how="left")
    res["ml_leak_loaded"] = res.ml_leak + res.ml_load
    res["spice_gate_sum_loaded"] = res.spice_gate_sum + res.spice_load
    n_missing = int(res.spice_leak.isna().sum())
    res = res.dropna(subset=["spice_leak"])
    out = layer_path(3, "data", "results", "part_c_results.csv")
    res.to_csv(out, index=False, float_format="%.10g")
    print(f"rows: {len(res)}  (SPICE reference missing for {n_missing}, see logs/part_c_failures.csv)")


if __name__ == "__main__":
    main()
