"""ML leakage of a static-CMOS circuit from the four transistor models.

For every transistor of a circuit simulation:
  1. terminal voltages (Vd, Vg, Vs, Vb) from the recorded node voltages
     (rails and inputs are ideal: vdd = VDD, vss = 0, inputs = 0 or VDD);
  2. state: NMOS ON if Vg > VDD/2, PMOS ON if Vg < VDD/2  -> one of the 4 models;
  3. corner parameters: VDD, T, W (wn / wp), and the NMOS or PMOS process draw;
  4. model predicts id, ig, is, ib (positive = into the terminal).
Circuit leakage = current delivered by the VDD supply (ML counterpart of
SPICE's -i(Vdd_src)), computed two ways:
  direct     : sum over every device terminal tied to "vdd" of the ML current
               flowing INTO that terminal (``rail_current``);
  kcl_closed : same sum, but ON-transistor channel currents are not taken from
               the model - they are solved from KCL at the internal nodes
               (``kcl_closed_rail_current``; reason in its docstring).

``oracle_leakage`` evaluates the same formula with SPICE's own BSIM4
per-device components instead of ML; it must reproduce SPICE's supply
current and thereby validates the formula, the terminal mapping and signs.
"""
from __future__ import annotations

from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

from .circuits import Device
from .config import load_config, general_path, layer_path
from .transistor_model import (COMPONENTS, TERMINALS, compose_terminals, device_sign,
                               predict_components, predict_currents)

TERMINAL_NODE = {"id": "d", "ig": "g", "is": "s", "ib": "b"}


@lru_cache(maxsize=1)
def load_bundles() -> dict:
    cases = load_config()["part_a"]["cases"]
    return {c: joblib.load(layer_path(1, "models", f"{c}_model.joblib")) for c in cases}


def device_table(sims: pd.DataFrame, devices: list[Device], input_nodes: list[str],
                 node_col: str = "v_{}") -> pd.DataFrame:
    """One row per (simulation row, device) with the model inputs.

    ``sims`` needs: vdd, temp, wn, wp, n_<p>, p_<p>, the logic value of each input
    node in column ``in_<node>`` (0/1), and recorded voltages of every other node
    in columns ``node_col.format(node)``.
    """
    params = load_config()["technology"]["process_params"]
    out = []
    vdd = sims["vdd"].to_numpy(float)

    def node_v(n):
        if n == "vdd":
            return vdd
        if n == "vss":
            return np.zeros(len(sims))
        if n in input_nodes:
            return sims[f"in_{n}"].to_numpy(float) * vdd
        return sims[node_col.format(n)].to_numpy(float)

    for dv in devices:
        t = pd.DataFrame({"sim_idx": sims.index.to_numpy(), "device": dv.name, "type": dv.type,
                          "vdd": vdd, "temp": sims["temp"].to_numpy(float),
                          "w": sims["wn" if dv.type == "nmos" else "wp"].to_numpy(float),
                          "vd": node_v(dv.d), "vg": node_v(dv.g), "vs": node_v(dv.s), "vb": node_v(dv.b)})
        pre = "n_" if dv.type == "nmos" else "p_"
        for p in params:
            t[p] = sims[pre + p].to_numpy(float)
        on = (t.vg > 0.5 * t.vdd) if dv.type == "nmos" else (t.vg < 0.5 * t.vdd)
        t["case"] = np.where(on, f"{dv.type}_on", f"{dv.type}_off")
        for term, attr in TERMINAL_NODE.items():
            t[f"node_{term}"] = getattr(dv, attr)
        out.append(t)
    return pd.concat(out, ignore_index=True)


def predict_device_currents(table: pd.DataFrame) -> pd.DataFrame:
    """Add ML columns id, ig, is, ib (A, into terminal) using the case's model,
    plus ``ich_d`` = the channel part of the drain current (A, into drain)."""
    table = table.copy()
    for k in TERMINALS + ["ich_d"]:
        table[k] = np.nan
    bundles = load_bundles()
    lmin = load_config()["technology"]["lmin"]
    for case, idx in table.groupby("case").groups.items():
        rows = table.loc[idx]
        b = bundles[case]
        pred = predict_currents(b, rows)
        table.loc[idx, TERMINALS] = pred[TERMINALS].to_numpy()
        comp = predict_components(b, rows)
        t = device_sign(b["device"])
        m = np.where(t * rows["vd"].to_numpy() >= t * rows["vs"].to_numpy(), 1, -1)
        table.loc[idx, "ich_d"] = t * m * comp["ich"]
    return table


