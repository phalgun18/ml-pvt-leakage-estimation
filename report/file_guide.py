"""Build report/File_Guide.pdf: what every file in the repository is, how it is
made and used, and what it tells you.

The script walks the repository and FAILS if any file has no description, so
the guide stays complete when files are added. (Git internals, __pycache__,
tmp/ scratch and the PDF itself are skipped.)

Run (from the repository root):  python -m report.file_guide
Optional:  --preview DIR   also writes page PNGs for a quick visual check.
"""
from __future__ import annotations

import argparse
import fnmatch
import textwrap
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "report" / "File_Guide.pdf"
SKIP_DIRS = {".git", "__pycache__", "tmp"}
CASES = ["nmos_on", "nmos_off", "pmos_on", "pmos_off"]
GATES = ["inv", "nand2", "nor2", "and2", "or2"]

ACCENT, INK, INK2, RULE, SHADE = "#1F3864", "#111111", "#4a4a4a", "#c9c9c9", "#eef3fa"

# --------------------------------------------------------------------------------------
# Descriptions.  key = path or glob (relative, forward slashes)
#   what  : what the file is
#   made  : which command / step creates it
#   used  : who reads it
#   tells : what you learn from it
# --------------------------------------------------------------------------------------
D: dict[str, dict] = {}


def add(path, what, made="", used="", tells=""):
    D[path] = {"what": what, "made": made, "used": used, "tells": tells}


# ---------------- repository root
add(".gitignore", "Git ignore rules.", "Hand-written.", "git.",
    "Which files are NOT versioned: Python caches, *.log run logs, tmp/ scratch, and the 370 MB "
    "full CLA SPICE file layer3/data/raw/part_c_spice.csv (too big for GitHub, regenerable).")
add("README.md", "Main project documentation.", "Hand-written / updated with the project.", "People.",
    "Assignment values, software setup, folder layout, how every stage is run, how a simulation is "
    "validated, the modelling approach and the final results summary.")
add("requirements.txt", "Python package list with the verified versions.", "Hand-written.",
    "pip install -r requirements.txt.",
    "numpy, pandas, matplotlib, scikit-learn, scipy and joblib versions used; ngspice-46 is an "
    "external program (path in project_config.json).")
add("project_config.json", "THE single settings file for the whole project.", "Hand-written.",
    "Every script, through common_scripts/config.py.",
    "ngspice path, model-card path, nominal VDD 0.9 V and its +/-10 % range, L = 32 nm, W range, "
    "temperature range, the five process parameters and their expected nominals, the mandatory "
    ".options line, solver robustness options, worker count, all random seeds, the 70/15/15 split, "
    "200 corners, the gate list, CLA carry-in and the metric tolerances.")
add("32nm_LP.pm", "The ORIGINAL assigned BSIM4 model card (PTM 32 nm Low Power). Never modified.",
    "Provided by the course (checksum cb3d190c...).",
    "common_scripts/model_card.py reads it and writes a patched private copy for every simulation.",
    "NMOS and PMOS device physics; its vth0/toxe/ndep/u0/xj values are the nominals that are varied "
    "+/-10 %.")
add("logs/setup_check.json", "Result of the environment check.", "python -m common_scripts.setup_check",
    "report/build_report.py (simulator and package versions).",
    "Python and package versions, ngspice version/path, model-card nominal check, patch round-trip "
    "check and one nominal simulation per transistor case with its KCL sum: overall PASS/FAIL.")

# ---------------- common_scripts
add("common_scripts/__init__.py", "Marks common_scripts/ as a Python package (empty).", "", "Python imports.")
add("common_scripts/config.py", "Loads project_config.json and builds all file paths.", "", "Every script.",
    "Defines REPO_ROOT, layer_path(n, ...) for layer1/2/3 files, general_path(...) for root files, "
    "and the VDD / width sampling ranges.")
add("common_scripts/model_card.py", "Reads and patches the BSIM4 model card.", "",
    "All SPICE drivers (layer1/2/3 scripts) and setup_check.",
    "How process variation is applied: only vth0, toxe, ndep, u0, xj are replaced, inside the NMOS "
    "or PMOS block, in a temporary copy; every patched value is re-parsed and verified.")
add("common_scripts/spice_runner.py", "Runs ngspice in batch mode and validates the output.", "",
    "All SPICE drivers.",
    "The acceptance rules for a simulation: exit code 0, no error/non-convergence text, every "
    "requested value printed exactly once and finite. Uses set numdgt=15 (full precision) and the "
    "current sign convention -i(Vx) = current INTO the device terminal.")
add("common_scripts/netlists.py", "Builds the single-transistor netlists (Part A).", "",
    "layer1/scripts/generate_spice_data.py, setup_check.",
    "Netlist structure: one voltage source per terminal, literal values, mandatory .options, "
    ".temp, and the printed outputs (4 terminal currents + BSIM4 diagnostic components).")
add("common_scripts/circuits.py", "Static-CMOS gates as transistor lists + generic circuit netlist writer.",
    "", "layer2 (gates) and layer3 (CLA) SPICE drivers and the ML gate code.",
    "Exact topology of INV, NAND2, NOR2, AND2 (NAND2+INV), OR2 (NOR2+INV), which input drives which "
    "transistor, the 'vss' ground rail, convergence options and .nodeset.")
