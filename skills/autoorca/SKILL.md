---
name: autoorca
description: Build, run, validate, and debug ORCA 6.1 computational-chemistry workflows with explicit method provenance, energy-consistency gates, excited-state identity tracking, manual-driven syntax verification, and resource-aware automation. Use for multi-step ORCA calculations, photophysics workflows, TD-DFT/STEOM diagnostics, ESD rate calculations, reusable templates, and long-running job orchestration.
version: 3.4.6
---

# AutoORCA — Scientifically Guarded ORCA Workflows

This skill automates **process without relaxing physical consistency**. A calculation is not considered successful merely because ORCA terminates normally: the workflow must also preserve method provenance, state identity, and valid energy definitions.

## Core principles

1. **Scientific consistency before automation.** Never let a script combine quantities that are not physically comparable.
2. **Human review before execution.** Every newly generated or modified ORCA input must be inspected and explicitly approved before it runs.
3. **Record method provenance.** Every reported number must carry the electronic method, functional, basis, dispersion, solvent treatment, charge/multiplicity, excited-state formalism, geometry source, and ORCA version needed to interpret it.
4. **Phase the work.** Use independent stages with review gates and restartability.
5. **Track the electronic state, not only the root number.** `IROOT 1` is an ordering label, not a permanent state identity.
6. **Controlled comparisons only.** When testing TDA vs full TD-DFT, basis sets, functionals, solvent models, etc., change one variable at a time unless explicitly performing a factorial comparison.
7. **Use the ORCA manual as the syntax authority.** Treat local observations as local until confirmed by the manual/changelog.
8. **Do not choose a method because it gives the expected answer.** Agreement with a desired color, wavelength, or literature value is evidence to evaluate, not a criterion for method selection.
9. **Respect computational resources.** Parallelism, `%MaxCore`, scratch, and queueing must reflect the actual machine.
10. **Never let an ordinal root choose the science.** A human selects the R0 state from energy/oscillator-strength/NTO evidence and confirms its identity after S1 optimization.
11. **Use experience before generation.** Archived successes, known failures, and local observations must constrain new input construction before human review.

---

# 1. Calculation identity and provenance

For every important result, maintain a method fingerprint. At minimum record:

```text
method_family:      DFT / TD-DFT / STEOM-CCSD / DLPNO-STEOM-CCSD / ...
functional:         CAM-B3LYP / PBE0 / ... (if applicable)
basis:              def2-SVPD / def2-TZVPD / ...
dispersion:         D3BJ / D4 / none
solvent_model:      CPCM / SMD / none
solvent:            water / methanol / ...
solvent_regime:     equilibrium / non-equilibrium / method-default
tda:                true / false / n.a.
relativistic:       none / ZORA / DKH / ...
charge:             integer
multiplicity:       integer
root_requested:     integer or n.a.
state_identity:     NTO/configuration description when relevant
geometry_source:    calculation that produced the coordinates
orca_version:       exact build if known
```

A geometry may be optimized at a cheaper or different level than a final single-point energy. That is allowed. What is **not** allowed is silently subtracting incompatible absolute energies and calling the result an adiabatic gap, reorganization energy, reaction energy, or `E00`.

---

# 2. ENERGY-CONSISTENCY GATE — hard stop

Before calculating or reporting any quantity formed from differences of absolute electronic energies, explicitly list every energy in the expression.

## Required rule

The energies being subtracted must share the same underlying model settings, including as applicable:

- functional,
- basis set,
- dispersion correction,
- solvent model and solvent,
- solvent equilibrium regime when it affects the state energy,
- relativistic treatment,
- frozen-core / PNO / correlation settings that materially define the energy,
- charge and multiplicity.

For an S0/S1 cycle, state-specific formalisms are expected: the two S0 legs may be `DFT`, while the two S1 legs may be `TD-DFT` (or another explicitly recorded excited-state method). Do not require those `method_family` labels to be identical across states. Instead, require the S0 pair to match each other, the S1 pair to match each other (including TDA/response formalism), and all four legs to share the listed underlying settings.

**Different geometry optimization levels are allowed; incompatible shared model settings inside the same energy difference are not.**

If the gate fails:

