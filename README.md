# AutoORCA — Automated ORCA Photophysics Cascade Framework

A methodology and script toolkit for automating multi-step ORCA quantum chemistry workflows: ground-state optimization → excited-state TD-DFT → ESD internal conversion rates → quantum yield reports.

## What This Repository Contains

```
.
├── README.md                      # This file
├── .gitignore                     # Excludes ORCA outputs, binaries, manual
├── skills/autoorca/SKILL.md       # Claude Code skill — methodology reference
├── scripts/
│   ├── shared_functions.sh        # Core library (run_orca, monitoring, data extraction)
│   ├── phase1_s0.sh               # Template: S0 Opt+Freq
│   ├── phase2_s1.sh               # Template: S1 TD-DFT Opt
│   ├── phase3_esd.sh              # Template: ESD(IC)
│   ├── phase4_report.sh           # Template: quantum yield + report
│   └── autopilot.sh               # Chains all phases with auto-review
└── templates/                     # Empty — your verified templates will accumulate here
    └── .gitkeep
```

## What You Need to Provide

| Resource | How to obtain | Expected location |
|----------|--------------|-------------------|
| **ORCA 6.1 binary** | [ORCA forum](https://orcaforum.kofo.mpg.de) (academic license) | `$ORCA_ROOT/orca` |
| **ORCA 6.1 manual** | Convert the PDF to markdown, or keep the PDF as reference | `$ORCA_ROOT/manual/orca_manual_kb/` (optional) |
| **`myorca` wrapper** | A simple script that calls ORCA with the right environment | `~/bin/myorca` or in `$PATH` |
| **`tsp` (Task Spooler)** | `apt install tsp` or equivalent | System utility |
| **Molecule input files** | Your `.inp` or `.xyz` files for the molecules you want to study | `$ORCA_ROOT/<project>/` |

### `myorca` wrapper example

```bash
#!/bin/bash
ORCA_PATH="/path/to/orca/installation"
export PATH=$ORCA_PATH:$PATH
export LD_LIBRARY_PATH=$ORCA_PATH:$LD_LIBRARY_PATH
$ORCA_PATH/orca "$1" > "${1%.inp}.out" 2>&1
```

## Quick Start

```bash
# 1. Create a project directory
mkdir -p $ORCA_ROOT/my-project
cd $ORCA_ROOT/my-project

# 2. Copy the phase script templates
cp $ORCA_ROOT/scripts/phase1_s0.sh .
cp $ORCA_ROOT/scripts/phase2_s1.sh .
cp $ORCA_ROOT/scripts/phase3_esd.sh .
cp $ORCA_ROOT/scripts/phase4_report.sh .
cp $ORCA_ROOT/scripts/autopilot.sh .

# 3. Edit each phase script — set MOLECULES, INPUTS, and functional/basis
# 4. Place your molecule .inp files in the project directory
# 5. Run the full cascade
tsp bash autopilot.sh
```

## How It Works

### Phased Architecture

Each phase runs independently with review gates between them:

```
Phase 1: S0 Opt+Freq  →  check imaginary frequencies  →  extract S0 energy
Phase 2: S1 TD-DFT Opt  →  extract E_em, f_osc  →  validate data
Phase 3: ESD(IC)  →  extract k_IC  →  validate rate
Phase 4: Python script  →  calculate Phi_F  →  write report.md
```

### Shared State

A `cascade_status.json` file in the project directory tracks progress across phases. Each phase reads current state, does its work, updates the state.

### Template Knowledge Base

As calculations succeed, templates are auto-saved to `$ORCA_ROOT/templates/` with `@TYPE`, `@FUNCTIONAL`, `@BASIS`, and `@VERIFIED` tags. This becomes your personal knowledge base — **never** committed to this repository.

### Monitoring

The `run_orca()` function in `shared_functions.sh` runs ORCA in the background and monitors:
- Process existence (detect crashes)
- Output file growth (detect stalls)
- Error patterns (detect input errors, functional issues, file-not-found, etc.)

### Resource Management

- **tsp** ensures serial job execution (no two ORCA jobs run simultaneously)
- **!PAL16(4x4)** syntax for parallel numerical frequency displacements
- Memory and disk budgeting guidelines in the SKILL.md

## ORCA 6.1 Notes

- **CAM-B3LYP** and **PBE0** are recommended for TD-DFT (native gradient support)
- **B3LYP** TD-DFT gradients are NOT reliably supported — avoid
- **ESD(IC)** requires `nacme true` in `%tddft` block (NOT `do_ic`)
- Manual reference: `manual/orca_manual_kb/` (not included — convert from PDF yourself)

## License

This workflow framework is provided as-is for academic use. ORCA itself requires a separate academic license from the Max Planck Institute.
