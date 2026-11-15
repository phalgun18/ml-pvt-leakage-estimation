"""Part B step 0: draw the 200 PVT corners (shared by Part B and Part C).

A corner = one draw of VDD, temperature, NMOS width, PMOS width, and the five
process parameters, drawn separately for NMOS (n_*) and PMOS (p_*). Within a
circuit, all NMOS share the n_* draw and all PMOS share the p_* draw.
Distributions follow spec Section 4 (uniform, nominal +/-10 %, VDD first).

Output: data/raw/corners.csv  (not overwritten unless --force)

Run:  python -m layer2.scripts.generate_corners [--force]
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from common_scripts.config import load_config, general_path, layer_path, vdd_range, width_range
from common_scripts.model_card import nominal_params

PATH = layer_path(2, "data", "raw", "corners.csv")


def draw_corners(n: int, seed: int) -> pd.DataFrame:
    tech = load_config()["technology"]
    tol = tech["process_tolerance"]
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({"corner_id": np.arange(1, n + 1)})
    df["vdd"] = rng.uniform(*vdd_range(), n)
    df["temp"] = rng.uniform(tech["temp_min_c"], tech["temp_max_c"], n)
    df["wn"] = rng.uniform(*width_range(), n)
    df["wp"] = rng.uniform(*width_range(), n)
    nom = nominal_params()
    for dev, pre in (("nmos", "n_"), ("pmos", "p_")):
        for p in tech["process_params"]:
            lo, hi = sorted((nom[dev][p] * (1 - tol), nom[dev][p] * (1 + tol)))
            df[pre + p] = rng.uniform(lo, hi, n)
    return df


def load_corners() -> pd.DataFrame:
    return pd.read_csv(PATH)


def corner_process(row) -> dict[str, dict[str, float]]:
    params = load_config()["technology"]["process_params"]
    return {"nmos": {p: float(row[f"n_{p}"]) for p in params},
            "pmos": {p: float(row[f"p_{p}"]) for p in params}}


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if PATH.exists() and not args.force:
        print(f"[skip] {PATH} exists (use --force)")
        return
    df = draw_corners(cfg["part_b"]["n_corners"], cfg["part_b"]["corner_seed"])
    PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(PATH, index=False, float_format="%.12g")
    print(f"[ok] {len(df)} corners -> {PATH}")


if __name__ == "__main__":
    main()