1. Do not report the derived quantity.
2. Identify which energy legs are inconsistent.
3. Propose consistent single-point calculations on the existing geometries.
4. Rebuild the energy cycle only after those calculations finish.

## Four-point photophysics cycle

Let `R0` be the optimized S0 geometry and `R1` the optimized S1 geometry. Using one consistent final energy level:

```text
E0_R0 = S0 electronic energy at R0
E1_R0 = S1 electronic energy at R0
E0_R1 = S0 electronic energy at R1
E1_R1 = S1 electronic energy at R1
```

Then:

```text
E_abs = E1_R0 - E0_R0                  vertical absorption
E_em  = E1_R1 - E0_R1                  vertical emission
E_ad  = E1_R1 - E0_R0                  adiabatic electronic gap
lambda_e = E1_R0 - E1_R1               excited-state relaxation
lambda_g = E0_R1 - E0_R0               ground-state reorganization
E00 = E_ad + (ZPE_S1_R1 - ZPE_S0_R0)   0-0 energy
```

Sanity checks for an ordinary two-surface relaxation picture:

```text
E_abs >= E_ad >= E_em
E_abs - E_em = lambda_e + lambda_g
lambda_e >= 0
lambda_g >= 0
```

Small violations may arise from numerical noise or differing solvation conventions; large violations are a **hard warning** for mixed methods, wrong state, wrong geometry, wrong sign, or wrong energy extraction.

Do not define `E00` as “vertical emission minus an assumed reorganization energy”. Do not infer a fluorescence-band interval by simply placing the experimental maximum between vertical emission and `E00`.

---

# 3. Controlled method comparisons

A method comparison is interpretable only when the compared calculations differ in the intended variable.

## Examples

### TDA vs full TD-DFT
Use the same:

- geometry,
- functional,
- basis,
- dispersion,
- solvent and solvent regime,
- numerical settings,
- target state.

Change only:

```text
%tddft
  TDA true
end
```

versus

```text
%tddft
  TDA false
end
```

ORCA 6.1 uses TDA as the default TD-DFT approximation; `TDA false` requests full TD-DFT. Never attribute a wavelength shift solely to TDA→full TD-DFT if the basis set or geometry changed at the same time.

### Basis-set convergence
Use one fixed geometry and one fixed electronic method. Compare, for example, `def2-SVPD` and `def2-TZVPD` as single points first. If the shift is unexpectedly large, investigate state identity and diffuse-orbital character before reoptimizing both surfaces.

### Functional comparison
Use the same geometry, basis, solvent settings, TDA/full-TDDFT choice, and target state. A “redder” result is not automatically better.

---

# 4. Ground-state geometry and frequencies

For every S0 minimum:

1. Confirm optimization convergence.
2. Confirm the frequency calculation actually ran.
3. Confirm zero meaningful imaginary frequencies for a minimum.
4. Preserve `.xyz`, `.hess`, `.gbw`, and the output used to establish provenance.

Do not treat “frequency summary not found” as zero imaginary frequencies.

For very low-magnitude imaginary modes, inspect the mode before deciding whether it is numerical noise. Tightening optimization/grid settings or displacing along the mode may be necessary.

---

# 5. TD-DFT absorption and solvation

For vertical absorption in solvent, ORCA 6.1 LR-CPCM uses non-equilibrium solvation by default because excitation is fast relative to solvent nuclear reorganization.

For excited-state geometry optimizations, frequencies, and ORCA_ESD, equilibrium solvation is the default when analytic gradients are requested / inside ESD.

Therefore record `CPCMEQ` behavior explicitly whenever comparing vertical and relaxed-state energies. Do not assume that identical `CPCM(Water)` text means identical solvent response in every stage.

For ICT states:

- prefer a range-separated functional as a candidate, but do not assume it is automatically accurate;
- inspect NTOs / transition densities;
- check basis-set sensitivity, especially diffuse functions;
- consider higher-level references where tractable.

---

# 6. Excited-state optimization — state identity gate

A converged excited-state geometry is only valid for interpretation if the intended electronic state was followed.

## Minimum checks