add("common_scripts/cla.py", "The 3-bit carry-lookahead adder built from the five gate types.", "",
    "layer3 scripts.",
    "Gate-level structure (39 gates: 24 NAND2, 9 AND2, 6 OR2; 186 transistors), XOR = 4 NAND2, "
    "lookahead carry equations, logic simulation of all 64 input vectors.")
add("common_scripts/transistor_model.py", "The physics-informed ML transistor model (feature + target "
    "definition, inference).", "", "layer1 training; layer2/layer3 predictions.",
    "How the 4 terminal currents are built from 7 BSIM4 components, the 19 input features, the "
    "log-normalised targets, sign rules, and predict_currents(): the one function every layer uses "
    "to call the trained models.")
add("common_scripts/gate_ml.py", "ML leakage of a gate/circuit from the transistor models.", "",
    "layer2 prediction/attribution, layer3 simulation self-check.",
    "Maps node voltages to each transistor's Vd/Vg/Vs/Vb, picks the ON/OFF model, computes supply "
    "leakage with KCL-closed ON channels, and the SPICE physical self-check.")
add("common_scripts/metrics.py", "Error metrics used everywhere.", "", "All compare / train scripts.",
    "Definitions: relative error, median, P95, mean, bias, R2 on log10|I|, sign errors and the "
    "1e-15 A evaluation floor.")
add("common_scripts/plotting.py", "Shared matplotlib style (colours, fonts, saving).", "", "All plotting code.",
    "Nothing numeric; keeps all figures visually consistent.")
add("common_scripts/setup_check.py", "Environment / installation check.", "Run it: python -m common_scripts.setup_check",
    "You, before running anything.", "Writes logs/setup_check.json; PASS means Python, packages, ngspice "
    "and the model card are all usable.")

# ---------------- layer1 (Part A)
add("layer1/scripts/__init__.py", "Package marker (empty).", "", "Python imports.")
add("layer1/scripts/generate_samples.py", "STEP A1: draws the random input samples.",
    "Run: python -m layer1.scripts.generate_samples", "generate_spice_data.py.",
    "Creates layer1/data/raw/<case>_samples.csv (10,000 per case, seeded).")
add("layer1/scripts/generate_spice_data.py", "STEP A2: simulates every sample in ngspice (40,000 runs, parallel, "
    "resumable).", "Run: python -m layer1.scripts.generate_spice_data", "-",
    "Creates <case>_spice_raw.csv, the 4 deliverable datasets in data/processed/, the example "
    "netlists in layer1/spice/ and failure logs (none occurred).")
add("layer1/scripts/validate_data.py", "STEP A3: data check.", "Run: python -m layer1.scripts.validate_data", "-",
    "Missing/duplicate/out-of-range checks, KCL check, decomposition check, and the three trend plots.")
add("layer1/scripts/train_models.py", "STEP A4: trains and selects the ML models -> PRODUCES THE MODEL FILES.",
    "Run: python -m layer1.scripts.train_models", "-",
    "Creates layer1/models/<case>_model.joblib, the train/val/test splits, the model comparison "
    "tables and the test-set metrics.")
add("layer1/scripts/plot_results.py", "STEP A5: Part A result plots.", "Run: python -m layer1.scripts.plot_results",
    "-", "Parity plots, error CDF and model comparison chart in layer1/outputs/.")

for c in CASES:
    C = c.replace("_", " ").upper()
    add(f"layer1/spice/{c}.sp", f"Example single-transistor netlist, {C} (sample 1 of the dataset).",
        "generate_spice_data.py", "Deliverable 2; can be run by hand: ngspice -b " + f"{c}.sp",
        "What exactly is simulated: 4 terminal sources, the transistor card line, mandatory .options, "
        "temperature and the printed currents.")
    add(f"layer1/spice/{c}_card.pm", f"Patched model-card copy used by {c}.sp.", "generate_spice_data.py",
        f"Included by {c}.sp.", "The original card with this sample's 5 process-parameter values.")
    add(f"layer1/data/raw/{c}_samples.csv", f"Random INPUTS for {C} (10,000 rows, no currents).",
        "generate_samples.py", "generate_spice_data.py.",
        "Columns sample_id, vdd, temp, w, vd, vs, vg, vb, vth0, toxe, ndep, u0, xj.")
    add(f"layer1/data/raw/{c}_spice_raw.csv", f"Full SPICE results for {C}: inputs + terminal currents + "
        "BSIM4 diagnostic components (x_*).", "generate_spice_data.py",
        "train_models.py, validate_data.py (needs the x_* columns).",
        "Per sample: id, ig, is, ib and the internal components (channel, junctions, gate tunnelling, "
        "impact ionisation, vth) used as physics-informed training targets.")
    add(f"layer1/data/processed/{c}.csv", f"DELIVERABLE 1: the {C} dataset in the required format.",
        "generate_spice_data.py", "validate_data.py, error_attribution.py, you / graders.",
        "Exactly the 16 spec columns vdd, temp, w, vd, vs, vg, vb, vth0, toxe, ndep, u0, xj, id, ig, is, "
        "ib for 10,000 samples.")
    add(f"layer1/data/processed/splits/{c}_split.csv", f"Train/validation/test label of every {C} sample.",
        "train_models.py (seed 42)", "train_models.py.", "sample_id -> train (7,000) / val (1,500) / test (1,500).")
    add(f"layer1/models/{c}_model.joblib", f"TRAINED ML MODEL for {C} (deliverable 5).",
        "python -m layer1.scripts.train_models",
        "layer2 and layer3 predictions (through common_scripts/transistor_model.predict_currents).",
        "A bundle: one fitted regressor per learned component (MLP ensembles / polynomial ridge / "
        "HGB as selected), feature definition, selection info and metadata.")
    add(f"layer1/outputs/parity_{c}.png", f"Predicted vs SPICE plot, {C}, test set (deliverable 5).",
        "plot_results.py", "Report.", "One log-log panel per terminal with median / P95 error; points on "
        "the diagonal = accurate.")
    add(f"layer1/outputs/predictions_test_{c}.csv", f"Test-set predictions, {C}.", "train_models.py",
        "plot_results.py.", "Inputs, SPICE id..ib and ML id_pred..ib_pred for the 1,500 test samples.")