def kcl_closed_rail_current(table: pd.DataFrame, input_nodes: list[str], rail: str = "vdd",
                            fixed_nodes: tuple[str, ...] = ("vdd", "vss")) -> pd.Series:
    """Supply current with ON-transistor channel currents closed by KCL.

    An ON transistor's channel current is set by the circuit (it carries whatever
    the OFF network and tunnelling paths leak through it) at |Vds| ~ 1e-8..1e-6 V,
    where conductance x Vds cannot be predicted reliably. Here every ON channel
    current is an unknown; all other ML currents (OFF devices entirely; gate,
    junction and substrate components of ON devices) are kept. The unknowns are
    solved from KCL at every node that is not a rail or an input (min-norm
    least squares; parallel ON devices only need their sum).
    """
    out = {}
    for sim, g in table.groupby("sim_idx", sort=False):
        inputs = set(input_nodes)
        base = {k: g[k].to_numpy().copy() for k in TERMINALS}
        on = g["case"].str.endswith("_on").to_numpy()
        base["id"][on] -= g["ich_d"].to_numpy()[on]
        base["is"][on] += g["ich_d"].to_numpy()[on]
        nodes = sorted({n for k in TERMINALS for n in g[f"node_{k}"]} - set(fixed_nodes) - inputs)
        nidx = {n: i for i, n in enumerate(nodes)}
        on_rows = np.flatnonzero(on)
        r = np.zeros(len(nodes))
        for k in TERMINALS:
            for j, n in enumerate(g[f"node_{k}"].to_numpy()):
                if n in nidx:
                    r[nidx[n]] += base[k][j]
        A = np.zeros((len(nodes), len(on_rows)))
        dn, sn = g["node_id"].to_numpy(), g["node_is"].to_numpy()
        for c, j in enumerate(on_rows):
            if dn[j] in nidx:
                A[nidx[dn[j]], c] += 1.0
            if sn[j] in nidx:
                A[nidx[sn[j]], c] -= 1.0
        ch = np.linalg.lstsq(A, -r, rcond=None)[0] if len(on_rows) and len(nodes) else np.zeros(len(on_rows))
        total = sum(base[k][g[f"node_{k}"].to_numpy() == rail].sum() for k in TERMINALS)
        for c, j in enumerate(on_rows):
            total += ch[c] * ((dn[j] == rail) - (sn[j] == rail))
        out[sim] = total
    return pd.Series(out)


def rail_current(table: pd.DataFrame, rail: str = "vdd") -> pd.Series:
    """Sum of currents INTO all device terminals tied to ``rail``, per simulation."""
    contrib = sum(np.where(table[f"node_{k}"] == rail, table[k], 0.0) for k in TERMINALS)
    return pd.Series(contrib, index=table.index).groupby(table["sim_idx"]).sum()


SELF_CHECK_ABS_A = 1e-15     # SPICE round-off floor on gate/body terminals (Part A)
SELF_CHECK_REL = 1e-3
RAIL_OVERSHOOT_V = 1e-6


def spice_self_check(sims: pd.DataFrame, devices: list[Device], input_nodes: list[str]) -> pd.DataFrame:
    """Validate converged SPICE operating points (beyond 'ngspice exited 0').

    pass = (a) sum of the devices' own BSIM4 currents into the VDD rail equals the
               supply-source current within 1e-15 A + 1e-3 relative, and
           (b) no node lies outside [0, VDD] by more than 1 uV.
    Catches false convergence (seen on a few stacked gates: nodes ~10 uV past the
    rail, supply current wrong by >50 % or of the wrong sign).
    """
    orc = rail_current(oracle_device_currents(device_table(sims, devices, input_nodes), sims), "vdd")
    orc = orc.reindex(sims.index).to_numpy()
    diff = np.abs(orc - sims["i_vdd"].to_numpy())
    vn = sims.filter(regex=r"^v_")
    over = np.maximum(vn.max(axis=1).to_numpy() - sims["vdd"].to_numpy(), -vn.min(axis=1).to_numpy())
    ok = (diff <= SELF_CHECK_ABS_A + SELF_CHECK_REL * np.abs(sims["i_vdd"].to_numpy())) & \
         (over <= RAIL_OVERSHOOT_V)
    return pd.DataFrame({"self_check_abs_diff_A": diff, "rail_overshoot_V": over,
                         "self_check_ok": ok}, index=sims.index)


def oracle_device_currents(table: pd.DataFrame, sims: pd.DataFrame) -> pd.DataFrame:
    """Terminal currents rebuilt from SPICE's BSIM4 per-device diagnostics."""
    table = table.copy()
    lmin = load_config()["technology"]["lmin"]
    for k in TERMINALS:
        table[k] = np.nan
    for (dev, typ), idx in table.groupby(["device", "type"]).groups.items():
        rows = table.loc[idx]
        s = sims.loc[rows.sim_idx]
        comp = {"ich": s[f"d_{dev}_id"].to_numpy(), "jd": -s[f"d_{dev}_ibd"].to_numpy(),
                "js": -s[f"d_{dev}_ibs"].to_numpy(), "igcs": s[f"d_{dev}_igcs"].to_numpy(),
                "igcd": s[f"d_{dev}_igcd"].to_numpy(), "igb": s[f"d_{dev}_igb"].to_numpy(),
                "isub": s[f"d_{dev}_isub"].to_numpy()}
        assert set(comp) == set(COMPONENTS)
        term = compose_terminals(comp, rows, typ, lmin)
        for k in TERMINALS:
            table.loc[idx, k] = term[k]
    return table
