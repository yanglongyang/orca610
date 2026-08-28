#!/usr/bin/env bash
#==============================================================================
# shared_functions.sh — common helpers for AutoORCA 3.x
#==============================================================================

# Do not hard-code one installation. Override with environment variables.
ORCA_ROOT="${ORCA_ROOT:-/data/software/orca610}"
MYORCA="${MYORCA:-$HOME/bin/myorca}"
TEMPLATE_DIR="${TEMPLATE_DIR:-$ORCA_ROOT/templates}"
MANUAL_DIR="${MANUAL_DIR:-$ORCA_ROOT/manual/orca_manual_kb}"

export PATH="$ORCA_ROOT:$PATH"
export LD_LIBRARY_PATH="$ORCA_ROOT:${LD_LIBRARY_PATH:-}"

WORKDIR="${AUTOORCA_WORKDIR:-$PWD}"
WORKDIR="$(realpath "$WORKDIR")"
STATUS_FILE="${STATUS_FILE:-$WORKDIR/cascade_status.json}"
cd "$WORKDIR" || exit 1

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

slugify() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]//g'
}

#------------------------------------------------------------------------------
# Status/provenance
#------------------------------------------------------------------------------
init_status() {
    python3 - "$STATUS_FILE" "$@" <<'PYEOF'
import json, os, sys
path = sys.argv[1]
mols = sys.argv[2:]
if os.path.exists(path):
    with open(path) as f:
        data = json.load(f)
else:
    data = {"schema_version": 2, "phase": "initialized", "molecules": {}, "methods": {}, "warnings": []}
data.setdefault("molecules", {})
data.setdefault("methods", {})
data.setdefault("warnings", [])
for mol in mols:
    data["molecules"].setdefault(mol, {})
with open(path, "w") as f:
    json.dump(data, f, indent=2)
PYEOF
}

update_status() {
    python3 - "$STATUS_FILE" "$@" <<'PYEOF'
import sys, json, os
status_file = sys.argv[1]
args = sys.argv[2:]
if os.path.exists(status_file):
    with open(status_file) as f:
        data = json.load(f)
else:
    data = {"schema_version": 2, "phase": "initialized", "molecules": {}, "methods": {}, "warnings": []}
data.setdefault("molecules", {})
data.setdefault("methods", {})
data.setdefault("warnings", [])

def coerce(v):
    if v == "null": return None
    if v == "true": return True
    if v == "false": return False
    try: return float(v)
    except ValueError: return v

i = 0
while i < len(args):
    if args[i] == "--phase":
        data["phase"] = args[i+1]; i += 2
    elif args[i] == "--mol":
        mol, key, val = args[i+1:i+4]
        data["molecules"].setdefault(mol, {})[key] = coerce(val)
        i += 4
    elif args[i] == "--warn":
        data["warnings"].append(args[i+1]); i += 2
    else:
        i += 1
with open(status_file, "w") as f:
    json.dump(data, f, indent=2)
PYEOF
}

record_method() {
    local label="$1" functional="$2" basis="$3" dispersion="$4" solvent="$5"
    local tda="$6" charge="$7" mult="$8" geometry_source="$9"
    python3 - "$STATUS_FILE" "$label" "$functional" "$basis" "$dispersion" "$solvent" "$tda" "$charge" "$mult" "$geometry_source" <<'PYEOF'
import json, os, sys
(path, label, functional, basis, dispersion, solvent, tda, charge, mult, geometry_source) = sys.argv[1:]
with open(path) as f:
    d = json.load(f)
d.setdefault("methods", {})[label] = {
    "functional": functional,
    "basis": basis,
    "dispersion": dispersion,
    "solvent": solvent,
    "tda": None if tda == "n.a." else (tda.lower() == "true"),
    "charge": int(charge),
    "multiplicity": int(mult),
    "geometry_source": geometry_source,
    "orca_version": os.environ.get("ORCA_VERSION", "6.1.x (set ORCA_VERSION for exact build)")
}
with open(path, "w") as f:
    json.dump(d, f, indent=2)
PYEOF
}

