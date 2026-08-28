#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/shared_functions.sh"
CONFIG="${AUTOORCA_CONFIG:-$WORKDIR/project_config.sh}"
[ -f "$CONFIG" ] && source "$CONFIG" || source "$SCRIPT_DIR/project_config.sh.example"

init_status "${MOLECULES[@]}"
record_method "s1_optfreq" "$S1_FUNCTIONAL" "$S1_BASIS" "$S1_DISPERSION" "$S1_SOLVENT" "$S1_TDA" "$CHARGE" "$MULT" "S0 optimized geometry"
record_method "vertical_emission" "$EM_FUNCTIONAL" "$EM_BASIS" "$EM_DISPERSION" "$EM_SOLVENT" "$EM_TDA" "$CHARGE" "$MULT" "S1 optimized geometry"

log "=================================================="
log "  PHASE 2: S1 Opt+Freq + clean emission SP"
log "=================================================="

for mol in "${MOLECULES[@]}"; do
    s0_xyz=$(python3 - "$STATUS_FILE" "$mol" <<'PYEOF'
import json,sys
with open(sys.argv[1]) as f:d=json.load(f)
print(d["molecules"][sys.argv[2]].get("s0_xyz", ""))
PYEOF
)
    [ -f "$s0_xyz" ] || { log "FATAL: missing S0 optimized geometry for $mol"; exit 1; }

    opt_inp="${mol}_S1_OptFreq.inp"
    opt_out="${mol}_S1_OptFreq.out"
    s1_xyz="${mol}_S1_OptFreq.xyz"
    s1_hess="${mol}_S1_OptFreq.hess"

    if [ ! -f "$opt_inp" ]; then
        {
            echo "# ${mol} S1 Opt+Freq — state tracking enabled"
            echo "! Opt Freq ${S1_FUNCTIONAL} RIJCOSX ${S1_BASIS} ${S1_DISPERSION} ${S1_SOLVENT} TightOpt TightScf"
            echo "%maxcore ${MAXCORE}"
            echo "%pal nprocs ${NPROCS} end"
            echo "%tddft"
            echo "  nroots ${NROOTS}"
            echo "  iroot ${IROOT}"
            echo "  tda ${S1_TDA}"
            echo "  followiroot ${FOLLOW_IROOT}"
            echo "  donto true"
            echo "  ntostates ${NTO_STATES}"
            echo "  ntothresh ${NTO_THRESH}"
            echo "end"
            echo "* xyz ${CHARGE} ${MULT}"
            tail -n +3 "$s0_xyz"
            echo "*"
        } > "$opt_inp"
    fi

    run_orca "$opt_inp" || exit 1
    check_opt_converged "$opt_out" || { log "FATAL: S1 optimization convergence not confirmed for $mol"; exit 1; }

    set +e
    s1_imag=$(get_imag_count "$opt_out")
    imag_rc=$?
    set -e
    [ "$imag_rc" -ne 2 ] || { log "FATAL: S1 frequency summary missing"; exit 1; }
    if [ "$imag_rc" -eq 1 ]; then
        log "FATAL: $mol S1 has $s1_imag imaginary frequencies; do not use as an S1 minimum without review"
        exit 1
    fi
    [ -f "$s1_xyz" ] || { log "FATAL: $s1_xyz missing"; exit 1; }
    [ -f "$s1_hess" ] || { log "FATAL: $s1_hess missing"; exit 1; }

    final_root=$(get_final_iroot "$opt_out" "$IROOT")
    log "$mol: requested IROOT=$IROOT, final followed root=$final_root"
    # The safe default NTO_STATES is IROOT.  If root following moves that state,
    # request the NTO for the final root rather than silently analysing the old one.
    em_nto_states="$NTO_STATES"
    [ "$NTO_STATES" != "$IROOT" ] || em_nto_states="$final_root"

    # Separate SP avoids accidentally extracting a TD spectrum from a displaced
    # frequency sub-calculation. The solvent regime is explicit.
    em_inp="${mol}_S1_Emission.inp"
    em_out="${mol}_S1_Emission.out"
    if [ ! -f "$em_inp" ]; then
        {
            echo "# ${mol} vertical emission at optimized S1 geometry"
            echo "! ${EM_FUNCTIONAL} RIJCOSX ${EM_BASIS} ${EM_DISPERSION} ${EM_SOLVENT} TightScf"
            echo "%maxcore ${MAXCORE}"
            echo "%pal nprocs ${NPROCS} end"
            echo "%tddft"
            echo "  nroots ${NROOTS}"
            echo "  iroot ${final_root}"
            echo "  tda ${EM_TDA}"
            echo "  cpcmeq ${EM_CPCMEQ}"
            echo "  donto true"
            echo "  ntostates ${em_nto_states}"
            echo "  ntothresh ${NTO_THRESH}"
            echo "end"
            echo "* xyz ${CHARGE} ${MULT}"
            tail -n +3 "$s1_xyz"
            echo "*"
        } > "$em_inp"
    fi
    run_orca "$em_inp" || exit 1

    read -r e_em f_osc <<< "$(get_tddft_emission "$em_out" "$final_root")"
    [ "$e_em" != "0" ] || { log "FATAL: failed to extract target-state emission energy; inspect state identity manually"; exit 1; }
    lambda_em=$(python3 -c "print(f'{1e7/float(\"$e_em\"):.1f}')")

    update_status --phase "s1_running" \
        --mol "$mol" s1_energy_cm1 "$e_em" \
        --mol "$mol" s1_f_osc "$f_osc" \
        --mol "$mol" lambda_em "$lambda_em" \
        --mol "$mol" s1_xyz "$s1_xyz" \
        --mol "$mol" s1_hess "$s1_hess" \
        --mol "$mol" s1_imag_freq "$s1_imag" \
        --mol "$mol" s1_final_root "$final_root" \
        --mol "$mol" s1_converged true \
        --mol "$mol" state_identity_checked false

    update_status --warn "$mol: root following cannot prove chemical state identity; compare NTOs/configurations before final interpretation."
    save_template "$opt_inp" "s1-tddft-optfreq" "$S1_FUNCTIONAL" "$S1_BASIS" "$S1_SOLVENT" "$S1_DISPERSION" "$CHARGE" "$MULT" "$S1_TDA" "S1 optimization converged; zero imaginary frequencies"
done

update_status --phase "s1_done"
print_status