add("layer1/outputs/data_check.csv", "DELIVERABLE 3: data-check summary (one row per case).", "validate_data.py",
    "Report.", "Rows, failures, missing, duplicates, out-of-range, KCL violations/residuals, counts below "
    "1e-15 A, decomposition residuals, sign-rule agreement.")
add("layer1/outputs/data_check.json", "Same data check, with the per-parameter out-of-range breakdown.",
    "validate_data.py", "-", "Detailed version of data_check.csv.")
add("layer1/outputs/kcl_residuals.png", "Histogram of |id+ig+is+ib| per sample.", "validate_data.py", "Report.",
    "KCL holds to ~1e-15 A (solver round-off) for all 40,000 samples.")
add("layer1/outputs/trend_off_current_vs_temp.png", "Trend plot: OFF current vs temperature (deliverable 3).",
    "validate_data.py", "Report.", "~2.5 decades increase from -40 to 125 C (subthreshold physics).")
add("layer1/outputs/trend_off_current_vs_vth0.png", "Trend plot: OFF current vs vth0 (deliverable 3).",
    "validate_data.py", "Report.", "Lower |vth0| -> more leakage (~1 decade over +/-10 %).")
add("layer1/outputs/trend_gate_current_vs_toxe.png", "Trend plot: gate current vs toxe (deliverable 3).",
    "validate_data.py", "Report.", "Thinner oxide -> exponentially more gate tunnelling (~1.5 decades).")
add("layer1/outputs/model_comparison_table.csv", "DELIVERABLE 4: 4 model types x 4 cases on validation.",
    "train_models.py", "Report.", "Mean R2 (log), median and P95 error per case and model type.")
add("layer1/outputs/model_comparison_validation.csv", "Model comparison per terminal.", "train_models.py",
    "model_comparison_table.csv.", "Full metrics for every case x model x terminal.")
add("layer1/outputs/component_fit_validation.csv", "Validation error of every learned component.",
    "train_models.py", "Selection of the final model per component.",
    "Log-RMSE / median log error per case x model type x component.")
add("layer1/outputs/selected_component_models.csv", "Which model type was chosen for each component.",
    "train_models.py", "Report.", "e.g. polynomial ridge for the OFF channel current, MLP for the rest.")
add("layer1/outputs/selected_model_validation.csv", "Validation metrics of the final (selected) models.",
    "train_models.py", "-", "Per case and terminal, before the test set is touched.")
add("layer1/outputs/test_metrics.csv", "DELIVERABLE 5: test-set metrics of the chosen models.", "train_models.py",
    "Report.", "Per case and terminal: R2, median / P95 / mean error, bias, sign errors, samples below 1e-15 A.")
add("layer1/outputs/hyperparameters.json", "Hyperparameters of the four model types.", "train_models.py",
    "Report.", "poly_ridge, random forest, hist-gradient-boosting and MLP settings.")
add("layer1/outputs/error_cdf_test.png", "Cumulative test-error curves per terminal.", "plot_results.py",
    "Report.", "Fraction of samples below any error level (dashed line = 1 %).")
add("layer1/outputs/model_comparison.png", "Bar chart of the model comparison.", "plot_results.py", "Report.",
    "Validation P95 error per case and model type (lower is better).")
add("layer1/logs/part_a_spice_run.log", "Console log of the 40,000-simulation run (not in git).",
    "generate_spice_data.py", "You.", "Progress, speed (~150 sims/s), ok/failed counts per case.")
add("layer1/logs/part_a_train.log", "Console log of model training (not in git).", "train_models.py", "You.",
    "Validation comparison, selected models, test metrics as printed during training.")
add("layer1/logs/part_a_validate.log", "Console log of the data check (not in git).", "validate_data.py",
    "You.", "Printed data-check table.")
