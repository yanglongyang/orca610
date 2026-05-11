---
name: autoorca
description: Automate ORCA quantum chemistry workflows with phased cascade design, template-based knowledge accumulation, manual-driven debugging, error pattern monitoring, and resource-aware job scheduling. Use when the user asks to run multi-step ORCA calculations, set up automated computational chemistry pipelines, debug ORCA errors, build reusable calculation templates, or manage long-running quantum chemistry jobs. Applies to any functional, basis set, or calculation type — not specific to any one chemistry problem.
version: 2.0.0
---

# AutoORCA — Methodology for Automated Computational Chemistry

This skill encodes the **process**, not specific conclusions. It applies to any ORCA calculation type — swap the functional, basis, solvent, or method and the workflow remains the same.

## Core Principles

1. **Phase the work**: Break multi-step calculations into independent phases with review gates between them
2. **Accumulate knowledge**: Every successful calculation becomes a curated, searchable template
3. **Debug from the manual**: Never guess keywords — search the ORCA manual for correct syntax and working examples
4. **Monitor proactively**: Detect crashes, stalls, and data extraction failures automatically
5. **Respect resources**: queue jobs serially, parallelize at the right level, budget memory and disk

---

## Principle 1: Phased Cascade Architecture

### Why Phase?
A monolithic script that runs everything end-to-end will fail silently at step 3, wasting hours of compute. Phasing creates natural checkpoints where results are validated before proceeding.

### Standard Phase Design
```
Phase N: [Calculation Type]
  → Run calculation for all molecules
  → Extract key data into a shared JSON status file
  → Auto-review: check data against expected ranges
  → On failure: diagnose, fix input, re-run THIS phase only
  → On success: proceed to Phase N+1
```

### Shared State
Use a JSON file (`cascade_status.json`) as the single source of truth between phases:
```json
{
  "phase": "s0_done",
  "molecules": {
    "MOL-1": { "s0_energy": -978.51, "s0_imag_freq": 0, "s1_energy_cm1": null, ... }
  }
}
```
Each phase reads current state, runs its work, updates state.

### Phase Script Template
```bash
#!/bin/bash
source shared_functions.sh   # run_orca, get_*, check_*, update_status, print_status

for mol in "${MOLS[@]}"; do
    if orca_done "$outfile"; then
        log "Already completed — skipping"
    else
        run_orca "$input" || { log "FATAL: $mol failed"; exit 1; }
    fi
    # Extract data, update status
done
update_status --phase "next_phase"
print_status  # Human-readable summary for review
```

### Auto-Review Between Phases
Before advancing, validate extracted data against physical expectations:
```python
# Example: S1 emission data validation
if e_em <= 0:        issues.append("data extraction likely failed")
elif e_em < 5000:    issues.append("unreasonably low emission energy")
if f <= 0:           issues.append("oscillator strength not extracted")
if not converged:    issues.append("optimization did not converge")
```
Adjust thresholds per chemical system. The goal is catching extraction failures and physically impossible values — NOT enforcing narrow expectations.

---

## Principle 2: Template Knowledge Base

### Why Templates?
Trial-and-error on ORCA keywords is expensive (each attempt costs hours of compute). Templates capture what WORKED so you never solve the same problem twice.

### Template Directory Structure
```
templates/
  ├── s0_opt_freq_<functional>_<basis>.inp    # One per verified combination
  ├── s1_tddft_opt_<functional>_<basis>.inp
  └── esd_ic_<functional>_<basis>.inp
```

### Required Template Header Tags
```
# @TYPE:       <calculation-type>     e.g., s0-opt-freq, s1-tddft-opt, esd-vg-ic
# @FUNCTIONAL: <functional-name>
# @BASIS:      <basis-set>
# @SOLVENT:    <solvent-model>
# @ORCA:       <version>
# @VERIFIED:   <date> — <molecule> — <key result confirming it worked>
```

### Template Lifecycle
```
Run succeeds  →  save_template() auto-creates raw template from working input
              →  Curate: add detailed comments on WHY each setting, failed attempts, caveats
              →  Mark @VERIFIED with date and evidence
              
Run fails     →  If template existed and was the basis: update with failure log
              →  Mark @STATUS: DEPRECATED, point to working alternative
              →  Never delete — failures are as educational as successes
```

### When to Create Templates
- **After first successful run** of a new calculation type + functional + basis combination
- **When a known combination is used on a chemically different system** (add note about system type)
- **When a workaround is discovered** for a specific ORCA version limitation

### When NOT to Create Templates
- Never pre-create templates for calculation types not yet run
- Never from failed calculations (unless deprecating an existing one)

