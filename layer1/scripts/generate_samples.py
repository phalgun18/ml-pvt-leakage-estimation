"""Part A step 1a: draw the random input samples for the four transistor cases.

Per spec Section 4, every parameter is drawn independently and uniformly:
VDD first (0.9 V +/-10 %), then Vd, Vs ~ U(0, VDD), W ~ U(1, 8)*Lmin,
T ~ U(-40, 125) C, and vth0/toxe/ndep/u0/xj ~ nominal +/-10 % using the NMOS
or PMOS nominals from the model card. VG and VB are fixed by the case.

Output: data/raw/<case>_samples.csv  (sample_id + 12 input columns)
Each case uses its own seed (sample_seed + case index) so cases are
independent and individually reproducible. Existing files are not
overwritten unless --force is given.

Run:  python -m layer1.scripts.generate_samples [--case nmos_off] [--force]
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from common_scripts.config import load_config, general_path, layer_path, vdd_range, width_range
from common_scripts.model_card import nominal_params

INPUT_COLS = ["vdd", "temp", "w", "vd", "vs", "vg", "vb", "vth0", "toxe", "ndep", "u0", "xj"]


def draw_samples(case: str, n: int, seed: int) -> pd.DataFrame:
    cfg = load_config()
    c = cfg["part_a"]["cases"][case]
    tech = cfg["technology"]
    tol = tech["process_tolerance"]
    rng = np.random.default_rng(seed)

    vdd = rng.uniform(*vdd_range(), n)                       # VDD first
    df = pd.DataFrame({"sample_id": np.arange(1, n + 1), "vdd": vdd})
    df["temp"] = rng.uniform(tech["temp_min_c"], tech["temp_max_c"], n)
    df["w"] = rng.uniform(*width_range(), n)
    df["vd"] = rng.uniform(0.0, 1.0, n) * vdd                # U(0, VDD)
    df["vs"] = rng.uniform(0.0, 1.0, n) * vdd                # U(0, VDD)
    df["vg"] = vdd if c["vg"] == "vdd" else 0.0
    df["vb"] = vdd if c["vb"] == "vdd" else 0.0
    nom = nominal_params()[c["device"]]
    for p in tech["process_params"]:
        lo, hi = sorted((nom[p] * (1 - tol), nom[p] * (1 + tol)))   # handles negative PMOS vth0
        df[p] = rng.uniform(lo, hi, n)
    return df[["sample_id"] + INPUT_COLS]


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=list(cfg["part_a"]["cases"]))
    ap.add_argument("--force", action="store_true", help="overwrite existing sample files")
    args = ap.parse_args()

    for i, case in enumerate(cfg["part_a"]["cases"]):
        if args.case and case != args.case:
            continue
        out = layer_path(1, "data", "raw", f"{case}_samples.csv")
        if out.exists() and not args.force:
            print(f"[skip] {out.name} exists (use --force to regenerate)")
            continue
        df = draw_samples(case, cfg["part_a"]["n_samples"], cfg["part_a"]["sample_seed"] + i)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False, float_format="%.12g")
        print(f"[ok] {case}: {len(df)} samples -> {out}")


if __name__ == "__main__":
    main()
