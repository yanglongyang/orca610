#!/bin/bash
#==============================================================================
# Phase 2: S₁ TDDFT Optimization
#
# Generates S₁ input files from S₀ optimized geometries,
# runs TDDFT Opt, extracts E_em (cm⁻¹) and oscillator strength f.
# On completion, updates cascade_status.json → phase = "s1_done"
#==============================================================================
source "$(dirname "$0")/shared_functions.sh"

log "=================================================="
log "  PHASE 2: S₁ TDDFT Opt"
log "=================================================="

MOLS=("LSH-33" "LSH-34")

for mol in "${MOLS[@]}"; do
    log "--- $mol S₁ ---"

    xyz="${mol}.xyz"
    s1_inp="${mol}_S1_Opt.inp"
    s1_out="${mol}_S1_Opt.out"

    # Generate input file from template if it doesn't exist
    if [ ! -f "$s1_inp" ]; then
        template="$TEMPLATE_DIR/s1_tddft_opt_camb3lyp_631gd.inp"
        if [ -f "$template" ]; then
            log "Generating $s1_inp from template + $xyz"
            sed '/^\* xyz/q' "$template" > "$s1_inp"
            tail -n +3 "$xyz" >> "$s1_inp"
            echo "*" >> "$s1_inp"
        else
            log "WARNING: Template not found, using inline generation"
            {
                echo "# ${mol} S1 TDDFT Opt | CAM-B3LYP/6-31G(d) | CPCM(Methanol)"
                echo "! Opt CAM-B3LYP RIJCOSX 6-31G(d) CPCM(Methanol)"
                echo "! TightOpt"
                echo "! TightScf"
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
        run_orca "$s1_inp" || { log "FATAL: $mol S₁ failed"; exit 1; }
    fi

    # Check S1 convergence
    if grep -q "ORCA TERMINATED NORMALLY" "$s1_out"; then
        s1_conv=true
    else
        s1_conv=false
        log "WARNING: $mol S₁ may not have converged"
    fi

    # Save verified template on success
    save_template "$s1_inp" "s1-tddft-opt" "S1 TD-DFT Opt passed"

    # Extract emission data
    read e_em f_osc <<< $(get_tddft_emission "$s1_out")
    log "$mol: E_em = $e_em cm⁻¹, f = $f_osc"

    # Emission wavelength
    if [ "$e_em" != "0" ]; then
        lambda_em=$(python3 -c "print(f'{1e7/$e_em:.1f}')")
    else
        lambda_em="0"
    fi

    s1_xyz_file="${mol}_S1_Opt.xyz"

    update_status --phase "s1_running" \
        --mol "$mol" s1_energy_cm1 "$e_em" \
        --mol "$mol" s1_f_osc "$f_osc" \
        --mol "$mol" s1_xyz "$s1_xyz_file" \
        --mol "$mol" s1_converged "$s1_conv" \
        --mol "$mol" lambda_em "$lambda_em"

    log "$mol: λ_em = $lambda_em nm"
done

update_status --phase "s1_done"
print_status
log "Phase 2 finished. Review the summary above and run phase3_esd.sh when ready."
