"""Physics-informed transistor current model (shared by Part A, B and C).

WHY a decomposition
-------------------
The four terminal currents span ~15 decades, change sign, and cross zero
(e.g. ID when Vd ~ Vs). Regressing them directly in signed-log space gives
poor relative accuracy - and inside a logic gate, ON transistors sit at
|Vds| ~ 1e-8 V where only a model with I ~ Vds behaviour is meaningful.

BSIM4 builds every terminal current from a few single-signed, smooth
physical components. We verified on the SPICE data that the terminal
currents equal these sums to machine precision (see validate_data):

  NMOS-equivalent frame (all voltages multiplied by t = +1 NMOS / -1 PMOS),
  mode m = +1 if vd' >= vs' (BSIM4 swaps D/S internally when m = -1):

    ich   channel current (internal drain -> internal source)    >= 0
    jd,js reverse junction leakage of drain / source diode       >= 0
    igcs, igcd  gate-to-channel tunnelling (internal S / D side) sign(Vgs'), sign(Vgd')
    igb   gate-to-body tunnelling                                sign(Vgb' - 0.4 V)
    isub  impact-ionisation substrate current (int. drain->body) >= 0
  (ngspice reports PMOS internals already in this NMOS-equivalent frame.)

    m=+1: id' =  ich + jd + isub - igcd      is' = -ich + js - igcs
    m=-1: id' = -ich + jd - igcs             is' =  ich + js + isub - igcd
          ib' = -jd - js - isub - igb        ig' = igcs + igcd + igb
    terminal current (into the terminal) = t * (...)'

Each component is learned as log(component / physical normaliser):
    ich  / (W/L * vT * (1 - exp(-|vds|/vT)))  -> finite as Vds -> 0, so I ~ Vds
    jd   / (1 - exp(-vdb'/vT)), js likewise    (diode reverse characteristic)
    igcs, igcd, igb, isub / (W/L)
Smooth, single-signed, ~2-5 decade targets are far easier to fit to <1 %.

The saved bundle (joblib) stores the device type, feature definition,
the fitted component regressors and their metadata, so Part B/C inference
uses exactly the training-time pipeline via :func:`predict_currents`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

K_B_OVER_Q = 8.617333262e-5          # V/K
COMPONENTS = ["ich", "jd", "js", "igcs", "igcd", "igb", "isub"]
LOG_FLOOR = 1e-45                     # floor before log for exactly-zero components
TERMINALS = ["id", "ig", "is", "ib"]


class SeedEnsemble:
    """Average of identically configured regressors trained with different seeds
    (reduces MLP initialisation variance). Predicts the mean in target space."""

    def __init__(self, makers):
        self.makers = makers
        self.models_ = []

    def fit(self, X, y):
        self.models_ = [m().fit(X, y) for m in self.makers]
        self.makers = None            # lambdas are not picklable; keep only fitted models
        return self

    def predict(self, X):
        return np.mean([m.predict(X) for m in self.models_], axis=0)


def device_sign(device: str) -> int:
    return 1 if device == "nmos" else -1


def _frame(df: pd.DataFrame, device: str, lmin: float) -> dict[str, np.ndarray]:
    t = device_sign(device)
    vd, vs, vg, vb = (t * df[k].to_numpy(float) for k in ("vd", "vs", "vg", "vb"))
    m = np.where(vd >= vs, 1, -1)
    v_hi, v_lo = np.maximum(vd, vs), np.minimum(vd, vs)
    T = df["temp"].to_numpy(float) + 273.15
    vt = K_B_OVER_Q * T
    w = df["w"].to_numpy(float)
    return dict(t=t, m=m, vds=v_hi - v_lo, vgs=vg - v_lo, vgd=vg - v_hi, vbs=vb - v_lo,
                vdb=vd - vb, vsb=vs - vb, vt=vt, T=T, wl=w / lmin, w=w)


def features(df: pd.DataFrame, device: str, lmin: float) -> np.ndarray:
    """Mode-frame physical features (identical in training and inference)."""
    f = _frame(df, device, lmin)
    vth0 = np.abs(df["vth0"].to_numpy(float))
    cols = [
        f["vgs"], f["vds"], f["vgd"], f["vbs"], f["vdb"], f["vsb"],
        f["vgs"] - vth0,                                   # gate overdrive
        # log(vds + 10 uV): bounded as vds -> 0. In gates ON devices sit at |vds| ~ 1e-8 V,
        # below the training minimum (~1e-5 V); with the 10 uV offset that maps to
        # log(1e-5), i.e. inside the training range (the normalised target is flat there).
        f["vds"] / f["vt"], np.log(f["vds"] + 1e-5),
        df["vdd"].to_numpy(float),
        f["T"] / 300.0, 300.0 / f["T"],
        np.log(f["wl"]), f["wl"],
        vth0, df["toxe"].to_numpy(float) * 1e9, np.log(df["ndep"].to_numpy(float) / 1e18),
        df["u0"].to_numpy(float) * 100, df["xj"].to_numpy(float) * 1e9,
    ]
    return np.column_stack(cols)


FEATURE_NAMES = ["vgs", "vds", "vgd", "vbs", "vdb", "vsb", "vov", "vds_over_vt", "log_vds_plus_10uV",
                 "vdd", "T_over_300", "300_over_T", "log_wl", "wl",
                 "abs_vth0", "toxe_nm", "log_ndep", "u0_x100", "xj_nm"]


def normalisers(df: pd.DataFrame, device: str, lmin: float) -> dict[str, np.ndarray]:
    f = _frame(df, device, lmin)
    vt = f["vt"]
    n = {
        "ich": f["wl"] * vt * -np.expm1(-f["vds"] / vt),
        "jd": -np.expm1(-np.abs(f["vdb"]) / vt),
        "js": -np.expm1(-np.abs(f["vsb"]) / vt),
    }
    for c in ("igcs", "igcd", "igb", "isub"):
        n[c] = f["wl"]
    return {k: np.maximum(v, 1e-300) for k, v in n.items()}


IGB_SIGN_THRESHOLD_V = 0.4   # igb > 0 in inversion (Vgb' ~ VDD), < 0 in accumulation (Vgb' ~ 0)


def component_signs(df: pd.DataFrame, device: str, lmin: float) -> dict[str, np.ndarray]:
    """Physical sign of each component (verified 100 % on the Part A data):
    channel/junction/isub >= 0; igcs ~ sign(Vgs'), igcd ~ sign(Vgd'),
    igb ~ sign(Vgb' - 0.4 V)."""
    f = _frame(df, device, lmin)
    one = np.ones_like(f["vds"])
    sgn = lambda v: np.where(v >= 0, 1.0, -1.0)  # noqa: E731
    return {"ich": one, "jd": one, "js": one, "isub": one,
            "igcs": sgn(f["vgs"]), "igcd": sgn(f["vgd"]),
            "igb": sgn(f["vgs"] - f["vbs"] - IGB_SIGN_THRESHOLD_V)}


def components_from_spice(df: pd.DataFrame, device: str) -> pd.DataFrame:
    """Map ngspice BSIM4 diagnostics (x_*) to NMOS-equivalent components.

    ngspice already reports PMOS internals in the NMOS-equivalent frame, so no
    sign flip is applied here; the device sign enters only in compose_terminals.
    """
    return pd.DataFrame({
        "ich": df["x_id"], "jd": -df["x_ibd"], "js": -df["x_ibs"],
        "igcs": df["x_igcs"], "igcd": df["x_igcd"], "igb": df["x_igb"], "isub": df["x_isub"],
    }, index=df.index)


def compose_terminals(comp: dict[str, np.ndarray], df: pd.DataFrame, device: str,
                      lmin: float) -> dict[str, np.ndarray]:
    f = _frame(df, device, lmin)
    t, m = f["t"], f["m"]
    ich, jd, js = comp["ich"], comp["jd"], comp["js"]
    igcs, igcd, igb, isub = comp["igcs"], comp["igcd"], comp["igb"], comp["isub"]
    fwd = m == 1
    idp = np.where(fwd, ich + jd + isub - igcd, -ich + jd - igcs)
    isp = np.where(fwd, -ich + js - igcs, ich + js + isub - igcd)
    ibp = -jd - js - isub - igb
    igp = igcs + igcd + igb
    return {"id": t * idp, "ig": t * igp, "is": t * isp, "ib": t * ibp}


# ---- learned targets ---------------------------------------------------------
# Gate-to-channel tunnelling is learned as BSIM4 structures it: one total current
# Igc (= igcs + igcd, a function of the gate-source bias and oxide, not of the
# drain) and its source/drain partition share (a function of Vds; exactly 1/2 at
# Vds = 0). Learning igcs and igcd separately with all features forced the model
# to extrapolate into the (Vd, Vs) rail corners where logic gates operate and the
# uniform training data has only a handful of samples; the total without drain
# features only needs the 1-D edge (source at the rail), which is well populated.
# igb (gate-to-body) likewise has no drain dependence.
LEARNED = ["ich", "jd", "js", "igc", "igc_share", "igb", "isub"]
DRAIN_FEATURES = {"vds", "vgd", "vdb", "vds_over_vt", "log_vds_plus_10uV"}
NO_DRAIN = [i for i, n in enumerate(FEATURE_NAMES) if n not in DRAIN_FEATURES]
FEATURE_COLS = {t: (NO_DRAIN if t in ("igc", "igb") else list(range(len(FEATURE_NAMES))))
                for t in LEARNED}
SHARE_CLIP = 1e-6


def log_targets(df: pd.DataFrame, device: str, lmin: float) -> pd.DataFrame:
    """Learning targets: log(|component| / normaliser); logit for the Igc share."""
    comp = components_from_spice(df, device)
    norm = normalisers(df, device, lmin)
    out = {c: np.log(np.maximum(np.abs(comp[c].to_numpy()), LOG_FLOOR) / norm[c])
           for c in ("ich", "jd", "js", "igb", "isub")}
    igcs, igcd = comp["igcs"].to_numpy(), comp["igcd"].to_numpy()
    tot = np.abs(igcs) + np.abs(igcd)
    out["igc"] = np.log(np.maximum(tot, LOG_FLOOR) / norm["igcs"])
    share = np.clip(np.abs(igcs) / np.maximum(tot, 1e-300), SHARE_CLIP, 1 - SHARE_CLIP)
    out["igc_share"] = np.log(share / (1 - share))
    return pd.DataFrame(out, index=df.index)[LEARNED]


def sign_agreement(df: pd.DataFrame, device: str, lmin: float) -> dict[str, float]:
    """Fraction of non-zero SPICE components whose sign matches the physics rule."""
    comp = components_from_spice(df, device)
    sg = component_signs(df, device, lmin)
    out = {}
    for c in COMPONENTS:
        v = comp[c].to_numpy()
        nz = v != 0
        out[c] = float(np.mean(np.sign(v[nz]) == sg[c][nz])) if nz.any() else float("nan")
    return out


def predict_learned(bundle: dict, X: np.ndarray) -> dict[str, np.ndarray]:
    return {t: bundle["regressors"][t].predict(X[:, FEATURE_COLS[t]]) for t in LEARNED}


def predict_components(bundle: dict, df: pd.DataFrame) -> dict[str, np.ndarray]:
    X = features(df, bundle["device"], bundle["lmin"])
    norm = normalisers(df, bundle["device"], bundle["lmin"])
    sg = component_signs(df, bundle["device"], bundle["lmin"])
    y = predict_learned(bundle, X)
    out = {c: sg[c] * np.exp(y[c]) * norm[c] for c in ("ich", "jd", "js", "igb", "isub")}
    igc = np.exp(y["igc"]) * norm["igcs"]
    share = 1.0 / (1.0 + np.exp(-y["igc_share"]))
    out["igcs"] = sg["igcs"] * igc * share
    out["igcd"] = sg["igcd"] * igc * (1.0 - share)
    return out


def predict_currents(bundle: dict, df: pd.DataFrame) -> pd.DataFrame:
    """Predict id, ig, is, ib (A, positive = into terminal) for rows of ``df``.

    ``df`` needs columns vdd, temp, w, vd, vs, vg, vb, vth0, toxe, ndep, u0, xj.
    """
    comp = predict_components(bundle, df)
    return pd.DataFrame(compose_terminals(comp, df, bundle["device"], bundle["lmin"]), index=df.index)