### Searching Templates
```bash
grep -l "@TYPE: s1-tddft-opt" templates/*           # By calculation type
grep -l "@FUNCTIONAL: CAM-B3LYP" templates/*         # By functional
grep "@VERIFIED" templates/* | grep -v "PENDING\|DEPRECATED\|FAILED"  # Only verified
```

---

## Principle 3: Manual-Driven Debugging

### The Debugging Protocol
When ORCA produces an error, follow this exact sequence:

1. **Read the exact error**: `tail -30 output.out` or `grep -i "error\|abort\|fatal" output.out`
2. **Search the manual for the keyword**: `grep -r "<error keyword>" manual/orca_manual_kb/`
3. **Find working examples in the manual**: Look for complete input blocks — they show correct syntax
4. **Test with minimal system**: Create a 2-3 atom test input before running full molecule
5. **Validate**: Run the test, confirm the fix, THEN run the full calculation

### Common Manual Search Patterns
```bash
# Find all files mentioning a topic
grep -rl "internal conversion" manual/orca_manual_kb/

# Find keyword syntax in context
grep -B5 -A15 "ESD(IC)" manual/orca_manual_kb/<relevant_file>.md

# Extract complete example inputs (invaluable for syntax)
grep -B10 -A20 "xyzfile" manual/orca_manual_kb/<relevant_file>.md
```

### The Manual IS the Authority
- ORCA version-specific syntax differences are only documented in the manual
- Example inputs in the manual have been tested by the developers
- If the manual says a keyword exists and it doesn't work, check the ORCA version and changelog

---

## Principle 4: Proactive Monitoring

### What to Monitor
Don't just wait for `ORCA TERMINATED NORMALLY` — watch for failures in real-time.

### Process + Output Monitoring Pattern
```bash
run_orca() {
    /path/to/orca "$input" &    # Launch in background
    local pid=$!
    
    while kill -0 "$pid" 2>/dev/null; do
        sleep 180  # Check every 3 minutes
        
        # 1. Detect stalls (output not growing)
        if [ "$current_size" -eq "$last_size" ]; then
            stall_count=$((stall_count + 1))
        fi
        
        # 2. Scan for error patterns in output
        for pattern in "${ERROR_PATTERNS[@]}"; do
            if grep -q "$pattern" "$outfile"; then
                kill -9 "$pid"
                diagnose_error "$outfile" "$pattern"
                return 1
            fi
        done
    done
    
    # 3. Process ended — verify normal termination
    grep -q "ORCA TERMINATED NORMALLY" "$outfile" || { diagnose_error; return 1; }
}
```

### Error Pattern Library
Build the `ERROR_PATTERNS` array cumulatively — each new failure type enriches monitoring:
```bash
ERROR_PATTERNS=(
    "INPUT ERROR"                          # Invalid keyword in ! line
    "UNRECOGNIZED OR DUPLICATED KEYWORD"   # Typo or unsupported keyword
    "FATAL ERROR"                          # Generic module crash
    "Unknown identifier in"                # Invalid keyword in %block
    "expect a '\$', '!', '%'"              # Input file syntax error
    "does not exist"                       # Missing file reference
    "segmentation fault"                   # Memory corruption or bug
    # Add new patterns as discovered
)
```
After each new error type: add it to the patterns array. The monitoring system gets smarter every run.

### Diagnosis on Failure
```bash
diagnose_error() {
    echo "=== Last 20 lines of output ==="
    tail -20 "$outfile"
    echo "=== Error context ==="
    grep -i -B2 -A5 "error\|abort\|fatal" "$outfile" | tail -30
}
```
The goal: when something fails, the diagnosis should be in the log, not require re-running to reproduce.

---

## Principle 5: Resource Management

### Serial Job Queue (tsp)
```bash
tsp myorca mol1.inp    # Queue job 1
tsp myorca mol2.inp    # Queued behind job 1 — runs when job 1 finishes
```
tsp enforces serial execution. No two ORCA jobs run simultaneously unless explicitly designed to.

### Parallel Displacement Execution (for numerical frequencies)
ORCA 6.1 supports displacement-level parallelism via `nprocs_group`:
```
!PAL16(4x4)    # 16 total cores, 4 per displacement → 4 simultaneous displacements
```
Each displacement calculation is independent — near-linear speedup with group count.

### Memory Budgeting
```
%maxcore N    # MB per displacement group (not per core)
```
With G groups: peak memory ≈ G × N MB. Check `free -h` before starting.

### Disk Budgeting
Numerical frequency output grows with displacement count: ~2 MB per displacement accumulated in the output file. For N atoms with central differences: 6N × 2 MB. Check `df -h` before starting.

---

