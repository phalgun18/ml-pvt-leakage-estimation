# ML-Driven PVT Variation-Aware Leakage Estimation

Digital VLSI Design course project — team **Watt the leak**.

We estimate CMOS leakage under process, voltage and temperature (PVT)
variation with ML models of single transistors instead of full SPICE runs. We
then validate them hierarchically: transistor → gate → 3-bit CLA.

> **Status:** Parts A, B and C complete. Technical report:
> [report/DVD_ML_Leakage_Report.docx](report/DVD_ML_Leakage_Report.docx).

## 1. Assignment

| Item | Value |
|---|---|
| Model file | `32nm_LP.pm` (repository root): PTM Low Power 32 nm, BSIM4 level 54 (unmodified) |
| Nominal VDD | **0.9 V** (sampled 0.81–0.99 V). The card header says 1.0 V, but 0.9 V is what was assigned. |
| L | 32 nm |
| W | 32–256 nm (1–8 × Lmin) |
| Temperature | −40 to 125 °C |
| Test circuit | 3-bit carry-lookahead adder, Cin = 0 (64 input vectors) |

Process nominals (±10 %, drawn separately for NMOS and PMOS):

| | vth0 (V) | toxe (m) | ndep (cm⁻³) | u0 (m²/V·s) | xj (m) |
|---|---|---|---|---|---|
| NMOS | 0.63 | 1.6e-9 | 4.12e18 | 0.042 | 5e-8 |
| PMOS | −0.5808 | 1.62e-9 | 3.07e18 | 0.016 | 1e-8 |

## 2. Software

* Python 3.11.9 with the packages in `requirements.txt`
* ngspice-46 (`C:/ngspice/Spice64/bin/ngspice_con.exe`; it is not on PATH, so set the path in
  `project_config.json` → `paths.ngspice`)

Setup check:

```bash
# from the repository root
python -m common_scripts.setup_check     # writes logs/setup_check.json
```

## 3. Directory layout

```text
<repo root>/
├─ common_scripts/             shared Python: config, model-card patching, ngspice runner,
│                              netlists, circuits, CLA, transistor model, gate ML, metrics, plotting
│                              ... + setup_check.py (environment check)
├─ project_config.json         all settings: paths, ranges, seeds, tolerances
├─ 32nm_LP.pm                  original model card (read-only; checksum cb3d190c…)
├─ README.md, requirements.txt, logs/setup_check.json, tmp/ (scratch, git-ignored)
├─ report/                     technical report: code, figures, DVD_ML_Leakage_Report.docx
├─ layer1/  Part A   scripts/ | spice/ (4 netlists) | data/raw, data/processed (+splits)
│                    models/*.joblib | outputs/ (data check, trends, comparison, parity) | logs/
├─ layer2/  Part B   scripts/ | spice/ (5 gates) | data/raw (corners, gate SPICE) | data/results
│                    outputs/ (gate table, parity, attribution) | logs/
└─ layer3/  Part C   scripts/ | spice/cla3.sp | data/raw (CLA SPICE summary; full file git-ignored)
                     data/results | outputs/ (CLA tables, parity, rail check) | logs/
```

## 4. How a simulation is run (`common_scripts`)

1. **Model card** (`model_card.py`): the original card is read, and only the five
   process parameters are replaced inside the `nmos` or `pmos` block. The patched
   text is then re-parsed to verify every value. The patched copy is written as
   `card.pm` in a private temp directory, and the original file is never touched.
2. **Netlist** (`netlists.py`): all values are written as literal numbers. Every
   transistor terminal has its own voltage source, and every netlist includes
   `.options gmin=1e-18 abstol=1e-18 reltol=1e-6 vntol=1e-9`.
3. **Run** (`spice_runner.py`): `ngspice_con -b`, with a timeout. A result is accepted
   only if the exit code is 0, there is no error or non-convergence message, each
   requested output is printed exactly once, and every value is finite.
   Results are printed with `set numdgt=15`; ngspice's default of ~6 digits breaks the KCL
   check.

**Current sign convention:** every reported terminal current is `-i(Vx)`, i.e.
positive = current flowing **into** the device terminal. KCL is then
`id + ig + is + ib = 0`.

### Known simulator resolution limit
The card uses a gate resistance model (`rgatemod=1`). When the gate node sits at
≈VDD, the gate-source current can only be resolved to about 4.4e-16 A
(≈ machine-epsilon × VDD / R_gate). BSIM4's internal gate-tunnelling currents for an OFF
PMOS are about 1e-32 A, so PMOS OFF `ig` values near ±4e-16 A are round-off, not
physics. These are flagged in the data check rather than modelled as signal.

## 5. Running the stages

All commands are run from the **repository root**. Every stage skips work that is already done, so it can be safely re-run after an interruption.

### Part A: transistor models
```bash
python -m layer1.scripts.generate_samples          # layer1/data/raw/<case>_samples.csv (seeded)
python -m layer1.scripts.generate_spice_data       # 40k ngspice runs (~5 min, 12 threads)
python -m layer1.scripts.validate_data             # data check, KCL, trend plots
python -m layer1.scripts.train_models              # 4 model types x 4 cases, selection, test
python -m layer1.scripts.plot_results              # parity / error-CDF / comparison plots
```
Options: `--case nmos_off` on any step, `--limit N` (simulation test run),
`--models mlp,hgb` (training subset).

