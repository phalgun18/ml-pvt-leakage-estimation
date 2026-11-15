"""Read and patch the BSIM4 model card (32nm_LP.pm).

The card holds two blocks::

    .model  nmos  nmos  level = 54
    +version = 4.0 ... vth0 = 0.63 ...
    .model  pmos  pmos  level = 54
    ...

Rules (from the project specification):
* the original card is never modified; each simulation uses a patched copy;
* only the five process parameters (vth0, toxe, ndep, u0, xj) are changed;
* NMOS and PMOS values are patched independently, inside their own block.

Every patch is verified by parsing the patched text back.
"""
from __future__ import annotations

import re
from pathlib import Path

from .config import config_path, load_config

_MODEL_RE = r"^\s*\.model\s+{name}\s+"
_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"


def read_card(path: Path | None = None) -> str:
    return Path(path or config_path("model_card")).read_text(encoding="utf-8")


def _block_span(text: str, model_name: str) -> tuple[int, int]:
    m = re.search(_MODEL_RE.format(name=re.escape(model_name)), text, re.I | re.M)
    if not m:
        raise ValueError(f"model '{model_name}' not found in model card")
    nxt = re.search(r"^\s*\.model\s+", text[m.end():], re.I | re.M)
    return m.start(), (m.end() + nxt.start()) if nxt else len(text)


def _param_re(param: str) -> re.Pattern:
    # word boundary + '=' so 'xj' does not match 'xjbvs', etc.
    return re.compile(rf"(?<![\w])({re.escape(param)}\s*=\s*)({_NUM})", re.I)


def get_params(text: str, device: str, params: list[str] | None = None) -> dict[str, float]:
    cfg = load_config()["technology"]
    params = params or cfg["process_params"]
    s, e = _block_span(text, cfg["model_names"][device])
    block = text[s:e]
    out = {}
    for p in params:
        hits = _param_re(p).findall(block)
        if len(hits) != 1:
            raise ValueError(f"{device}: expected exactly one '{p}', found {len(hits)}")
        out[p] = float(hits[0][1])
    return out


def nominal_params() -> dict[str, dict[str, float]]:
    """Process-parameter nominals parsed from the original card."""
    text = read_card()
    return {d: get_params(text, d) for d in ("nmos", "pmos")}


def patch_card(text: str, values: dict[str, dict[str, float]]) -> str:
    """Return a copy of ``text`` with process parameters replaced.

    ``values`` = {"nmos": {"vth0": ..., ...}, "pmos": {...}}; either device
    may be omitted (it then keeps its nominal values).
    """
    cfg = load_config()["technology"]
    for device, params in values.items():
        s, e = _block_span(text, cfg["model_names"][device])
        block = text[s:e]
        for p, v in params.items():
            block, n = _param_re(p).subn(lambda m, v=v: f"{m.group(1)}{v:.12e}", block)
            if n != 1:
                raise ValueError(f"{device}: patched '{p}' {n} times (expected 1)")
        text = text[:s] + block + text[e:]
    # verify
    for device, params in values.items():
        got = get_params(text, device, list(params))
        for p, v in params.items():
            if abs(got[p] - v) > 1e-9 * abs(v):
                raise ValueError(f"verification failed for {device}.{p}: {got[p]} != {v}")
    return text


def write_patched_card(dest: Path, values: dict[str, dict[str, float]]) -> Path:
    dest.write_text(patch_card(read_card(), values), encoding="utf-8")
    return dest


def check_nominals() -> dict[str, dict[str, float]]:
    """Assert the card's nominals equal the assignment sheet values."""
    expected = load_config()["technology"]["expected_nominals"]
    got = nominal_params()
    for d in expected:
        for p, v in expected[d].items():
            if abs(got[d][p] - v) > 1e-9 * abs(v):
                raise ValueError(f"model card {d}.{p} = {got[d][p]}, expected {v}")
    return got
