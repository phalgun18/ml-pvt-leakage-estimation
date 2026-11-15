"""Project configuration and path helpers.

Repository layout:
  project_config.json, 32nm_LP.pm   general files at the repository root
  common_scripts/                   shared Python modules (this package) + setup_check.py
  report/                           technical report and the code that builds it
  layer1/scripts/                   Part A - transistor data + models   (data in layer1/...)
  layer2/scripts/                   Part B - gate-level validation      (data in layer2/...)
  layer3/scripts/                   Part C - 3-bit CLA validation       (data in layer3/...)

All scripts are run as modules from the repository root, e.g.
``python -m layer1.scripts.generate_samples``.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]         # .../ml-pvt-leakage-estimation
GENERAL_ROOT = REPO_ROOT                                # general files live at the root
CONFIG_FILE = REPO_ROOT / "project_config.json"


@lru_cache(maxsize=1)
def load_config() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def general_path(*parts: str) -> Path:
    """Path of a general (non-layer) file, relative to the repository root."""
    return GENERAL_ROOT.joinpath(*parts)


def layer_path(layer: int, *parts: str) -> Path:
    """Path inside layer1/ (Part A), layer2/ (Part B) or layer3/ (Part C)."""
    return REPO_ROOT.joinpath(f"layer{layer}", *parts)


def config_path(key: str) -> Path:
    """Resolve an entry of ``config['paths']`` (relative to the repository root)."""
    p = Path(load_config()["paths"][key])
    return p if p.is_absolute() else GENERAL_ROOT / p


def vdd_range() -> tuple[float, float]:
    t = load_config()["technology"]
    return t["vdd_nominal"] * (1 - t["vdd_tolerance"]), t["vdd_nominal"] * (1 + t["vdd_tolerance"])


def width_range() -> tuple[float, float]:
    t = load_config()["technology"]
    return t["w_min_mult"] * t["lmin"], t["w_max_mult"] * t["lmin"]
