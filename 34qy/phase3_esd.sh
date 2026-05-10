#!/bin/bash
#==============================================================================
# Phase 3: ESD-VG Internal Conversion Rate
#
# Generates ESD input files from S₁ optimized geometries,
# runs ESD with simplified VG + do_ic true, extracts k_IC.
# On completion, updates cascade_status.json → phase = "esd_done"
#==============================================================================
source "$(dirname "$0")/shared_functions.sh"

log "=================================================="
log "  PHASE 3: ESD-VG IC Rate"
log "=================================================="

MOLS=("LSH-33" "LSH-34")

for mol in "${MOLS[@]}"; do
    log "--- $mol ESD-VG ---"

    s1_xyz="${mol}_S1_Opt.xyz"
    esd_inp="${mol}_ESD.inp"
    esd_out="${mol}_ESD.out"

    # Generate ESD input from template
    if [ ! -f "$esd_inp" ]; then
        # Fall back to S0 xyz if S1 not available
        if [ ! -f "$s1_xyz" ]; then
            s1_xyz="${mol}.xyz"
        fi
        template="$TEMPLATE_DIR/esd_vg_ic_camb3lyp_631gd.inp"
        if [ -f "$template" ]; then
            log "Generating $esd_inp from template + $s1_xyz"
            sed '/^\* xyz/q' "$template" | sed "s/<MOL>/${mol}/g" > "$esd_inp"
            tail -n +3 "$s1_xyz" >> "$esd_inp"
            echo "*" >> "$esd_inp"
        else
            log "WARNING: Template not found, using inline generation"
            {
                echo "# ${mol} ESD(IC) | CAM-B3LYP/6-31G(d) | VG default | ORCA 6.1"
                echo "! CAM-B3LYP RIJCOSX 6-31G(d) CPCM(Methanol) ESD(IC) TightScf"
                echo ""
                echo "%maxcore 3072"
                echo ""
                echo "%pal"
                echo "   nprocs 16"
                echo "end"
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
                echo "  eshessian \"${mol}.hess\""
                echo "  usej true"
                echo "end"
                echo ""
                echo "* xyz 1 1"
                tail -n +3 "$s1_xyz"
                echo "*"
            } > "$esd_inp"
        fi
    fi

    if orca_done "$esd_out"; then
        log "$esd_out already completed."
    else
        run_orca "$esd_inp" || { log "FATAL: $mol ESD failed"; exit 1; }
    fi

    # Save verified template on success
    save_template "$esd_inp" "esd-vg-ic" "ESD-VG IC rate passed"

    # Extract k_IC
    k_ic=$(get_k_ic "$esd_out")
    log "$mol: k_IC = $k_ic s⁻¹"

    update_status --phase "esd_running" \
        --mol "$mol" k_ic "$k_ic"
done

update_status --phase "esd_done"
print_status
log "Phase 3 finished. Review the summary above and run phase4_report.sh when ready."
