#!/bin/bash
#==============================================================================
# Phase 3: ESD(IC) Internal Conversion Rate
#
# Generates ESD input from S1 optimized geometry.
# Uses S1 Hessian if available (from NumFreq), falls back to S0 Hessian (VG).
# Customize: MOLECULES, FUNCTIONAL, BASIS, SOLVENT below.
#==============================================================================
source "$(dirname "$0")/shared_functions.sh"

# ========================== CUSTOMIZE HERE ==========================
MOLECULES=("MOL1" "MOL2")
FUNCTIONAL="CAM-B3LYP"
BASIS="6-31G(d)"
SOLVENT="CPCM(Methanol)"
# ====================================================================

log "=================================================="
log "  PHASE 3: ESD(IC) IC Rate"
log "=================================================="

for mol in "${MOLECULES[@]}"; do
    log "--- $mol ESD(IC) ---"

    s1_xyz="${mol}_S1_Opt.xyz"
    esd_inp="${mol}_ESD.inp"
    esd_out="${mol}_ESD.out"

    # Determine which S1 Hessian to use
    s1_hess="${mol}_S1_NumFreq.hess"
    if [ ! -f "$s1_hess" ]; then
        log "No S1 NumFreq Hessian found, using S0 Hessian (VG approximation)"
        s1_hess="${mol}.hess"
    fi

    # Generate ESD input
    if [ ! -f "$esd_inp" ]; then
        if [ ! -f "$s1_xyz" ]; then
            s1_xyz="${mol}.xyz"
        fi
        {
            echo "# ${mol} ESD(IC) | ${FUNCTIONAL}/${BASIS} | ${SOLVENT}"
            echo "! ${FUNCTIONAL} RIJCOSX ${BASIS} ${SOLVENT} ESD(IC) TightScf"
            echo ""
            echo "%maxcore 3072"
            echo "%pal nprocs 16 end"
            echo ""
            echo "%tddft"
            echo "  nroots 5"
            echo "  iroot 1"
            echo "  nacme true"
            echo "  etf   true"
            echo "  tda   true"
            echo "end"
            echo ""
            echo "%esd"
            echo "  gshessian \"${mol}.hess\""
            echo "  eshessian \"${s1_hess}\""
            echo "  usej true"
            echo "end"
            echo ""
            echo "* xyz 1 1"
            tail -n +3 "$s1_xyz"
            echo "*"
        } > "$esd_inp"
    fi

    if orca_done "$esd_out"; then
        log "$esd_out already completed."
    else
        run_orca "$esd_inp" || { log "FATAL: $mol ESD failed"; exit 1; }
    fi

    k_ic=$(get_k_ic "$esd_out")
    log "$mol: k_IC = $k_ic s-1"

    update_status --phase "esd_running" --mol "$mol" k_ic "$k_ic"
    save_template "$esd_inp" "esd-vg-ic" "ESD(IC) passed"
done

update_status --phase "esd_done"
print_status
log "Phase 3 finished. Review above, then run phase4_report.sh."
