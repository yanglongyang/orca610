#!/bin/bash
#==============================================================================
# Autopilot — chains Phase 1 → 2 → 3 → 4 with auto-review between phases.
# Customize: source the project's shared_functions.sh, adjust review thresholds.
#==============================================================================
set -e
SCRIPT_DIR="$(dirname "$0")"
source "$SCRIPT_DIR/shared_functions.sh"

log "=================================================="
log "  AUTOPILOT: Phase 1 -> 2 -> 3 -> 4"
log "=================================================="

# ---- Phase 1 ----
log ""; log "########## PHASE 1: S0 Opt+Freq ##########"
bash "$SCRIPT_DIR/phase1_s0.sh"

python3 << 'PYEOF'
import json
with open("cascade_status.json") as f:
    d = json.load(f)
issues = []
for mol in d["molecules"]:
    m = d["molecules"][mol]
    e = m.get("s0_energy") or 0
    imag = m.get("s0_imag_freq") or 0
    print(f"[REVIEW] {mol}: S0={e:.6f} Eh, imag_freq={int(imag)}")
    if imag > 0:
        issues.append(f"{mol}: {int(imag)} imaginary frequencies!")
if issues:
    print("[REVIEW] ISSUES:", "; ".join(issues)); exit(1)
print("[REVIEW] S0 OK -> Phase 2")
PYEOF

# ---- Phase 2 ----
log ""; log "########## PHASE 2: S1 TD-DFT Opt ##########"
bash "$SCRIPT_DIR/phase2_s1.sh"

python3 << 'PYEOF'
import json
with open("cascade_status.json") as f:
    d = json.load(f)
issues = []
for mol in d["molecules"]:
    m = d["molecules"][mol]
    e = m.get("s1_energy_cm1") or 0
    f_val = m.get("s1_f_osc") or 0
    conv = m.get("s1_converged")
    print(f"[REVIEW] {mol}: E_em={e:.1f} cm-1, f={f_val:.6f}, conv={conv}")
    if not conv: issues.append(f"{mol}: S1 not converged")
    if e <= 0: issues.append(f"{mol}: E_em<=0 — extraction failed?")
    if f_val <= 0: issues.append(f"{mol}: f<=0 — extraction failed?")
if issues:
    print("[REVIEW] ISSUES:", "; ".join(issues)); exit(1)
print("[REVIEW] S1 OK -> Phase 3")
PYEOF

# ---- Phase 3 ----
log ""; log "########## PHASE 3: ESD(IC) ##########"
bash "$SCRIPT_DIR/phase3_esd.sh"

python3 << 'PYEOF'
import json
with open("cascade_status.json") as f:
    d = json.load(f)
issues = []
for mol in d["molecules"]:
    k = d["molecules"][mol].get("k_ic") or 0
    print(f"[REVIEW] {mol}: k_IC={k:.4e} s-1")
    if k == 0: issues.append(f"{mol}: k_IC=0 — ESD may have failed")
    elif k > 1e15: issues.append(f"{mol}: k_IC={k:.2e} s-1 — extreme value")
if issues:
    print("[REVIEW] ISSUES:", "; ".join(issues)); exit(1)
print("[REVIEW] ESD OK -> Phase 4")
PYEOF

# ---- Phase 4 ----
log ""; log "########## PHASE 4: Report ##########"
bash "$SCRIPT_DIR/phase4_report.sh"

log ""; log "=================================================="
log "  AUTOPILOT COMPLETE — see cascade_report.md"
log "=================================================="
print_status
