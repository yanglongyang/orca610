#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/shared_functions.sh"

log "=================================================="
log "  PHASE 4: guarded photophysics report"
log "=================================================="

python3 - "$STATUS_FILE" <<'PYEOF'
import json, sys
path=sys.argv[1]
with open(path) as f: data=json.load(f)

for mol,m in data.get("molecules",{}).items():
    fosc=float(m.get("s1_f_osc") or 0)
    wn=float(m.get("s1_energy_cm1") or 0)
    kic=float(m.get("k_ic") or 0)
    # Vacuum electric-dipole Einstein-A estimate from vertical f and wavenumber.
    # This is not a vibronic ESD fluorescence rate.
    kr_approx=(fosc*wn**2/1.499) if fosc>0 and wn>0 else 0.0
    kr=float(m.get("k_r") or kr_approx)
    m["k_r_approx"]=kr_approx

    kisc=m.get("k_isc")
    knr_other=m.get("k_nr_other")
    if kisc is not None or knr_other is not None:
        total=kr+kic+float(kisc or 0)+float(knr_other or 0)
        m["phi_f_model"]=kr/total if total>0 else None
        m["phi_f_model_complete"]=True
    else:
        total=kr+kic
        m["phi_f_two_channel"]=kr/total if total>0 else None
        m["phi_f_model_complete"]=False

data["phase"]="complete"
with open(path,"w") as f: json.dump(data,f,indent=2)

lines=["# AutoORCA Photophysics Report","","## Scientific caveats",""]
lines += [
    "- A normal ORCA termination is not by itself proof of a valid electronic-state assignment.",
    "- `k_r_approx` is an Einstein-A estimate from a vertical oscillator strength, not an ORCA_ESD vibronic fluorescence rate.",
    "- `Phi_F(two-channel)` uses only k_r and k_IC. It is not a complete fluorescence quantum yield when ISC or other non-radiative channels matter.",
    "- Do not construct E00 or reorganization energies from mixed method/basis/solvent energy legs; use the energy-consistency gate in SKILL.md.",
    ""
]

for mol,m in data.get("molecules",{}).items():
    lines += [f"## {mol}",""]
    keys=["s0_energy","s0_imag_freq","s1_energy_cm1","lambda_em","s1_f_osc","s1_imag_freq","s1_final_root","k_ic","k_r_approx","phi_f_two_channel","phi_f_model"]
    for k in keys:
        if k in m and m[k] is not None:
            lines.append(f"- **{k}**: {m[k]}")
    lines.append("")

lines += ["## Method provenance","", "```json", json.dumps(data.get("methods",{}),indent=2), "```", ""]
if data.get("warnings"):
    lines += ["## Warnings",""] + [f"- {w}" for w in data["warnings"]] + [""]

report="\n".join(lines)
with open("cascade_report.md","w") as f:f.write(report)
print(report)
PYEOF

print_status