add("layer1/logs/part_a_*_failures.csv", "Failed transistor simulations (only created if a run fails).",
    "generate_spice_data.py", "You.", "sample_id, time and error message; none occurred.")

# ---------------- layer2 (Part B)
add("layer2/scripts/__init__.py", "Package marker (empty).", "", "Python imports.")
add("layer2/scripts/generate_corners.py", "STEP B1: draws the 200 PVT corners (shared with Part C).",
    "Run: python -m layer2.scripts.generate_corners", "-", "Creates layer2/data/raw/corners.csv.")
add("layer2/scripts/simulate_gates.py", "STEP B2: SPICE reference for 5 gates x all inputs x 200 corners "
    "(3,600 runs).", "Run: python -m layer2.scripts.simulate_gates", "-",
    "Creates part_b_spice_<gate>.csv and the example gate netlists; every run passes the physical self-check.")
add("layer2/scripts/predict_gate_leakage.py", "STEP B3: ML gate leakage from the 4 layer1 models.",
    "Run: python -m layer2.scripts.predict_gate_leakage", "-",
    "Creates part_b_results.csv, part_b_device_predictions.csv and oracle_check.csv.")
add("layer2/scripts/compare_gate_results.py", "STEP B4: ML vs SPICE comparison for gates.",
    "Run: python -m layer2.scripts.compare_gate_results", "-",
    "Creates the gate results table, parity plot, error plots and worst-case list.")
add("layer2/scripts/error_attribution.py", "STEP B5: which transistor model causes the gate error.",
    "Run: python -m layer2.scripts.error_attribution", "-",
    "Creates error_attribution.csv and operating_point_coverage.csv.")
for g in GATES:
    G = g.upper()
    add(f"layer2/spice/{g}.sp", f"Example {G} gate netlist (corner 1) - deliverable 2.", "simulate_gates.py",
        "Deliverable; runnable with ngspice -b.", "Full transistor-level gate, sources, options, nodeset "
        "and printed currents / node voltages.")
    add(f"layer2/spice/{g}_card.pm", f"Patched model card for {g}.sp (corner 1 NMOS + PMOS values).",
        "simulate_gates.py", f"Included by {g}.sp.", "")
    add(f"layer2/data/raw/part_b_spice_{g}.csv", f"SPICE reference results for {G} (200 corners x all inputs).",
        "simulate_gates.py", "predict_gate_leakage.py, error_attribution.py.",
        "Per simulation: SPICE leakage i_vdd, ground and input currents, output and internal node "
        "voltages, per-transistor BSIM4 diagnostics, self-check results.")
add("layer2/data/raw/corners.csv", "The 200 PVT corners (shared by Part B and Part C).", "generate_corners.py",
    "All layer2 and layer3 scripts.", "corner_id, VDD, temperature, NMOS/PMOS widths and the 5 NMOS + 5 PMOS "
    "process parameters of each corner.")
add("layer2/data/results/part_b_results.csv", "Main Part B table: SPICE vs ML leakage per simulation.",
    "predict_gate_leakage.py", "compare_gate_results.py, layer3 prediction, report.",
    "Per gate/input/corner: spice_leak, ml_leak (final, KCL-closed), ml_leak_direct, oracle_leak, "
    "input currents (SPICE and ML), node voltages and corner values.")
add("layer2/data/results/part_b_device_predictions.csv", "Per-transistor ML predictions inside the gates.",
    "predict_gate_leakage.py", "Debugging / analysis.",
    "For every transistor of every gate simulation: Vd/Vg/Vs/Vb, ON/OFF model used and predicted "
    "id/ig/is/ib.")
add("layer2/outputs/gate_results_table.csv", "DELIVERABLE 6: gate results table (18 cases + overall).",
    "compare_gate_results.py", "Report, layer3 comparison.",
    "SPICE median, ML median, bias, median / P95 / mean / max error, R2 per gate and input combination.")
add("layer2/outputs/gate_parity.png", "DELIVERABLE 7: gate parity plot (log axes).", "compare_gate_results.py",
    "Report.", "ML vs SPICE leakage for all 3,600 simulations, coloured by gate.")
add("layer2/outputs/gate_error_by_case.png", "Median and P95 error per gate/input case.",
    "compare_gate_results.py", "Report.", "Which gate/input combinations are most and least accurate.")
add("layer2/outputs/gate_error_vs_corner.png", "Gate error vs temperature, VDD, vth0 and width.",
    "compare_gate_results.py", "Report.", "Which corner conditions give larger errors.")
add("layer2/outputs/gate_worst_cases.csv", "The 20 largest gate errors.", "compare_gate_results.py",
    "Report (error analysis).", "Gate, inputs, corner and its conditions for each worst case.")
add("layer2/outputs/oracle_check.csv", "Check of the leakage formula itself.", "predict_gate_leakage.py",
    "Report.", "Formula fed with SPICE's exact per-device currents reproduces SPICE to ~1e-6: the formula "
    "and sign handling are correct.")
add("layer2/outputs/error_attribution.csv", "Gate error when one transistor model is replaced by exact SPICE.",
    "error_attribution.py", "Report (error analysis).", "Which of the 4 models (NMOS/PMOS ON/OFF) causes "
    "the error for each gate/input case.")
