"""Part B step 3: SPICE reference for the 5 gates x all inputs x 200 corners.

Each (gate, input vector, corner) is one complete transistor-level netlist
(AND2/OR2 simulated as full gates, never as NAND/NOR + INV sums). Inputs are
exactly 0 or VDD. Recorded: supply / ground / input currents, every
internal node and the output voltage, plus BSIM4 per-device diagnostics
(used only to verify the leakage formula, never by the ML prediction).

These results are EVALUATION ONLY - never used for training.

Outputs
  data/raw/part_b_spice_<gate>.csv          one row per (corner, input vector)
  logs/part_b_failures.csv                  failed simulations (non-convergence or failed
                                            physical self-check, see gate_ml.spice_self_check)
  spice/gates/<gate>.sp (+ <gate>_card.pm)  runnable example netlist (corner 1, inputs 01/0)

Run:  python -m layer2.scripts.simulate_gates [--gate nand2] [--corner 17] [--workers 12]
"""
from __future__ import annotations

import argparse
import itertools
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd

from common_scripts.circuits import GATE_INPUTS, circuit_netlist, gate_devices, logic
from common_scripts.config import load_config, general_path, layer_path
from common_scripts.gate_ml import spice_self_check
from common_scripts.model_card import patch_card, read_card
from common_scripts.spice_runner import run_netlist
from layer2.scripts.generate_corners import corner_process, load_corners

RAW = lambda g: layer_path(2, "data", "raw", f"part_b_spice_{g}.csv")  # noqa: E731
FAIL = layer_path(2, "logs", "part_b_failures.csv")


def build(gate: str, bits: tuple[int, ...], c) -> tuple[str, list[str], list[str]]:
    ins = GATE_INPUTS[gate]
    devs, internal = gate_devices(gate, ins, "y")
    inputs = {n: (float(c["vdd"]) if bit else 0.0) for n, bit in zip(ins, bits)}
    title = f"{gate.upper()} inputs={''.join(map(str, bits))} corner={int(c['corner_id'])}"
    # initial guess = logic levels of the output and the NAND/NOR stage output
    vdd = float(c["vdd"])
    guess = {"y": vdd * logic(gate, bits)}
    if gate == "and2":
        guess["nand_out"] = vdd * logic("nand2", bits)
    if gate == "or2":
        guess["nor_out"] = vdd * logic("nor2", bits)
    net, outs = circuit_netlist(title, devs, inputs, vdd, float(c["temp"]),
                                float(c["wn"]), float(c["wp"]), probe_nodes=["y"] + internal,
                                nodeset=guess)
    return net, outs, internal


def sim(gate, bits, c, base_card):
    net, outs, internal = build(gate, bits, c)
    res = run_netlist(net, outs, extra_files={"card.pm": patch_card(base_card, corner_process(c))})
    row = {"corner_id": int(c["corner_id"]), "gate": gate, "inputs": "".join(map(str, bits)),
           "expected_out": logic(gate, bits)}
    return row, res


def write_example(gate, c, base_card):
    d = layer_path(2, "spice")
    d.mkdir(parents=True, exist_ok=True)
    bits = (0, 1) if len(GATE_INPUTS[gate]) == 2 else (0,)
    net, _, _ = build(gate, bits, c)
    (d / f"{gate}_card.pm").write_text(patch_card(base_card, corner_process(c)), encoding="utf-8")
    (d / f"{gate}.sp").write_text(net.replace('"card.pm"', f'"{gate}_card.pm"'), encoding="utf-8")


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", choices=cfg["part_b"]["gates"])
    ap.add_argument("--corner", type=int)
    ap.add_argument("--workers", type=int, default=cfg["spice"]["workers"])
    args = ap.parse_args()
    corners = load_corners()
    if args.corner:
        corners = corners[corners.corner_id == args.corner]
    base_card = read_card()
    for gate in cfg["part_b"]["gates"]:
        if args.gate and gate != args.gate:
            continue
        write_example(gate, load_corners().iloc[0], base_card)
        done = set()
        if RAW(gate).exists():
            old = pd.read_csv(RAW(gate), dtype={"inputs": str}, usecols=["corner_id", "inputs"])
            done = set(zip(old.corner_id, old.inputs))
        vecs = list(itertools.product((0, 1), repeat=len(GATE_INPUTS[gate])))
        jobs = [(bits, c) for _, c in corners.iterrows() for bits in vecs
                if (int(c.corner_id), "".join(map(str, bits))) not in done]
        print(f"[{gate}] to run: {len(jobs)} (already done: {len(done)})", flush=True)
        ok, fail = [], []
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(sim, gate, bits, c, base_card) for bits, c in jobs]
            for fut in as_completed(futs):
                row, res = fut.result()
                if res.ok:
                    ok.append({**row, **res.values})
                else:
                    fail.append({**row, "time": datetime.now().isoformat(timespec="seconds"),
                                 "error": res.error})
        if ok:
            df = pd.DataFrame(ok).sort_values(["corner_id", "inputs"]).reset_index(drop=True)
            # physical self-consistency of the converged operating point (see gate_ml)
            sims = df.merge(load_corners(), on="corner_id", how="left")
            for k, n in enumerate(GATE_INPUTS[gate]):
                sims[f"in_{n}"] = sims["inputs"].str[k].astype(int)
            devs, _ = gate_devices(gate, GATE_INPUTS[gate], "y")
            chk = spice_self_check(sims, devs, GATE_INPUTS[gate])
            df = pd.concat([df, chk], axis=1)
            for _, r in df[~df.self_check_ok].iterrows():
                fail.append({"corner_id": r.corner_id, "gate": gate, "inputs": r.inputs,
                             "expected_out": r.expected_out,
                             "time": datetime.now().isoformat(timespec="seconds"),
                             "error": f"self-check failed: |sum(device I) - I_vdd| = "
                                      f"{r.self_check_abs_diff_A:.2e} A (I_vdd {r.i_vdd:.2e}), "
                                      f"rail overshoot {r.rail_overshoot_V:.1e} V"})
            df = df[df.self_check_ok]
            ok = df.to_dict("records")
            df.to_csv(RAW(gate), mode="a", header=not RAW(gate).exists(), index=False,
                      float_format="%.15g")
        if fail:
            pd.DataFrame(fail).to_csv(FAIL, mode="a", header=not FAIL.exists(), index=False)
        print(f"[{gate}] ok={len(ok)} failed={len(fail)} ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