check_hessian_method_compatibility() {
    # ESD AH calculations should normally use GS/ES Hessians from compatible PES levels.
    # Returns nonzero on mismatch unless ALLOW_MIXED_HESSIANS=true.
    python3 - "$STATUS_FILE" "${ALLOW_MIXED_HESSIANS:-false}" <<'PYEOF'
import json, sys
path, allow = sys.argv[1], sys.argv[2].lower() == "true"
with open(path) as f:
    d = json.load(f)
a = d.get("methods", {}).get("s0_optfreq")
b = d.get("methods", {}).get("s1_optfreq")
if not a or not b:
    print("[METHOD-GATE] Missing s0_optfreq or s1_optfreq provenance.")
    sys.exit(1)
fields = ["functional", "basis", "dispersion", "solvent", "charge", "multiplicity"]
diff = [(k, a.get(k), b.get(k)) for k in fields if a.get(k) != b.get(k)]
if diff:
    print("[METHOD-GATE] GS/ES Hessian levels differ:")
    for k, x, y in diff:
        print(f"  {k}: S0={x!r}  S1={y!r}")
    if not allow:
        print("[METHOD-GATE] STOP. Set ALLOW_MIXED_HESSIANS=true only for a deliberate, documented approximation.")
        sys.exit(1)
    print("[METHOD-GATE] WARNING: continuing with explicitly allowed mixed Hessians.")
PYEOF
}

print_status() {
    python3 - "$STATUS_FILE" <<'PYEOF'
import json, sys
with open(sys.argv[1]) as f:
    d = json.load(f)
print("\n" + "="*68)
print(f"CASCADE STATUS — Phase: {d.get('phase','unknown')}")
print("="*68)
for mol, m in d.get("molecules", {}).items():
    print(f"\n{mol}:")
    for key in ["s0_energy", "s0_imag_freq", "s1_energy_cm1", "lambda_em", "s1_f_osc", "s1_converged", "s1_imag_freq", "k_ic", "k_r_approx", "phi_f_two_channel"]:
        if key in m:
            print(f"  {key}: {m[key]}")
if d.get("methods"):
    print("\nMethod provenance:")
    for label, meta in d["methods"].items():
        print(f"  {label}: {meta}")
if d.get("warnings"):
    print("\nWarnings:")
    for w in d["warnings"]:
        print("  -", w)
print("="*68 + "\n")
PYEOF
}

#------------------------------------------------------------------------------
# ORCA process helpers
#------------------------------------------------------------------------------
job_running() {
    local basename=$1
    ps aux | grep -v grep | grep -q "orca.*${basename}"
}

wait_for_job() {
    local basename=$1
    if job_running "$basename"; then
        log "Waiting for running job: $basename ..."
        while job_running "$basename"; do sleep 300; done
        sleep 5
        log "$basename finished."
    fi
}

orca_done() {
    local outfile=$1
    [ -f "$outfile" ] && grep -q "ORCA TERMINATED NORMALLY" "$outfile"
}

check_opt_converged() {
    local outfile=$1
    grep -Eq "HURRAY|THE OPTIMIZATION HAS CONVERGED" "$outfile"
}

# Print count to stdout. Return 0=no imaginary, 1=imaginary present, 2=summary absent.
get_imag_count() {
    local outfile=$1 n
    n=$(grep "Total number of imaginary perturbations" "$outfile" | tail -1 | awk '{print $NF}')
    if [ -z "$n" ]; then
        echo "NA"; return 2
    fi
    echo "$n"
    [ "$n" -eq 0 ] && return 0 || return 1
}

get_s0_energy() {
    local outfile=$1
    grep "FINAL SINGLE POINT ENERGY" "$outfile" | tail -1 | awk '{print $NF}'
}

get_natom() { head -1 "$1"; }

ERROR_PATTERNS=(
    "INPUT ERROR"
    "UNRECOGNIZED OR DUPLICATED KEYWORD"
    "FATAL ERROR"
    "segmentation fault"
    "ORCA finished with error"
)

