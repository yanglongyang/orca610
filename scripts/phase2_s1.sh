#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/shared_functions.sh"
CONFIG="${AUTOORCA_CONFIG:-$WORKDIR/project_config.sh}"
[ -f "$CONFIG" ] && source "$CONFIG" || source "$SCRIPT_DIR/project_config.sh.example"

init_status "${MOLECULES[@]}"
FOLLOW_IROOT="${FOLLOW_IROOT,,}"
if [ "$FOLLOW_IROOT" != "true" ] && [ -z "${FOLLOW_IROOT_RATIONALE:-}" ]; then
    log "FATAL: FOLLOW_IROOT=false requires an explicit user-requested FOLLOW_IROOT_RATIONALE."
    exit 2
fi
record_method "vertical_absorption" "$S1_FUNCTIONAL" "$S1_BASIS" "$S1_DISPERSION" "$S1_SOLVENT" "$S1_TDA" "$CHARGE" "$MULT" "S0 optimized geometry"
record_method "s1_opt" "$S1_FUNCTIONAL" "$S1_BASIS" "$S1_DISPERSION" "$S1_SOLVENT" "$S1_TDA" "$CHARGE" "$MULT" "S0 optimized geometry"
record_method "vertical_emission" "$EM_FUNCTIONAL" "$EM_BASIS" "$EM_DISPERSION" "$EM_SOLVENT" "$EM_TDA" "$CHARGE" "$MULT" "S1 optimized geometry"

log "=================================================="
log "  PHASE 2: R0 selection -> S1 Opt -> identity -> emission"
log "=================================================="

