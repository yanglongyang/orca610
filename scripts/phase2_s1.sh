#!/bin/bash
#==============================================================================
# Phase 2: S1 TD-DFT Optimization
#
# Generates S1 input from S0 optimized geometry + template (if available).
# Customize: MOLECULES, S1_FUNCTIONAL, S1_BASIS, S1_SOLVENT below.
#==============================================================================
source "$(dirname "$0")/shared_functions.sh"

# ========================== CUSTOMIZE HERE ==========================
MOLECULES=("MOL1" "MOL2")
S1_FUNCTIONAL="CAM-B3LYP"                    # Must support TD-DFT gradients
S1_BASIS="6-31G(d)"
S1_SOLVENT="CPCM(Methanol)"
# ====================================================================

log "=================================================="
log "  PHASE 2: S1 TD-DFT Opt"
log "=================================================="

for mol in "${MOLECULES[@]}"; do
    log "--- $mol S1 ---"

    xyz="${mol}.xyz"
    s1_inp="${mol}_S1_Opt.inp"
    s1_out="${mol}_S1_Opt.out"

    # Generate input file if it doesn't exist
    if [ ! -f "$s1_inp" ]; then
        template="$TEMPLATE_DIR/s1_tddft_opt_${S1_FUNCTIONAL,,}_${S1_BASIS//[()]/}.inp"
        # Note: template naming convention — lowercase functional, strip parens from basis
        # e.g.: s1_tddft_opt_cam-b3lyp_6-31gd.inp
        if [ -f "$template" ]; then
            log "Generating $s1_inp from template + $xyz"
            sed '/^\* xyz/q' "$template" > "$s1_inp"
            tail -n +3 "$xyz" >> "$s1_inp"
            echo "*" >> "$s1_inp"
        else
            log "No template found, generating inline"
            {
                echo "# ${mol} S1 TD-DFT Opt | ${S1_FUNCTIONAL}/${S1_BASIS} | ${S1_SOLVENT}"
                echo "! Opt ${S1_FUNCTIONAL} RIJCOSX ${S1_BASIS} ${S1_SOLVENT}"
                echo "! TightOpt TightScf"
                echo ""
                echo "%maxcore 3072"
                echo "%pal nprocs 16 end"
                echo ""
                echo "%tddft"
                echo "  nroots 5"
                echo "  iroot 1"
                echo "  tda   true"
                echo "end"
                echo ""
                echo "* xyz 1 1"
                tail -n +3 "$xyz"
                echo "*"
            } > "$s1_inp"
        fi
    fi

    if orca_done "$s1_out"; then
        log "$s1_out already completed."
    else
        run_orca "$s1_inp" || { log "FATAL: $mol S1 failed"; exit 1; }
    fi

    # Check convergence
    if grep -q "ORCA TERMINATED NORMALLY" "$s1_out"; then
        s1_conv=true
    else
        s1_conv=false
    fi

    # Extract emission data
    read e_em f_osc <<< $(get_tddft_emission "$s1_out")
    log "$mol: E_em = $e_em cm-1, f = $f_osc"

    lambda_em=$(python3 -c "print(f'{1e7/$e_em:.1f}')" 2>/dev/null || echo "0")
    s1_xyz_file="${mol}_S1_Opt.xyz"

    update_status --phase "s1_running" \
        --mol "$mol" s1_energy_cm1 "$e_em" \
        --mol "$mol" s1_f_osc "$f_osc" \
        --mol "$mol" s1_xyz "$s1_xyz_file" \
        --mol "$mol" s1_converged "$s1_conv" \
        --mol "$mol" lambda_em "$lambda_em"

    # Save verified template on success
    save_template "$s1_inp" "s1-tddft-opt" "S1 TD-DFT Opt passed"
done

update_status --phase "s1_done"
print_status
log "Phase 2 finished. Review above, then run phase3_esd.sh."