run_orca() {
    local input=$1
    local basename="${input%.inp}"
    local outfile="${basename}.out"

    if [ ! -x "$MYORCA" ]; then
        log "ERROR: MYORCA wrapper is not executable: $MYORCA"
        return 1
    fi

    wait_for_job "$basename"
    if orca_done "$outfile"; then
        log "Already completed: $basename — skipping"
        return 0
    fi

    if [ -f "$outfile" ]; then
        log "Removing stale/failed output: $outfile"
        rm -f "$outfile"
    fi

    log "Starting: $MYORCA $input"
    "$MYORCA" "$input" &
    local orca_pid=$!
    local check_interval="${ORCA_CHECK_INTERVAL:-300}"
    local stall_count=0 last_size=0 check_num=0 stall_reported=0
    local max_stalls="${ORCA_MAX_STALLS:-4}"

    while kill -0 "$orca_pid" 2>/dev/null; do
        sleep "$check_interval"
        check_num=$((check_num + 1))

        if [ -f "$outfile" ]; then
            local cur_size
            cur_size=$(wc -c < "$outfile" 2>/dev/null || echo 0)
            if [ "$cur_size" -eq "$last_size" ] && [ "$cur_size" -gt 0 ]; then
                stall_count=$((stall_count + 1))
                if [ "$stall_count" -ge "$max_stalls" ] && [ "$stall_reported" -eq 0 ]; then
                    log "WARNING: output unchanged for $((stall_count * check_interval / 60)) min — review before killing; long kernels can be silent"
                    stall_reported=1
                fi
            else
                stall_count=0; last_size=$cur_size; stall_reported=0
            fi
        fi

        if [ "$((check_num % 2))" -eq 0 ] && [ -f "$outfile" ]; then
            for pattern in "${ERROR_PATTERNS[@]}"; do
                if grep -qi "$pattern" "$outfile"; then
                    log "CRITICAL: detected error pattern '$pattern' in $outfile"
                    kill -9 "$orca_pid" 2>/dev/null || true
                    wait "$orca_pid" 2>/dev/null || true
                    diagnose_error "$basename" "$outfile" "$pattern"
                    return 1
                fi
            done
        fi
    done

    wait "$orca_pid" 2>/dev/null || true
    if orca_done "$outfile"; then
        log "SUCCESS: $basename completed normally"
        return 0
    fi
    log "ERROR: $basename process exited without normal termination"
    diagnose_error "$basename" "$outfile" ""
    return 1
}

#------------------------------------------------------------------------------
# Data extraction
#------------------------------------------------------------------------------
get_final_iroot() {
    local outfile=$1 requested=${2:-1}
    local r
    r=$(grep "The IROOT now is:" "$outfile" | tail -1 | awk '{print $NF}')
    echo "${r:-$requested}"
}

get_tddft_emission() {
    # Returns: E(cm-1) f. Pass the final root index if root following changed IROOT.
    local outfile=$1 root=${2:-1}
    local last_spec data e_ev f
    last_spec=$(grep -n "ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE" "$outfile" | tail -1 | cut -d: -f1)
    if [ -n "$last_spec" ]; then
        data=$(tail -n +"$last_spec" "$outfile" | grep -E "0-1A[[:space:]]+->[[:space:]]+${root}-1A" | head -1)
        e_ev=$(echo "$data" | awk '{print $4}')
        f=$(echo "$data" | awk '{print $7}')
    fi
    if [[ "$e_ev" =~ ^[0-9]+([.][0-9]+)?$ ]] && [[ "$f" =~ ^[-+]?[0-9]*\.?[0-9]+([Ee][-+]?[0-9]+)?$ ]]; then
        python3 - "$e_ev" "$f" <<'PYEOF'
import sys
print(f"{float(sys.argv[1])*8065.544005:.2f} {float(sys.argv[2]):.10g}")
PYEOF
    else
        echo "0 0"
    fi
}

get_k_ic() {
    local outfile=$1
    grep -i "calculated internal conversion rate constant" "$outfile" | tail -1 | awk '{print $(NF-1)}'
}