- request enough roots to cover nearby states;
- inspect state composition at the start and end;
- use NTOs when practical;
- use `FOLLOWIROOT TRUE` when crossings/root flipping are plausible;
- if the state changes character substantially, restart or redefine the target state instead of blindly continuing by root number.

Recommended pattern:

```text
%tddft
  NRoots        5
  IRoot         1
  FollowIRoot   true
  DoNTO         true
end
```

`FOLLOWIROOT` is a robustness tool, not proof that the state remained chemically meaningful. Confirm the final state character.

## Excited-state frequency

If an S1 minimum is used for `E00`, vibronic analysis, or an AH ESD calculation, perform an S1 frequency/Hessian calculation when feasible. ORCA 6.1 documentation shows excited-state `Opt Freq` workflows; the frequency step may require numerical differentiation and can be expensive.

A normally terminated excited-state optimization is not sufficient evidence that the structure is a minimum.

---

# 7. Vertical emission

Report vertical emission at the S1 geometry using an explicitly stated final electronic method.

If the S1 geometry was optimized with TDA for stability but the final emission is reported with full TD-DFT, say so. This is a legitimate composite protocol provided the reported emission energy itself is computed consistently at the stated final level.

If `FOLLOWIROOT` changed the numerical root index, do not automatically extract “root 1” as the target emission. Match by state character.

---

# 8. STEOM / DLPNO-STEOM as a high-level reference

Use the phrase **high-level reference** rather than “gold standard” unless an external benchmark justifies stronger language.

For STEOM-CCSD:

- inspect `Percentage Active Character`;
- ORCA 6.1 states that values above 98% are considered converged with respect to active space;
- if below 98%, increase the relevant roots / active-space coverage and reassess;
- a dominant HOMO→LUMO amplitude alone does not replace the active-character diagnostic.

When using STEOM solvation:

```text
%mdci
  DoSolv true
end
```

is required for the CPCM/SMD perturbative solvation correction described by ORCA 6.1, and the manual labels this solvation treatment experimental. Record that limitation.

When comparing a high-level state with a TD-DFT state, match **state composition**, not merely “S1”, “S2”, etc.

---

# 9. ORCA_ESD rules

## Fluorescence

Prefer `ESD(FLUOR)` when the goal is a vibronically resolved fluorescence rate/spectrum rather than converting one vertical oscillator strength into a full experimental quantum yield.

ORCA_ESD can include Franck-Condon/Herzberg-Teller effects and, with CPCM, applies the documented refractive-index treatment to the fluorescence rate.

## Internal conversion

For `ESD(IC)` in ORCA 6.1:

- provide the **ground-state geometry matching the ground-state Hessian**;
- provide both ground-state and excited-state Hessians for an AH-style calculation;
- use NACME (`nacme true`) and ETF (`etf true`);
- the ORCA 6.1 manual recommends **full TD-DFT** (`TDA false`) for the NACME calculation;
- do not silently replace a missing S1 Hessian with the S0 Hessian and call the result an exact AH IC calculation.

Reference pattern:

```text
! CAM-B3LYP def2-SVP ESD(IC) CPCM(Methanol) TightSCF

%tddft
  TDA false
  NRoots 5
  IRoot 1
  NACME true
  ETF true
end

%esd
  GSHessian "mol_S0.hess"
  ESHessian "mol_S1.hess"
  UseJ true
end

* xyzfile 0 1 mol_S0.xyz
```

If an approximate excited-state PES is required, generate and document that approximation explicitly. Never disguise an approximation as a computed S1 Hessian.

---

# 10. Radiative rates and quantum yield

Do not report a general fluorescence quantum yield from only `k_r` and `k_IC` unless the two-channel assumption is explicitly stated.

General kinetic expression:

```text
Phi_F = k_r / (k_r + k_IC + k_ISC + k_nr,other + ...)
```

If only `k_r` and `k_IC` are available, report:

```text
Phi_F(two-channel) = k_r / (k_r + k_IC)
```

and label it an approximation / upper-bound-like model, not a complete experimental quantum yield prediction.

A radiative rate estimated from a vertical oscillator strength is also an approximation. Prefer ORCA_ESD fluorescence rates when vibronic effects matter.

---

# 11. Manual-driven debugging and version claims

