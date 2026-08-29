#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/shared_functions.sh"
[ "$#" -eq 1 ] || { echo "Usage: $0 calculation.inp" >&2; exit 2; }
run_orca "$1"
