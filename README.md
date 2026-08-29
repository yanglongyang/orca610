# AutoORCA 3.4.5 — Experience-, State-, and Review-Gated Photophysics

AutoORCA is a methodology + shell-script framework for running multi-step ORCA 6.1 calculations **without allowing automation to hide method inconsistencies**.

The 3.0 revision added scientific guardrails missing from the early version. Version 3.4.5 restores persistent experience memory: prior successes and failures are consulted before input generation, while human state-selection and hash-bound review remain mandatory. The v3.1.1 fluorescence-probe analysis layer remains included.

## Repository layout

```text
.
├── README.md
├── skills/autoorca/SKILL.md
├── references/
│   ├── photophysics_consistency.md
│   ├── probe_pair_analysis.md
│   ├── ict_nto_analysis.md
│   ├── hole_electron_analysis.md
│   ├── solvent_effects.md
│   ├── tict_diagnostics.md
│   └── fluorescence_probe_mechanism.md
├── scripts/
│   ├── project_config.sh.example
│   ├── shared_functions.sh
│   ├── phase1_s0.sh
│   ├── phase2_s1.sh
│   ├── phase3_esd.sh
│   ├── phase4_report.sh
│   ├── energy_cycle_guard.py       # refuses mixed-level E00/energy cycles
│   ├── probe_pair_compare.py        # matched probe/product spectral comparison
│   ├── solvent_series_report.py     # fixed-geometry vs solvent-relaxed gate
│   ├── tict_scan_builder.py         # root-followed S1 dihedral scan input
│   ├── fluorescence_probe_report.py # evidence-ranked Markdown + JSON report
│   ├── input_review.py               # review summary + SHA256 dependency manifest
│   ├── input_approve.py              # records explicit human approval only
│   ├── state_gate.py                 # human R0 selection and S1 identity confirmation
│   ├── experience_gate.py            # pre-generation rules/templates/failure lookup
│   ├── run_reviewed_input.sh         # reviewed runner for ad-hoc calculations
│   └── autopilot.sh
└── templates/
    ├── s0_opt_freq_camb3lyp_631gd.inp
    ├── s1_tddft_opt_camb3lyp_631gd.inp
    ├── esd_ic_ah_camb3lyp_631gd.inp
    ├── historical/                  # project-specific successful examples
    └── deprecated/
        └── ... historical local-failure records
```

## What changed from the early version

### Scientific hard stops

AutoORCA now treats these as errors or explicit warnings rather than silently continuing:

- missing frequency summary is **not** interpreted as zero imaginary frequencies;
- a normally terminated optimization must also show optimization convergence;
- ESD(IC) no longer uses an S1 geometry as the main input geometry;
- ESD(IC) no longer silently substitutes the S0 Hessian for a missing S1 Hessian;
- the IC NACME stage defaults to full TD-DFT (`TDA false`), following the ORCA 6.1 manual recommendation;
- GS/ES Hessian method provenance is compared before ESD(IC);
- state/root identity is recorded and flagged for NTO/configuration review;
- quantum yield is not presented as a complete result when only `k_r` and `k_IC` are known;
- `E00` / reorganization energies are governed by an explicit energy-consistency gate in `SKILL.md`.

### Engineering fixes

The old repository contained several project-specific assumptions despite claiming to be generic. The 3.0 revision removes or fixes them:

- no hard-coded `LSH-33` / `LSH-34` status printing;
- no hard-coded `/home/yang/bin/myorca` requirement (use `MYORCA` env var; default `$HOME/bin/myorca`);
- no hard-coded 16-core inputs (default config uses 8, configurable);
- `%MaxCore` documentation corrected: it is MB **per processing core**;
- `cascade_status.json` is actually auto-created;
- template metadata is no longer hard-coded to CAM-B3LYP/6-31G(d)/MeOH/+1 regardless of the input;
- duplicate hyphen/underscore templates were removed;
- the template filename slug convention is now consistent.

## Quick start

