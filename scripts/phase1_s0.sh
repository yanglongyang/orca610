#!/bin/bash
#==============================================================================
# Phase 1: S0 Ground State Optimization + Frequency Check
#
# Customize: MOLECULES, INPUT_FILES, FUNCTIONAL, BASIS, SOLVENT below
#==============================================================================
source "$(dirname "$0")/shared_functions.sh"

# ========================== CUSTOMIZE HERE ==========================
MOLECULES=("MOL1" "MOL2")                    # Your molecule basenames
INPUT_FILES=("MOL1.inp" "MOL2.inp")          # Your S0 input files
# ====================================================================

log "=================================================="
log "  PHASE 1: S0 Opt+Freq"
log "=================================================="

ALL_PASS=true

for i in "${!MOLECULES[@]}"; do
    mol="${MOLECULES[$i]}"
    inp="${INPUT_FILES[$i]}"
    out="${mol}.out"

    log "--- $mol S0 ---"

    if orca_done "$out"; then
        log "$out already completed."
    else
        run_orca "$inp" || { log "FATAL: $mol S0 failed"; exit 1; }
    fi

    # Check imaginary frequencies
    if check_imag "$out"; then
        n_imag=0
        log "$mol: No imaginary frequencies -- PASS"
    else
        n_imag=$(grep "Total number of imaginary perturbations" "$out" | tail -1 | awk '{print $NF}')
        log "$mol: $n_imag imaginary frequency(ies) -- NEEDS REVIEW"
        ALL_PASS=false
    fi

    # Extract energy
    s0e=$(get_s0_energy "$out")
    xyz="${mol}.xyz"
    hess="${mol}.hess"

    update_status --phase "s0_running" \
        --mol "$mol" s0_energy "$s0e" \
        --mol "$mol" s0_imag_freq "$n_imag" \
        --mol "$mol" s0_xyz "$xyz" \
        --mol "$mol" s0_hess "$hess"

    log "$mol S0 energy = $s0e Eh"
done

if $ALL_PASS; then
    update_status --phase "s0_done"
    log "Phase 1 complete -- all molecules passed frequency check."
else
    update_status --phase "s0_imag_warning"
    log "Phase 1 complete -- WARNING: imaginary frequencies detected. Review required."
fi

print_status
log "Phase 1 finished. Review above, then run phase2_s1.sh."
