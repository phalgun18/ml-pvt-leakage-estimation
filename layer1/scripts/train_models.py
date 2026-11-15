"""Part A step 2: train, compare and select the transistor models.

For each case: fixed-seed 70/15/15 split -> for each of 4 model types, fit one
regressor per physical component (see common/transistor_model.py) on the
TRAIN set (learned targets: ich, jd, js, igc total + igc source share, igb,
isub; see transistor_model.LEARNED) -> compose the 4 terminal currents -> score against the SPICE
terminal currents on the VALIDATION set. The model type with the lowest mean
P95 relative error over the terminals is selected; only then is it scored
once on the TEST set.

Model types (scikit-learn), all on the same 19 physics features, targets =
log(|component| / normaliser):
  poly_ridge   StandardScaler -> PolynomialFeatures(deg 3) -> RidgeCV
  rf           RandomForestRegressor(400 trees)
  hgb          HistGradientBoostingRegressor(3000 iters, lr 0.05, early stop)
  mlp          mean of 3 seeds of StandardScaler -> MLPRegressor(3x128 tanh, adam, early stop),
               standardised target

Outputs
  data/processed/splits/<case>_split.csv           sample_id -> train/val/test
  outputs/part_a/model_comparison_validation.csv   per case x model x terminal
  outputs/part_a/model_comparison_table.csv        4 x 4 summary (deliverable 4)
  outputs/part_a/test_metrics.csv                  chosen models on test (deliverable 5)
  outputs/part_a/predictions_test_<case>.csv
  models/<case>_model.joblib                       saved bundles (deliverable 5)

Run:  python -m layer1.scripts.train_models [--case nmos_on] [--models mlp,hgb] [--jobs 12]
"""
from __future__ import annotations

import argparse
import json
import time
import warnings

import joblib
import numpy as np
import pandas as pd
import sklearn
from joblib import Parallel, delayed
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import RidgeCV
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

from common_scripts.config import load_config, general_path, layer_path
from common_scripts.metrics import error_stats
from common_scripts.transistor_model import (COMPONENTS, FEATURE_COLS, LEARNED, SeedEnsemble, FEATURE_NAMES,
                                         TERMINALS, features,
                                         log_targets, predict_currents)

OUT = layer_path(1, "outputs")
MODEL_TYPES = ["poly_ridge", "rf", "hgb", "mlp"]
EVAL_FLOOR = 1e-15   # A; percentage metrics use |I_spice| >= floor


def make_model(kind: str, seed: int):
    if kind == "poly_ridge":
        return make_pipeline(StandardScaler(), PolynomialFeatures(3), StandardScaler(),
                             RidgeCV(alphas=np.logspace(-6, 2, 17)))
    if kind == "rf":
        return RandomForestRegressor(n_estimators=400, min_samples_leaf=1, max_features=0.6,
                                     n_jobs=1, random_state=seed)
    if kind == "hgb":
        return HistGradientBoostingRegressor(max_iter=3000, learning_rate=0.05, max_leaf_nodes=31,
                                             min_samples_leaf=10, l2_regularization=1e-3,
                                             early_stopping=True, validation_fraction=0.1,
                                             n_iter_no_change=100, random_state=seed)
    if kind == "mlp":
        from functools import partial
        return SeedEnsemble([partial(_mlp, seed + k) for k in range(3)])
    raise ValueError(kind)


def _mlp(seed: int):
    """One ensemble member: standardised X and y, 3x128 tanh MLP."""
    mlp = MLPRegressor(hidden_layer_sizes=(128, 128, 128), activation="tanh", solver="adam",
                       learning_rate_init=1e-3, batch_size=128, alpha=1e-6, max_iter=4000,
                       early_stopping=True, validation_fraction=0.1, n_iter_no_change=60,
                       tol=1e-8, random_state=seed)
    return TransformedTargetRegressor(regressor=make_pipeline(StandardScaler(), mlp),
                                      transformer=StandardScaler())


HYPERPARAMS = {
    "poly_ridge": "StandardScaler -> PolynomialFeatures(degree=3) -> RidgeCV(alpha in 1e-6..1e2)",
    "rf": "400 trees, max_features=0.6, min_samples_leaf=1",
    "hgb": "max_iter=3000, lr=0.05, max_leaf_nodes=31, min_samples_leaf=10, l2=1e-3, early stop (100)",
    "mlp": "average of 3 seeds of: 3x128 tanh, adam lr=1e-3, batch 128, alpha=1e-6, early stop (60), standardised X and y",
}


