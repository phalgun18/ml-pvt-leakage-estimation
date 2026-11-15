"""3-bit carry-lookahead adder built ONLY from INV / NAND2 / NOR2 / AND2 / OR2.

Inputs  a2 a1 a0, b2 b1 b0, c0 (carry-in, tied to logic 0 by a 0 V source)
Outputs s2 s1 s0 (sum), c3 (carry-out)

  generate   g_i = AND2(a_i, b_i)
  propagate  p_i = XOR(a_i, b_i)          XOR = 4 x NAND2:
             n1 = NAND(x,y); n2 = NAND(x,n1); n3 = NAND(y,n1); out = NAND(n2,n3)
  lookahead carries (every carry from g/p directly, 2-input trees):
    u0  = AND2(p0, c0)                    p0.c0
    c1  = OR2(g0, u0)                     g0 + p0c0
    t21 = AND2(p1, g0)                    p1g0
    t22 = AND2(p1, u0)                    p1p0c0
    c2  = OR2(g1, OR2(t21, t22))          g1 + p1g0 + p1p0c0
    t31 = AND2(p2, g1)                    p2g1
    t32 = AND2(p2, t21)                   p2p1g0
    t33 = AND2(p2, t22)                   p2p1p0c0
    c3  = OR2(OR2(g2, t31), OR2(t32, t33))
  sums       s_i = XOR(p_i, c_i)

39 gates: 24 NAND2, 9 AND2, 6 OR2 -> 186 transistors.
Gate input order matters (NAND2 'a' = top NMOS, NOR2 'a' = top PMOS) and is the
same in the SPICE netlist and in the Part-B gate models used for prediction.
"""
from __future__ import annotations

from dataclasses import dataclass

from .circuits import Device, gate_devices, logic

INPUTS = ["a0", "a1", "a2", "b0", "b1", "b2", "c0"]
OUTPUTS = ["s0", "s1", "s2", "c3"]


@dataclass(frozen=True)
class Gate:
    name: str
    type: str
    ins: tuple[str, ...]
    out: str


def _xor(tag: str, x: str, y: str, out: str) -> list[Gate]:
    n1, n2, n3 = f"{tag}_n1", f"{tag}_n2", f"{tag}_n3"
    return [Gate(f"{tag}_1", "nand2", (x, y), n1), Gate(f"{tag}_2", "nand2", (x, n1), n2),
            Gate(f"{tag}_3", "nand2", (y, n1), n3), Gate(f"{tag}_4", "nand2", (n2, n3), out)]


def cla3_gates() -> list[Gate]:
    g: list[Gate] = []
    for i in range(3):
        g.append(Gate(f"gen{i}", "and2", (f"a{i}", f"b{i}"), f"g{i}"))
        g += _xor(f"xp{i}", f"a{i}", f"b{i}", f"p{i}")
    g += [Gate("u0", "and2", ("p0", "c0"), "u0"),
          Gate("c1", "or2", ("g0", "u0"), "c1"),
          Gate("t21", "and2", ("p1", "g0"), "t21"),
          Gate("t22", "and2", ("p1", "u0"), "t22"),
          Gate("o2", "or2", ("t21", "t22"), "o2"),
          Gate("c2", "or2", ("g1", "o2"), "c2"),
          Gate("t31", "and2", ("p2", "g1"), "t31"),
          Gate("t32", "and2", ("p2", "t21"), "t32"),
          Gate("t33", "and2", ("p2", "t22"), "t33"),
          Gate("o31", "or2", ("g2", "t31"), "o31"),
          Gate("o32", "or2", ("t32", "t33"), "o32"),
          Gate("c3", "or2", ("o31", "o32"), "c3")]
    for i in range(3):
        g += _xor(f"xs{i}", f"p{i}", f"c{i}", f"s{i}")
    return g


def evaluate(gates: list[Gate], inputs: dict[str, int]) -> dict[str, int]:
    """Logic-simulate (gates are listed in topological order)."""
    v = dict(inputs)
    for gt in gates:
        v[gt.out] = logic(gt.type, tuple(v[i] for i in gt.ins))
    return v


def cla3_devices(gates: list[Gate]) -> tuple[list[Device], list[str]]:
    """Flat transistor list + every non-rail, non-input node (for probing)."""
    devs, nodes = [], []
    for gt in gates:
        d, internal = gate_devices(gt.type, list(gt.ins), gt.out, p=f"_{gt.name}")
        devs += d
        nodes += [gt.out] + internal
    return devs, list(dict.fromkeys(nodes))


def internal_logic_levels(gates: list[Gate], v: dict[str, int]) -> dict[str, int]:
    """Logic level of every gate output and AND2/OR2 first-stage node (for .nodeset)."""
    lv = {}
    for gt in gates:
        lv[gt.out] = v[gt.out]
        bits = tuple(v[i] for i in gt.ins)
        if gt.type == "and2":
            lv[f"nand_out_{gt.name}"] = logic("nand2", bits)
        if gt.type == "or2":
            lv[f"nor_out_{gt.name}"] = logic("nor2", bits)
    return lv


def vectors(cin: int = 0) -> list[dict[str, int]]:
    """All 64 (A, B) combinations with the configured carry-in."""
    out = []
    for a in range(8):
        for b in range(8):
            v = {f"a{i}": (a >> i) & 1 for i in range(3)}
            v.update({f"b{i}": (b >> i) & 1 for i in range(3)})
            v["c0"] = cin
            out.append(v)
    return out


def vector_label(v: dict[str, int]) -> str:
    a = sum(v[f"a{i}"] << i for i in range(3))
    b = sum(v[f"b{i}"] << i for i in range(3))
    return f"A{a}_B{b}"
