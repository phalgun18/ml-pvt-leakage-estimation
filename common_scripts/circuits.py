"""Static-CMOS circuits as transistor lists (used by Part B and Part C).

A circuit is a list of Device(name, type, d, g, s, b). Rails are the nodes (ngspice treats "gnd" as node 0, so ground rail = "vss")
"vdd" and "vss". The SAME description is used to
  * write the SPICE netlist (flat, one M-card per device), and
  * map recorded node voltages onto each device's (Vd, Vg, Vs, Vb) for ML.

Measured quantities (sign conventions):
  i_vdd    = -i(Vdd_src)  current delivered BY the VDD supply  (= gate leakage)
  i_gnd    =  i(Vss)      current sunk into ground
  i_in_<x> = -i(V<x>)     current delivered by input source x (gate tunnelling)
By KCL: i_vdd + sum(i_in) = i_gnd.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import load_config


@dataclass(frozen=True)
class Device:
    name: str
    type: str   # "nmos" | "pmos"
    d: str
    g: str
    s: str
    b: str


def inv(a: str, y: str, p: str = "") -> list[Device]:
    return [Device(f"mp{p}", "pmos", y, a, "vdd", "vdd"),
            Device(f"mn{p}", "nmos", y, a, "vss", "vss")]


def nand2(a: str, b: str, y: str, x: str, p: str = "") -> list[Device]:
    """Parallel PMOS pull-up, series NMOS pull-down; x = node between the NMOS."""
    return [Device(f"mpa{p}", "pmos", y, a, "vdd", "vdd"),
            Device(f"mpb{p}", "pmos", y, b, "vdd", "vdd"),
            Device(f"mna{p}", "nmos", y, a, x, "vss"),      # top NMOS (drain at output)
            Device(f"mnb{p}", "nmos", x, b, "vss", "vss")]  # bottom NMOS (source at ground)


def nor2(a: str, b: str, y: str, yi: str, p: str = "") -> list[Device]:
    """Series PMOS pull-up, parallel NMOS pull-down; yi = node between the PMOS."""
    return [Device(f"mpa{p}", "pmos", yi, a, "vdd", "vdd"),  # top PMOS (source at VDD)
            Device(f"mpb{p}", "pmos", y, b, yi, "vdd"),      # bottom PMOS (drain at output)
            Device(f"mna{p}", "nmos", y, a, "vss", "vss"),
            Device(f"mnb{p}", "nmos", y, b, "vss", "vss")]


# gate name -> (input count, builder(inputs, out, prefix) -> devices, internal nodes)
def gate_devices(gate: str, ins: list[str], out: str, p: str = "") -> tuple[list[Device], list[str]]:
    if gate == "inv":
        return inv(ins[0], out, p), []
    if gate == "nand2":
        return nand2(ins[0], ins[1], out, f"x{p}", p), [f"x{p}"]
    if gate == "nor2":
        return nor2(ins[0], ins[1], out, f"yi{p}", p), [f"yi{p}"]
    if gate == "and2":   # NAND2 -> INV, simulated as ONE complete gate
        n = f"nand_out{p}"
        return nand2(ins[0], ins[1], n, f"x{p}", p) + inv(n, out, f"i{p}"), [f"x{p}", n]
    if gate == "or2":    # NOR2 -> INV
        n = f"nor_out{p}"
        return nor2(ins[0], ins[1], n, f"yi{p}", p) + inv(n, out, f"i{p}"), [f"yi{p}", n]
    raise ValueError(gate)


GATE_INPUTS = {"inv": ["a"], "nand2": ["a", "b"], "nor2": ["a", "b"], "and2": ["a", "b"], "or2": ["a", "b"]}


def logic(gate: str, bits: tuple[int, ...]) -> int:
    a = bits[0]
    b = bits[1] if len(bits) > 1 else None
    return {"inv": lambda: 1 - a, "nand2": lambda: 1 - (a & b), "nor2": lambda: 1 - (a | b),
            "and2": lambda: a & b, "or2": lambda: a | b}[gate]()


DIAG = ("id", "igcs", "igcd", "igb", "isub", "ibd", "ibs")


def circuit_netlist(title: str, devices: list[Device], inputs: dict[str, float], vdd: float,
                    temp: float, wn: float, wp: float, probe_nodes: list[str],
                    card_name: str = "card.pm", diagnostics: bool = True,
                    nodeset: dict[str, float] | None = None) -> tuple[str, list[str]]:
    """Return (netlist text, list of printed output names).

    ``nodeset`` gives Newton an initial guess (e.g. logic levels of gate
    outputs). It does not change the converged solution - the required
    .options tolerances still apply - it only prevents DC non-convergence
    ("timestep too small") seen with gmin=abstol=1e-18 on stacked gates.
    """
    from .spice_runner import control_block

    cfg = load_config()
    lmin = cfg["technology"]["lmin"]
    f = lambda x: f"{x:.12g}"  # noqa: E731
    lines = [f"* {title}", f'.include "{card_name}"',
             f"Vdd_src vdd 0 {f(vdd)}", "Vss vss 0 0"]
    for n, v in inputs.items():
        lines.append(f"V{n} {n} 0 {f(v)}")
    for dv in devices:
        w = wn if dv.type == "nmos" else wp
        lines.append(f"{dv.name} {dv.d} {dv.g} {dv.s} {dv.b} {dv.type} W={f(w)} L={f(lmin)}")
    lines += [cfg["spice"]["options_line"],
              cfg["spice"]["circuit_convergence_line"],   # solver robustness only: iteration limits + stronger pivoting
              f".temp {f(temp)}"]
    if nodeset:
        lines.append(".nodeset " + " ".join(f"v({n})={f(v)}" for n, v in nodeset.items()))
    outs = {"i_vdd": "-i(Vdd_src)", "i_gnd": "i(Vss)"}
    outs.update({f"i_in_{n}": f"-i(V{n})" for n in inputs})
    outs.update({f"v_{n}": f"v({n})" for n in probe_nodes})
    if diagnostics:
        for dv in devices:
            for q in DIAG:
                outs[f"d_{dv.name}_{q}"] = f"@{dv.name}[{q}]"
    lines += [control_block(outs), ".end", ""]
    return "\n".join(lines), list(outs)
