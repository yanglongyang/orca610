#!/bin/bash
#==============================================================================
# Autopilot Cascade — runs Phase 2, 3, 4 sequentially with auto-review gates.
# Submit ONCE to tsp. No human intervention needed between phases.
#==============================================================================
set -e
WORKDIR="/data/software/orca610/34qy"
cd "$WORKDIR"
source shared_functions.sh

log "=================================================="
log "  AUTOPILOT CASCADE: Phase 1 → 2 → 3 → 4"
log "=================================================="

#--------------------------------------------------------------------
# Phase 1: S₀ Opt+Freq
#--------------------------------------------------------------------
log ""
log "########## PHASE 1: S₀ Opt+Freq ##########"
bash phase1_s0.sh
log "Phase 1 complete."

# Auto-review S₀ results
python3 << 'PYEOF'
import json
with open("/data/software/orca610/34qy/cascade_status.json") as f:
    d = json.load(f)
issues = []
for mol in ["LSH-33", "LSH-34"]:
    m = d["molecules"][mol]
    e = m.get("s0_energy") or 0
    imag = m.get("s0_imag_freq") or 0
    print(f"[REVIEW] {mol}: S0={e:.6f} Eh, imag_freq={int(imag)}")
    if imag > 0:
        issues.append(f"{mol}: {int(imag)} imaginary frequencies!")
    if e == 0:
        issues.append(f"{mol}: S0 energy not extracted")
if issues:
    print("[REVIEW] ISSUES FOUND:")
    for i in issues: print(f"  - {i}")
    exit(1)
print("[REVIEW] All S0 results OK — proceeding to Phase 2")
PYEOF

#--------------------------------------------------------------------
# Phase 2: S₁ TD-DFT Opt
#--------------------------------------------------------------------
log ""
log "########## PHASE 2: S₁ TD-DFT Opt ##########"
bash phase2_s1.sh
log "Phase 2 complete."

# Auto-review S₁ results
python3 << 'PYEOF'
import json
with open("/data/software/orca610/34qy/cascade_status.json") as f:
    d = json.load(f)
issues = []
for mol in ["LSH-33", "LSH-34"]:
    m = d["molecules"][mol]
    e = m.get("s1_energy_cm1") or 0
    f = m.get("s1_f_osc") or 0
    conv = m.get("s1_converged")
    print(f"[REVIEW] {mol}: E_em={e:.1f} cm-1, f={f:.6f}, converged={conv}")
    if not conv:
        issues.append(f"{mol}: S1 did not converge")
    if e <= 0:
        issues.append(f"{mol}: E_em={e:.1f} cm-1 is <=0 (data extraction likely failed)")
    elif e < 5000 or e > 40000:
        issues.append(f"{mol}: E_em={e:.1f} cm-1 looks unreasonable (expected 5000-40000)")
    if f <= 0:
        issues.append(f"{mol}: f={f:.6f} is <=0 (data extraction likely failed)")
    elif f < 0.001:
        issues.append(f"{mol}: f={f:.6f} very small — possibly dark state, check iroot")
if issues:
    print("[REVIEW] ISSUES FOUND:")
    for i in issues: print(f"  - {i}")
    exit(1)
print("[REVIEW] All S1 results look reasonable — proceeding to Phase 3")
PYEOF

#--------------------------------------------------------------------
# Phase 3: ESD-VG IC Rate
#--------------------------------------------------------------------
log ""
log "########## PHASE 3: ESD-VG IC Rate ##########"
bash phase3_esd.sh
log "Phase 3 complete."

# Auto-review ESD results
python3 << 'PYEOF'
import json
with open("/data/software/orca610/34qy/cascade_status.json") as f:
    d = json.load(f)
issues = []
for mol in ["LSH-33", "LSH-34"]:
    m = d["molecules"][mol]
    k = m.get("k_ic") or 0
    print(f"[REVIEW] {mol}: k_IC={k:.4e} s-1")
    if k == 0:
        issues.append(f"{mol}: k_IC=0 — ESD may have failed or extraction issue")
    elif k > 1e15:
        issues.append(f"{mol}: k_IC={k:.2e} s-1 looks extreme")
if issues:
    print("[REVIEW] ISSUES FOUND:")
    for i in issues: print(f"  - {i}")
    exit(1)
print("[REVIEW] All ESD-VG results look reasonable — proceeding to Phase 4")
PYEOF

#--------------------------------------------------------------------
# Phase 4: Quantum Yield + Report
#--------------------------------------------------------------------
log ""
log "########## PHASE 4: Report Generation ##########"
bash phase4_report.sh

log ""
log "=================================================="
log "  AUTOPILOT COMPLETE — Report: cascade_report.md"
log "=================================================="
print_status