add("layer2/outputs/operating_point_coverage.csv", "Training-data coverage of real gate operating points.",
    "error_attribution.py", "Report.", "Only ~1-11 of 10,000 training samples lie near the rail-corner "
    "biases where gate transistors operate.")
add("layer2/logs/part_b_failures.csv", "Failed / rejected gate simulations (only created if any fail).",
    "simulate_gates.py", "You.", "Convergence or self-check failures; none in the final run.")

# ---------------- layer3 (Part C)
add("layer3/scripts/__init__.py", "Package marker (empty).", "", "Python imports.")
add("layer3/scripts/simulate_test_circuit.py", "STEP C1: SPICE of the full 3-bit CLA netlist "
    "(64 vectors x 200 corners = 12,800 runs).", "Run: python -m layer3.scripts.simulate_test_circuit", "-",
    "Creates part_c_spice.csv (full) + part_c_spice_summary.csv and the example netlist; checks "
    "self-consistency and output logic.")
add("layer3/scripts/predict_circuit_leakage.py", "STEP C2: hierarchical ML leakage of the CLA.",
    "Run: python -m layer3.scripts.predict_circuit_leakage", "-",
    "Creates part_c_results.csv: spec-method sum of 39 gate leakages and the loading-aware variant.")
add("layer3/scripts/compare_circuit_results.py", "STEP C3: CLA ML vs SPICE comparison.",
    "Run: python -m layer3.scripts.compare_circuit_results", "-",
    "Creates the test-circuit tables, parity plot, error breakdown and rail-deviation check.")
add("layer3/spice/cla3.sp", "Complete transistor-level CLA netlist (corner 1, A=5, B=3) - deliverable 2.",
    "simulate_test_circuit.py", "Deliverable; runnable with ngspice -b.", "All 186 transistors, input "
    "sources, options and outputs.")
add("layer3/spice/cla3_card.pm", "Patched model card for cla3.sp (corner 1).", "simulate_test_circuit.py",
    "Included by cla3.sp.", "")
add("layer3/data/raw/part_c_spice.csv", "FULL CLA SPICE record incl. per-transistor diagnostics "
    "(~370 MB, NOT in git).", "simulate_test_circuit.py", "Only for deep debugging.",
    "Every current, node voltage and BSIM4 component of every CLA simulation.")
add("layer3/data/raw/part_c_spice_summary.csv", "Compact CLA SPICE results (13 MB, in git).",
    "simulate_test_circuit.py", "predict_circuit_leakage.py, compare_circuit_results.py, resume, report.",
    "Per corner and vector: SPICE leakage i_vdd, ground/input currents, all 39 gate-output voltages, "
    "self-check and logic-check results.")
add("layer3/data/results/part_c_results.csv", "Main Part C table: SPICE vs hierarchical ML per simulation.",
    "predict_circuit_leakage.py", "compare_circuit_results.py, report figures.",
    "spice_leak (full netlist), ml_leak (spec method), ml_leak_loaded (+ loading gate tunnelling), "
    "isolated-gate SPICE sums, loading currents and the gate calls used.")
add("layer3/outputs/circuit_results_table.csv", "DELIVERABLE 8: test-circuit metrics.", "compare_circuit_results.py",
    "Report.", "Spec method 69.4 % vs loading-aware 98.4 % mean accuracy, plus the ML-only and "
    "loading-only error splits.")
add("layer3/outputs/circuit_results_by_vector.csv", "Metrics per input vector (64 rows).",
    "compare_circuit_results.py", "-", "Whether some A/B input combinations are worse than others.")
add("layer3/outputs/circuit_vs_gate_accuracy.csv", "Part C vs Part B accuracy summary.",
    "compare_circuit_results.py", "Report.", "Gate level 98.6 %, CLA spec method 69.4 %, CLA loading-aware 98.4 %.")
add("layer3/outputs/circuit_parity.png", "DELIVERABLE 8: CLA parity plots (log axes).", "compare_circuit_results.py",
    "Report.", "Left: spec method (below the diagonal = missing loading); right: loading-aware (on the diagonal).")
add("layer3/outputs/circuit_error_breakdown.png", "Distribution of the different CLA errors.",
    "compare_circuit_results.py", "Report.", "Shows the error is loading (gate tunnelling), not ML.")
add("layer3/outputs/rail_deviation.json", "Check of the 'inputs at exactly 0 / VDD' assumption.",
    "compare_circuit_results.py", "Report.", "CLA gate outputs sit within ~0.3 uV (median) / 18 uV (max) of the rails.")
add("layer3/logs/part_c_spice_run.log", "Console log of the 12,800 CLA simulations (not in git).",
    "simulate_test_circuit.py", "You.", "Progress and ok/failed counts.")
add("layer3/logs/part_c_compare.log", "Console log of the Part C comparison (not in git).",
    "compare_circuit_results.py", "You.", "Printed results table.")
add("layer3/logs/part_c_failures.csv", "Failed CLA simulations (only created if any fail).",
    "simulate_test_circuit.py", "You.", "None in the final run.")