When ORCA fails:

1. read the exact error and nearby warnings;
2. search the ORCA 6.1 manual for the relevant module/keyword;
3. check the detailed changelog;
4. reproduce with a minimal test system if practical;
5. only then promote a workaround into a reusable rule.

Distinguish:

```text
Official limitation: documented by the manual/changelog.
Local observation: reproducible in this exact ORCA build/environment.
Hypothesis: plausible explanation not yet confirmed.
```

Do not convert a local crash into statements such as “B3LYP TD-DFT gradients are unsupported in ORCA 6.1” unless official documentation confirms that scope. ORCA 6.1 documents analytic TD-DFT gradients generally.

---

# 12. Template lifecycle

A template is evidence that a syntax/protocol ran, not evidence that the method is universally appropriate.

Required metadata:

```text
# @TYPE:
# @FUNCTIONAL:
# @BASIS:
# @DISPERSION:
# @SOLVENT:
# @TDA:
# @CHARGE:
# @MULT:
# @ORCA:
# @SYSTEM:
# @STATUS: VERIFIED / PENDING / DEPRECATED
# @VERIFIED:
```

Rules:

- never auto-label a template with hard-coded functional/basis/charge values that were not parsed or supplied;
- never mark a calculation “verified” solely because ORCA terminated normally;
- for optimization templates, require optimization convergence;
- for minimum-geometry templates, require the intended frequency check;
- preserve deprecated templates separately from active templates;
- avoid duplicate filenames that differ only by hyphen/underscore conventions.

---

# 13. Resource management

ORCA 6.1 `%MaxCore` is a memory limit **per processing core**, not per displacement group. A conservative rule is:

```text
MaxCore_MB * nprocs <= ~0.75 * available_RAM_MB
```

Allow margin because ORCA can exceed `%MaxCore` in some modules.

For numerical frequencies/gradients, ORCA supports multi-process grouping through `%pal nprocs` + `nprocs_group` and convenience forms such as `PAL16(4x4)`.

Do not hard-code one core count for every machine. Read it from project configuration / environment. Queue independent full jobs serially unless intentional concurrency is budgeted.

---

# 14. Phased cascade architecture

A robust photophysics workflow may look like:

```text
Phase 0  structure preparation / conformer check
Phase 1  S0 optimization + frequency
Phase 2  vertical absorption at R0
Phase 3  S1 optimization + state tracking
Phase 4  S1 frequency/Hessian when needed
Phase 5  vertical emission at R1
Phase 6  consistent four-point energies / E00 if requested
Phase 7  high-level reference calculations
Phase 8  ESD fluorescence / IC / ISC where justified
Phase 9  report with provenance and uncertainty
```

Not every project needs every phase. Add only calculations that answer the scientific question.

At each review gate ask:

```text
Did ORCA finish?
Did the intended optimization/frequency/state calculation finish?
Is the state identity correct?
Are the method fingerprints compatible for the quantity being derived?
Are the units and signs plausible?
Does a physical sanity check fail?
```

A failed scientific gate stops the cascade even when the software exit code is zero.

---

# 15. Reporting language

Use calibrated conclusions.

Prefer:

```text
"The tested TD-DFT protocols predict shorter wavelengths than the
DLPNO-STEOM-CCSD high-level reference for this state."
```

Avoid:

```text
"TD-DFT is intrinsically wrong for this molecule."
"The reddest method is the best method."
"The high-level result proves the experimental maximum before a spectrum is measured."
```

When experiment is only visual color, say “qualitatively consistent with red emission”; do not claim quantitative wavelength agreement.

---

# 16. ORCA 6.1 manual anchors

Use the installed/local manual when available. The most relevant official sections are:

- 2.1.3 — Global Memory Use (`%MaxCore` per processing core)
- 2.5 — Parallel and Multi-Process Runs
- 4.6 — Vibrational Frequencies
- 5.5 — Excited State Dynamics
- 5.5.5 — Internal Conversion Rates
- 5.5.7 — ESD with STEOM/EOM and higher-level methods
- 5.6.6 — LR-CPCM equilibrium vs non-equilibrium conditions
- 5.6.16 — Excited-State Geometry Optimization and `FOLLOWIROOT`
- 5.10.4 — STEOM Percentage Active Character
- 5.10.8 — STEOM solvation (`DoSolv`)
- Appendix 1 — Detailed changelog