#------------------------------------------------------------------------------
# Templates
#------------------------------------------------------------------------------
save_template() {
    local input=$1 type_tag=$2 functional=$3 basis=$4 solvent=$5 dispersion=$6
    local charge=$7 mult=$8 tda=$9 note=${10:-"syntax/run verified"}
    local fslug bslug template_name template_path geom_start today

    fslug=$(slugify "$functional")
    bslug=$(slugify "$basis")
    template_name="${type_tag//-/_}_${fslug}_${bslug}.inp"
    template_path="$TEMPLATE_DIR/$template_name"
    mkdir -p "$TEMPLATE_DIR"

    if [ -f "$template_path" ]; then
        log "Template $template_name exists — not overwriting curated file"
        return 0
    fi

    geom_start=$(grep -n -m1 -E '^\*[[:space:]]+xyz|^\*[[:space:]]+XYZ' "$input" | cut -d: -f1)
    if [ -z "$geom_start" ]; then
        log "WARNING: cannot locate geometry block; template not saved"
        return 1
    fi
    today=$(date '+%Y-%m-%d')

    {
        echo "#==============================================================================="
        echo "# @TYPE:       $type_tag"
        echo "# @FUNCTIONAL: $functional"
        echo "# @BASIS:      $basis"
        echo "# @SOLVENT:    $solvent"
        echo "# @DISPERSION: $dispersion"
        echo "# @TDA:        $tda"
        echo "# @CHARGE:     $charge"
        echo "# @MULT:       $mult"
        echo "# @ORCA:       ${ORCA_VERSION:-6.1.x}"
        echo "# @STATUS:     VERIFIED-SYNTAX"
        echo "# @VERIFIED:   $today — ${input%.inp} — $note"
        echo "#==============================================================================="
        head -n "$((geom_start - 1))" "$input"
        echo ""
        echo "* xyz $charge $mult"
        echo "  <INSERT GEOMETRY HERE>"
        echo "*"
    } > "$template_path"
    log "Template saved: $template_path"
}

#------------------------------------------------------------------------------
# Diagnostics / notifications
#------------------------------------------------------------------------------
diagnose_error() {
    local basename=$1 outfile=$2 matched_pattern=${3:-}
    local diag="/tmp/orca_diag_${$}.txt"
    {
        echo "--- Last 30 lines ---"
        tail -30 "$outfile" 2>/dev/null
        echo ""
        echo "--- Error/warning context ---"
        grep -i -B2 -A5 "error\|abort\|fatal\|warning\|cannot\|unable\|fail" "$outfile" 2>/dev/null | tail -60
    } > "$diag"
    [ -n "$matched_pattern" ] && log "Matched pattern: $matched_pattern"
    log "Diagnosis saved to $diag"
}

EMAIL_TO="${EMAIL_TO:-}"
EMAIL_FROM="${EMAIL_FROM:-${SMTP_USER:-}}"
SMTP_USER="${SMTP_USER:-}"
SMTP_PASS="${SMTP_PASS:-}"
SMTP_HOST="${SMTP_HOST:-smtp.163.com}"
SMTP_PORT="${SMTP_PORT:-465}"

send_notification() {
    local subject="$1" body="$2"
    [ -z "$SMTP_PASS" ] && { log "Email not configured — skipping"; return 0; }
    python3 - "$subject" "$body" "$EMAIL_TO" "$EMAIL_FROM" "$SMTP_USER" "$SMTP_PASS" "$SMTP_HOST" "$SMTP_PORT" <<'PYEOF'
import sys, smtplib
from email.mime.text import MIMEText
s,b,t,f,u,p,h,port=sys.argv[1:9]
if not all([t,f,u,p]):
    raise SystemExit("Email configuration incomplete")
msg=MIMEText(b,'plain','utf-8'); msg['Subject']=s; msg['From']=f; msg['To']=t
with smtplib.SMTP_SSL(h,int(port)) as sv:
    sv.login(u,p); sv.sendmail(f,[t],msg.as_string())
PYEOF
}

notify_summary() {
    local event="$1" subject="[AutoORCA] ${1} — $(date '+%m/%d %H:%M')"
    local body
    body=$(python3 - "$STATUS_FILE" <<'PYEOF'
import json, sys
with open(sys.argv[1]) as f: d=json.load(f)
lines=["Phase: "+d.get("phase","unknown"),""]
for mol,m in d.get("molecules",{}).items():
    lines.append(mol+":")
    for k,v in m.items():
        lines.append(f"  {k}: {v}")
print("\n".join(lines))
PYEOF
)
    send_notification "$subject" "$body"
}
