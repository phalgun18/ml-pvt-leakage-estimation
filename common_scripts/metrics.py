"""Error metrics shared by Parts A, B and C.

Definitions (stated once, used everywhere):
* relative error  e = |pred - ref| / |ref|      (a sign error therefore gives e >= 100 %)
* percentage metrics use only samples with |ref| >= floor, because relative
  error of a value at the simulator's resolution is meaningless. The number
  of excluded samples is always reported alongside.
* bias = median(pred / ref - 1)  (signed; + means the model over-predicts)
* R2 is computed on log10|I| (the quantity spans many decades; R2 on raw
  current would be dominated by the few largest samples). Samples where
  pred and ref differ in sign are kept with |pred| (their e is reported).
* absolute error: median and P95 of |pred - ref| over ALL samples (no floor).
"""
from __future__ import annotations

import numpy as np


def error_stats(pred, ref, floor: float = 1e-15) -> dict:
    pred = np.asarray(pred, float)
    ref = np.asarray(ref, float)
    abs_err = np.abs(pred - ref)
    m = np.abs(ref) >= floor
    out = {
        "n": int(len(ref)), "n_used": int(m.sum()), "n_below_floor": int((~m).sum()),
        "floor_A": floor,
        "median_abs_err_A": float(np.median(abs_err)) if len(ref) else np.nan,
        "p95_abs_err_A": float(np.percentile(abs_err, 95)) if len(ref) else np.nan,
    }
    if m.sum() == 0:
        out.update(median_err_pct=np.nan, p95_err_pct=np.nan, mean_err_pct=np.nan,
                   max_err_pct=np.nan, bias_pct=np.nan, r2_log10=np.nan, sign_errors=0)
        return out
    rel = abs_err[m] / np.abs(ref[m])
    lp = np.log10(np.maximum(np.abs(pred[m]), 1e-300))
    lr = np.log10(np.abs(ref[m]))
    ss_res = np.sum((lp - lr) ** 2)
    ss_tot = np.sum((lr - lr.mean()) ** 2)
    out.update(
        median_err_pct=float(np.median(rel) * 100),
        p95_err_pct=float(np.percentile(rel, 95) * 100),
        mean_err_pct=float(np.mean(rel) * 100),
        max_err_pct=float(np.max(rel) * 100),
        bias_pct=float(np.median(pred[m] / ref[m] - 1) * 100),
        r2_log10=float(1 - ss_res / ss_tot) if ss_tot > 0 else np.nan,
        sign_errors=int(np.sum(np.sign(pred[m]) != np.sign(ref[m]))),
    )
    return out