def split_ids(ids: np.ndarray, fracs, seed: int) -> pd.Series:
    rng = np.random.default_rng(seed)
    perm = rng.permutation(ids)
    n = len(ids)
    n_tr, n_va = int(round(fracs[0] * n)), int(round(fracs[1] * n))
    lab = np.empty(n, dtype=object)
    lab[:n_tr], lab[n_tr:n_tr + n_va], lab[n_tr + n_va:] = "train", "val", "test"
    return pd.Series(lab, index=perm).sort_index()


def fit_one(case, kind, comp, X, y, seed):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        t0 = time.time()
        model = make_model(kind, seed).fit(X, y)
    return case, kind, comp, model, time.time() - t0


def terminal_metrics(pred: pd.DataFrame, ref: pd.DataFrame) -> list[dict]:
    return [{"terminal": k, **error_stats(pred[k].to_numpy(), ref[k].to_numpy(), EVAL_FLOOR)}
            for k in TERMINALS]


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=list(cfg["part_a"]["cases"]))
    ap.add_argument("--models", default=",".join(MODEL_TYPES))
    ap.add_argument("--jobs", type=int, default=12)
    args = ap.parse_args()
    cases = [c for c in cfg["part_a"]["cases"] if not args.case or c == args.case]
    kinds = args.models.split(",")
    lmin = cfg["technology"]["lmin"]
    seed = cfg["part_a"]["split_seed"]

    data = {}
    for case in cases:
        dev = cfg["part_a"]["cases"][case]["device"]
        raw = pd.read_csv(layer_path(1, "data", "raw", f"{case}_spice_raw.csv")).sort_values("sample_id")
        raw = raw.drop_duplicates("sample_id").set_index("sample_id", drop=False)
        split = split_ids(raw.sample_id.to_numpy(), cfg["part_a"]["split_fractions"], seed)
        sp_dir = layer_path(1, "data", "processed", "splits")
        sp_dir.mkdir(parents=True, exist_ok=True)
        split.rename("split").rename_axis("sample_id").to_csv(sp_dir / f"{case}_split.csv")
        raw["split"] = split
        data[case] = (dev, raw, features(raw, dev, lmin), log_targets(raw, dev, lmin))
        print(f"[{case}] split: {raw.split.value_counts().to_dict()}")

    tasks = []
    for case, (dev, raw, X, Y) in data.items():
        tr = (raw.split == "train").to_numpy()
        for kind in kinds:
            for comp in LEARNED:
                tasks.append(delayed(fit_one)(case, kind, comp, X[tr][:, FEATURE_COLS[comp]],
                                              Y[comp].to_numpy()[tr], seed))
    print(f"fitting {len(tasks)} regressors with {args.jobs} jobs ...", flush=True)
    t0 = time.time()
    fitted = Parallel(n_jobs=args.jobs, verbose=5)(tasks)
    print(f"done in {time.time() - t0:.0f}s")

    regs, fit_time = {}, {}
    for case, kind, comp, model, dt in fitted:
        regs.setdefault((case, kind), {})[comp] = model
        fit_time[(case, kind)] = fit_time.get((case, kind), 0) + dt

    rows, comp_rows = [], []
    for (case, kind), r in regs.items():
        dev, raw, X, Y = data[case]
        bundle = {"case": case, "device": dev, "lmin": lmin, "regressors": r}
        va = raw[raw.split == "val"]
        pred = predict_currents(bundle, va)
        for m in terminal_metrics(pred, va):
            rows.append({"case": case, "model": kind, "fit_time_s": fit_time[(case, kind)], **m})
        Xv = features(va, dev, lmin)
        Yv = log_targets(va, dev, lmin)
        for comp in LEARNED:
            res = r[comp].predict(Xv[:, FEATURE_COLS[comp]]) - Yv[comp].to_numpy()
            comp_rows.append({"case": case, "model": kind, "component": comp,
                              "val_rmse_log": float(np.sqrt(np.mean(res ** 2))),
                              "val_median_abs_log": float(np.median(np.abs(res)))})
    val = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    val_path = OUT / "model_comparison_validation.csv"
    if args.case or args.models != ",".join(MODEL_TYPES):        # partial run: keep other rows
        if val_path.exists():
            old = pd.read_csv(val_path)
            old = old[~(old.case.isin(cases) & old.model.isin(kinds))]
            val = pd.concat([old, val], ignore_index=True)
    val.to_csv(val_path, index=False)
    pd.DataFrame(comp_rows).to_csv(OUT / "component_fit_validation.csv", index=False)

    summary = (val.groupby(["case", "model"])
               .agg(R2_log10_mean=("r2_log10", "mean"),
                    median_err_pct_mean=("median_err_pct", "mean"),
                    p95_err_pct_mean=("p95_err_pct", "mean"),
                    p95_err_pct_worst=("p95_err_pct", "max"),
                    fit_time_s=("fit_time_s", "first"))
               .reset_index())
    summary.to_csv(OUT / "model_comparison_table.csv", index=False)
    with pd.option_context("display.width", 200, "display.float_format", "{:.4g}".format):
        print("\nVALIDATION (mean over terminals with |I| >= 1e-15 A)\n", summary.to_string(index=False))

    # ---- final model per case: best model type PER COMPONENT (validation log-RMSE).
    # The physics differ by component (e.g. subthreshold channel current is ~exp(polynomial),
    # which poly_ridge captures best; tunnelling/ON-channel suit the MLP), so each component
    # regressor is chosen independently. Selection uses the validation set only.
    cr = pd.DataFrame(comp_rows)
    choice = (cr[cr.case.isin(cases) & cr.model.isin(kinds)]
              .sort_values("val_rmse_log").groupby(["case", "component"]).first()["model"])
    choice.reset_index().to_csv(OUT / "selected_component_models.csv", index=False)
    hyb_rows = []
    test_rows = []
    for case in cases:
        dev, raw, X, Y = data[case]
        picks = {c: choice[(case, c)] for c in LEARNED}
        best = "hybrid[" + ",".join(f"{c}:{k}" for c, k in picks.items()) + "]"
        bundle = {"case": case, "device": dev, "lmin": lmin, "model_type": best,
                  "component_model_types": picks,
                  "regressors": {c: regs[(case, k)][c] for c, k in picks.items()},
                  "feature_names": FEATURE_NAMES,
                  "components": COMPONENTS, "learned_targets": LEARNED,
                  "feature_cols": FEATURE_COLS, "sklearn_version": sklearn.__version__,
                  "selection": "per component: lowest validation RMSE of log(|component|/normaliser)",
                  "hyperparameters": {k: HYPERPARAMS[k] for k in set(picks.values())},
                  "eval_floor_A": EVAL_FLOOR}
        va = raw[raw.split == "val"]
        for m in terminal_metrics(predict_currents(bundle, va), va):
            hyb_rows.append({"case": case, "model": "selected (per-component)", **m})
        joblib.dump(bundle, layer_path(1, "models", f"{case}_model.joblib"), compress=3)
        te = raw[raw.split == "test"]
        pred = predict_currents(bundle, te)
        out = te[["sample_id"] + ["vdd", "temp", "w", "vd", "vs", "vg", "vb", "vth0", "toxe", "ndep", "u0", "xj"]
                 + TERMINALS].copy()
        for k in TERMINALS:
            out[f"{k}_pred"] = pred[k]
        out.to_csv(OUT / f"predictions_test_{case}.csv", index=False, float_format="%.10g")
        for m in terminal_metrics(pred, te):
            test_rows.append({"case": case, "model": best, **m})
        print(f"[{case}] selected: {best}")
    hyb = pd.DataFrame(hyb_rows)
    hyb.to_csv(OUT / "selected_model_validation.csv", index=False)
    with pd.option_context("display.width", 200, "display.float_format", "{:.4g}".format):
        print("\nVALIDATION, selected per-component model\n",
              hyb.groupby("case")[["r2_log10", "median_err_pct", "p95_err_pct"]].mean().to_string())
    test = pd.DataFrame(test_rows)
    test.to_csv(OUT / "test_metrics.csv", index=False)
    with pd.option_context("display.width", 200, "display.float_format", "{:.4g}".format):
        print("\nTEST (chosen models)\n", test[["case", "model", "terminal", "n_used", "n_below_floor",
                                               "r2_log10", "median_err_pct", "p95_err_pct",
                                               "bias_pct", "sign_errors"]].to_string(index=False))
    (OUT / "hyperparameters.json").write_text(json.dumps(HYPERPARAMS, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