for mol in "${MOLECULES[@]}"; do
    s0_xyz=$(python3 - "$STATUS_FILE" "$mol" <<'PYEOF'
import json,sys
with open(sys.argv[1]) as f:d=json.load(f)
print(d["molecules"][sys.argv[2]].get("s0_xyz", ""))
PYEOF
)
    [ -f "$s0_xyz" ] || { log "FATAL: missing S0 optimized geometry for $mol"; exit 1; }

    vertical_inp="${mol}_R0_Absorption.inp"; vertical_out="${mol}_R0_Absorption.out"
    if [ ! -f "$vertical_inp" ]; then
        {
            write_autoorca_metadata "vertical_absorption" "TD-DFT" "$S1_FUNCTIONAL" "$S1_BASIS" "$S1_DISPERSION" "$S1_SOLVENT" "nonequilibrium" "$s0_xyz"
            echo "# ${mol} R0 vertical TD-DFT state-selection calculation"
            echo "! ${S1_FUNCTIONAL} RIJCOSX ${S1_BASIS} ${S1_DISPERSION} ${S1_SOLVENT} TightScf"
            echo "%maxcore ${MAXCORE}"
            echo "%pal nprocs ${NPROCS} end"
            echo "%tddft"
            echo "  nroots ${NROOTS}"
            echo "  tda ${S1_TDA}"
            echo "  cpcmeq ${ABS_CPCMEQ}"
            echo "  donto true"
            echo "  ntostates ${NTO_STATES}"
            echo "  ntothresh ${NTO_THRESH}"
            echo "end"
            echo "* xyzfile ${CHARGE} ${MULT} \"${s0_xyz}\""
        } > "$vertical_inp"
        register_input_for_review "$vertical_inp" "vertical_absorption" || exit 1
        log "Generated $vertical_inp — REVIEW_REQUIRED. No ORCA job was started."
        exit 3
    fi
    run_orca "$vertical_inp" || { rc=$?; exit "$rc"; }

    if ! require_state_selection "$mol" "$vertical_inp" "$vertical_out"; then
        log "STATE_SELECTION_REQUIRED for $mol. Inspect R0 roots, NTOs, oscillator strengths and excitation energies, then run:"
        log "python3 $STATE_GATE_TOOL select --manifest $STATE_GATE_FILE --species $mol --vertical-input $vertical_inp --vertical-output $vertical_out --root ROOT --state-character DESCRIPTION --selection-basis NTO --selection-basis oscillator_strength --selection-basis excitation_energy"
        exit 4
    fi
    selected_root=$(selected_state_root "$mol")

    opt_inp="${mol}_S1_Opt.inp"; opt_out="${mol}_S1_Opt.out"; s1_xyz="${mol}_S1_Opt.xyz"
    if [ ! -f "$opt_inp" ]; then
        {
            write_autoorca_metadata "s1_opt" "TD-DFT" "$S1_FUNCTIONAL" "$S1_BASIS" "$S1_DISPERSION" "$S1_SOLVENT" "equilibrium" "$s0_xyz" "${mol}_R0_root_${selected_root}_approved"
            echo "# ${mol} S1 optimization; root selected by human at R0"
            echo "! Opt ${S1_FUNCTIONAL} RIJCOSX ${S1_BASIS} ${S1_DISPERSION} ${S1_SOLVENT} TightOpt TightScf"
            echo "%maxcore ${MAXCORE}"
            echo "%pal nprocs ${NPROCS} end"
            echo "%tddft"
            echo "  nroots ${NROOTS}"
            echo "  iroot ${selected_root}"
            echo "  tda ${S1_TDA}"
            echo "  followiroot ${FOLLOW_IROOT}"
            echo "  cpcmeq ${S1_CPCMEQ}"
            echo "  donto true"
            echo "  ntostates ${NTO_STATES}"
            echo "  ntothresh ${NTO_THRESH}"
            echo "end"
            echo "* xyzfile ${CHARGE} ${MULT} \"${s0_xyz}\""
        } > "$opt_inp"
        register_input_for_review "$opt_inp" "s1_opt" || exit 1
        log "Generated $opt_inp — REVIEW_REQUIRED. No ORCA job was started."
        exit 3
    fi
    run_orca "$opt_inp" || { rc=$?; exit "$rc"; }
    check_opt_converged "$opt_out" || { log "FATAL: S1 optimization convergence not confirmed for $mol"; exit 1; }
    [ -f "$s1_xyz" ] || { log "FATAL: $s1_xyz missing"; exit 1; }
    final_root=$(get_final_iroot "$opt_out" "$selected_root")

    if ! require_state_identity "$mol" "$opt_inp" "$opt_out"; then
        log "STATE_IDENTITY_REQUIRED for $mol (selected root=$selected_root; final followed root=$final_root). Inspect final-state NTO/configuration evidence, then run:"
        log "python3 $STATE_GATE_TOOL confirm --manifest $STATE_GATE_FILE --species $mol --opt-input $opt_inp --opt-output $opt_out --final-root $final_root --state-character DESCRIPTION --evidence NTO --evidence oscillator_strength --evidence excitation_energy"
        exit 4
    fi
    confirmed_root=$(confirmed_state_root "$mol")
    [ "$confirmed_root" = "$final_root" ] || { log "FATAL: confirmed final root $confirmed_root does not match optimization output root $final_root"; exit 4; }

    s1_hess=""; s1_imag=""
    if [ "${S1_FREQUENCY,,}" = "true" ]; then
        freq_inp="${mol}_S1_Freq.inp"; freq_out="${mol}_S1_Freq.out"; s1_hess="${mol}_S1_Freq.hess"
        record_method "s1_freq" "$S1_FUNCTIONAL" "$S1_BASIS" "$S1_DISPERSION" "$S1_SOLVENT" "$S1_TDA" "$CHARGE" "$MULT" "human-confirmed S1 optimized geometry"
        if [ ! -f "$freq_inp" ]; then
            {
                write_autoorca_metadata "s1_freq" "TD-DFT" "$S1_FUNCTIONAL" "$S1_BASIS" "$S1_DISPERSION" "$S1_SOLVENT" "equilibrium" "$s1_xyz" "${mol}_S1_identity_confirmed_root_${final_root}"
                echo "# ${mol} S1 frequency after human state-identity confirmation"
                echo "! Freq ${S1_FUNCTIONAL} RIJCOSX ${S1_BASIS} ${S1_DISPERSION} ${S1_SOLVENT} TightScf"
                echo "%maxcore ${MAXCORE}"
                echo "%pal nprocs ${NPROCS} end"
                echo "%tddft"
                echo "  nroots ${NROOTS}"
                echo "  iroot ${final_root}"
                echo "  tda ${S1_TDA}"
                echo "  followiroot ${FOLLOW_IROOT}"
                echo "  cpcmeq ${S1_CPCMEQ}"
                echo "  donto true"
                echo "  ntostates ${NTO_STATES}"
                echo "  ntothresh ${NTO_THRESH}"
                echo "end"
                echo "* xyzfile ${CHARGE} ${MULT} \"${s1_xyz}\""
            } > "$freq_inp"
            register_input_for_review "$freq_inp" "s1_freq" || exit 1
            log "Generated $freq_inp — REVIEW_REQUIRED. No ORCA job was started."
            exit 3
        fi
        run_orca "$freq_inp" || { rc=$?; exit "$rc"; }
        [ -f "$s1_hess" ] || { log "FATAL: S1 frequency Hessian missing: $s1_hess"; exit 1; }
        s1_imag=$(get_imag_count "$freq_out" || true)
    fi

    em_inp="${mol}_S1_Emission.inp"; em_out="${mol}_S1_Emission.out"
    if [ ! -f "$em_inp" ]; then
        {
            write_autoorca_metadata "vertical_emission" "TD-DFT" "$EM_FUNCTIONAL" "$EM_BASIS" "$EM_DISPERSION" "$EM_SOLVENT" "equilibrium" "$s1_xyz" "${mol}_S1_identity_confirmed_root_${final_root}"
            echo "# ${mol} vertical emission at human-confirmed S1 geometry"
            echo "! ${EM_FUNCTIONAL} RIJCOSX ${EM_BASIS} ${EM_DISPERSION} ${EM_SOLVENT} TightScf"
            echo "%maxcore ${MAXCORE}"
            echo "%pal nprocs ${NPROCS} end"
            echo "%tddft"
            echo "  nroots ${NROOTS}"
            echo "  iroot ${final_root}"
            echo "  tda ${EM_TDA}"
            echo "  cpcmeq ${EM_CPCMEQ}"
            echo "  donto true"
            echo "  ntostates ${NTO_STATES}"
            echo "  ntothresh ${NTO_THRESH}"
            echo "end"
            echo "* xyzfile ${CHARGE} ${MULT} \"${s1_xyz}\""
        } > "$em_inp"
        register_input_for_review "$em_inp" "vertical_emission" || exit 1
        log "Generated $em_inp — REVIEW_REQUIRED. No ORCA job was started."
        exit 3
    fi
    run_orca "$em_inp" || { rc=$?; exit "$rc"; }
    read -r e_em f_osc <<< "$(get_tddft_emission "$em_out" "$final_root")"
    [ "$e_em" != "0" ] || { log "FATAL: failed to extract target-state emission energy"; exit 1; }
    lambda_em=$(python3 -c "print(f'{1e7/float(\"$e_em\"):.1f}')")

    update_status --phase "s1_running" --mol "$mol" s1_energy_cm1 "$e_em" --mol "$mol" s1_f_osc "$f_osc" --mol "$mol" lambda_em "$lambda_em" --mol "$mol" s1_xyz "$s1_xyz" --mol "$mol" s1_hess "$s1_hess" --mol "$mol" s1_imag_freq "$s1_imag" --mol "$mol" s1_selected_root "$selected_root" --mol "$mol" s1_final_root "$final_root" --mol "$mol" s1_converged true --mol "$mol" state_identity_checked true
done

update_status --phase "s1_done"
print_status