Official online manual: `https://www.faccts.de/docs/orca/6.1/manual/`

---

# 17. Fluorescence Probe Analysis (v3.1)

Trigger this mode when comparing an intact probe, released fluorophore, reaction product, or reference dye. Preserve all v3.0 energy/provenance/state-identity gates; this is an added interpretation layer, not a replacement.

1. Read `references/probe_pair_analysis.md` and require matched **phase-specific** protocols before attributing a spectral difference to chemistry. `E00` is reportable only with a passing four-point energy-cycle source.
2. Read `references/ict_nto_analysis.md`; request NTOs for relevant R0/R1 states and verify state identity before comparing them.
3. Use `references/solvent_effects.md` to label fixed-geometry and solvent-relaxed series separately.
4. Use `references/tict_diagnostics.md` only for user-defined dihedrals. A twisted geometry alone is never a TICT conclusion.
5. Use `references/fluorescence_probe_mechanism.md` to report only evidence-ranked hypotheses.

Core commands:

```bash
python3 scripts/probe_pair_compare.py probe_pair_results.json
python3 scripts/solvent_series_report.py solvent_series.json
python3 scripts/tict_scan_builder.py tict_scan.json tict_scan.inp
python3 scripts/fluorescence_probe_report.py report_input.json analysis/
```

Hard rules:

- Do not infer fluorescence quantum yield from oscillator strength alone.
- Do not classify ICT from HOMO/LUMO pictures alone, or TICT from a dihedral alone.
- Do not call a solvent-relaxed calculation a pure solvent effect.
- Do not compare chemically different species' total electronic energies as reaction energies without a balanced thermochemical cycle.
- Do not infer a mechanism from one descriptor; in particular, a HOMO-LUMO-gap shift alone cannot support it.
- Flag likely conformer sensitivity when flexible substituents or D-pi-A torsions can change the spectrum; full ensemble photophysics is outside v3.1.

---

# 18. Mandatory pre-run review gate (v3.2)

Read `references/pre_run_review.md` before generating or executing any ORCA input. Generation, validation, approval, and execution are separate actions:

```text
GENERATED -> REVIEW_REQUIRED -> APPROVED -> RUNNING -> COMPLETED
```

For every generated or modified `.inp`:

1. Run `input_review.py review` and inspect its full raw input, semantic summary, SHA256, dependency manifest, and warnings.
2. Explain important settings and unusual choices to the user.
3. Wait for explicit approval of that exact displayed input/dependency set.
4. Only then invoke `input_approve.py`; this action records `approved_by: human` and hash-bound approval.
5. Rerun the phase or autopilot. `run_orca()` independently verifies approval immediately before launching ORCA.

Never self-approve, infer approval from silence, or add an auto-approval/global-approval bypass. A verified template is not execution approval for a molecule-specific instance. Changes to an input or known external dependency (`xyzfile`, `moinp`, `GSHessian`, `ESHessian`) invalidate approval and require a new review. Existing completed outputs with no review record are `IMPORTED_UNREVIEWED`: review can authorize their transparent use, but never retroactively prove pre-run approval.

---

# 19. State-selection and provenance gates (v3.3)

For an AutoORCA TD-DFT singlet-state workflow, use this mandatory sequence:

```text
S0 Opt/Freq -> R0 vertical TD-DFT/NTO -> human STATE_SELECTION_APPROVED
-> S1 Opt (FOLLOWIROOT true) -> human STATE_IDENTITY_MATCH
-> optional S1 Freq -> emission / ESD / report
```

