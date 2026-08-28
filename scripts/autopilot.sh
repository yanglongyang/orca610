#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/shared_functions.sh"

log "=================================================="
log "  AUTOORCA 3.x — SCIENTIFICALLY GUARDED CASCADE"
log "=================================================="

bash "$SCRIPT_DIR/phase1_s0.sh"
bash "$SCRIPT_DIR/phase2_s1.sh"
bash "$SCRIPT_DIR/phase3_esd.sh"
bash "$SCRIPT_DIR/phase4_report.sh"

log "AUTOPILOT COMPLETE — inspect cascade_report.md and state/NTO diagnostics before scientific interpretation."