# ---------------- report
add("report/__init__.py", "Package marker (empty).", "", "Python imports.")
add("report/DVD_ML_Leakage_Report.docx", "DELIVERABLE 10: the technical report (Word).",
    "python -m report.build_report", "Graders.", "Setup, data generation, models, gate and CLA results, "
    "error analysis, limitations, reproducibility - 17 figures, 16 tables.")
add("report/build_report.py", "Builds the Word report from the result files.", "Run: python -m report.build_report",
    "-", "Every number in the report is read from the outputs, nothing typed by hand.")
add("report/docx_writer.py", "Minimal Word (.docx) writer using only the Python standard library.", "",
    "build_report.py.", "Headings, tables, figures, lists, table of contents, page numbers.")
add("report/report_figures.py", "Makes the four report-only figures.", "Run: python -m report.report_figures",
    "build_report.py.", "Creates report/figures/*.png.")
add("report/file_guide.py", "Builds THIS guide (File_Guide.pdf).", "Run: python -m report.file_guide", "-",
    "Fails if any repository file has no description.")
add("report/File_Guide.pdf", "This document.", "python -m report.file_guide", "You.", "")
add("report/walkthrough.py", "Builds Project_Walkthrough.pdf.", "Run: python -m report.walkthrough", "-",
    "Reads the result files and tells the project step by step.")
add("report/Project_Walkthrough.pdf", "Step-by-step story of the project, from the first script to the report.",
    "python -m report.walkthrough", "You / graders.", "For every step: script, command, files produced, "
    "results, and the problems found and fixed on the way.")
add("report/figures/partc_accuracy_ladder.png", "Part C accuracy bars (spec / ceiling / loading / ceiling).",
    "report_figures.py", "Report section 5.", "69.36 % -> 70.07 % ceiling; 98.40 % -> 99.99 % ceiling.")
add("report/figures/gate_error_attribution.png", "Gate error with one model replaced by exact SPICE.",
    "report_figures.py", "Report section 6.", "PMOS ON / NMOS ON gate tunnelling dominate the gate error.")
add("report/figures/gate_error_vs_vdd.png", "Gate error vs VDD, PMOS toxe and temperature.",
    "report_figures.py", "Report section 6.", "Errors larger at high VDD / thin oxide, smaller at high temperature.")
add("report/figures/partc_error_vs_corner.png", "CLA error vs temperature and NMOS toxe.",
    "report_figures.py", "Report section 6.", "Missing loading current is largest for thin oxide and low temperature.")


# --------------------------------------------------------------------------------------
def repo_files() -> list[str]:
    out = []
    for p in ROOT.rglob("*"):
        rel = p.relative_to(ROOT)
        if not p.is_file() or any(part in SKIP_DIRS for part in rel.parts):
            continue
        out.append(rel.as_posix())
    return sorted(out)


def describe(path: str) -> dict | None:
    if path in D:
        return D[path]
    for k, v in D.items():
        if any(ch in k for ch in "*?[") and fnmatch.fnmatch(path, k):
            return v
    return None


