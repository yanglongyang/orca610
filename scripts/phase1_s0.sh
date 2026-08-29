#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/shared_functions.sh"
CONFIG="${AUTOORCA_CONFIG:-$WORKDIR/project_config.sh}"
[ -f "$CONFIG" ] && source "$CONFIG" || source "$SCRIPT_DIR/project_config.sh.example"

init_status "${MOLECULES[@]}"
record_method "s0_optfreq" "$S0_FUNCTIONAL" "$S0_BASIS" "$S0_DISPERSION" "$S0_SOLVENT" "n.a." "$CHARGE" "$MULT" "initial geometry"

log "=================================================="
log "  PHASE 1: S0 Opt+Freq"
log "=================================================="

ALL_PASS=true
for mol in "${MOLECULES[@]}"; do
    initial_xyz="${mol}.xyz"
    inp="${mol}_S0_OptFreq.inp"
    out="${mol}_S0_OptFreq.out"
    opt_xyz="${mol}_S0_OptFreq.xyz"
    hess="${mol}_S0_OptFreq.hess"

    [ -f "$initial_xyz" ] || { log "FATAL: missing initial geometry $initial_xyz"; exit 1; }

    if [ ! -f "$inp" ]; then
        {
            write_autoorca_metadata "s0_optfreq" "DFT" "$S0_FUNCTIONAL" "$S0_BASIS" "$S0_DISPERSION" "$S0_SOLVENT" "ground_state" "$initial_xyz"
            echo "# ${mol} S0 Opt+Freq"
            echo "! Opt Freq ${S0_FUNCTIONAL} RIJCOSX ${S0_BASIS} ${S0_DISPERSION} ${S0_SOLVENT} TightOpt TightScf"
            echo "%maxcore ${MAXCORE}"
            echo "%pal nprocs ${NPROCS} end"
            echo "* xyzfile ${CHARGE} ${MULT} \"${initial_xyz}\""
        } > "$inp"
        register_input_for_review "$inp" "s0_optfreq" || exit 1
        log "Generated $inp — REVIEW_REQUIRED. No ORCA job was started; inspect the complete review and explicitly approve this exact input."
        exit 3
    fi

    run_orca "$inp" || { rc=$?; exit "$rc"; }

    if ! check_opt_converged "$out"; then
        log "FATAL: $mol ORCA terminated but S0 optimization convergence was not confirmed"
        exit 1
    fi

    set +e
    n_imag=$(get_imag_count "$out")
    imag_rc=$?
    set -e
    case "$imag_rc" in
        0) log "$mol: zero imaginary frequencies — PASS" ;;
        1) log "$mol: $n_imag imaginary frequencies — REVIEW REQUIRED"; ALL_PASS=false ;;
        2) log "FATAL: $mol frequency summary not found; do not interpret this as zero imaginary frequencies"; exit 1 ;;
    esac

    s0e=$(get_s0_energy "$out")
    [ -n "$s0e" ] || { log "FATAL: failed to extract S0 energy"; exit 1; }
    [ -f "$opt_xyz" ] || { log "FATAL: optimized geometry $opt_xyz missing"; exit 1; }
    [ -f "$hess" ] || { log "FATAL: Hessian $hess missing"; exit 1; }

    update_status --phase "s0_running" \
        --mol "$mol" s0_energy "$s0e" \
        --mol "$mol" s0_imag_freq "$n_imag" \
        --mol "$mol" s0_xyz "$opt_xyz" \
        --mol "$mol" s0_hess "$hess"

    if [ "$imag_rc" -eq 0 ]; then
        save_template "$inp" "s0-opt-freq" "$S0_FUNCTIONAL" "$S0_BASIS" "$S0_SOLVENT" "$S0_DISPERSION" "$CHARGE" "$MULT" "n.a." "optimization converged; zero imaginary frequencies"
    fi
done

if $ALL_PASS; then
    update_status --phase "s0_done"
else
    update_status --phase "s0_imag_warning"
    exit 1
fi
print_status