## Principle 6: Email Notifications

### Why Notify?
Long calculations (hours to days) don't require constant monitoring. Email notifications let you know when a phase completes or the entire cascade finishes.

### Configuration
Set environment variables before running phase scripts or autopilot:
```bash
export SMTP_PASS="your-auth-code"      # Required — SMTP authorization code
export EMAIL_TO="you@example.com"      # Default: same as SMTP_USER
export SMTP_HOST="smtp.163.com"        # Default: smtp.163.com
export SMTP_PORT="465"                 # Default: 465 (SSL)
export SMTP_USER="you@example.com"     # Default: same as EMAIL_TO
```

### SMTP Providers
| Provider | SMTP_HOST | PORT | Auth Method |
|----------|-----------|:---:|-------------|
| 163.com | smtp.163.com | 465 | Authorization code (not login password) |
| QQ Mail | smtp.qq.com | 465 | Authorization code |
| Gmail | smtp.gmail.com | 587 | App password |

### Automatic Triggers
- `phase3_esd.sh` calls `notify_summary "ESD(IC) Complete"` after both ESD jobs finish
- `phase4_report.sh` calls `notify_summary "Cascade Complete"` after report generation
- `notify_summary()` reads `cascade_status.json` and includes all key data in the email body

### Email Format
```
Subject: [AutoORCA] ESD(IC) Complete — 05/11 15:30
Body:
  Phase: esd_done
  MOL1:
    s0_energy: -978.51
    s1_energy_cm1: 19459.9
    k_ic: 0.0495
    ...
  Working directory: /data/software/orca610/34qy
```

---

## Recipe: Setting Up a New Cascade

Apply this methodology to any multi-step calculation:

1. **Understand the chemistry**: What are the input molecules? What properties do you need?
2. **Design the phases**: What calculations must precede what? What data flows between them?
3. **Choose functional/basis**: Consult manual for method-specific limitations (gradient support, solvent compatibility)
4. **Create templates**: Start empty — templates grow as calculations succeed
5. **Write phase scripts**: One script per phase, all sourcing shared_functions.sh
6. **Set up monitoring**: Initialize ERROR_PATTERNS, write diagnose_error()
7. **Budget resources**: Memory per job × concurrent jobs vs available RAM. Disk for output accumulation
8. **Test one molecule first**: Run the full cascade on the simplest molecule before scaling up
9. **Submit with tsp**: Single command, serial execution, auto-continuation
10. **Accumulate templates**: After each success, curate the template with discovered knowledge

---

## Project Directory Structure

```
$ORCA_ROOT/                          # /data/software/orca610
  ├── orca                           # ORCA binary
  ├── manual/orca_manual_kb/         # ORCA 6.1 manual in markdown (shared, read-only)
  ├── templates/                     # Verified calculation templates (shared, accumulates)
  │   ├── s0_opt_freq_*.inp
  │   ├── s1_tddft_opt_*.inp
  │   └── esd_vg_ic_*.inp
  ├── scripts/
  │   └── shared_functions.sh        # run_orca, get_*, check_*, save_template, etc.
  └── <project>/                     # One subdirectory per project
      ├── MOL-1.inp                  # Input files
      ├── MOL-1.out                  # Output files (generated)
      ├── phase1_s0.sh               # Phase scripts (customize per project)
      ├── phase2_s1.sh
      ├── phase3_esd.sh
      ├── autopilot.sh               # Chains all phases
      └── cascade_status.json        # Shared state (auto-created)
```

Shared resources (`manual/`, `templates/`, `scripts/`) live at `$ORCA_ROOT`.
Project-specific files live in `$ORCA_ROOT/<project>/`.

---

## Quick Reference: ORCA 6.1 Manual Sections

All paths relative to `$ORCA_ROOT/manual/orca_manual_kb/`:

| Topic | Path |
|-------|------|
| Input file structure | `07_Essential_Calculation_Elements/01_general_structure_of_the_input_file.md` |
| Parallel execution | `07_.../05_parallel_and_multi-process_runs.md` |
| Dispersion corrections | `08_Model_Chemistries/04_dispersion_corrections.md` |
| NumFreq / Hessian | `09_Structure_and_Reactivity/06_vibrational_frequencies.md` |
| ESD (excited state dynamics) | `10_Spectroscopy_and_Properties/05_excited_state_dynamics.md` |
| TD-DFT excited states | `10_.../06_excited_states_via_rpa_cis_td-dft_and_sf-tda.md` |
| Compound jobs / automation | `13_Workflows_and_Automatization/` |
| Change log (version diffs) | `16_Detailed_change_log/` |
| Full index | `20_Index/01_content.md` |
