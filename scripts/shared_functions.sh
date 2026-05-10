#!/bin/bash
#==============================================================================
# shared_functions.sh — sourced by all phase scripts
#==============================================================================
# This file lives in $ORCA_ROOT/scripts/ and is sourced by project-specific
# phase scripts. It auto-detects the project working directory from the
# calling script's location.

# ---- Project root (shared resources) ----
ORCA_ROOT="/data/software/orca610"
export PATH=$ORCA_ROOT:$PATH
export LD_LIBRARY_PATH=$ORCA_ROOT:$LD_LIBRARY_PATH

# ---- Shared paths (project-level, NOT per-task) ----
TEMPLATE_DIR="$ORCA_ROOT/templates"
MANUAL_DIR="$ORCA_ROOT/manual/orca_manual_kb"

# ---- Working directory (auto-detected from calling script's location) ----
# If the calling script is in a project subdirectory, use that as WORKDIR.
# Otherwise fall back to current directory.
if [ -n "${BASH_SOURCE[1]}" ]; then
    WORKDIR=$(dirname "$(realpath "${BASH_SOURCE[1]}")")
else
    WORKDIR="$PWD"
fi
STATUS_FILE="$WORKDIR/cascade_status.json"

cd "$WORKDIR"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

#--------------------------------------------------------------------
# Check if an ORCA job is currently running for a given basename
#--------------------------------------------------------------------
job_running() {
    local basename=$1
    ps aux | grep -v grep | grep -q "orca.*${basename}"
}

#--------------------------------------------------------------------
# Wait for a running ORCA job to complete, polling tail every 5 min
#--------------------------------------------------------------------
wait_for_job() {
    local basename=$1
    local outfile="${basename}.out"
    if job_running "$basename"; then
        log "Waiting for running job: $basename ..."
        while job_running "$basename"; do
            local last_line=$(tail -1 "$outfile" 2>/dev/null | head -c 120)
            log "  [$basename] $last_line"
            sleep 300
        done
        sleep 5
        log "$basename finished."
    fi
}

#--------------------------------------------------------------------
# Check if output file indicates normal termination
#--------------------------------------------------------------------
orca_done() {
    local outfile=$1
    [ -f "$outfile" ] && grep -q "ORCA TERMINATED NORMALLY" "$outfile"
}

#--------------------------------------------------------------------
# Count imaginary frequencies. Returns 0 if none, 1 if any found.
#--------------------------------------------------------------------
check_imag() {
    local outfile=$1
    local n=$(grep "Total number of imaginary perturbations" "$outfile" | tail -1 | awk '{print $NF}')
    if [ -n "$n" ] && [ "$n" -gt 0 ]; then
        log "WARNING: $n imaginary frequencies found"
        return 1
    fi
    return 0
}

#--------------------------------------------------------------------
# Extract final S0 energy (Hartree)
#--------------------------------------------------------------------
get_s0_energy() {
    local outfile=$1
    grep "FINAL SINGLE POINT ENERGY" "$outfile" | tail -1 | awk '{print $NF}'
}

#--------------------------------------------------------------------
# Get number of atoms from .xyz file
#--------------------------------------------------------------------
get_natom() {
    head -1 "$1"
}

#--------------------------------------------------------------------
# Run ORCA via myorca, with background process+output monitoring.
# Detects crashes (process gone but no normal termination) and
# common error patterns (INPUT ERROR, functional derivative, etc.)
#--------------------------------------------------------------------
ERROR_PATTERNS=(
    "INPUT ERROR"
    "UNRECOGNIZED OR DUPLICATED KEYWORD"
    "Third functional derivative of a B88"
    "FATAL ERROR"
    "segmentation fault"
    "ORCA finished with error"
    "abort"
)