- Do not default scientifically to `IROOT=1`. The selected root is per species and is hash-bound to its completed R0 vertical input/output by `state_gate.py select`.
- Auto-generated S1 optimization and S1 frequency inputs always write `FOLLOWIROOT true`; never omit or disable it unless the user explicitly requests that exception and records a scientific rationale in the input review.
- S1 optimization is separate from S1 frequency. Set `S1_FREQUENCY=true` only when an S1 Hessian is needed for minimum validation, E00/ZPE, vibronic analysis, or AH ESD.
- Before emission, ESD, or reporting, require `state_gate.py confirm` for the optimized-state input/output. Root following is not itself proof of state identity.
- Generated inputs must carry `# @...` machine-readable provenance lines. The review tool reads these before heuristic parsing; use quoted `xyzfile` coordinates so geometry source and hash are explicit.
- Write `CPCMEQ` explicitly in all AutoORCA TD-DFT inputs. Record the chosen absorption, optimization, frequency, and emission solvent regimes.
- Never execute AutoORCA-generated input by direct `orca`, `$MYORCA`, or `mpirun orca` invocation. Standard phases and ad-hoc inputs must use the review-aware runner: `scripts/run_reviewed_input.sh input.inp`.

---

# 20. Experience-consistency gate (v3.4.5)

Read `references/experience_memory.md` before constructing any ORCA input. The mandatory order is:

```text
identify calculation type -> experience lookup -> manual/method check
-> generate input -> experience preflight PASS -> human input review -> run
```

1. Run `scripts/experience_gate.py lookup --calculation-type TYPE` before writing any input. Search structured rules in `knowledge/rules/`, verified-success templates, deprecated failures, and relevant project-local observations.
2. Classify evidence as `MANUAL_CONFIRMED`, `VERIFIED_SUCCESS`, `VERIFIED_FAILURE`, or `LOCAL_OBSERVATION`; never promote a local crash into a universal method claim automatically.
3. Run `scripts/experience_gate.py check input.inp --calculation-type TYPE` before registering input review. A matching confirmed forbidden pattern, or an exact repeat with identical input hash, dependency fingerprints, and ORCA version, is a hard refusal, not a review warning. Similar local failures remain visible warnings.
4. Use successful templates as syntax/protocol references only. Every molecule-specific instance still needs state selection (when relevant), experience check, and hash-bound human approval.
5. Preserve runtime failures with `record-failure`, including input/provenance/dependency hashes/version/environment; review and curate them before creating a reusable rule. When templates, cases, or rules later change, the runner re-evaluates unchanged inputs. New hard evidence stops execution; irrelevant evidence refreshes only the experience record. Human input approval is never refreshed automatically.

### Human acknowledgement of new experience warnings

When `EXPERIENCE_WARNING_ACK_REQUIRED` is raised, the executing agent must:

1. Display the newly surfaced similar failures and explain why they are similar.
2. State that execution is blocked and that prior input approval does not acknowledge new evidence.
3. Wait for explicit human acknowledgement. Silence, inference, or a previous approval is not acknowledgement.
4. Only then run `experience_gate.py acknowledge input.inp --manifest experience_checks.json --human-acknowledged`.

The executing agent must never acknowledge an experience warning on its own. The acknowledgement record is distinct from input approval and stores `acknowledged_by: human`, `acknowledged_at`, and every matched local-failure record hash. All matching records participate in the gate; command output shows at most five entries plus the total count.

For an acknowledgement-required event, show every newly surfaced similar failure before invoking the acknowledgement command; the five-entry limit applies only to ordinary lookup display.

### AutoORCA software incidents are source fixes, not input experience rules

When a reproducible defect is in AutoORCA's own runner, manifest handling, parser, or gate logic, fix and regression-test the repository source first. Preserve it separately as an engineering incident with trigger, root cause, and fix commit. Do not add a scientific-input experience rule as a substitute for repairing deterministic AutoORCA software.

### ORCA execution-environment gate

Before every launch, compare the input `# @ORCA:` value with the currently resolved ORCA binary version. If unavailable or mismatched, stop with `ORCA_VERSION_REVIEW_REQUIRED`; regenerate the input provenance and obtain a new human input approval. A completed output records its parsed actual version, resolved binary path, and input SHA256 in runtime provenance. Never reuse a prior actual version merely because the input path matches: its SHA256 must also match.

For example, the ORCA 6.1 rule `ORCA61-TDDFT-001` rejects `TDDFT` or `TD-DFT` in the simple `!` line. Use the `%tddft ... end` block instead. Do not repeat a recorded syntax failure merely because an archive was not consulted.