```bash
# 1. Copy scripts into a project directory, or call them from this repository.
cp /path/to/orca610/scripts/project_config.sh.example ./project_config.sh

# 2. Edit project_config.sh
#    - molecules
#    - charge/multiplicity
#    - functional/basis/dispersion/solvent
#    - NPROCS and MAXCORE

# 3. Put initial XYZ files in the working directory:
#    MOL1.xyz, MOL2.xyz, ...

# 4. Configure the ORCA wrapper if needed
export ORCA_ROOT=/data/software/orca610
export MYORCA=$HOME/bin/myorca
export ORCA_VERSION=6.1.0

# 5. Run
AUTOORCA_WORKDIR="$PWD" bash /path/to/orca610/scripts/autopilot.sh
```

## Mandatory pre-run review and state selection (v3.3)

Newly generated inputs never start ORCA immediately. AutoORCA records `REVIEW_REQUIRED`, prints a semantic summary plus the complete raw input, and stops. After inspecting that exact input and explicitly deciding to run it, record the human approval:

```bash
python3 /path/to/orca610/scripts/input_review.py review MOL1_S0_OptFreq.inp
# inspect the displayed complete raw input, settings, SHA256, and dependencies
python3 /path/to/orca610/scripts/input_approve.py MOL1_S0_OptFreq.inp

# rerun the phase/autopilot only after approval
```

Approval is bound to the input SHA256 and hashes for `xyzfile`, `moinp`, `GSHessian`, and `ESHessian` dependencies. Any edit invalidates approval and requires a new review. There is deliberately no global, silent, or auto-approval switch.

The gate is checked before an existing ORCA job or completed `.out` is trusted. Historical outputs with no v3.2 review are labelled `IMPORTED_UNREVIEWED`; reviewing them now permits transparent use, but never retroactively claims pre-run approval. For standalone TICT generation outside `$AUTOORCA_WORKDIR`, pass `--manifest "$INPUT_REVIEW_FILE"` (or export that variable) so it shares the workflow manifest.

For TD-DFT fluorescence workflows, AutoORCA next produces a reviewed R0 vertical absorption/NTO input. After it completes, select the desired per-molecule electronic state explicitly before S1 optimization:

```bash
python3 /path/to/orca610/scripts/state_gate.py select \
  --manifest state_gates.json --species MOL1 \
  --vertical-input MOL1_R0_Absorption.inp --vertical-output MOL1_R0_Absorption.out \
  --root 2 --state-character "donor-to-acceptor ICT" \
  --selection-basis NTO --selection-basis oscillator_strength --selection-basis excitation_energy
```

S1 optimization always writes `FOLLOWIROOT true`, uses the selected root, and is separate from optional S1 frequency work (`S1_FREQUENCY=true`). After S1 optimization, confirm the state at the optimized geometry before emission, ESD, or reporting:

```bash
python3 /path/to/orca610/scripts/state_gate.py confirm \
  --manifest state_gates.json --species MOL1 \
  --opt-input MOL1_S1_Opt.inp --opt-output MOL1_S1_Opt.out \
  --final-root 2 --state-character "donor-to-acceptor ICT" \
  --evidence NTO --evidence oscillator_strength --evidence excitation_energy
```

Use `scripts/run_reviewed_input.sh input.inp` for ad-hoc AutoORCA inputs; never call ORCA or its wrapper directly.

## Experience-consistency gate (v3.4.5)

Before any generated input is written, AutoORCA queries structured known-failure rules, available template evidence, and project-local observations. It repeats the check against the rendered input before human review. A known invalid syntax pattern or an exact repeat of a recorded local failure under the same ORCA version is refused immediately; it cannot become a reviewable input. Similar prior failures are shown as warnings for scientific inspection. For example, ORCA 6.1 rule `ORCA61-TDDFT-001` rejects `TDDFT` / `TD-DFT` in the `!` line and requires TD-DFT controls in `%tddft`.

The preflight record is hash-bound to the input and the complete consulted evidence index (rules, templates, and local cases). If only the evidence index changes, AutoORCA re-evaluates the unchanged input: new hard evidence stops execution; newly surfaced similar local failures require a separate human acknowledgement with `experience_gate.py acknowledge input.inp --manifest experience_checks.json --human-acknowledged`; unrelated changes refresh the experience record without invalidating its independent human input approval. Before launch, the runner requires the input's declared ORCA version to match the currently resolved ORCA binary; a mismatch requires regenerated metadata and new human approval. Afterward it records the output-reported actual version, binary path, and input SHA256 in status provenance. An exact local failure means identical input hash, dependency fingerprints, and ORCA version. Runtime failures persist the full input, machine-readable provenance, dependency fingerprints, ORCA version, selected environment information, and output tail in `experience/cases/failure/` as `LOCAL_OBSERVATION`; they never become universal rules without human curation. See `references/experience_memory.md`.

