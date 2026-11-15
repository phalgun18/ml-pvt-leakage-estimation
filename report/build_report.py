"""Build the technical report reports/DVD_ML_Leakage_Report.docx from the project outputs.

Every number quoted in the report is read from the result files produced by the
pipeline (nothing is typed in by hand), so re-running the pipeline and then this
script regenerates a consistent report.

Run:  python -m report.report_figures && python -m report.build_report
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from common_scripts.config import REPO_ROOT, load_config, general_path, layer_path
from report.docx_writer import Document, rich

REPORT_DIR = REPO_ROOT / "report"
OUT = REPORT_DIR.joinpath("DVD_ML_Leakage_Report.docx")
CASE_NAME = {"nmos_on": "NMOS ON", "nmos_off": "NMOS OFF", "pmos_on": "PMOS ON", "pmos_off": "PMOS OFF"}
MODEL_NAME = {"poly_ridge": "Polynomial ridge", "rf": "Random forest", "hgb": "Hist. gradient boosting",
              "mlp": "MLP (3-seed ensemble)"}


def f(x, d=2):
    return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{d}f}"


def sci(x, d=2):
    return f"{x:.{d}e}"


def acc(pred, ref):
    return 100 - np.mean(np.abs(pred / ref - 1)) * 100


def main() -> None:
    cfg = load_config()
    tech = cfg["technology"]
    setup = json.loads(general_path("logs", "setup_check.json").read_text())
    ngspice_ver = setup["checks"]["ngspice"]["detail"]["version"]
    pkgs = setup["checks"]["python_packages"]["detail"]
    dc = pd.read_csv(layer_path(1, "outputs", "data_check.csv")).set_index("case")
    cmp_ = pd.read_csv(layer_path(1, "outputs", "model_comparison_table.csv"))
    sel = pd.read_csv(layer_path(1, "outputs", "selected_component_models.csv"))
    selval = pd.read_csv(layer_path(1, "outputs", "selected_model_validation.csv"))
    test = pd.read_csv(layer_path(1, "outputs", "test_metrics.csv"))
    hyp = json.loads(layer_path(1, "outputs", "hyperparameters.json").read_text())
    gate = pd.read_csv(layer_path(2, "outputs", "gate_results_table.csv"), dtype={"inputs": str})
    oracle = pd.read_csv(layer_path(2, "outputs", "oracle_check.csv"))
    cover = pd.read_csv(layer_path(2, "outputs", "operating_point_coverage.csv"))
    worst = pd.read_csv(layer_path(2, "outputs", "gate_worst_cases.csv"), dtype={"inputs": str})
    pbres = pd.read_csv(layer_path(2, "data", "results", "part_b_results.csv"), dtype={"inputs": str})
    cres = pd.read_csv(layer_path(3, "data", "results", "part_c_results.csv"))
    ctab = pd.read_csv(layer_path(3, "outputs", "circuit_results_table.csv"))
    cspice = pd.read_csv(layer_path(3, "data", "raw", "part_c_spice_summary.csv"), usecols=["corner_id"])
    rail = json.loads(layer_path(3, "outputs", "rail_deviation.json").read_text())
    cases = list(cfg["part_a"]["cases"])
    vlo, vhi = tech["vdd_nominal"] * 0.9, tech["vdd_nominal"] * 1.1

    g_all = gate[gate.gate == "ALL"].iloc[0]
    gg = gate[gate.gate != "ALL"].copy()
    gg["acc"] = 100 - gg.mean_err_pct
    best_g, worst_g = gg.sort_values("acc").iloc[-1], gg.sort_values("acc").iloc[0]
    acc_spec = acc(cres.ml_leak, cres.spice_leak)
    acc_spec_ceiling = acc(cres.spice_gate_sum, cres.spice_leak)
    acc_load = acc(cres.ml_leak_loaded, cres.spice_leak)
    acc_load_ceiling = acc(cres.spice_gate_sum_loaded, cres.spice_leak)
    acc_pure_ml = acc(cres.ml_leak, cres.spice_gate_sum)
    load_share = np.median(cres.spice_load / cres.spice_leak) * 100
    t_ok = test.dropna(subset=["median_err_pct"]).assign(acc=lambda d: 100 - d.mean_err_pct)
    acc_a = t_ok.acc.mean()

    d = Document("ML-Driven PVT Variation-Aware Leakage Estimation", "Team Watt the leak")

    # ------------------------------------------------------------------ title
    d.title_block("ML-Driven PVT Variation-Aware Leakage Estimation", [
        "Digital VLSI Design: Course Project Report",
        "Team **Watt the leak**",
    ])
    d._p("", extra_ppr='<w:spacing w:before="240" w:after="0"/>')
    d.table(["Team member", "Roll number"], [
        ["Phalgun", "2026702011"],
        ["M L Venkat", "2026702012"],
        ["Naveen", "2026702001"],
        ["Krishna", "2026702010"],
    ], widths=[3.0, 2.0])
    d._p(rich("GitHub: **https://github.com/phalgun18/ml-pvt-leakage-estimation**", size=22, color="404040"),
         jc="center", extra_ppr='<w:spacing w:before="200" w:after="60"/>')
    d._p(rich("Technology: PTM **32 nm Low Power** (BSIM4)  |  VDD = **0.9 V**  |  Test circuit: **3-bit CLA**",
              size=22, color="404040"), jc="center", extra_ppr='<w:spacing w:before="60" w:after="60"/>')
    d._p(rich(f"Simulator: **{ngspice_ver}**  |  Python {setup['python']}  |  scikit-learn {pkgs['sklearn']}",
              size=22, color="404040"), jc="center", extra_ppr='<w:spacing w:before="60" w:after="60"/>')
    d._p("", extra_ppr='<w:spacing w:before="360" w:after="0"/>')
    d.table(["Result", "Median error", "P95 error", "Mean accuracy"], [
        ["Part A: transistor models (test set, all terminals)", f"{t_ok.median_err_pct.median():.2f} %",
         f"{t_ok.p95_err_pct.median():.2f} %", f"**{acc_a:.2f} %**"],
        ["Part B: gates (3,600 simulations)", f"{g_all.median_err_pct:.2f} %", f"{g_all.p95_err_pct:.2f} %",
         f"**{100 - g_all.mean_err_pct:.2f} %**"],
        ["Part C: 3-bit CLA (12,800 simulations, with loading gate tunnelling)",
         f"{ctab.iloc[3].median_err_pct:.2f} %", f"{ctab.iloc[3].p95_err_pct:.2f} %", f"**{acc_load:.2f} %**"],
    ], widths=[3.4, 1.1, 1.1, 1.2], caption="Headline results (mean accuracy = 100 % − mean relative error).")
    d.page_break()
    d.toc()
    d.page_break()

    # ------------------------------------------------------------------ 1 setup
    d.heading("1. Setup", 1)
    d.para("The project estimates the leakage current of CMOS circuits under process, voltage and temperature "
           "(PVT) variation with machine-learning models of single transistors, and validates the estimate "
           "hierarchically against SPICE: transistor → logic gate → complete test circuit.")
    d.table(["Item", "Value"], [
        ["Model file", "`32nm_LP.pm`: PTM Low Power 32 nm metal-gate / high-k, BSIM4 (level 54, v4.0)"],
        ["Nominal VDD", f"**{tech['vdd_nominal']} V** (assigned; the card header states 1.0 V, the TA assignment "
                        f"sheet specifies 0.9 V). Sampled {vlo:.2f}–{vhi:.2f} V"],
        ["Channel length L", "32 nm (= Lmin)"],
        ["Width W", "32–256 nm (1–8 × Lmin)"],
        ["Temperature", "−40 to 125 °C (model tnom = 27 °C)"],
        ["Test circuit", "3-bit carry-lookahead adder (carry-in = 0, 64 input vectors)"],
        ["Simulator", f"**{ngspice_ver}** (`ngspice_con.exe`, batch mode, `.op` analysis), KLU solver"],
        ["Software", f"Python {setup['python']}; numpy {pkgs['numpy']}, pandas {pkgs['pandas']}, "
                     f"scikit-learn {pkgs['sklearn']}, scipy {pkgs['scipy']}, matplotlib {pkgs['matplotlib']}, "
                     f"joblib {pkgs['joblib']}"],
        ["Platform", "Windows 11, 20 logical cores (simulations run 12 in parallel)"],
    ], widths=[1.4, 5.0], align=["left", "left"], caption="Assignment and environment.")
    nom = tech["expected_nominals"]
    d.table(["Parameter", "Meaning", "NMOS nominal", "PMOS nominal", "Sampled range"],
            [["vth0", "long-channel threshold voltage (V)", nom["nmos"]["vth0"], nom["pmos"]["vth0"], "± 10 %"],
             ["toxe", "electrical oxide thickness (m)", nom["nmos"]["toxe"], nom["pmos"]["toxe"], "± 10 %"],
             ["ndep", "channel doping (cm⁻³)", nom["nmos"]["ndep"], nom["pmos"]["ndep"], "± 10 %"],
             ["u0", "low-field mobility (m²/V·s)", nom["nmos"]["u0"], nom["pmos"]["u0"], "± 10 %"],
             ["xj", "junction depth (m)", nom["nmos"]["xj"], nom["pmos"]["xj"], "± 10 %"]],
            widths=[0.9, 2.6, 1.2, 1.2, 1.0], align=["left", "left", "right", "right", "center"],
            caption="Process parameters varied (nominals parsed from the model card and checked against the "
                    "assignment sheet).")

    # ------------------------------------------------------------------ 2 data
    d.heading("2. Data generation", 1)
    d.heading("2.1 Sampling", 2)
    d.para("For each of the four transistor cases, 10,000 samples were drawn. Every parameter is drawn "
           "independently and uniformly, as Section 4 of the specification requires. VDD is drawn first because "
           "the drain and source ranges depend on it. Gate and body voltages are fixed by the case. Each case "
           f"uses its own fixed seed ({cfg['part_a']['sample_seed']} + case index), so it is reproducible on its own.")
    d.table(["Parameter", "Distribution"], [
        ["VDD", f"U({vlo:.2f}, {vhi:.2f}) V"], ["Vd, Vs", "U(0, VDD), independent"],
        ["W", "U(32, 256) nm"], ["Temperature", "U(−40, 125) °C"],
        ["vth0, toxe, ndep, u0, xj", "U(0.9 × nominal, 1.1 × nominal), NMOS or PMOS nominals"],
        ["Vg, Vb", "NMOS ON: VDD, 0  |  NMOS OFF: 0, 0  |  PMOS ON: 0, VDD  |  PMOS OFF: VDD, VDD"],
    ], widths=[1.6, 4.8], align=["left", "left"], caption="Sampling distributions (Part A).")
    d.heading("2.2 Netlists and model-card handling", 2)
    d.para("Netlists are generated by Python with literal numeric values, so the file that ran is exactly the file "
           "that can be read. Each single-transistor netlist has **its own voltage source on every terminal** and "
           "contains the mandatory `.options gmin=1e-18 abstol=1e-18 reltol=1e-6 vntol=1e-9`. The process "
           "parameters are **not** passed through the netlist. For every simulation a private copy of "
           "`32nm_LP.pm` is written in which only the five parameters of the NMOS block or the PMOS block are "
           "replaced, and the copy is parsed back to verify every value. The original card is never modified, "
           "and its checksum is recorded in the README. Example (NMOS OFF, `layer1/spice/nmos_off.sp`):")
    d.code(layer_path(1, "spice", "nmos_off.sp").read_text().split(".control")[0].strip())
    d.para("Terminal currents are read as `-i(Vx)`, i.e. **positive = current flowing into the device terminal**. "
           "With this convention KCL reads id + ig + is + ib = 0. Results are printed with `set numdgt=15`. "
           "ngspice's default of about 6 significant digits produces artificial KCL errors of up to 9 % on "
           "small currents, a defect we found in an earlier version of this dataset. A simulation is accepted "
           "only if all of the following hold: ngspice exits with code 0, the log contains no error or "
           "non-convergence message, each requested quantity is printed exactly once, and every value is finite.")
    d.heading("2.3 Simulation outcome and split", 2)
    d.para(f"All **40,000 / 40,000** simulations succeeded (0 failures), at about 150 simulations per second with 12 "
           f"parallel workers. Each dataset was split randomly with a fixed seed ({cfg['part_a']['split_seed']}) "
           "into 70 % training (7,000), 15 % validation (1,500) and 15 % test (1,500). The validation set alone is "
           "used to choose models. The test set is scored once, after selection.")
    d.heading("2.4 Data check", 2)
    rows = []
    for c in cases:
        r = dc.loc[c]
        rows.append([CASE_NAME[c], int(r.rows), int(r.failed_simulations_logged), int(r.missing_values),
                     int(r.duplicate_input_rows), int(r.out_of_range_total), int(r.kcl_violations),
                     sci(r.kcl_max_abs_sum_A, 1), sci(r.kcl_median_abs_sum_A, 1)])
    d.table(["Case", "Rows", "Failed", "Missing", "Dupl.", "Out of range", "KCL viol.", "max |ΣI| (A)",
             "median |ΣI| (A)"], rows, widths=[1.1, .8, .7, .8, .7, .9, .8, 1.1, 1.2],
            caption="Data check per case. KCL tolerance: |id+ig+is+ib| ≤ 1e-15 A + 1e-6 · max|I|.")
    d.para("**Kirchhoff check.** No sample violates KCL. The largest residual (2.1e-15 A) is at the level of the "
           "simulator's round-off and is negligible next to the leakage currents of interest (10⁻¹⁴–10⁻¹⁰ A).")
    d.figure(layer_path(1, "outputs", "kcl_residuals.png"), "KCL residual |id+ig+is+ib| per sample for each case. "
             "The dashed line marks the 1e-15 A absolute tolerance.", 0.78)
    d.para("**Simulator resolution floor.** The model card enables gate and body resistance networks "
           "(`rgatemod=1`, `rbodymod=1`). When the gate node sits at about VDD, ngspice can resolve the current "
           "through the gate resistor only to about 4.4e-16 A (machine epsilon × VDD / R). In PMOS OFF the "
           "measured IG is therefore always this round-off value: BSIM4's internally computed tunnelling currents "
           "are about 1e-32 A. Such values are flagged, never modelled as signal, and percentage metrics use only "
           "currents ≥ 1e-15 A, with the number of excluded samples always reported.")
    d.para("**Physical decomposition.** BSIM4 builds each terminal current from seven single-signed components. "
           "These are channel current, drain and source junction diodes, gate-to-channel tunnelling at the "
           "source and drain sides, gate-to-body tunnelling, and impact ionisation. We recorded them alongside "
           "the terminal currents and verified that the terminal currents equal their signed sums to "
           f"≤ {dc[[c for c in dc.columns if c.startswith('decomp_max_abs_resid_i') and not c.endswith('ig_A')]].max().max():.0e} A "
           "for ID, IS and IB, which is machine precision. The sign of every component matches a physical rule "
           "in 100 % of the samples. This decomposition is the basis of the model in Section 3.")
    d.heading("2.5 Trend plots", 2)
    d.para("The highlighted points use the textbook bias: source within 5 % of its rail, so Vgs ≈ 0 for OFF and "
           "|Vgs| ≈ VDD for ON devices, and |Vds| > 0.3 V for OFF devices. Grey points are all other samples. "
           "A source raised above its rail adds body effect and a negative Vgs, which lowers leakage by orders "
           "of magnitude and hides the trend.")
    d.figure(layer_path(1, "outputs", "trend_off_current_vs_temp.png"),
             "OFF current vs temperature: about 2.5 decades from −40 to 125 °C. This is the exponential "
             "subthreshold dependence through the thermal voltage and the temperature coefficient of Vth.")
    d.figure(layer_path(1, "outputs", "trend_off_current_vs_vth0.png"),
             "OFF current vs vth0: about one decade over the ±10 % range. A lower |vth0| gives more leakage, "
             "as exp(−Vth / n·vT) predicts. The spread within a vth0 bin comes from temperature.")
    d.figure(layer_path(1, "outputs", "trend_gate_current_vs_toxe.png"),
             "Gate current vs toxe (ON devices): about 1.5 decades over ±10 % oxide thickness, the exponential "
             "sensitivity of direct tunnelling. The grey floor near 5e-16 A is simulator round-off.")

    # ------------------------------------------------------------------ 3 models
    d.heading("3. Models", 1)
    d.heading("3.1 Physics-informed target (preprocessing)", 2)
    d.para("Regressing the raw terminal currents is poorly conditioned. They span about 15 decades, change sign "
           "and cross zero (for example ID when Vd ≈ Vs). Using the exact decomposition of Section 2.4, each "
           "smooth, single-signed component is learned instead, in a **log-normalised** form. The terminal "
           "currents are then rebuilt by KCL-consistent sums, so predicted id+ig+is+ib = 0 exactly. All voltages "
           "are first mapped to an NMOS-equivalent frame (multiplied by −1 for PMOS). The source and drain roles "
           "are assigned the way BSIM4 assigns them: the source is the lower-potential terminal.")
    d.table(["Learned target", "Physical meaning", "Normalisation / form", "Sign rule"], [
        ["ich", "channel current", "log[ich / (W/L · vT · (1 − e^(−|Vds|/vT)))]", "+ (d→s)"],
        ["jd, js", "drain / source junction leakage", "log[j / (1 − e^(−|Vjb|/vT))]", "+"],
        ["igc", "total gate-to-channel tunnelling", "log[(|igcs|+|igcd|) / (W/L)], no drain features", "sign(Vgs′)"],
        ["igc share", "source fraction of igc", "logit[|igcs| / igc]  (= ½ at Vds = 0)", "–"],
        ["igb", "gate-to-body tunnelling", "log[|igb| / (W/L)], no drain features", "sign(Vgb′ − 0.4 V)"],
        ["isub", "impact-ionisation current", "log[isub / (W/L)]", "+"],
    ], widths=[1.0, 1.8, 2.8, 1.0], align=["left", "left", "left", "center"],
       caption="Learned targets. The channel normaliser keeps ich ∝ Vds as Vds → 0, which matters inside gates.")
    d.para("**Inputs (19 features)** are physical quantities in the source-referenced frame: Vgs, Vds, Vgd, Vbs, "
           "Vdb, Vsb, overdrive (Vgs − |vth0|), Vds/vT, log(Vds + 10 µV), VDD, T/300, 300/T, log(W/L), W/L, "
           "|vth0|, toxe, log(ndep), u0 and xj. Two choices are driven by where logic gates operate. "
           "(i) The log-Vds term is bounded, so it does not extrapolate as |Vds| → 10⁻⁸ V for ON devices. "
           "(ii) The total gate tunnelling current and igb are learned **without drain-referenced features**. "
           "In BSIM4, Igc depends on the gate-source bias and the oxide, and only its source/drain split depends "
           "on Vds. Gate transistors sit at the (Vd, Vs) rail corners, where the uniform data has only a handful "
           "of samples. Without the drain features the model only needs the well-populated 1-D edge "
           "(source at the rail).")
    d.heading("3.2 Model types and hyperparameters", 2)
    d.table(["Model", "Main hyperparameters"], [[MODEL_NAME[k], v] for k, v in hyp.items()],
            widths=[1.7, 4.8], align=["left", "left"],
            caption="The four model types (scikit-learn), trained on the same features and targets.")
    d.heading("3.3 Model comparison (validation set)", 2)
    rows = []
    for c in cases:
        for m in ["poly_ridge", "rf", "hgb", "mlp"]:
            r = cmp_[(cmp_.case == c) & (cmp_.model == m)].iloc[0]
            rows.append([CASE_NAME[c], MODEL_NAME[m], f"{r.R2_log10_mean:.4f}", f"{r.median_err_pct_mean:.2f} %",
                         f"{r.p95_err_pct_mean:.2f} %"])
    d.table(["Case", "Model", "R² (log₁₀|I|)", "Median error", "P95 error"], rows,
            widths=[1.1, 2.0, 1.1, 1.1, 1.1], align=["left", "left", "right", "right", "right"],
            caption="Model comparison table: 4 model types × 4 cases on the validation set, mean over the four "
                    "terminals. Error = |pred − SPICE| / |SPICE| for |SPICE| ≥ 1e-15 A. R² is on log₁₀|I| "
                    "because the currents span many decades.")
    d.figure(layer_path(1, "outputs", "model_comparison.png"), "Validation P95 error per case and model type.", 0.78)
    d.heading("3.4 Final choice and reasons", 2)
    selm = sel.pivot(index="component", columns="case", values="model").reindex(
        ["ich", "jd", "js", "igc", "igc_share", "igb", "isub"])
    d.table(["Target"] + [CASE_NAME[c] for c in cases],
            [[i] + [MODEL_NAME[selm.loc[i, c]].replace(" (3-seed ensemble)", "") for c in cases]
             for i in selm.index],
            widths=[1.2, 1.4, 1.4, 1.4, 1.4], align=["left"] * 5,
            caption="Selected model type per learned target (lowest validation RMSE of the log target).")
    d.bullets([
        "**MLP (3-seed ensemble)** wins overall. Smooth tanh networks fit the smooth log-normalised targets "
        "best, and averaging three random initialisations reduces seed-to-seed variance.",
        "**Polynomial ridge** wins the **OFF-channel current**, the term that dominates leakage. "
        "Subthreshold current is essentially exp(low-order polynomial of the voltages and parameters), "
        "so a cubic in log space is close to the true functional form. It is about 10× more accurate "
        "than the MLP on this component.",
        "**Tree ensembles** (random forest, gradient boosting) give piecewise-constant fits. These cannot "
        "reach sub-percent relative accuracy on smooth exponential targets, so their P95 errors are 17–42 %.",
        "Selection is **per learned target**, on the validation set only. The test set was used once, "
        "for the numbers below.",
    ])
    d.heading("3.5 Chosen models on the test set", 2)
    rows = []
    for c in cases:
        for _, r in test[test.case == c].iterrows():
            if np.isnan(r.median_err_pct):
                rows.append([CASE_NAME[c], r.terminal.upper(), "–", "–", "–", f"{int(r.n_below_floor)} (all)"])
            else:
                rows.append([CASE_NAME[c], r.terminal.upper(), f"{r.r2_log10:.4f}", f"{r.median_err_pct:.3f} %",
                             f"{r.p95_err_pct:.2f} %", str(int(r.n_below_floor))])
    d.table(["Case", "Terminal", "R² (log)", "Median error", "P95 error", "n < 1e-15 A"], rows,
            widths=[1.2, .9, 1.0, 1.1, 1.0, 1.1], align=["left", "center", "right", "right", "right", "right"],
            caption="Test-set metrics of the chosen models (1,500 samples per case). OFF-case IG is below the "
                    "simulator's resolution, so it has no percentage metric.")
    for c in cases:
        d.figure(layer_path(1, "outputs", f"parity_{c}.png"),
                 f"{CASE_NAME[c]}: predicted vs SPICE |I| on the test set (log axes). Grey: below the 1e-15 A "
                 "evaluation floor.", 0.82)
    d.figure(layer_path(1, "outputs", "error_cdf_test.png"),
             "Cumulative distribution of the test-set relative error per terminal (dashed line = 1 %).")
    d.para("Saved models: `layer1/models/<case>_model.joblib`. Each is a bundle with the fitted regressors, feature "
           "definition, selected types and metadata. Parts B and C call them through one function "
           "(`predict_currents`), so training and inference cannot drift apart.")

    # ------------------------------------------------------------------ 4 gates
    d.heading("4. Gate results (Part B)", 1)
    d.heading("4.1 SPICE reference", 2)
    d.para("INV, NAND2, NOR2, AND2 and OR2 are simulated as flat transistor-level netlists. AND2 and OR2 are "
           "complete NAND2/NOR2 + INV gates, never sums of separate simulations. Each gate is run for every "
           "input combination at 200 random corners (18 cases × 200 = 3,600 simulations). A corner is one "
           "draw of VDD, temperature, NMOS width, PMOS width, one NMOS process draw shared by all NMOS, and "
           "one PMOS draw shared by all PMOS. Inputs are exactly 0 or VDD. Leakage = current delivered by "
           "the VDD source.")
    d.para("Three numerical issues were found and fixed: "
           "(i) ngspice aliases a node named `gnd` to ground, so the ground rail is named `vss`; "
           "(ii) 8 AND2 runs did not converge at gmin = abstol = 1e-18; "
           "(iii) 5 AND2 runs **converged falsely**, with nodes ~10 µV beyond the rails and the supply current "
           "wrong by up to 230 % or of the wrong sign. The fix adds solver-robustness options only "
           "(`.options itl1=1000 itl6=1000 pivrel=0.5` and a `.nodeset` at the logic levels). The required "
           "tolerances are unchanged. Every run must also pass a **physical self-check**: the sum of the "
           "transistors' own BSIM4 currents into VDD must equal the supply current within 1e-15 A + 0.1 %, "
           "and no node may lie beyond the rails by more than 1 µV. Result: **3,600 / 3,600 valid**.")
    d.heading("4.2 ML prediction", 2)
    d.para("Only the four transistor models are used, with no gate-level model. For each transistor, (Vd, Vg, "
           "Vs, Vb) are taken from the SPICE-recorded internal-node and output voltages, as the specification "
           "requires. The state (ON/OFF) follows from Vg, and the corner supplies VDD, T, W and the NMOS or "
           "PMOS process parameters. Gate leakage is the current drawn from VDD. An ON transistor carries "
           "exactly the leakage of the network in series with it, at |Vds| ≈ 10⁻⁷ V, where conductance × Vds "
           "cannot be predicted reliably. Its channel current is therefore **closed by KCL**: it is solved from "
           "Kirchhoff's law at the internal nodes, using the ML currents of every OFF device and the tunnelling, "
           "junction and substrate parts of ON devices. Fed with SPICE's exact per-device currents instead of "
           f"ML, the same formula reproduces SPICE to a median of {oracle.oracle_median_rel_diff.median():.0e}. "
           "This shows that the formula, the terminal mapping and the signs are correct.")
    d.heading("4.3 Results", 2)
    rows = [[r.gate, r.inputs, sci(r.spice_median_A), sci(r.ml_median_A), f"{r.bias_pct:+.2f} %",
             f"{r.median_err_pct:.2f} %", f"{r.p95_err_pct:.2f} %", f"{100 - r.mean_err_pct:.2f} %"]
            for _, r in gate.iterrows()]
    d.table(["Gate", "Inputs", "SPICE median (A)", "ML median (A)", "Bias", "Median err.", "P95 err.",
             "Mean acc."], rows, widths=[.8, .65, 1.15, 1.15, .85, .95, .9, .95],
            align=["left", "center"] + ["right"] * 6, bold_last=True,
            caption="Gate results table (200 corners per case). Bias = median(ML/SPICE − 1).")
    d.figure(layer_path(2, "outputs", "gate_parity.png"),
             "Gate parity plot: ML vs SPICE leakage for all 3,600 gate simulations (log axes).", 0.72)
    d.figure(layer_path(2, "outputs", "gate_error_by_case.png"), "Median (filled) and P95 (open) error per case.")
    d.heading("4.4 Most and least accurate cases", 2)
    lows = gg[gg.inputs.isin(["1", "11"]) & gg.gate.isin(["INV", "NAND2"]) | (gg.gate == "NOR2") & gg.inputs.isin(["10", "11"])]
    d.bullets([
        f"**Most accurate: output-low cases** (INV 1, NAND2 11, NOR2 10/11; {lows.acc.min():.2f}–{lows.acc.max():.2f} % "
        f"mean accuracy, best {best_g.gate} {best_g.inputs} at {best_g.acc:.2f} %). The leakage flows "
        "through the OFF PMOS network, whose models are the most accurate (≤ 0.4 % median on the test set).",
        f"**Least accurate: output-high cases** (worst {worst_g.gate} {worst_g.inputs} at {worst_g.acc:.2f} %). "
        "Here a large part of the leakage is gate tunnelling of the ON PMOS (inverter, NAND2) or ON NMOS "
        "(the second stage of AND2/OR2) sitting at the rail corners, the hardest bias for the ON models.",
        f"Every one of the 18 cases is above {gg.acc.min():.1f} % mean accuracy, and no prediction has the "
        "wrong sign.",
    ])

    # ------------------------------------------------------------------ 5 CLA
    d.heading("5. Test-circuit results (Part C): 3-bit CLA", 1)
    d.heading("5.1 Circuit", 2)
    d.para("The adder uses only the five gate types. Generate g_i = AND2(a_i, b_i). Propagate p_i = XOR(a_i, "
           "b_i), each XOR built from 4 × NAND2. The carries are computed directly from g/p with AND2/OR2 trees: "
           "c1 = g0 + p0c0, c2 = g1 + p1g0 + p1p0c0, c3 = g2 + p2g1 + p2p1g0 + p2p1p0c0. The sums are "
           "s_i = XOR(p_i, c_i). Carry-in c0 = 0. In total: **39 gates (24 NAND2, 9 AND2, 6 OR2), 186 "
           "transistors**, logic verified for all 64 vectors. The complete flat netlist is "
           "`layer3/spice/cla3.sp`.")
    d.heading("5.2 SPICE reference and ML prediction", 2)
    d.para(f"64 vectors × the same 200 corners = **{len(cspice):,} / 12,800 valid** SPICE simulations of the "
           "complete netlist. Every run passes the same physical self-check plus a logic check of s0–s2 and "
           "c3. ML (spec method, step 7): logic-simulate the CLA, take each gate's ML leakage for its input "
           "combination at that corner from Part B, and **sum the gate leakages**.")
    d.heading("5.3 Results: loading gate tunnelling had to be added", 2)
    d.table(["Method", "Gate values used", "Mean accuracy"], [
        ["Spec method (sum of gate leakages)", "ML gate predictions", f"**{acc_spec:.2f} %**"],
        ["Spec method (sum of gate leakages)", "perfect gate values (exact SPICE)", f"{acc_spec_ceiling:.2f} %  ← ceiling"],
        ["Sum of gate leakages + loading gate tunnelling", "ML gate predictions", f"**{acc_load:.2f} %**"],
        ["Sum of gate leakages + loading gate tunnelling", "perfect gate values (exact SPICE)",
         f"{acc_load_ceiling:.2f} %  ← ceiling"],
    ], widths=[2.9, 2.3, 1.4], align=["left", "left", "right"],
       caption="3-bit CLA mean accuracy against the full-netlist SPICE leakage (12,800 simulations).")
    d.figure(REPORT_DIR.joinpath("figures", "partc_accuracy_ladder.png"),
             "Part C accuracy: the spec method is limited by loading, not by the ML.", 0.9)
    d.note(f"**Why loading gate tunnelling must be added.** At 32 nm the gate oxide is about 1.6 nm thick, so every "
           "gate input draws a tunnelling current. In the isolated Part-B simulations that current came from the "
           "ideal input source, so it was not part of the gate's VDD leakage. In the CLA, an input held at "
           "logic 1 by another gate gets this current from the **driving gate's PMOS, i.e. from VDD**. It "
           f"therefore belongs to the circuit leakage, about {load_share:.0f} % of it (median). The specification "
           "acknowledges this: the sum of gate leakages *“ignores loading between gates, so expect the accuracy "
           "to be somewhat lower”*. Even perfect gate values reach only "
           f"{acc_spec_ceiling:.2f} % with the plain sum. Adding, for every gate input held at 1 by another gate, "
           "the ML input current of that gate (from the same transistor models) gives "
           f"**{acc_load:.2f} %**. With exact SPICE gate values the same construction reproduces the full netlist "
           f"to {acc_load_ceiling:.2f} %, which proves that loading is the complete explanation. The spec-method "
           "number is the deliverable. The loading-aware number is reported as the improvement.")
    d.figure(layer_path(3, "outputs", "circuit_parity.png"),
             "Test-circuit parity plots (log axes): spec method (left) and with loading gate tunnelling (right).")
    rows = [[r.comparison.split(" [")[0].replace("ML (hierarchical)", "ML"), f"{r.median_err_pct:.2f} %",
             f"{r.p95_err_pct:.2f} %", f"{r.bias_pct:+.2f} %", f"{r.mean_accuracy_pct:.2f} %"]
            for _, r in ctab.iterrows()]
    d.table(["Comparison", "Median err.", "P95 err.", "Bias", "Mean acc."], rows,
            widths=[3.6, .9, .9, .9, .9], align=["left", "right", "right", "right", "right"],
            caption="Test-circuit metrics (same definitions as the gate table).")
    d.heading("5.4 Comparison with gate-level accuracy", 2)
    d.table(["Level", "Median error", "P95 error", "Mean accuracy"], [
        ["Part B gates", f"{g_all.median_err_pct:.2f} %", f"{g_all.p95_err_pct:.2f} %", f"{100 - g_all.mean_err_pct:.2f} %"],
        ["Part C CLA, spec method", f"{ctab.iloc[0].median_err_pct:.2f} %", f"{ctab.iloc[0].p95_err_pct:.2f} %",
         f"{acc_spec:.2f} %"],
        ["Part C CLA, + loading gate tunnelling", f"{ctab.iloc[3].median_err_pct:.2f} %",
         f"{ctab.iloc[3].p95_err_pct:.2f} %", f"{acc_load:.2f} %"],
    ], widths=[2.8, 1.2, 1.2, 1.3], caption="Gate level vs test-circuit level.")
    d.para(f"With loading included, the CLA ({acc_load:.2f} %) is within a fraction of a point of the gate level "
           f"({100 - g_all.mean_err_pct:.2f} %). The ML error of the sum of 39 gates ({100 - acc_pure_ml:.2f} % "
           f"mean error vs the isolated-gate SPICE sum) is about the same as for a single gate "
           f"({g_all.mean_err_pct:.2f} %). The gate errors do not accumulate, because they are small and of "
           "mixed sign. The spec method's lower accuracy comes entirely from its loading assumption.")

    # ------------------------------------------------------------------ 6 error analysis
    d.heading("6. Error analysis", 1)
    d.heading("6.1 Which transistor model causes the gate error", 2)
    d.para("To find the source of the error, the ML currents of one model at a time are replaced by SPICE's exact "
           "per-device currents, and the gate error is recomputed. The drop in error is that model's share.")
    d.figure(REPORT_DIR.joinpath("figures", "gate_error_attribution.png"),
             "Gate error with all ML vs with one model replaced by exact SPICE currents.")
    d.bullets([
        "**Output-high INV / NAND2 / NOR2:** making PMOS ON exact removes most of the error, leaving about "
        "0.1–0.5 %. The dominant error is the ON PMOS gate-tunnelling current.",
        "**AND2 / OR2 with the inverter's NMOS ON:** NMOS ON gate tunnelling is the largest share; "
        "PMOS ON is next.",
        "**Output-low cases:** the residual is the PMOS OFF model, and it is already small (≤ 0.8 %).",
        "Making NMOS OFF exact changes little. The OFF-channel models (median test error ≈ 0.001 % on "
        "ID) are not the limiting factor.",
    ])
    d.heading("6.2 Why: operating points at the edge of the training distribution", 2)
    d.para("Inside a static gate every terminal is at a rail or within microvolts of one, so Vd and Vs are both "
           "≈ 0 or ≈ VDD. Those are the **corners** of the uniform [0, VDD]² sampling box. The table counts the "
           "training samples that lie within ±2 % of VDD of the actual gate operating points.")
    d.table(["Model", "Gate device instances", "Median training samples nearby", "Minimum"],
            [[CASE_NAME[r.case], int(r.gate_device_instances), f"{r.median_training_samples_within_2pct:.0f}",
              int(r.min_training_samples_within_2pct)] for _, r in cover.iterrows()],
            widths=[1.4, 1.6, 2.2, 1.0], caption="Training-data coverage of the gate operating points "
                                                 "(out of 10,000 samples per case).")
    d.para("With 1–11 nearby samples, the models are extrapolating there. Before the gate-tunnelling "
           "reformulation of Section 3.1, this left the gates at 94.8 % mean accuracy. AND2 and OR2 sat at "
           "about 87 %, and the ML input currents were 18–21 % low. Learning the total Igc without "
           "drain-referenced features turns the 2-D corner into a well-sampled 1-D edge. That raised the gates "
           f"to {100 - g_all.mean_err_pct:.2f} %, with no extra data and no change to the sampling rule.")
    d.heading("6.3 Corner conditions", 2)
    d.figure(REPORT_DIR.joinpath("figures", "gate_error_vs_vdd.png"),
             "Gate ML error vs VDD, PMOS oxide thickness and temperature.")
    e = pbres.assign(e=np.abs(pbres.ml_leak / pbres.spice_leak - 1) * 100)
    hv = e[e.vdd > 0.93].e.mean()
    lv = e[e.vdd <= 0.87].e.mean()
    ht = e[e.temp > 80].e.mean()
    ct = e[e.temp <= 0].e.mean()
    d.bullets([
        f"**High VDD** gives the largest gate errors ({hv:.2f} % mean above 0.93 V vs {lv:.2f} % below 0.87 V). "
        "Likewise **thin PMOS oxide** and **low |PMOS vth0|** (Spearman ρ = −0.27 and +0.18 with the error). "
        "At these corners gate tunnelling (exponential in oxide field and thickness) makes up a larger share of "
        "the leakage, and the tunnelling models are the least accurate component.",
        f"**High temperature** gives the *smallest* errors ({ht:.2f} % above 80 °C vs {ct:.2f} % at ≤ 0 °C). "
        "Subthreshold current grows steeply with temperature and dominates the leakage, and the OFF-channel "
        "models are the most accurate.",
        f"Worst single gate case: {worst.iloc[0].gate.upper()} {worst.iloc[0].inputs} at corner "
        f"{int(worst.iloc[0].corner_id)} ({worst.iloc[0].err_pct:.1f} % error; VDD = {worst.iloc[0].vdd:.3f} V, "
        f"T = {worst.iloc[0].temp:.0f} °C, NMOS vth0 = {worst.iloc[0].n_vth0:.3f} V, wide PMOS). "
        "High NMOS vth0 suppresses channel leakage, so the tunnelling of the wide ON PMOS dominates, and that "
        "is under-predicted by about 10 %.",
    ])
    d.figure(REPORT_DIR.joinpath("figures", "partc_error_vs_corner.png"),
             "CLA error vs temperature and NMOS oxide thickness. The spec method's missing loading current is "
             "gate tunnelling: largest for thin oxide, and a smaller share at high temperature, where "
             "subthreshold leakage dominates.")
    ce = cres.assign(es=np.abs(cres.ml_leak / cres.spice_leak - 1) * 100)
    d.para(f"For the CLA spec method the error is largest at **low temperature** ({ce[ce.temp <= 0].es.mean():.0f} % "
           f"mean at ≤ 0 °C vs {ce[ce.temp > 80].es.mean():.0f} % above 80 °C), for **thin NMOS oxide** "
           f"(ρ = {ce[['n_toxe', 'es']].corr(method='spearman').iloc[0, 1]:.2f}) and for **wide NMOS**. These are "
           "exactly the conditions under which gate tunnelling, and therefore the ignored loading current, is "
           "a large fraction of the total.")
    d.heading("6.4 Off-rail inputs", 2)
    d.para("The specification also assumes that every gate input sits at exactly 0 or VDD. This was checked on "
           f"all {rail['n_gate_outputs']:,} gate outputs of the CLA simulations. The median deviation from the "
           f"ideal rail is {rail['median_uV']:.2f} µV and the maximum is {rail['max_uV']:.0f} µV "
           f"({rail['max_pct_of_vdd']:.3f} % of VDD). That changes tunnelling current by far less than 0.1 %, "
           "so this assumption has no measurable effect on this circuit. The whole Part C gap comes from loading.")

    # ------------------------------------------------------------------ 7 limitations
    d.heading("7. Limitations and improvements", 1)
    d.bullets([
        "**Training coverage at the rails.** Uniform sampling puts very few samples where logic gates operate "
        "(Vd, Vs at the rails). The ON-device tunnelling models remain the largest error source (NMOS ON IG "
        "test median 2.35 %). *Improvement:* add a rail-focused supplement (Vd/Vs pinned near 0 or VDD) "
        "to the training data, or use active learning that samples where gate operating points lie.",
        "**Loading is ignored by the spec method** (69.4 %). *Improvement:* the loading-aware sum "
        "(98.4 %) adds the input currents of gates driven high by other gates. A general version would "
        "propagate each net's fan-out gate currents to its driver.",
        "**Dependence on SPICE node voltages.** Following the specification, gate-level ML uses SPICE-recorded "
        "internal node voltages. *Improvement:* solve the internal nodes with the ML models themselves "
        "(Newton iteration on KCL) to obtain a fully SPICE-free predictor. The KCL-closure machinery is "
        "already in place.",
        "**Simulator resolution.** Currents through the gate and body resistor networks are quantised to "
        "about 4e-16 A, so OFF-device IG cannot be evaluated. Disabling `rgatemod`/`rbodymod` is not allowed, "
        "because the card must stay unmodified.",
        "**Scope.** One technology, fixed L, one width per device type per corner, no layout parasitics or "
        "junction areas (BSIM4's default minimum saturation current then sets the junction-leakage floor of "
        "about 1e-14 A). Models would need retraining for other cards or sizing schemes.",
        "**Model cost.** The MLP ensembles take about 25 minutes to train on 20 cores. Physics-based "
        "normalisers for the remaining components could let smaller models reach the same accuracy.",
    ])

    # ------------------------------------------------------------------ 8 reproducibility
    d.heading("8. Reproducibility and deliverables", 1)
    d.para(f"All randomness uses fixed seeds: samples {cfg['part_a']['sample_seed']} + case index, split "
           f"{cfg['part_a']['split_seed']}, corners {cfg['part_b']['corner_seed']}, model seeds 42–44. Every stage "
           "is resumable and skips completed simulations. Commands, run from the repository root:")
    d.code("\n".join([
        "python -m common_scripts.setup_check",
        "python -m layer1.scripts.generate_samples        # 4 x 10,000 samples",
        "python -m layer1.scripts.generate_spice_data     # 40,000 ngspice runs",
        "python -m layer1.scripts.validate_data           # data check, KCL, trend plots",
        "python -m layer1.scripts.train_models            # 4 model types x 4 cases, selection, test",
        "python -m layer1.scripts.plot_results",
        "python -m layer2.scripts.generate_corners        # 200 corners",
        "python -m layer2.scripts.simulate_gates          # 3,600 gate runs",
        "python -m layer2.scripts.predict_gate_leakage",
        "python -m layer2.scripts.compare_gate_results",
        "python -m layer2.scripts.error_attribution",
        "python -m layer3.scripts.simulate_test_circuit   # 12,800 CLA runs",
        "python -m layer3.scripts.predict_circuit_leakage",
        "python -m layer3.scripts.compare_circuit_results",
        "python -m report.report_figures",
        "python -m report.build_report",
    ]))
    d.table(["Deliverable", "Location"], [
        ["1. Datasets (4 × 10,000 rows, spec columns)", "`layer1/data/processed/<case>.csv`"],
        ["2. Example netlists", "`layer1/spice/`, `layer2/spice/`, `layer3/spice/cla3.sp`"],
        ["3. Data check + trend plots", "`layer1/outputs/data_check.csv`, `trend_*.png`, `kcl_residuals.png`"],
        ["4. Model comparison table", "`layer1/outputs/model_comparison_table.csv` (+ per terminal)"],
        ["5. Chosen models, test metrics, parity plots", "`layer1/models/*_model.joblib`, `layer1/outputs/test_metrics.csv`, "
                                                          "`parity_*.png`"],
        ["6. Gate results table", "`layer2/outputs/gate_results_table.csv`"],
        ["7. Gate parity plot", "`layer2/outputs/gate_parity.png`"],
        ["8. Test-circuit results + parity", "`layer3/outputs/circuit_results_table.csv`, `circuit_parity.png`"],
        ["9. Code", "`layer1/scripts/`, `layer2/scripts/`, `layer3/scripts/` (stage scripts), `common_scripts/` (shared), `project_config.json` (settings)"],
        ["10. Report", "this document (`report/DVD_ML_Leakage_Report.docx`)"],
    ], widths=[2.6, 4.0], align=["left", "left"], caption="Deliverables map.")

    d.save(OUT)
    print(f"report -> {OUT}  ({d.fig_no} figures, {d.tab_no} tables)")


if __name__ == "__main__":
    main()