run_orca() {
    local input=$1
    local basename="${input%.inp}"
    local outfile="${basename}.out"

    wait_for_job "$basename"
    if orca_done "$outfile"; then
        log "Already completed: $basename — skipping"
        return 0
    fi

    # Remove any stale failed output so we get a fresh run
    if [ -f "$outfile" ] && ! grep -q "ORCA TERMINATED NORMALLY" "$outfile"; then
        log "Removing stale/failed output: $outfile"
        rm -f "$outfile"
    fi

    log "Starting: myorca $input"

    # Launch ORCA in background so we can monitor it
    /home/yang/bin/myorca "$input" &
    local orca_pid=$!
    local check_interval=180  # 3 minutes between checks
    local stall_count=0
    local last_size=0
    local max_stalls=5        # 5 * 3min = 15min of no output = stalled

    while kill -0 "$orca_pid" 2>/dev/null; do
        sleep "$check_interval"

        # Check output growth (detect stalls)
        if [ -f "$outfile" ]; then
            local cur_size=$(wc -c < "$outfile" 2>/dev/null || echo 0)
            if [ "$cur_size" -eq "$last_size" ]; then
                stall_count=$((stall_count + 1))
                if [ "$stall_count" -ge "$max_stalls" ]; then
                    log "WARNING: Output stalled for $((stall_count * check_interval / 60)) min — possible hang"
                fi
            else
                stall_count=0
                last_size=$cur_size
                # Show progress: last meaningful line
                local last_line=$(grep -v "^\s*$" "$outfile" 2>/dev/null | tail -1 | head -c 130)
                log "  [$basename] $last_line"
            fi
        fi

        # Scan for error patterns
        if [ -f "$outfile" ]; then
            for pattern in "${ERROR_PATTERNS[@]}"; do
                if grep -q "$pattern" "$outfile"; then
                    log "CRITICAL: Detected error pattern '$pattern' in $outfile"
                    log "Killing ORCA process $orca_pid and aborting..."
                    kill -9 "$orca_pid" 2>/dev/null
                    wait "$orca_pid" 2>/dev/null
                    diagnose_error "$basename" "$outfile" "$pattern"
                    return 1
                fi
            done
        fi
    done

    # Process finished — wait and check result
    wait "$orca_pid" 2>/dev/null

    if orca_done "$outfile"; then
        log "SUCCESS: $basename completed normally"
        return 0
    fi

    # Process exited but output doesn't show normal termination
    log "ERROR: $basename process exited but no normal termination found"
    diagnose_error "$basename" "$outfile" ""
    return 1
}

#--------------------------------------------------------------------
# Save a successfully-run input file as a verified template.
# Only called after ORCA TERMINATED NORMALLY is confirmed.
#--------------------------------------------------------------------
save_template() {
    local input=$1
    local type_tag=$2
    local note=$3  # optional: brief note about this specific run

    mkdir -p "$TEMPLATE_DIR"

    local basename="${input%.inp}"
    local template_name="${type_tag}_camb3lyp_631gd.inp"
    local template_path="$TEMPLATE_DIR/$template_name"

    # Extract geometry placeholder line count for later reuse
    local geom_start=$(grep -n '^\* xyz' "$input" | head -1 | cut -d: -f1)

    # If a curated template already exists, do NOT overwrite it.
    # Curated templates contain detailed comments and are more valuable
    # than auto-saved raw inputs. Only save if no template exists yet.
    if [ -f "$template_path" ]; then
        log "Template $template_name already exists — skipping (curated version preserved)"
        return 0
    fi

    log "Creating new template: $template_name"

    # Build annotated template
    local today=$(date '+%Y-%m-%d')
    local header_block=$(head -n "$((geom_start - 1))" "$input")

    cat > "$template_path" << EOF
#===============================================================================
# @TYPE:       ${type_tag}
# @FUNCTIONAL: CAM-B3LYP
# @BASIS:      6-31G(d)
# @SOLVENT:    CPCM(Methanol)
# @DISPERSION: D3BJ
# @ORCA:       6.1.0 (libXC 7.0.0)
# @CHARGE:     1
# @MULT:       1
# @VERIFIED:   ${today} — ${basename} — ${note}
#===============================================================================
${header_block}
#===============================================================================
# To reuse: replace the geometry section below with your coordinates.
# Geometry must be charge=1, multiplicity=1 (closed-shell singlet).
#===============================================================================

* xyz 1 1
  <INSERT GEOMETRY HERE — from optimized .xyz of previous phase>
*
EOF

    log "Template saved: $template_path"
}

#--------------------------------------------------------------------
# Diagnose why an ORCA job failed — extract error context from output
#--------------------------------------------------------------------
diagnose_error() {
    local basename=$1
    local outfile=$2
    local matched_pattern=$3

    log "=============================================="
    log "  ERROR DIAGNOSIS: $basename"
    log "=============================================="

    if [ -n "$matched_pattern" ]; then
        log "Matched pattern: $matched_pattern"
    fi

    # Extract the last error/warning context
    log "--- Last 20 lines of output ---"
    tail -20 "$outfile" 2>/dev/null | while IFS= read -r line; do
        log "  $line"
    done

    # Extract specific error messages
    log "--- Error context ---"
    grep -i -B2 -A5 "error\|abort\|fatal\|WARNING\|cannot\|unable\|fail" "$outfile" 2>/dev/null | tail -30 | while IFS= read -r line; do
        log "  $line"
    done

    # Check if process is still alive
    if job_running "$basename"; then
        log "STATUS: ORCA process for $basename is still running (zombie?)"
    else
        log "STATUS: ORCA process for $basename has exited (crashed or killed)"
    fi

    log "=============================================="
}

