"""Part C step 6: SPICE reference for the complete 3-bit CLA netlist.

64 input vectors (A, B in 0..7, carry-in = 0) x the same 200 corners as Part B
= 12,800 simulations of ONE flat 186-transistor netlist. Leakage = current
delivered by the VDD supply. Each result must pass:
  * ngspice convergence + output parsing (spice_runner),
  * the physical self-check (sum of the devices' own BSIM4 currents into VDD
    equals the supply current, no node beyond the rails),
  * a logic check: s2 s1 s0 and c3 at the expected logic levels.

Outputs
  data/raw/part_c_spice.csv                  FULL record per (corner, vector), incl. per-device
                                             BSIM4 diagnostics (~370 MB; git-ignored, regenerable)
  data/raw/part_c_spice_summary.csv          compact record (tracked): corner, vector, inputs,
                                             supply/ground/input currents, gate-output voltages,
                                             self-check results. Used by prediction and resume.
  logs/part_c_failures.csv                   failures (if any)
  spice/circuits/cla3.sp (+ cla3_card.pm)    runnable example (corner 1, A=5, B=3)

Run:  python -m layer3.scripts.simulate_test_circuit [--corner 17] [--workers 12]
"""
from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pandas as pd

from common_scripts.circuits import circuit_netlist
from common_scripts.cla import (INPUTS, OUTPUTS, cla3_devices, cla3_gates, evaluate, internal_logic_levels,
                            vector_label, vectors)
from common_scripts.config import load_config, general_path, layer_path
from common_scripts.gate_ml import spice_self_check
from common_scripts.model_card import patch_card, read_card
from common_scripts.spice_runner import run_netlist
from layer2.scripts.generate_corners import corner_process, load_corners

RAW = layer_path(3, "data", "raw", "part_c_spice.csv")
SUMMARY = layer_path(3, "data", "raw", "part_c_spice_summary.csv")
FAIL = layer_path(3, "logs", "part_c_failures.csv")
GATES = cla3_gates()
DEVICES, NODES = cla3_devices(GATES)
GATE_OUTPUTS = [g.out for g in GATES]


def summary_columns(df: pd.DataFrame) -> list[str]:
    keep = ["corner_id", "vector"] + [f"in_{n}" for n in INPUTS] + ["i_vdd", "i_gnd"]
    keep += [c for c in df.columns if c.startswith("i_in_")] + [f"v_{n}" for n in GATE_OUTPUTS]
    keep += ["self_check_abs_diff_A", "rail_overshoot_V", "self_check_ok", "logic_ok"]
    return [c for c in keep if c in df.columns]


def build(v: dict[str, int], c, card_name: str = "card.pm") -> tuple[str, list[str]]:
    vdd = float(c["vdd"])
    lv = internal_logic_levels(GATES, evaluate(GATES, v))
    return circuit_netlist(f"3-bit CLA {vector_label(v)} cin={v['c0']} corner={int(c['corner_id'])}",
                           DEVICES, {n: vdd * v[n] for n in INPUTS}, vdd, float(c["temp"]),
                           float(c["wn"]), float(c["wp"]), probe_nodes=NODES, card_name=card_name,
                           nodeset={n: vdd * b for n, b in lv.items()})


def sim(v, c, card_text):
    net, outs = build(v, c)
    res = run_netlist(net, outs, extra_files={"card.pm": card_text})
    return {"corner_id": int(c["corner_id"]), "vector": vector_label(v), **{f"in_{n}": v[n] for n in INPUTS}}, res


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--corner", type=int)
    ap.add_argument("--workers", type=int, default=cfg["spice"]["workers"])
    args = ap.parse_args()
    corners = load_corners()
    if args.corner:
        corners = corners[corners.corner_id == args.corner]
    base = read_card()
    vecs = vectors(cfg["part_c"]["cin"])

    ex_dir = layer_path(3, "spice")
    ex_dir.mkdir(parents=True, exist_ok=True)
    c1 = load_corners().iloc[0]
    ex_v = next(v for v in vecs if vector_label(v) == "A5_B3")
    (ex_dir / "cla3_card.pm").write_text(patch_card(base, corner_process(c1)), encoding="utf-8")
    (ex_dir / "cla3.sp").write_text(build(ex_v, c1, card_name="cla3_card.pm")[0], encoding="utf-8")

    done = set()
    if SUMMARY.exists():
        old = pd.read_csv(SUMMARY, usecols=["corner_id", "vector"])
        done = set(zip(old.corner_id, old.vector))
    t0, n_ok, n_fail = time.time(), 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for _, c in corners.iterrows():
            todo = [v for v in vecs if (int(c.corner_id), vector_label(v)) not in done]
            if not todo:
                continue
            card = patch_card(base, corner_process(c))
            results = list(ex.map(lambda v: sim(v, c, card), todo))
            ok = [{**row, **res.values} for row, res in results if res.ok]
            fail = [{**row, "error": res.error} for row, res in results if not res.ok]
            if ok:
                df = pd.DataFrame(ok)
                sims = df.merge(corners[corners.corner_id == c.corner_id], on="corner_id", how="left")
                chk = spice_self_check(sims, DEVICES, INPUTS)
                vdd = float(c["vdd"])
                exp = [evaluate(GATES, {n: r[f"in_{n}"] for n in INPUTS}) for _, r in df.iterrows()]
                logic_ok = pd.Series([all(int(r[f"v_{o}"] > vdd / 2) == e[o] for o in OUTPUTS)
                                      for (_, r), e in zip(df.iterrows(), exp)])
                df = pd.concat([df, chk], axis=1)
                df["logic_ok"] = logic_ok.to_numpy()
                bad = ~(df.self_check_ok & df.logic_ok)
                for _, r in df[bad].iterrows():
                    fail.append({"corner_id": r.corner_id, "vector": r.vector,
                                 "error": f"self_check_ok={r.self_check_ok} logic_ok={r.logic_ok} "
                                          f"|dI|={r.self_check_abs_diff_A:.2e} overshoot={r.rail_overshoot_V:.1e}"})
                df = df[~bad]
                df.to_csv(RAW, mode="a", header=not RAW.exists(), index=False, float_format="%.15g")
                df[summary_columns(df)].to_csv(SUMMARY, mode="a", header=not SUMMARY.exists(), index=False,
                                               float_format="%.15g")
                n_ok += len(df)
            if fail:
                pd.DataFrame([{**f, "time": datetime.now().isoformat(timespec="seconds")} for f in fail]) \
                    .to_csv(FAIL, mode="a", header=not FAIL.exists(), index=False)
                n_fail += len(fail)
            if int(c.corner_id) % 20 == 0:
                print(f"  corner {int(c.corner_id)}: ok={n_ok} failed={n_fail} "
                      f"({time.time() - t0:.0f}s)", flush=True)
    print(f"[cla3] ok={n_ok} failed={n_fail} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