# ---------------- simple flowing page layout on top of matplotlib
class Pdf:
    W, H = 8.27, 11.69                      # A4 inches
    L, R, TOP, BOT = 0.75, 0.75, 0.8, 0.8
    FOOTER = "File guide"

    def __init__(self, path: Path, preview: Path | None):
        self.pdf = PdfPages(path)
        self.preview = preview
        self.page_no = 0
        self.fig = None
        self.y = 0.0
        self.new_page()

    @property
    def width(self):
        return self.W - self.L - self.R

    def new_page(self):
        if self.fig is not None:
            self._finish()
        self.page_no += 1
        self.fig = plt.figure(figsize=(self.W, self.H))
        self.fig.patch.set_facecolor("white")
        self.y = self.TOP

    def _finish(self):
        self.fig.text(self.W / 2 / self.W, 0.4 / self.H, f"{self.FOOTER}  |  page {self.page_no}",
                      ha="center", va="center", fontsize=7.5, color=INK2)
        self.pdf.savefig(self.fig)
        if self.preview:
            self.preview.mkdir(parents=True, exist_ok=True)
            self.fig.savefig(self.preview / f"page_{self.page_no:02d}.png", dpi=70)
        plt.close(self.fig)

    def need(self, h):
        if self.y + h > self.H - self.BOT:
            self.new_page()

    def _txt(self, x, text, size, color=INK, weight="normal", family="sans-serif", style="normal"):
        self.fig.text(x / self.W, 1 - self.y / self.H, text, fontsize=size, color=color, weight=weight,
                      family=family, style=style, va="top", ha="left")

    @staticmethod
    def wrap(text, size, width_in, mono=False):
        cw = (0.60 if mono else 0.53) * size / 72      # average char width (in)
        return textwrap.wrap(text, max(20, int(width_in / cw))) or [""]

    def title(self, text, sub):
        self.y = 1.6
        self._txt(self.L, text, 22, ACCENT, "bold")
        self.y += 0.55
        for item in sub:
            for line in self.wrap(item, 11, self.width):
                self._txt(self.L, line, 11, INK2)
                self.y += 0.25
        self.y += 0.2

    def h1(self, text):
        self.need(0.75)
        self.y += 0.15
        self._txt(self.L, text, 15, ACCENT, "bold")
        self.y += 0.32
        self.fig.add_artist(Rectangle((self.L / self.W, 1 - self.y / self.H), self.width / self.W, 0.012 / self.H,
                                      transform=self.fig.transFigure, color=ACCENT, lw=0))
        self.y += 0.15

    def h2(self, text):
        self.need(1.1)
        self.y += 0.08
        self._txt(self.L, text, 11.5, ACCENT, "bold")
        self.y += 0.27

    def para(self, text, size=9.5, color=INK, indent=0.0):
        for line in self.wrap(text, size, self.width - indent):
            self.need(size / 72 * 1.45)
            self._txt(self.L + indent, line, size, color)
            self.y += size / 72 * 1.45
        self.y += 0.06

    def bullets(self, items, size=9.5):
        for it in items:
            lines = self.wrap(it, size, self.width - 0.25)
            for i, line in enumerate(lines):
                self.need(size / 72 * 1.45)
                if i == 0:
                    self._txt(self.L + 0.05, "•", size, ACCENT)
                self._txt(self.L + 0.25, line, size)
                self.y += size / 72 * 1.45
        self.y += 0.06

    def code(self, lines, size=8.3):
        longest = max(len(x) for x in lines)
        size = min(size, (self.width - 0.2) / (0.6 * longest) * 72)
        h = len(lines) * size / 72 * 1.4 + 0.12
        if h < self.H - self.TOP - self.BOT:
            self.need(h)
        top = self.y
        self.fig.add_artist(Rectangle((self.L / self.W, 1 - (top + h) / self.H), self.width / self.W, h / self.H,
                                      transform=self.fig.transFigure, color="#f4f4f4", lw=0))
        self.y += 0.06
        for line in lines:
            self.need(size / 72 * 1.4)
            self._txt(self.L + 0.1, line, size, INK, family="monospace")
            self.y += size / 72 * 1.4
        self.y += 0.14

    def entry(self, path, d):
        rows = [("What", d["what"]), ("Made by", d["made"]), ("Used by", d["used"]), ("Tells you", d["tells"])]
        rows = [(k, v) for k, v in rows if v and v != "-"]
        body = [(k, self.wrap(v, 8.6, self.width - 1.05)) for k, v in rows]
        h = 0.27 + sum(len(ls) for _, ls in body) * 8.6 / 72 * 1.4 + 0.12
        self.need(h)
        top = self.y
        self.fig.add_artist(Rectangle((self.L / self.W, 1 - (top + 0.24) / self.H), self.width / self.W,
                                      0.24 / self.H, transform=self.fig.transFigure, color=SHADE, lw=0))
        self.y += 0.05
        self._txt(self.L + 0.08, path, 9, ACCENT, "bold", family="monospace")
        self.y += 0.24
        for k, lines in body:
            self._txt(self.L + 0.1, k, 8.2, INK2, "bold")
            for line in lines:
                self._txt(self.L + 0.95, line, 8.6)
                self.y += 8.6 / 72 * 1.4
        self.y += 0.1
        self.fig.add_artist(Rectangle((self.L / self.W, 1 - self.y / self.H), self.width / self.W, 0.006 / self.H,
                                      transform=self.fig.transFigure, color=RULE, lw=0))
        self.y += 0.08

    def close(self):
        self._finish()
        self.pdf.close()


SECTIONS = [
    ("1. Root files", ["", "logs/"], "General files that apply to the whole project."),
    ("2. common_scripts/  (shared Python code)", ["common_scripts/"],
     "Modules imported by every layer. You never run them directly, except setup_check.py."),
    ("3. layer1/  (Part A: transistor data and ML models)", ["layer1/"],
     "Simulates single NMOS / PMOS transistors and trains the four ML models."),
    ("4. layer2/  (Part B: gate-level validation)", ["layer2/"],
     "Simulates INV, NAND2, NOR2, AND2, OR2 in SPICE and predicts their leakage with the layer1 models."),
    ("5. layer3/  (Part C: 3-bit carry-lookahead adder)", ["layer3/"],
     "Simulates the full CLA in SPICE and predicts its leakage by summing gate predictions."),
    ("6. report/  (technical report and this guide)", ["report/"], "Report generation code and outputs."),
]


def section_of(path):
    for i, (_, prefixes, _) in enumerate(SECTIONS):
        for pre in prefixes:
            if pre == "" and "/" not in path:
                return i
            if pre and path.startswith(pre):
                return i
    return None


SUBORDER = ["scripts/", "spice/", "data/raw/", "data/processed/", "data/results/", "models/", "outputs/",
            "logs/", "figures/"]


ORDER = {k: i for i, k in enumerate(D)}


