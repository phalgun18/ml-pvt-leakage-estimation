"""SPICE netlist builders.

Netlists are generated from Python with literal numeric values (no .param
indirection), so the file that ran is exactly the file you can read.
Process parameters are NOT in the netlist: they live in the patched model
card copy ``card.pm`` that is written next to each netlist.
"""
from __future__ import annotations

from .config import load_config

CARD_NAME = "card.pm"

# Terminal currents reported as current flowing INTO each device terminal.
TRANSISTOR_OUTPUTS = {"id": "-i(Vd)", "ig": "-i(Vg)", "is": "-i(Vs)", "ib": "-i(Vb)"}

# Diagnostic BSIM4 internal quantities (NOT deliverable columns, NOT ML inputs).
# Signs follow ngspice's internal convention (channel current in the internal
# d->s "mode" frame; BSIM4 swaps d/s internally when Vds < 0).
DIAG_OUTPUTS = {f"x_{n}": f"@m1[{n}]" for n in
                ("id", "isub", "igidl", "igisl", "igb", "igcs", "igcd", "ibd", "ibs", "vth")}


def _fmt(x: float) -> str:
    return f"{x:.12g}"


def transistor_netlist(case: str, device: str, s: dict, card_name: str = CARD_NAME,
                       diagnostics: bool = True) -> str:
    """Single-FET netlist; every terminal has its own voltage source.

    ``s`` needs keys vdd, temp, w, vd, vs, vg, vb.
    """
    from .spice_runner import control_block

    cfg = load_config()
    lmin = cfg["technology"]["lmin"]
    model = cfg["technology"]["model_names"][device]
    return "\n".join([
        f"* {case.upper()} single-transistor netlist (32nm LP)",
        f'.include "{card_name}"',
        f"* VDD = {_fmt(s['vdd'])} V (sets the VG/VB/VD/VS ranges)",
        f"Vd d 0 {_fmt(s['vd'])}",
        f"Vg g 0 {_fmt(s['vg'])}",
        f"Vs s 0 {_fmt(s['vs'])}",
        f"Vb b 0 {_fmt(s['vb'])}",
        f"M1 d g s b {model} W={_fmt(s['w'])} L={_fmt(lmin)}",
        cfg["spice"]["options_line"],
        f".temp {_fmt(s['temp'])}",
        control_block({**TRANSISTOR_OUTPUTS, **(DIAG_OUTPUTS if diagnostics else {})}),
        ".end",
        "",
    ])