**Model form** (`common_scripts/transistor_model.py`): BSIM4 terminal currents are
exact sums of 7 physical components: channel, 2 junction diodes, 3 gate-tunnelling
paths and impact ionisation. This was verified on all 40k samples to 1e-18 A, i.e.
machine precision. Each component is learned as `log(|component| / physical normaliser)`.
Its sign follows a physics rule that was verified on 100 % of samples. The terminal currents are then
rebuilt by KCL-consistent sums. The model type is selected **per component** on
the validation set: polynomial ridge for subthreshold channel current, MLP for the rest.
### Part B: gate-level validation
```bash
python -m layer2.scripts.generate_corners          # layer2/data/raw/corners.csv (200 corners, seed 31415)
python -m layer2.scripts.simulate_gates            # 3,600 SPICE runs (+ physical self-check)
python -m layer2.scripts.predict_gate_leakage      # ML leakage from the 4 transistor models
python -m layer2.scripts.compare_gate_results      # results table, parity + error plots
python -m layer2.scripts.error_attribution         # which transistor model causes the error
```
Options: `--gate nand2`, `--corner 17` (simulate_gates).

**Gate SPICE.** Netlists are flat, one M-card per transistor (`common_scripts/circuits.py`).
AND2/OR2 are simulated as complete gates. The ground rail is named `vss`, because ngspice
aliases `gnd` to node 0. On top of the required `.options`, gate and circuit netlists add
`.options itl1=1000 itl6=1000 pivrel=0.5` and a `.nodeset` at the logic levels. These are
solver-robustness settings only. Without them, 8 AND2 runs did not converge and 5 converged
falsely, with nodes ~10 µV past the rail and the supply current wrong by up to 230 %. Every run
must also pass a **physical self-check**: the sum of the transistors' own BSIM4 currents into
VDD must equal the supply current within 1e-15 A + 0.1 %, and no node may sit more than 1 µV
outside the rails. Result: 3,600/3,600 runs pass.

**Gate ML leakage** = current drawn from VDD. Each transistor's (Vd, Vg, Vs, Vb) comes from the
SPICE node voltages, and its state (ON/OFF) from Vg. **ON-transistor channel currents are
closed by KCL** at the internal nodes instead of being predicted. An ON channel carries
exactly what the rest of the circuit leaks, but at |Vds| ~ 1e-7 V its conductance × Vds is
far outside the training data. The plain VDD-rail sum is also reported (`ml_leak_direct`):
median 7.2 % → 1.9 % with KCL closure. The same formula fed SPICE's exact per-device
currents reproduces SPICE to a median of ~1e-6 (`layer2/outputs/oracle_check.csv`).

### Part C: 3-bit carry-lookahead adder
```bash
python -m layer3.scripts.simulate_test_circuit     # 64 vectors x 200 corners = 12,800 runs (~35 min)
python -m layer3.scripts.predict_circuit_leakage   # hierarchical ML: sum of Part-B gate predictions
python -m layer3.scripts.compare_circuit_results   # tables, parity, error breakdown
```
**Circuit** (`common_scripts/cla.py`): built only from the five gate types. It has 39 gates
(24 NAND2, 9 AND2, 6 OR2) and 186 transistors. g_i = AND2, p_i = XOR made of 4 NAND2, and
c1..c3 are lookahead AND2/OR2 trees of g/p. s_i = XOR(p_i, c_i), with carry-in c0 = 0. The logic
is verified for all 64 vectors, and each SPICE run is checked again: physical self-check plus
output logic levels.

**ML** (spec method): logic-simulate the CLA, take each gate's Part-B ML leakage at its input
bits and corner, and sum. This ignores inter-gate loading, as the spec says. A gate input held
at 1 by another gate draws gate-tunnelling current from the driver's VDD, which the isolated gate
did not count. That missing current is ~28 % of the CLA leakage. The **loading-aware** variant
adds the ML input current of every gate input that is driven high by another gate. Applied
to the SPICE gate results, the same construction reproduces the full netlist to 0.003 %.

### Gate-tunnelling model form (affects Parts A–C)
Gate-to-channel tunnelling is learned as BSIM4 structures it. The total Igc = igcs + igcd
depends on the gate–source bias and the oxide, not on the drain. Its source share depends on Vds
and is exactly ½ at Vds = 0. The total and igb are trained **without drain-referenced features**.
Logic gates operate at the (Vd, Vs) rail corners, where uniform sampling has ~4 of 10,000
samples. The total then only needs the 1-D edge (source at the rail, ~200 samples).
Validation accuracy is unchanged. Gate-level mean error fell from 5.2 % to 1.4 %, and ML
input-current error fell from ~20 % to ~2 %.

## 6. Results summary

| Level | Median error | P95 error | Mean accuracy |
|---|---|---|---|
| Part A transistor models (test set, selected; per terminal) | 0.001–2.4 % | 0.4–7.4 % | — |
| Part B gates, 3,600 runs | 0.91 % | 4.63 % | **98.59 %** |
| Part C CLA, spec method (no loading), 12,800 runs | 28.6 % | 63.3 % | 69.36 % |
| Part C CLA, loading-aware, 12,800 runs | 0.97 % | 5.12 % | **98.40 %** |

Report (regenerated from the results):
```bash
python -m report.report_figures
python -m report.build_report     # report/DVD_ML_Leakage_Report.docx
```

**Large file.** `layer3/data/raw/part_c_spice.csv` (~370 MB, per-device diagnostics) is
git-ignored. The tracked `part_c_spice_summary.csv` holds everything prediction, resume and
analysis need. Re-running `python -m layer3.scripts.simulate_test_circuit` only simulates vectors
missing from the summary.

## 7. Reproducibility
All randomness uses fixed seeds from the config file: Part A samples `20261115`,
split `42`, Part B/C corners `31415`.
