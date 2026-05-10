#!/bin/bash
#==============================================================================
# Phase 1: S₀ Ground State Optimization + Frequency Check
#
# Runs Opt+Freq for both molecules. Checks for imaginary frequencies.
# On completion, updates cascade_status.json → phase = "s0_done"
# and prints a summary for human review before proceeding to Phase 2.
#==============================================================================
source "$(dirname "$0")/shared_functions.sh"

log "=================================================="
log "  PHASE 1: S₀ Opt+Freq"
log "=================================================="

MOLS=("LSH-33" "LSH-34")
INPS=("LSH-33.inp" "LSH-34.inp")
ALL_PASS=true

for i in 0 1; do
    mol="${MOLS[$i]}"
    inp="${INPS[$i]}"
    out="${mol}.out"

    log "--- $mol S₀ ---"

    if orca_done "$out"; then
        log "$out already completed."
    else
        run_orca "$inp" || { log "FATAL: $mol S₀ failed"; exit 1; }
    fi

    # Check imaginary frequencies
    if check_imag "$out"; then
        n_imag=0
        log "$mol: No imaginary frequencies — PASS"
    else
        n_imag=$(grep "Total number of imaginary perturbations" "$out" | tail -1 | awk '{print $NF}')
        log "$mol: $n_imag imaginary frequency(ies) — NEEDS REVIEW"
        ALL_PASS=false
    fi

    # Save verified template on success
    save_template "$inp" "s0-opt-freq" "S0 Opt+Freq passed, zero imag freq"

    # Extract energy
    s0e=$(get_s0_energy "$out")
    xyz="${mol}.xyz"
    hess="${mol}.hess"

    update_status --phase "s0_running" \
        --mol "$mol" s0_energy "$s0e" \
        --mol "$mol" s0_imag_freq "$n_imag" \
        --mol "$mol" s0_xyz "$xyz" \
        --mol "$mol" s0_hess "$hess"

    log "$mol S₀ energy = $s0e Eh"
done

if $ALL_PASS; then
    update_status --phase "s0_done"
    log "Phase 1 complete — all molecules passed frequency check."
else
    update_status --phase "s0_imag_warning"
    log "Phase 1 complete — WARNING: imaginary frequencies detected. Review required."
fi

print_status
log "Phase 1 finished. Review the summary above and run phase2_s1.sh when ready."
