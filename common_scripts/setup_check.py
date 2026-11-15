"""Phase-2 environment and setup verification.

Checks: Python packages, ngspice executable/version, model-card nominals,
card patching round-trip, and one nominal-corner simulation per transistor
case (validated output + KCL). Writes logs/setup_check.json.

Run:  python -m common_scripts.setup_check      (from the project root)
"""
from __future__ import annotations

import importlib
import json
import platform
import sys
from datetime import datetime

from common_scripts.config import config_path, load_config, general_path, layer_path
from common_scripts.model_card import check_nominals, patch_card, read_card, get_params
from common_scripts.netlists import CARD_NAME, TRANSISTOR_OUTPUTS, transistor_netlist
from common_scripts.spice_runner import ngspice_version, run_netlist

REQUIRED = ["numpy", "pandas", "matplotlib", "sklearn", "scipy", "joblib"]


def main() -> int:
    cfg = load_config()
    report = {"time": datetime.now().isoformat(timespec="seconds"),
              "python": sys.version.split()[0], "platform": platform.platform(),
              "checks": {}}
    ok_all = True

    def record(name, ok, detail):
        nonlocal ok_all
        ok_all &= bool(ok)
        report["checks"][name] = {"status": "PASS" if ok else "FAIL", "detail": detail}
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    # 1. packages
    vers = {}
    for p in REQUIRED:
        try:
            vers[p] = importlib.import_module(p).__version__
        except Exception as e:  # noqa: BLE001
            vers[p] = f"MISSING ({e})"
    record("python_packages", all("MISSING" not in v for v in vers.values()), vers)

    # 2. ngspice
    try:
        record("ngspice", True, {"path": str(config_path("ngspice")), "version": ngspice_version()})
    except Exception as e:  # noqa: BLE001
        record("ngspice", False, str(e))
        return 1

    # 3. model card nominals
    try:
        record("model_card_nominals", True, check_nominals())
    except Exception as e:  # noqa: BLE001
        record("model_card_nominals", False, str(e))

    # 4. patch round-trip: +10% on every param, NMOS and PMOS independently
    try:
        nom = check_nominals()
        new = {d: {p: v * 1.1 for p, v in nom[d].items()} for d in nom}
        txt = patch_card(read_card(), new)
        back = {d: get_params(txt, d) for d in nom}
        untouched = read_card().replace(" ", "") != txt.replace(" ", "")
        only_n = patch_card(read_card(), {"nmos": new["nmos"]})
        pmos_kept = get_params(only_n, "pmos") == nom["pmos"]
        record("model_card_patch", untouched and pmos_kept,
               {"patched_values": back, "pmos_unchanged_when_only_nmos_patched": pmos_kept})
    except Exception as e:  # noqa: BLE001
        record("model_card_patch", False, str(e))

    # 5. one nominal simulation per case
    vdd = cfg["technology"]["vdd_nominal"]
    tech = cfg["technology"]
    card = read_card()
    sims = {}
    for case, c in cfg["part_a"]["cases"].items():
        s = {"vdd": vdd, "temp": 27.0, "w": 2 * tech["lmin"],
             "vg": vdd if c["vg"] == "vdd" else 0.0, "vb": vdd if c["vb"] == "vdd" else 0.0}
        # drain/source chosen so the channel is biased in the conducting direction
        s["vd"], s["vs"] = (vdd, 0.0) if c["device"] == "nmos" else (0.0, vdd)
        res = run_netlist(transistor_netlist(case, c["device"], s), list(TRANSISTOR_OUTPUTS),
                          extra_files={CARD_NAME: card})
        if not res.ok:
            sims[case] = {"ok": False, "error": res.error}
            record(f"sim_{case}", False, res.error)
            continue
        v = res.values
        ksum = sum(v.values())
        kmax = max(abs(x) for x in v.values())
        tol = cfg["metrics"]["kcl_abs_tol_a"] + cfg["metrics"]["kcl_rel_tol"] * kmax
        sims[case] = {**v, "kcl_sum": ksum, "kcl_tol": tol}
        record(f"sim_{case}", abs(ksum) <= tol,
               {k: f"{x:.6e}" for k, x in {**v, "kcl_sum": ksum}.items()})

    report["overall"] = "PASS" if ok_all else "FAIL"
    out = general_path("logs", "setup_check.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nOVERALL: {report['overall']}  ->  {out}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