def sort_key(path):
    pos = ORDER.get(path, next((ORDER[k] for k in D if any(ch in k for ch in "*?[")
                                and fnmatch.fnmatch(path, k)), 10**6))
    for i, s in enumerate(SUBORDER):
        if f"/{s}" in f"/{path}":
            return (i, pos, path)
    return (-1, pos, path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path, help="also save page PNGs here")
    args = ap.parse_args()

    files = repo_files()
    if "report/File_Guide.pdf" not in files:
        files.append("report/File_Guide.pdf")
    missing = [f for f in files if describe(f) is None]
    if missing:
        raise SystemExit("No description for:\n  " + "\n  ".join(missing))

    doc = Pdf(OUT, args.preview)
    doc.title("File Guide", ["ML-Driven PVT Variation-Aware Leakage Estimation",
                             "Team Watt the leak  |  32 nm LP  |  VDD 0.9 V  |  3-bit CLA",
                             f"Every file in the repository: what it is, how it is made, who uses it, "
                             f"what it tells you  ({len(files)} files, {date.today():%d %b %Y})"])
    doc.h1("How to read this guide")
    doc.para("Each file has a box with up to four lines: What (the file), Made by (the command or step "
             "that creates it), Used by (which script or person reads it) and Tells you (the information "
             "you get from it). Every Python script is run from the repository root with "
             "'python -m <folder>.<module>'. Files marked 'not in git' are kept locally but not "
             "versioned.")
    doc.h2("Which command creates what")
    doc.code([
        "python -m common_scripts.setup_check             -> logs/setup_check.json",
        "python -m layer1.scripts.generate_samples        -> layer1/data/raw/<case>_samples.csv",
        "python -m layer1.scripts.generate_spice_data     -> layer1/data/raw/<case>_spice_raw.csv,",
        "                                                    layer1/data/processed/<case>.csv, layer1/spice/*",
        "python -m layer1.scripts.validate_data           -> layer1/outputs/data_check.*, trend_*.png, kcl_*.png",
        "python -m layer1.scripts.train_models            -> layer1/models/<case>_model.joblib  (THE MODELS)",
        "                                                    + splits, comparison tables, test metrics",
        "python -m layer1.scripts.plot_results            -> layer1/outputs/parity_*.png, error_cdf, comparison",
        "python -m layer2.scripts.generate_corners        -> layer2/data/raw/corners.csv",
        "python -m layer2.scripts.simulate_gates          -> layer2/data/raw/part_b_spice_<gate>.csv, layer2/spice/*",
        "python -m layer2.scripts.predict_gate_leakage    -> layer2/data/results/*, layer2/outputs/oracle_check.csv",
        "python -m layer2.scripts.compare_gate_results    -> layer2/outputs/gate_* (table, parity, plots)",
        "python -m layer2.scripts.error_attribution       -> layer2/outputs/error_attribution.csv, coverage",
        "python -m layer3.scripts.simulate_test_circuit   -> layer3/data/raw/part_c_spice*.csv, layer3/spice/*",
        "python -m layer3.scripts.predict_circuit_leakage -> layer3/data/results/part_c_results.csv",
        "python -m layer3.scripts.compare_circuit_results -> layer3/outputs/* (tables, parity, rail check)",
        "python -m report.report_figures                  -> report/figures/*.png",
        "python -m report.build_report                    -> report/DVD_ML_Leakage_Report.docx",
        "python -m report.file_guide                      -> report/File_Guide.pdf  (this file)",
        "python -m report.walkthrough                    -> report/Project_Walkthrough.pdf",
    ])
    doc.para("Order matters: each stage reads the previous stage's files. All simulation steps are "
             "resumable - re-running them skips results that already exist.", size=9)
    doc.h2("Where the models are")
    doc.bullets([
        "The trained ML models are the four files layer1/models/<case>_model.joblib "
        "(nmos_on, nmos_off, pmos_on, pmos_off). They are created by layer1/scripts/train_models.py.",
        "train_models.py needs the Part A data first: run generate_samples and generate_spice_data "
        "before it.",
        "layer2 and layer3 do not train models of their own: they load these four files through "
        "common_scripts/transistor_model.py.",
    ])
    doc.h2("Folder layout")
    doc.code([
        "ml-pvt-leakage-estimation/",
        "|- project_config.json, 32nm_LP.pm, README.md, requirements.txt, .gitignore",
        "|- logs/            setup_check.json",
        "|- common_scripts/  shared Python modules + setup_check.py",
        "|- layer1/          Part A   scripts/ spice/ data/ models/ outputs/ logs/",
        "|- layer2/          Part B   scripts/ spice/ data/ outputs/ logs/",
        "|- layer3/          Part C   scripts/ spice/ data/ outputs/ logs/",
        "|- report/          report code, figures, Word report, this guide",
    ])

    grouped = {i: [] for i in range(len(SECTIONS))}
    for f in files:
        grouped[section_of(f)].append(f)
    for i, (title, _, intro) in enumerate(SECTIONS):
        doc.new_page()
        doc.h1(title)
        doc.para(intro, color=INK2)
        current = None
        for f in sorted(grouped[i], key=sort_key):
            sub = next((s for s in SUBORDER if f"/{s}" in f"/{f}"), None)
            if sub != current and i >= 2:
                current = sub
                doc.h2(sub.rstrip("/") if sub else "folder root")
            doc.entry(f, describe(f))
    doc.close()
    print(f"guide -> {OUT}  ({doc.page_no} pages, {len(files)} files described)")


if __name__ == "__main__":
    main()
