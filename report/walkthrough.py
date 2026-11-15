"""Build report/Project_Walkthrough.pdf: the project told step by step, from the
first script to the final report - which script was written, how it was run,
which files it produced, what the results were, and which problems were found
and fixed on the way.

Current results are read from the output files. The few numbers from earlier
iterations (before a fix was made) are recorded in EARLIER below; they were
measured during development and are labelled as such in the PDF.

Run (from the repository root):  python -m report.walkthrough [--preview DIR]
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from report.file_guide import ACCENT, INK, INK2, RULE, SHADE, Pdf, plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "report" / "Project_Walkthrough.pdf"
L1, L2, L3, RP = ROOT / "layer1", ROOT / "layer2", ROOT / "layer3", ROOT / "report"

# Results of earlier iterations, measured during development (not reproducible from the
# final files because the fixes replaced them).
EARLIER = {
    "gate_direct_median": 7.2,          # gate median error, plain VDD-rail sum, before KCL closure
    "gate_kcl_median_before_igc": 1.9,  # gate median error with KCL closure, before Igc reformulation
    "gate_mean_acc_before_igc": 94.83,  # gate mean accuracy before Igc reformulation
    "and2_or2_acc_before_igc": "87-89",
    "input_current_err_before_igc": "18-21",
    "and2_nonconverged": 8, "and2_false_converged": 5,
    "old_kcl_rel_err": 9,               # KCL residual with ngspice's default 6-digit print
}


class Walk(Pdf):
    FOOTER = "Project walkthrough"

    def image(self, path: Path, caption: str, width_frac: float = 1.0):
        img = plt.imread(path)
        w = self.width * width_frac
        h = w * img.shape[0] / img.shape[1]
        h_max = 5.2
        if h > h_max:
            w, h = w * h_max / h, h_max
        self.need(h + 0.35)
        x = self.L + (self.width - w) / 2
        ax = self.fig.add_axes([x / self.W, 1 - (self.y + h) / self.H, w / self.W, h / self.H])
        ax.imshow(img)
        ax.axis("off")
        self.y += h + 0.06
        for line in self.wrap(caption, 8, self.width - 0.4):
            self._txt(self.L + 0.2, line, 8, INK2, style="italic")
            self.y += 8 / 72 * 1.4
        self.y += 0.12

    def step(self, n, title):
        self.need(1.3)
        self.y += 0.12
        top = self.y
        self.fig.add_artist(Rectangle((self.L / self.W, 1 - (top + 0.36) / self.H), self.width / self.W,
                                      0.36 / self.H, transform=self.fig.transFigure, color=ACCENT, lw=0))
        self.y += 0.08
        self._txt(self.L + 0.1, f"STEP {n}", 11, "white", "bold")
        self._txt(self.L + 0.95, title, 11, "white", "bold")
        self.y += 0.4

    def kv(self, rows):
        for k, v in rows:
            if not v:
                continue
            lines = self.wrap(v, 9, self.width - 1.25)
            self.need(len(lines) * 9 / 72 * 1.42 + 0.05)
            self._txt(self.L + 0.05, k, 8.6, ACCENT, "bold")
            for line in lines:
                mono = k in ("Command",)
                self._txt(self.L + 1.2, line, 9, INK, family="monospace" if mono else "sans-serif")
                self.y += 9 / 72 * 1.42
            self.y += 0.04
        self.y += 0.05

    def box(self, title, text, color="#fff4e5", edge="#e8a33d"):
        lines = self.wrap(text, 8.8, self.width - 0.35)
        h = 0.3 + len(lines) * 8.8 / 72 * 1.42 + 0.1
        self.need(h)
        top = self.y
        self.fig.add_artist(Rectangle((self.L / self.W, 1 - (top + h) / self.H), self.width / self.W, h / self.H,
                                      transform=self.fig.transFigure, color=color, lw=0))
        self.fig.add_artist(Rectangle((self.L / self.W, 1 - (top + h) / self.H), 0.05 / self.W, h / self.H,
                                      transform=self.fig.transFigure, color=edge, lw=0))
        self.y += 0.08
        self._txt(self.L + 0.18, title, 9, INK, "bold")
        self.y += 0.22
        for line in lines:
            self._txt(self.L + 0.18, line, 8.8, INK)
            self.y += 8.8 / 72 * 1.42
        self.y = top + h + 0.12

    def table(self, header, rows, widths, size=8.4):
        tot = sum(widths)
        xs = np.cumsum([0] + [w / tot * self.width for w in widths])
        rh = size / 72 * 1.75
        self.need(rh * (len(rows) + 1) + 0.1)
        top = self.y
        self.fig.add_artist(Rectangle((self.L / self.W, 1 - (top + rh) / self.H), self.width / self.W, rh / self.H,
                                      transform=self.fig.transFigure, color=ACCENT, lw=0))
        self.y += 0.04
        for x, h in zip(xs, header):
            self._txt(self.L + x + 0.05, h, size, "white", "bold")
        self.y = top + rh
        for i, r in enumerate(rows):
            if i % 2:
                self.fig.add_artist(Rectangle((self.L / self.W, 1 - (self.y + rh) / self.H), self.width / self.W,
                                              rh / self.H, transform=self.fig.transFigure, color="#f3f3f3", lw=0))
            self.y += 0.04
            for x, v in zip(xs, r):
                bold = str(r[0]).startswith("ALL") or str(r[0]).startswith("Overall")
                self._txt(self.L + x + 0.05, str(v), size, INK, "bold" if bold else "normal")
            self.y += rh - 0.04
        self.y += 0.15


def pct(x, d=2):
    return f"{x:.{d}f} %"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path)
    args = ap.parse_args()

    cfg = json.loads((ROOT / "project_config.json").read_text())
    setup = json.loads((ROOT / "logs" / "setup_check.json").read_text())
    ngspice = setup["checks"]["ngspice"]["detail"]["version"]
    dc = pd.read_csv(L1 / "outputs" / "data_check.csv").set_index("case")
    cmp_ = pd.read_csv(L1 / "outputs" / "model_comparison_table.csv")
    sel = pd.read_csv(L1 / "outputs" / "selected_component_models.csv")
    test = pd.read_csv(L1 / "outputs" / "test_metrics.csv").dropna(subset=["median_err_pct"])
    corners = pd.read_csv(L2 / "data" / "raw" / "corners.csv")
    n_gate = sum(len(pd.read_csv(p, usecols=["corner_id"])) for p in (L2 / "data" / "raw").glob("part_b_spice_*.csv"))
    gate = pd.read_csv(L2 / "outputs" / "gate_results_table.csv", dtype={"inputs": str})
    oracle = pd.read_csv(L2 / "outputs" / "oracle_check.csv")
    cover = pd.read_csv(L2 / "outputs" / "operating_point_coverage.csv")
    csum = pd.read_csv(L3 / "data" / "raw" / "part_c_spice_summary.csv", usecols=["corner_id"])
    cres = pd.read_csv(L3 / "data" / "results" / "part_c_results.csv")
    rail = json.loads((L3 / "outputs" / "rail_deviation.json").read_text())
    speed = None
    log = L1 / "logs" / "part_a_spice_run.log"
    if log.exists():
        m = re.findall(r"\((\d+) sims/s\)", log.read_text(errors="ignore"))
        speed = int(np.median([int(x) for x in m])) if m else None

    acc = lambda p, s: 100 - np.mean(np.abs(p / s - 1)) * 100  # noqa: E731
    g_all = gate[gate.gate == "ALL"].iloc[0]
    acc_a = (100 - test.mean_err_pct).mean()
    acc_b = 100 - g_all.mean_err_pct
    acc_c_spec, acc_c_ceil = acc(cres.ml_leak, cres.spice_leak), acc(cres.spice_gate_sum, cres.spice_leak)
    acc_c_load, acc_c_lceil = acc(cres.ml_leak_loaded, cres.spice_leak), acc(cres.spice_gate_sum_loaded, cres.spice_leak)

    d = Walk(OUT, args.preview)
    d.title("Project Walkthrough", [
        "ML-Driven PVT Variation-Aware Leakage Estimation",
        "Team Watt the leak  |  32 nm LP  |  VDD 0.9 V  |  3-bit CLA",
        "Step by step from the first script to the final report: what was written, how it was run, "
        f"which files it produced and what the results were.  ({date.today():%d %b %Y})"])

    d.h1("The idea in one paragraph")
    d.para("Running SPICE for every process, voltage and temperature (PVT) condition is slow. The project "
           "replaces it with machine-learning models of single transistors. First thousands of single "
           "NMOS/PMOS transistors are simulated in ngspice and four ML models are trained on them (Part A, "
           "layer1). Then the models predict the leakage of logic gates and are checked against SPICE "
           "(Part B, layer2). Finally the gate predictions are combined into a complete 3-bit adder and "
           "checked against SPICE of the full circuit (Part C, layer3).")
    d.h2("Final results")
    d.table(["Level", "What is compared", "Mean accuracy"], [
        ["Part A", "transistor currents, test set", pct(acc_a)],
        ["Part B", f"18 gate/input cases x {len(corners)} corners", pct(acc_b)],
        ["Part C (spec method)", "3-bit CLA, sum of gate leakages", pct(acc_c_spec)],
        ["Part C (+ loading)", "3-bit CLA, + loading gate tunnelling", pct(acc_c_load)],
    ], [1.4, 3.0, 1.2])
    d.para("Mean accuracy = 100 % minus the mean relative error |ML - SPICE| / SPICE.", size=8.5, color=INK2)

    # ------------------------------------------------------------------ step 0
    d.new_page()
    d.h1("Phase 0 - Getting ready")
    d.step(0, "Check the tools and the model card")
    d.kv([("Script", "common_scripts/setup_check.py (uses config.py, model_card.py, spice_runner.py, netlists.py)"),
          ("Command", "python -m common_scripts.setup_check"),
          ("What it does", "Checks the Python packages, finds ngspice, parses the five process parameters from "
                           "32nm_LP.pm and compares them with the assignment sheet, tests that the card can be "
                           "patched for NMOS and PMOS separately, and runs one nominal simulation per "
                           "transistor case."),
          ("Produced", "logs/setup_check.json"),
          ("Result", f"OVERALL PASS. Simulator {ngspice}, Python {setup['python']}. All four nominal "
                     "simulations satisfy KCL (sum of the four terminal currents ~1e-16 A).")])
    d.box("Problem found and fixed",
          "ngspice's default print keeps only ~6 significant digits, which produced artificial KCL errors of "
          f"up to {EARLIER['old_kcl_rel_err']} % in an older dataset. All netlists now use 'set numdgt=15'. "
          "We also found that when a gate or body node sits at VDD, ngspice can resolve the current through "
          "the card's gate/body resistors only to about 4e-16 A - so such tiny values are treated as "
          "round-off, never as signal.")

    # ------------------------------------------------------------------ Part A
    d.h1("Part A - Transistors and ML models (layer1)")
    d.step(1, "Draw the random input samples")
    d.kv([("Script", "layer1/scripts/generate_samples.py"),
          ("Command", "python -m layer1.scripts.generate_samples"),
          ("What it does", "For each case (NMOS ON, NMOS OFF, PMOS ON, PMOS OFF) draws 10,000 samples: VDD "
                           "first (0.81-0.99 V), then Vd and Vs uniform 0..VDD, width 32-256 nm, temperature "
                           "-40..125 C and vth0/toxe/ndep/u0/xj at +/-10 % of the NMOS or PMOS nominal. Vg and "
                           "Vb are fixed by the case. Fixed seeds."),
          ("Produced", "layer1/data/raw/<case>_samples.csv  (4 files x 10,000 rows)"),
          ("Result", "40,000 input points, ready to simulate.")])
    d.step(2, "Simulate every sample in ngspice")
    d.kv([("Script", "layer1/scripts/generate_spice_data.py"),
          ("Command", "python -m layer1.scripts.generate_spice_data"),
          ("What it does", "For every sample: writes a private copy of the model card with only that sample's "
                           "five parameters changed (NMOS or PMOS block), builds a netlist with its own voltage "
                           "source on every terminal and the mandatory .options, runs ngspice, checks the "
                           "output and saves the four terminal currents plus BSIM4's internal current "
                           "components. Runs 12 simulations in parallel and can resume after interruption."),
          ("Produced", "layer1/data/raw/<case>_spice_raw.csv, layer1/data/processed/<case>.csv (the four "
                       "deliverable datasets, exact spec columns), layer1/spice/<case>.sp + card (examples)"),
          ("Result", f"{int(dc.rows.sum()):,} / 40,000 simulations succeeded, "
                     f"{int(dc.failed_simulations_logged.sum())} failed"
                     + (f", about {speed} simulations per second." if speed else "."))])
    d.step(3, "Check the data")
    d.kv([("Script", "layer1/scripts/validate_data.py"),
          ("Command", "python -m layer1.scripts.validate_data"),
          ("What it does", "Checks missing values, duplicates, ranges and Kirchhoff's current law "
                           "(id+ig+is+ib = 0) for every sample; verifies that the terminal currents equal the "
                           "sum of BSIM4's internal components; draws the three trend plots."),
          ("Produced", "layer1/outputs/data_check.csv/.json, kcl_residuals.png, trend_off_current_vs_temp.png, "
                       "trend_off_current_vs_vth0.png, trend_gate_current_vs_toxe.png"),
          ("Result", f"0 missing, 0 duplicates, 0 out of range, {int(dc.kcl_violations.sum())} KCL violations "
                     f"(largest residual {dc.kcl_max_abs_sum_A.max():.1e} A). Terminal currents = sum of the "
                     "7 BSIM4 components to machine precision - the basis of the ML model.")])
    d.image(L1 / "outputs" / "trend_off_current_vs_temp.png",
            "Trend: OFF current rises ~2.5 decades from -40 to 125 C (coloured points = textbook bias).", 0.92)
    d.step(4, "Train, compare and select the ML models")
    d.kv([("Script", "layer1/scripts/train_models.py  (model definition in common_scripts/transistor_model.py)"),
          ("Command", "python -m layer1.scripts.train_models"),
          ("What it does", "Splits each dataset 70/15/15 (seed 42). Instead of the raw currents (15 decades, "
                           "sign changes) it learns 7 smooth physical components in log form and rebuilds the "
                           "terminal currents from them. Four model types are trained on every component: "
                           "polynomial ridge, random forest, gradient boosting, MLP (3-seed ensemble). The best "
                           "type per component is chosen on the validation set; the test set is scored once "
                           "at the end."),
          ("Produced", "layer1/models/<case>_model.joblib  (THE 4 MODELS), data/processed/splits/*, "
                       "outputs/model_comparison_table.csv, selected_component_models.csv, test_metrics.csv, "
                       "predictions_test_<case>.csv"),
          ("Result", "MLP best overall; polynomial ridge best for the OFF channel current (the main leakage "
                     "term). Test-set mean accuracy " + pct(acc_a) + " over all terminals.")])
    rows = []
    for case in ["nmos_on", "nmos_off", "pmos_on", "pmos_off"]:
        r = cmp_[cmp_.case == case].set_index("model")
        rows.append([case.replace("_", " ").upper()] + [pct(r.loc[m, "p95_err_pct_mean"], 1)
                                                       for m in ["poly_ridge", "rf", "hgb", "mlp"]])
    d.table(["Case (validation P95 error)", "Poly ridge", "Random forest", "Grad. boosting", "MLP"], rows,
            [2.0, 1.0, 1.1, 1.1, 0.9])
    d.step(5, "Plot the Part A results")
    d.kv([("Script", "layer1/scripts/plot_results.py"), ("Command", "python -m layer1.scripts.plot_results"),
          ("Produced", "layer1/outputs/parity_<case>.png, error_cdf_test.png, model_comparison.png"),
          ("Result", "Predictions lie on the diagonal for every terminal; OFF-device ID median error "
                     f"{test[(test.case == 'nmos_off') & (test.terminal == 'id')].median_err_pct.iloc[0]:.3f} %.")])
    d.image(L1 / "outputs" / "parity_nmos_off.png", "NMOS OFF: ML vs SPICE on the test set (log axes).", 0.72)

    # ------------------------------------------------------------------ Part B
    d.h1("Part B - Logic gates (layer2)")
    d.step(6, "Draw the 200 PVT corners")
    d.kv([("Script", "layer2/scripts/generate_corners.py"), ("Command", "python -m layer2.scripts.generate_corners"),
          ("What it does", "One corner = VDD, temperature, NMOS width, PMOS width, one NMOS and one PMOS draw of "
                           "the five process parameters. Seed 31415. Shared with Part C."),
          ("Produced", "layer2/data/raw/corners.csv"), ("Result", f"{len(corners)} corners.")])
    d.step(7, "SPICE reference for INV, NAND2, NOR2, AND2, OR2")
    d.kv([("Script", "layer2/scripts/simulate_gates.py  (gate topologies in common_scripts/circuits.py)"),
          ("Command", "python -m layer2.scripts.simulate_gates"),
          ("What it does", "Simulates every gate for every input combination at every corner (18 x 200) as a "
                           "complete transistor-level netlist and records the supply current, all node "
                           "voltages and per-transistor details. Each result must pass a physical self-check."),
          ("Produced", "layer2/data/raw/part_b_spice_<gate>.csv, layer2/spice/<gate>.sp + card"),
          ("Result", f"{n_gate:,} / 3,600 valid simulations.")])
    d.box("Problems found and fixed",
          "(1) ngspice treats a node named 'gnd' as ground - the ground rail was renamed 'vss'. "
          f"(2) {EARLIER['and2_nonconverged']} AND2 runs did not converge with gmin = abstol = 1e-18. "
          f"(3) {EARLIER['and2_false_converged']} AND2 runs 'converged' to wrong answers (nodes ~10 uV past "
          "the rail, supply current wrong by up to 230 %). Fix: solver options itl1/itl6 = 1000, pivrel = 0.5 "
          "and a logic-level .nodeset (required tolerances unchanged), plus a self-check that the "
          "transistors' own currents add up to the supply current. After the fix all 3,600 pass.")
    d.step(8, "ML prediction of gate leakage")
    d.kv([("Script", "layer2/scripts/predict_gate_leakage.py  (logic in common_scripts/gate_ml.py)"),
          ("Command", "python -m layer2.scripts.predict_gate_leakage"),
          ("What it does", "For every transistor in every gate takes Vd, Vg, Vs, Vb from the SPICE node "
                           "voltages, picks the ON/OFF model, predicts its currents with the layer1 models and "
                           "computes the current drawn from VDD. ON-transistor channel currents are solved "
                           "from Kirchhoff's law instead of being predicted."),
          ("Produced", "layer2/data/results/part_b_results.csv, part_b_device_predictions.csv, "
                       "layer2/outputs/oracle_check.csv"),
          ("Result", f"The formula fed with SPICE's own per-transistor currents reproduces SPICE to "
                     f"{oracle.oracle_median_rel_diff.median():.0e} (median) - the method is exact.")])
    d.box("Improvement made",
          "An ON transistor carries the leakage at |Vds| ~ 1e-7 V, where conductance x Vds cannot be "
          f"predicted. Summing the ML currents directly gave a {EARLIER['gate_direct_median']} % median error; "
          "closing the ON channels with KCL brought it to "
          f"{EARLIER['gate_kcl_median_before_igc']} %.", color="#e9f5ec", edge="#2e9d57")
    d.step(9, "Compare ML with SPICE")
    d.kv([("Script", "layer2/scripts/compare_gate_results.py"),
          ("Command", "python -m layer2.scripts.compare_gate_results"),
          ("Produced", "layer2/outputs/gate_results_table.csv, gate_parity.png, gate_error_by_case.png, "
                       "gate_error_vs_corner.png, gate_worst_cases.csv"),
          ("Result", f"Mean accuracy {pct(acc_b)}, median error {pct(g_all.median_err_pct)}, P95 "
                     f"{pct(g_all.p95_err_pct)}, no sign errors.")])
    gt = gate[gate.gate != "ALL"].copy()
    gt["acc"] = 100 - gt.mean_err_pct
    best, worst = gt.sort_values("acc").iloc[-1], gt.sort_values("acc").iloc[0]
    d.table(["Gate result", "Case", "Mean accuracy"],
            [["Best", f"{best.gate} {best.inputs}", pct(best.acc)], ["Worst", f"{worst.gate} {worst.inputs}", pct(worst.acc)],
             ["Overall (3,600)", "all 18 cases", pct(acc_b)]], [1.5, 2.5, 1.6])
    d.image(L2 / "outputs" / "gate_parity.png", "Gate parity plot: ML vs SPICE for all gate simulations.", 0.62)
    d.step(10, "Find where the gate error comes from")
    d.kv([("Script", "layer2/scripts/error_attribution.py"), ("Command", "python -m layer2.scripts.error_attribution"),
          ("What it does", "Replaces one transistor model at a time by SPICE's exact currents and measures how "
                           "much the gate error drops; counts how many training samples lie near the real gate "
                           "operating points."),
          ("Produced", "layer2/outputs/error_attribution.csv, operating_point_coverage.csv"),
          ("Result", "The ON-transistor gate-tunnelling models cause most of the error. Gate transistors sit at "
                     "the rail corners (Vd, Vs = 0 or VDD) where only "
                     f"{int(cover.min_training_samples_within_2pct.min())}-"
                     f"{int(cover.median_training_samples_within_2pct.max())} of 10,000 training samples lie.")])
    d.box("Improvement made (back to Step 4)",
          f"Before this step the gates were at {EARLIER['gate_mean_acc_before_igc']} % mean accuracy (AND2/OR2 "
          f"~{EARLIER['and2_or2_acc_before_igc']} %, ML input currents {EARLIER['input_current_err_before_igc']} % "
          "low). In BSIM4 the gate-tunnelling current depends on the gate-source bias, not on the drain, so the "
          "model was changed to learn the TOTAL tunnelling current without drain inputs plus its source/drain "
          "share. The training data did not change. Steps 4, 5, 8 and 9 were re-run: gates rose to "
          f"{pct(acc_b)}.", color="#e9f5ec", edge="#2e9d57")

    # ------------------------------------------------------------------ Part C
    d.h1("Part C - 3-bit carry-lookahead adder (layer3)")
    d.step(11, "SPICE of the complete adder")
    d.kv([("Script", "layer3/scripts/simulate_test_circuit.py  (adder structure in common_scripts/cla.py)"),
          ("Command", "python -m layer3.scripts.simulate_test_circuit"),
          ("What it does", "Builds the adder only from INV/NAND2/NOR2/AND2/OR2 (39 gates, 186 transistors; "
                           "XOR = 4 NAND2; lookahead carries from AND2/OR2), checks its logic for all 64 "
                           "inputs, and simulates the full netlist for 64 input vectors x the same 200 corners. "
                           "Every run passes the self-check and an output-logic check."),
          ("Produced", "layer3/data/raw/part_c_spice_summary.csv (in git), part_c_spice.csv (370 MB, local "
                       "only), layer3/spice/cla3.sp + card"),
          ("Result", f"{len(csum):,} / 12,800 valid simulations, 0 failures.")])
    d.step(12, "Hierarchical ML prediction")
    d.kv([("Script", "layer3/scripts/predict_circuit_leakage.py"),
          ("Command", "python -m layer3.scripts.predict_circuit_leakage"),
          ("What it does", "For each input vector: logic-simulates the adder to find every gate's inputs, takes "
                           "that gate's ML leakage from Part B at the same corner, and sums the 39 gates (the "
                           "spec method). Also computes a loading-aware version that adds the gate-tunnelling "
                           "current drawn by gate inputs held high by another gate."),
          ("Produced", "layer3/data/results/part_c_results.csv")])
    d.step(13, "Compare the adder with SPICE")
    d.kv([("Script", "layer3/scripts/compare_circuit_results.py"),
          ("Command", "python -m layer3.scripts.compare_circuit_results"),
          ("Produced", "layer3/outputs/circuit_results_table.csv, circuit_parity.png, circuit_error_breakdown.png, "
                       "circuit_results_by_vector.csv, circuit_vs_gate_accuracy.csv, rail_deviation.json"),
          ("Result", "See the table: the spec method is limited by loading between gates, not by the ML.")])
    d.table(["3-bit CLA mean accuracy", "Gate values used", "Accuracy"], [
        ["Spec method (sum of gate leakages)", "ML predictions", pct(acc_c_spec)],
        ["Spec method", "perfect SPICE gates (ceiling)", pct(acc_c_ceil)],
        ["+ loading gate tunnelling", "ML predictions", pct(acc_c_load)],
        ["+ loading gate tunnelling", "perfect SPICE gates (ceiling)", pct(acc_c_lceil)],
    ], [2.6, 2.2, 1.0])
    d.box("Why loading gate tunnelling had to be added",
          "Every gate input draws a small tunnelling current (1.6 nm oxide). In the isolated gate simulations "
          "that current came from an ideal input source and was not counted. Inside the adder, an input held at "
          "logic 1 gets it from the driving gate's VDD, so it is part of the circuit leakage. Even perfect gate "
          f"values reach only {pct(acc_c_ceil)} with the plain sum; adding the loading current gives "
          f"{pct(acc_c_load)} with ML and {pct(acc_c_lceil)} with exact SPICE gates. The other spec assumption "
          f"(inputs exactly at 0 / VDD) was checked: gate outputs are within {rail['median_uV']:.2f} uV "
          f"(median) / {rail['max_uV']:.0f} uV (max) of the rails - negligible.")
    d.image(L3 / "outputs" / "circuit_parity.png",
            "Adder parity: spec method (left, below the diagonal = missing loading) vs with loading (right).", 1.0)

    # ------------------------------------------------------------------ report
    d.h1("Finishing - Report and documentation")
    d.step(14, "Report figures and the Word report")
    d.kv([("Script", "report/report_figures.py, report/build_report.py (writer: report/docx_writer.py)"),
          ("Command", "python -m report.report_figures  then  python -m report.build_report"),
          ("Produced", "report/figures/*.png, report/DVD_ML_Leakage_Report.docx"),
          ("Result", "Technical report (deliverable 10) with all required sections; every number is read "
                     "from the result files.")])
    d.step(15, "Guides")
    d.kv([("Script", "report/file_guide.py, report/walkthrough.py"),
          ("Command", "python -m report.file_guide ;  python -m report.walkthrough"),
          ("Produced", "report/File_Guide.pdf (every file explained), report/Project_Walkthrough.pdf (this "
                       "document)")])
    d.h2("Complete run order")
    d.code(["python -m common_scripts.setup_check",
            "python -m layer1.scripts.generate_samples",
            "python -m layer1.scripts.generate_spice_data",
            "python -m layer1.scripts.validate_data",
            "python -m layer1.scripts.train_models",
            "python -m layer1.scripts.plot_results",
            "python -m layer2.scripts.generate_corners",
            "python -m layer2.scripts.simulate_gates",
            "python -m layer2.scripts.predict_gate_leakage",
            "python -m layer2.scripts.compare_gate_results",
            "python -m layer2.scripts.error_attribution",
            "python -m layer3.scripts.simulate_test_circuit",
            "python -m layer3.scripts.predict_circuit_leakage",
            "python -m layer3.scripts.compare_circuit_results",
            "python -m report.report_figures",
            "python -m report.build_report",
            "python -m report.file_guide",
            "python -m report.walkthrough"])
    d.para("All randomness uses fixed seeds (samples 20261115+case, split 42, corners 31415, models 42-44); "
           "the simulation steps resume and skip finished work.", size=8.8, color=INK2)
    d.close()
    print(f"walkthrough -> {OUT}  ({d.page_no} pages)")


if __name__ == "__main__":
    main()
