"""Run NGSPICE in batch mode and parse validated results.

A netlist is accepted only if ALL of the following hold:
* ngspice returned exit code 0 within the timeout;
* no error / non-convergence message appears in the log;
* every requested output vector was printed exactly once;
* every value is finite.

Outputs are printed with ``set numdgt=15`` so currents keep ~15 significant
digits (ngspice's default print keeps only ~6, which breaks the KCL check).

Current convention: for a voltage source ``Vx node 0 ...``, ngspice's
``i(Vx)`` is the current flowing INTO the + terminal of the source, i.e. OUT
of the circuit node. We therefore report ``-i(Vx)`` = current flowing INTO
the device terminal from that source.
"""
from __future__ import annotations

import math
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .config import config_path, load_config

_VALUE_RE = re.compile(r"^\s*([A-Za-z_][\w@\[\]\(\)\.]*)\s*=\s*(\S+)\s*$", re.M)
_FATAL_PATTERNS = [
    re.compile(p, re.I | re.M)
    for p in (
        r"^\s*error\b",
        r"no convergence",
        r"singular matrix",
        r"timestep too small",
        r"simulation\(s\) aborted",
        r"analysis .*failed",
        r"could not find",
        r"unknown (?:model|device|parameter)",
        r"fatal",
    )
]


@dataclass
class SimResult:
    ok: bool
    values: dict[str, float] = field(default_factory=dict)
    error: str = ""
    log: str = ""


def ngspice_exe() -> Path:
    exe = config_path("ngspice")
    if not exe.exists():
        raise FileNotFoundError(f"ngspice not found at {exe}")
    return exe


def ngspice_version() -> str:
    out = subprocess.run([str(ngspice_exe()), "-v"], capture_output=True, text=True, timeout=30)
    m = re.search(r"ngspice-\S+", out.stdout + out.stderr)
    return m.group(0) if m else "unknown"


def control_block(outputs: dict[str, str]) -> str:
    """Build a .control section computing and printing named expressions.

    ``outputs`` maps output name -> ngspice expression, e.g.
    {"id": "-i(Vd)", "vx": "v(x)"}.
    """
    digits = load_config()["spice"]["print_digits"]
    lines = [".control", f"set numdgt={digits}", "op"]
    for name, expr in outputs.items():
        lines.append(f"let {name} = {expr}")
    for name in outputs:
        lines.append(f"print {name}")
    lines += [".endc"]
    return "\n".join(lines)


def run_netlist(netlist: str, expected: list[str], extra_files: dict[str, str] | None = None,
                workdir: Path | None = None, timeout: float | None = None,
                keep: bool = False) -> SimResult:
    """Write ``netlist`` (+ ``extra_files``, e.g. the patched model card) to a
    private temp dir, run ngspice there, and parse the ``expected`` outputs."""
    timeout = timeout or load_config()["spice"]["timeout_s"]
    base = workdir or config_path("tmp_dir")
    base.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="run_", dir=base))
    for name, text in (extra_files or {}).items():
        (run_dir / name).write_text(text, encoding="utf-8")
    sp = run_dir / "circuit.sp"
    sp.write_text(netlist, encoding="utf-8")
    try:
        proc = subprocess.run([str(ngspice_exe()), "-b", sp.name], cwd=run_dir,
                              capture_output=True, text=True, timeout=timeout)
        log = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        return SimResult(False, error=f"timeout after {timeout}s")
    finally:
        if not keep:
            shutil.rmtree(run_dir, ignore_errors=True)
    return parse_output(log, expected, proc.returncode)


def parse_output(log: str, expected: list[str], returncode: int = 0) -> SimResult:
    if returncode != 0:
        return SimResult(False, error=f"ngspice exit code {returncode}", log=log)
    for pat in _FATAL_PATTERNS:
        m = pat.search(log)
        if m:
            line = log[max(0, m.start() - 80): m.end() + 120].strip().replace("\n", " | ")
            return SimResult(False, error=f"simulator message: {line}", log=log)
    found: dict[str, list[str]] = {}
    for name, val in _VALUE_RE.findall(log):
        found.setdefault(name.lower(), []).append(val)
    values = {}
    for name in expected:
        hits = found.get(name.lower(), [])
        if len(hits) != 1:
            return SimResult(False, error=f"output '{name}' printed {len(hits)} times", log=log)
        try:
            v = float(hits[0])
        except ValueError:
            return SimResult(False, error=f"output '{name}' not numeric: {hits[0]}", log=log)
        if not math.isfinite(v):
            return SimResult(False, error=f"output '{name}' not finite: {v}", log=log)
        values[name] = v
    return SimResult(True, values=values, log=log)


def new_tag() -> str:
    return uuid.uuid4().hex[:10]
