#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
[ "$#" -eq 1 ] || { echo "Usage: $0 calculation.inp" >&2; exit 2; }
INPUT_PATH="$(realpath "$1")"
# Standalone check/approve/run share this input's manifests unless the caller
# deliberately supplies AUTOORCA_WORKDIR or manifest environment overrides.
INPUT_DIR="$(dirname "$INPUT_PATH")"
export AUTOORCA_WORKDIR="${AUTOORCA_WORKDIR:-$INPUT_DIR}"
source "$SCRIPT_DIR/shared_functions.sh"
run_orca "$INPUT_PATH"
