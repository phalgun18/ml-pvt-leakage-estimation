"""Part A step 1b: simulate every sample in ngspice (resumable, parallel).

For each sample: patch a private copy of the model card (only the case's
device block, only vth0/toxe/ndep/u0/xj), build the single-FET netlist,
run ngspice, validate, and record the 4 terminal currents (+ diagnostic
BSIM4 internals).

Outputs
  data/raw/<case>_spice_raw.csv     sample_id, inputs, id/ig/is/ib, x_* diagnostics
                                    (appended in chunks -> safe to interrupt)
  logs/part_a_<case>_failures.csv   failed samples with the error message
  data/processed/<case>.csv         deliverable: exactly the 16 spec columns,
                                    written once all samples are done
  spice/transistor/<case>.sp (+ <case>_card.pm)  runnable example netlist

Re-running skips samples already in the raw file; failed samples are retried.

Run:  python -m layer1.scripts.generate_spice_data [--case pmos_off] [--limit 50] [--workers 12]
"""
from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd

from common_scripts.config import load_config, general_path, layer_path
from common_scripts.model_card import patch_card, read_card
from common_scripts.netlists import CARD_NAME, DIAG_OUTPUTS, TRANSISTOR_OUTPUTS, transistor_netlist
from common_scripts.spice_runner import run_netlist
from layer1.scripts.generate_samples import INPUT_COLS

CURRENT_COLS = list(TRANSISTOR_OUTPUTS)
DIAG_COLS = list(DIAG_OUTPUTS)
DELIVERABLE_COLS = INPUT_COLS + CURRENT_COLS
CHUNK = 500


def simulate_row(case: str, device: str, row: dict, base_card: str) -> dict:
    params = {p: row[p] for p in load_config()["technology"]["process_params"]}
    card = patch_card(base_card, {device: params})
    res = run_netlist(transistor_netlist(case, device, row),
                      CURRENT_COLS + DIAG_COLS, extra_files={CARD_NAME: card})
    return {"sample_id": row["sample_id"], "ok": res.ok, "error": res.error, **res.values}


def write_example(case: str, device: str, row: dict, base_card: str) -> None:
    d = layer_path(1, "spice")
    d.mkdir(parents=True, exist_ok=True)
    card_name = f"{case}_card.pm"
    params = {p: row[p] for p in load_config()["technology"]["process_params"]}
    (d / card_name).write_text(patch_card(base_card, {device: params}), encoding="utf-8")
    (d / f"{case}.sp").write_text(
        f"* Example = sample_id {int(row['sample_id'])} of {case} "
        f"(process params in {card_name})\n"
        + transistor_netlist(case, device, row, card_name=card_name), encoding="utf-8")


def run_case(case: str, limit: int | None, workers: int) -> dict:
    cfg = load_config()
    device = cfg["part_a"]["cases"][case]["device"]
    samples = pd.read_csv(layer_path(1, "data", "raw", f"{case}_samples.csv"))
    if limit:
        samples = samples.head(limit)
    raw_path = layer_path(1, "data", "raw", f"{case}_spice_raw.csv")
    fail_path = layer_path(1, "logs", f"part_a_{case}_failures.csv")
    base_card = read_card()

    done = set(pd.read_csv(raw_path, usecols=["sample_id"])["sample_id"]) if raw_path.exists() else set()
    todo = samples[~samples["sample_id"].isin(done)]
    write_example(case, device, samples.iloc[0].to_dict(), base_card)
    print(f"\n[{case}] total={len(samples)} already_done={len(done & set(samples.sample_id))} "
          f"to_run={len(todo)} workers={workers}")

    n_ok = n_fail = 0
    t0 = time.time()
    ok_buf, fail_buf = [], []

    def flush():
        nonlocal ok_buf, fail_buf
        if ok_buf:
            out = pd.DataFrame(ok_buf)[["sample_id"] + INPUT_COLS + CURRENT_COLS + DIAG_COLS]
            out.sort_values("sample_id").to_csv(raw_path, mode="a", header=not raw_path.exists(),
                                                index=False, float_format="%.15g")
            ok_buf = []
        if fail_buf:
            fail_path.parent.mkdir(exist_ok=True)
            pd.DataFrame(fail_buf).to_csv(fail_path, mode="a", header=not fail_path.exists(), index=False)
            fail_buf = []

    rows = {int(r["sample_id"]): r for r in todo.to_dict("records")}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(simulate_row, case, device, r, base_card): sid for sid, r in rows.items()}
        for k, fut in enumerate(as_completed(futs), 1):
            sid = futs[fut]
            try:
                r = fut.result()
            except Exception as e:  # noqa: BLE001  (patching/IO errors are logged, not hidden)
                r = {"sample_id": sid, "ok": False, "error": f"python exception: {e!r}"}
            if r["ok"]:
                n_ok += 1
                ok_buf.append({**rows[sid], **{c: r[c] for c in CURRENT_COLS + DIAG_COLS}})
            else:
                n_fail += 1
                fail_buf.append({"sample_id": sid, "time": datetime.now().isoformat(timespec="seconds"),
                                 "error": r["error"]})
            if k % CHUNK == 0 or k == len(futs):
                flush()
                rate = k / (time.time() - t0)
                print(f"  [{case}] {k}/{len(futs)} ok={n_ok} fail={n_fail} ({rate:.0f} sims/s)", flush=True)
    flush()

    # deliverable CSV only once every sample of the full run succeeded
    raw = pd.read_csv(raw_path) if raw_path.exists() else pd.DataFrame()
    missing = sorted(set(samples.sample_id) - set(raw.get("sample_id", [])))
    status = {"case": case, "ran_ok": n_ok, "ran_failed": n_fail,
              "rows_in_raw": len(raw), "missing": len(missing)}
    if not missing and not limit:
        raw = raw.drop_duplicates("sample_id").sort_values("sample_id")
        out = layer_path(1, "data", "processed", f"{case}.csv")
        out.parent.mkdir(parents=True, exist_ok=True)
        raw[DELIVERABLE_COLS].to_csv(out, index=False, float_format="%.15g")
        status["deliverable"] = str(out)
    print(f"[{case}] {status}")
    return status


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=list(cfg["part_a"]["cases"]))
    ap.add_argument("--limit", type=int, help="only the first N samples (testing)")
    ap.add_argument("--workers", type=int, default=cfg["spice"]["workers"])
    args = ap.parse_args()
    for case in cfg["part_a"]["cases"]:
        if not args.case or case == args.case:
            run_case(case, args.limit, args.workers)


if __name__ == "__main__":
    main()