#--------------------------------------------------------------------
# Extract TD-DFT emission data from S1 optimized output
# Returns: "E_em(cm-1) f_osc"
#--------------------------------------------------------------------
get_tddft_emission() {
    local outfile=$1
    local e_ev=""
    local f=""

    # ORCA 6.1: look for the last "0-1A  ->  1-1A" line in absorption spectrum
    # Format: 0-1A  ->  1-1A    <eV>   <cm-1>   <nm>   <fosc(D2)> ...
    # awk fields: $1=0-1A $2=-> $3=1-1A $4=eV $5=cm-1 $6=nm $7=fosc
    local last_spec=$(grep -n "ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE" "$outfile" | tail -1 | cut -d: -f1)
    if [ -n "$last_spec" ]; then
        local data=$(tail -n +"$last_spec" "$outfile" | grep "0-1A.*1-1A" | head -1)
        e_ev=$(echo "$data" | awk '{print $4}')
        f=$(echo "$data" | awk '{print $7}')
    fi

    # Fallback: "STATE  1:" format
    if [ -z "$e_ev" ]; then
        local state_line=$(grep "STATE\s*1:" "$outfile" | tail -1)
        if [ -n "$state_line" ]; then
            e_ev=$(echo "$state_line" | sed -n 's/.*E=\s*[0-9.]*\s*au\s*\([0-9.]*\)\s*eV.*/\1/p')
        fi
    fi

    if [ -n "$e_ev" ] && [ -n "$f" ]; then
        local e_cm1=$(python3 -c "print('{:.2f}'.format(float($e_ev)*8065.54))")
        echo "$e_cm1 $f"
    else
        echo "0 0"
    fi
}

#--------------------------------------------------------------------
# Extract k_IC from ESD output
#--------------------------------------------------------------------
get_k_ic() {
    local outfile=$1
    # Format: "The calculated internal conversion rate constant is  -4.954889e-02 s-1"
    local val=$(grep -i "internal conversion rate constant" "$outfile" | tail -1 | awk '{print $(NF-1)}')
    # Take absolute value (ORCA reports negative for S1→S0 direction)
    val="${val#-}"
    echo "${val:-0}"
}

#--------------------------------------------------------------------
# Write JSON status (simple key=value approach using python)
#--------------------------------------------------------------------
update_status() {
    python3 - "$@" << 'PYEOF'
import sys, json

status_file = "/data/software/orca610/34qy/cascade_status.json"
with open(status_file) as f:
    data = json.load(f)

# args: phase field value [phase field value ...]
args = sys.argv[1:]
i = 0
while i < len(args):
    if args[i] == "--phase":
        data["phase"] = args[i+1]
        i += 2
    elif args[i] == "--mol":
        mol = args[i+1]
        key = args[i+2]
        val = args[i+3]
        if val == "null":
            data["molecules"][mol][key] = None
        elif val == "true":
            data["molecules"][mol][key] = True
        elif val == "false":
            data["molecules"][mol][key] = False
        else:
            try:
                data["molecules"][mol][key] = float(val)
            except ValueError:
                data["molecules"][mol][key] = val
        i += 4
    else:
        i += 1

with open(status_file, "w") as f:
    json.dump(data, f, indent=2)
print(f"Status updated: phase={data['phase']}")
PYEOF
}

#--------------------------------------------------------------------
# Print summary of current status
#--------------------------------------------------------------------
print_status() {
    python3 - "$STATUS_FILE" << 'PYEOF'
import sys, json

with open(sys.argv[1]) as f:
    d = json.load(f)

print(f"\n{'='*60}")
print(f"  CASCADE STATUS — Phase: {d['phase']}")
print(f"{'='*60}")
for mol in ["LSH-33", "LSH-34"]:
    m = d["molecules"][mol]
    print(f"\n  {mol}:")
    print(f"    S₀ Energy:      {m['s0_energy']} Eh")
    print(f"    S₀ Imag Freq:   {m['s0_imag_freq']}")
    print(f"    S₁ E_em:        {m['s1_energy_cm1']} cm⁻¹")
    print(f"    S₁ f_osc:        {m['s1_f_osc']}")
    print(f"    S₁ converged:   {m['s1_converged']}")
    print(f"    k_IC:           {m['k_ic']} s⁻¹")
    print(f"    Φ_F:            {m['phi_f']}")
    print(f"    λ_em:           {m['lambda_em']} nm")
print(f"\n{'='*60}\n")
PYEOF
}