## Current cascade

```text
Phase 1  S0 Opt+Freq
         -> convergence + imaginary-frequency gate
         -> S0 geometry/Hessian + method provenance

Phase 2  R0 vertical TD-DFT + NTO
         -> human state-selection gate
         -> S1 Opt with FOLLOWIROOT true
         -> human final state-identity gate
         -> optional S1 Freq and clean vertical-emission SP

Phase 3  ESD(IC)
         -> method-compatibility gate for S0/S1 Hessians
         -> ground-state input geometry
         -> approved R0 root at that S0 geometry (not the followed R1 ordinal root)
         -> full TD-DFT NACME by default

Phase 4  Report
         -> approximate radiative rate clearly labeled
         -> two-channel Phi_F clearly labeled when ISC/other knr are absent
         -> provenance + warnings retained
```

## Fluorescence-probe analysis

```text
intact probe
       |
       | enzyme / analyte / chemical reaction
       v
released fluorophore

AutoORCA v3.1:
  S0/S1 -> absorption/emission -> NTO/state identity
       -> controlled pair comparison -> solvent/TICT evidence
       -> evidence-ranked mechanistic report
```

Start with a user-defined project/species file; atom fragments and TICT dihedrals are never guessed:

```bash
python3 scripts/probe_pair_compare.py examples/probe_pair_results.example.json
python3 scripts/solvent_series_report.py examples/solvent_series.example.json
python3 scripts/tict_scan_builder.py examples/tict_scan.example.json tict_scan.inp
```

The v3.1 layer is limited to singlet fluorescence photophysics. It does not add triplet, ISC, phosphorescence, or SOC workflows. A missing Multiwfn installation only records `NOT_RUN` for quantitative hole-electron analysis; ORCA-native NTO analysis still works.

## Important methodological rule: geometry level vs energy level

It is valid to optimize geometries at different or cheaper levels and then evaluate them with a common higher-level method.

It is **not** valid to subtract unrelated absolute energies, for example:

```text
E(S1, CAM-B3LYP/def2-SVPD) - E(S0, B3LYP/def2-SVP)
```

and call the result an adiabatic excitation energy or `E00`.

For a four-point photophysical cycle, evaluate all four final energy legs at one consistent energy level. See `skills/autoorca/SKILL.md` and `references/photophysics_consistency.md`. A machine-checkable example is provided via `scripts/energy_cycle_guard.py examples/energy_cycle.example.json`.

## ORCA 6.1 points verified against the official manual

- TD-DFT uses TDA by default; `TDA false` requests full TD-DFT.
- `FOLLOWIROOT TRUE` is available for difficult excited-state optimizations.
- LR-CPCM uses non-equilibrium solvation by default for vertical excitation and equilibrium behavior for excited-state gradients/frequencies/ESD unless overridden.
- ESD(IC) requires GS/ES Hessian information; the manual recommends full TD-DFT for NACME and uses the GS geometry in the example.
- STEOM `Percentage Active Character > 98%` is the manual's active-space convergence criterion.
- `%MaxCore` is MB per processing core.

Official manual: https://www.faccts.de/docs/orca/6.1/manual/

## Historical B3LYP failure record

The old repository generalized a local ORCA 6.1.0/LibXC crash into an ORCA-wide statement that B3LYP TD-DFT gradients were unreliable/unsupported. That wording was too strong.

The historical failed input has been retained under `templates/deprecated/` as a **local environment observation**. ORCA 6.1 documentation states that analytic TD-DFT gradients are available generally, so a local failure should be reproduced and checked against the changelog before becoming a global rule.

## Scope

This repository provides workflow guardrails, not a universal recommendation for CAM-B3LYP, 6-31G(d), CPCM, D3BJ, TDA/full TD-DFT, or any other specific method. Method selection remains system- and property-dependent.
