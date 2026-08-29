#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/shared_functions.sh"
CONFIG="${AUTOORCA_CONFIG:-$WORKDIR/project_config.sh}"
[ -f "$CONFIG" ] && source "$CONFIG" || source "$SCRIPT_DIR/project_config.sh.example"

if [ "${S1_FREQUENCY,,}" != "true" ]; then
    log "PHASE 3 SKIPPED: AH ESD(IC) requires an S1 Hessian; set S1_FREQUENCY=true to request its reviewed calculation."
    exit 0
fi

init_status "${MOLECULES[@]}"
check_hessian_method_compatibility

# For an AH IC calculation, use the same PES method as the Hessians by default.
record_method "esd_ic" "$S0_FUNCTIONAL" "$S0_BASIS" "$S0_DISPERSION" "$S0_SOLVENT" "$IC_TDA" "$CHARGE" "$MULT" "S0 geometry + S0/S1 Hessians"

log "=================================================="
log "  PHASE 3: ESD(IC) — guarded AH workflow"
log "=================================================="

for mol in "${MOLECULES[@]}"; do
    read -r s0_xyz s0_hess s1_hess <<< "$(python3 - "$STATUS_FILE" "$mol" <<'PYEOF'
import json,sys
with open(sys.argv[1]) as f:d=json.load(f)
m=d["molecules"][sys.argv[2]]
print(m.get("s0_xyz",""), m.get("s0_hess",""), m.get("s1_hess",""))
PYEOF
)"

    s1_opt_inp="${mol}_S1_Opt.inp"
    s1_opt_out="${mol}_S1_Opt.out"
    require_state_identity "$mol" "$s1_opt_inp" "$s1_opt_out" || { log "FATAL: ESD(IC) requires confirmed final S1 state identity"; exit 4; }

    for f in "$s0_xyz" "$s0_hess" "$s1_hess"; do
        [ -f "$f" ] || { log "FATAL: required ESD(IC) file missing: $f"; exit 1; }
    done

    inp="${mol}_ESD_IC.inp"
    out="${mol}_ESD_IC.out"
    if [ ! -f "$inp" ]; then
        {
            write_autoorca_metadata "esd_ic" "TD-DFT" "$S0_FUNCTIONAL" "$S0_BASIS" "$S0_DISPERSION" "$S0_SOLVENT" "equilibrium" "$s0_xyz" "${mol}_S1_identity_confirmed"
            echo "# ${mol} S1->S0 ESD(IC), AH Hessians"
            echo "! ${S0_FUNCTIONAL} RIJCOSX ${S0_BASIS} ${S0_DISPERSION} ${S0_SOLVENT} ESD(IC) TightScf"
            echo "%maxcore ${MAXCORE}"
            echo "%pal nprocs ${NPROCS} end"
            echo "%tddft"
            echo "  tda ${IC_TDA}"
            echo "  nroots ${NROOTS}"
            echo "  iroot $(python3 - "$STATUS_FILE" "$mol" <<'PYEOF'
import json,sys
with open(sys.argv[1]) as f:d=json.load(f)
print(int(d["molecules"][sys.argv[2]]["s1_final_root"]))
PYEOF
)"
            echo "  nacme true"
            echo "  etf true"
            echo "end"
            echo "%esd"
            echo "  gshessian \"${s0_hess}\""
            echo "  eshessian \"${s1_hess}\""
            echo "  usej true"
            echo "end"
            echo "* xyzfile ${CHARGE} ${MULT} \"${s0_xyz}\""
        } > "$inp"
        register_input_for_review "$inp" "esd_ic" || exit 1
        log "Generated $inp — REVIEW_REQUIRED. No ORCA job was started; inspect the complete review and explicitly approve this exact input."
        exit 3
    fi

    run_orca "$inp" || { rc=$?; exit "$rc"; }
    k_ic=$(get_k_ic "$out")
    [[ "$k_ic" =~ ^[+]?[0-9]*\.?[0-9]+([Ee][-+]?[0-9]+)?$ ]] || { log "FATAL: failed to extract non-negative k_IC"; exit 1; }
    update_status --phase "esd_running" --mol "$mol" k_ic "$k_ic"
    save_template "$inp" "esd-ic-ah" "$S0_FUNCTIONAL" "$S0_BASIS" "$S0_SOLVENT" "$S0_DISPERSION" "$CHARGE" "$MULT" "$IC_TDA" "ESD(IC) completed with explicit S0/S1 Hessians"
done

update_status --phase "esd_done"
print_status
