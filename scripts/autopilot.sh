#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/shared_functions.sh"

log "=================================================="
log "  AUTOORCA 3.x — SCIENTIFICALLY GUARDED CASCADE"
log "=================================================="

run_phase() {
    local phase_script=$1 rc
    if bash "$phase_script"; then
        return 0
    else
        rc=$?
        if [ "$rc" -eq 3 ]; then
            log "AUTOPILOT STOPPED: REVIEW_REQUIRED. Approve the displayed exact input, then restart autopilot."
        elif [ "$rc" -eq 4 ]; then
            log "AUTOPILOT STOPPED: STATE GATE REQUIRED. Select/confirm the electronic state, then restart autopilot."
        fi
        return "$rc"
    fi
}

run_phase "$SCRIPT_DIR/phase1_s0.sh"
run_phase "$SCRIPT_DIR/phase2_s1.sh"
run_phase "$SCRIPT_DIR/phase3_esd.sh"
run_phase "$SCRIPT_DIR/phase4_report.sh"

log "AUTOPILOT COMPLETE — inspect cascade_report.md and state/NTO diagnostics before scientific interpretation."
