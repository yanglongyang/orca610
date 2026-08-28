# Review Notes — migration from AutoORCA 2.1 to 3.0

Date: 2026-08-28

This review focused on scientific correctness first, then automation robustness.

## Critical issues found in the old repository

### 1. No energy-consistency gate

The old `SKILL.md` described phase validation but never required method/basis/solvent consistency for energy differences. This allowed a workflow to optimize S0 and S1 at different levels and later combine absolute energies into E00/reorganization quantities without a hard stop.

**Fix:** added the ENERGY-CONSISTENCY GATE, four-point definitions, inequalities, closure checks, and `scripts/energy_cycle_guard.py`.

### 2. ESD(IC) used the wrong geometry and wrong fallback

Old `phase3_esd.sh` built ESD(IC) from the S1 optimized geometry. The ORCA 6.1 manual's IC example uses the **ground-state geometry**, with GS and ES Hessians supplied.

The old script also silently used the S0 Hessian as the S1 Hessian when an S1 Hessian was absent. That hides a PES approximation and can make the result look more rigorous than it is.

**Fix:** phase 3 now requires S0 geometry + S0 Hessian + S1 Hessian and stops when a required file is missing.

### 3. ESD(IC) used TDA even though the ORCA 6.1 manual recommends full TD-DFT for NACME

Old input: `tda true`.

Official ORCA 6.1 Sec. 5.5.5 example: `tda false # Full TDDFT is recommended over TDA`.

**Fix:** `IC_TDA=false` by default.

### 4. “B3LYP TD-DFT gradients are not reliably supported” was overgeneralized

The repository converted a local sequence of ORCA 6.1.0/LibXC crashes into a general ORCA claim. The ORCA 6.1 manual states that analytic gradients are available for TD-DFT generally.

**Fix:** the failure record is retained under `templates/deprecated/` but relabeled as a local environment observation. The README no longer tells users to avoid B3LYP globally.

### 5. `%MaxCore` semantics were wrong

Old `SKILL.md` said `%maxcore` was effectively per displacement group. ORCA 6.1 documents `%MaxCore` as MB **per processing core** and recommends budgeting roughly `MaxCore * nprocs` below available RAM with margin.

**Fix:** corrected in `SKILL.md` and configuration comments.

## Major automation defects found

### 6. Template metadata was hard-coded regardless of the actual input

Old `save_template()` always wrote:

- CAM-B3LYP
- 6-31G(d)
- CPCM(Methanol)
- D3BJ
- charge +1
- multiplicity 1

This was scientifically dangerous because a successful run with a different method could be archived under false provenance.

**Fix:** metadata is passed explicitly to `save_template()` and filenames are generated from those values.

### 7. Status printing was hard-coded to LSH-33 and LSH-34

Old `print_status()` iterated exactly those two molecule names, contradicting the claim that the skill was generic.

**Fix:** dynamic iteration over `cascade_status.json`.

### 8. `cascade_status.json` was described as auto-created but no initializer existed

Old `update_status()` immediately opened the file and would fail if it did not already exist.

**Fix:** added `init_status()` and defensive creation in `update_status()`.

### 9. Template lookup naming did not match stored template filenames

The old phase-2 slug construction produced forms such as `cam-b3lyp` / `6-31gd`, while repository templates used `camb3lyp` / `631gd`. Therefore the advertised template reuse path could silently miss templates and fall back to inline input generation.

**Fix:** one `slugify()` convention is used everywhere; duplicate hyphen/underscore templates were removed.

### 10. Missing frequency output could be accepted as “zero imaginary frequencies”

Old `check_imag()` returned success when the frequency-summary grep returned nothing.

**Fix:** three-state result: zero imaginary / imaginary present / summary missing. Missing summary is a hard stop.

### 11. Normal termination was treated as optimization convergence

Old S1 phase used `ORCA TERMINATED NORMALLY` as the convergence check.

**Fix:** explicit optimization-convergence check (`HURRAY` / convergence marker) plus frequency gate.

### 12. Emission extraction could accidentally read a spectrum from a displaced frequency subcalculation

A combined Opt/Freq output can contain many electronic-structure evaluations. Taking the last spectrum is not a safe definition of the final vertical emission.

**Fix:** phase 2 performs a separate clean vertical-emission single point on the final S1 geometry.

### 13. Root number was treated as state identity

Old workflow extracted root 1 without requiring NTO/configuration continuity.

**Fix:** `FOLLOWIROOT`, NTO generation, final-root recording, and a persistent warning that state identity still requires character inspection.

## Reporting issues fixed

### 14. Quantum yield was presented as complete using only k_r and k_IC

Old report used:

`Phi_F = k_r / (k_r + k_IC)`

without acknowledging ISC or other nonradiative pathways.

**Fix:** renamed to `Phi_F(two-channel)` unless additional rates are supplied. The report explicitly states its approximation.

### 15. Radiative rate from a single oscillator strength was presented too strongly

The old code estimated `k_r` from vertical `f` and emission energy and then treated it like a complete radiative rate.

**Fix:** renamed `k_r_approx`; the skill recommends `ESD(FLUOR)` for vibronic fluorescence rates/spectra when appropriate.

## Official ORCA 6.1 anchors used for this revision

- Sec. 2.1.3 — Global Memory Use
- Sec. 2.5 — Parallel and Multi-Process Runs
- Sec. 4.6 — Vibrational Frequencies
- Sec. 5.5 / 5.5.5 — Excited State Dynamics / Internal Conversion
- Sec. 5.6.6 — LR-CPCM equilibrium vs non-equilibrium
- Sec. 5.6.16 — excited-state optimization and FOLLOWIROOT
- Sec. 5.10.4 — STEOM Percentage Active Character
- Sec. 5.10.8 — STEOM solvation

Official manual: https://www.faccts.de/docs/orca/6.1/manual/
