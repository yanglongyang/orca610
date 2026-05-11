#!/bin/bash
#==============================================================================
# Phase 4: Quantum Yield Calculation & Report
#
# Reads cascade_status.json, calculates Phi_F, writes cascade_report.md.
# No customization needed — reads all data from the status file.
#==============================================================================
source "$(dirname "$0")/shared_functions.sh"

log "=================================================="
log "  PHASE 4: Quantum Yield & Report"
log "=================================================="

python3 << 'PYEOF'
import json

with open("cascade_status.json") as f:
    data = json.load(f)

molecules = list(data["molecules"].keys())

for mol in molecules:
    m = data["molecules"][mol]
    f_val = m.get("s1_f_osc") or 0
    e_em = m.get("s1_energy_cm1") or 0
    k_ic = m.get("k_ic") or 0

    if f_val > 0 and e_em > 0:
        k_r = (f_val * e_em**2) / 1.499e8 * 1e8
    else:
        k_r = 0

    phi_f = k_r / (k_r + k_ic) if (k_r + k_ic) > 0 else 0
    lam = (1e7 / e_em) if e_em > 0 else 0

    m["k_r"] = k_r
    m["phi_f"] = phi_f
    m["lambda_em"] = lam
    data["molecules"][mol] = m

data["phase"] = "complete"

with open("cascade_status.json", "w") as f:
    json.dump(data, f, indent=2)

# ---- Generate Report ----
def fmt(val, dec=4):
    if val is None or val == 0:
        return "N/A"
    return f"{val:.{dec}f}"

lines = []
lines.append("# Photophysical Cascade Report")
lines.append("")
lines.append("## Results Summary")
lines.append("")
header = "| Parameter | " + " | ".join(molecules) + " |"
lines.append(header)
lines.append("|" + "|".join([":---:"] * (len(molecules) + 1)) + "|")

keys = [
    ("S0 Energy (Eh)", "s0_energy", 6),
    ("E_em (cm-1)", "s1_energy_cm1", 1),
    ("lambda_em (nm)", "lambda_em", 1),
    ("f_osc", "s1_f_osc", 6),
    ("k_r (s-1)", "k_r", 2),
    ("k_IC (s-1)", "k_ic", 2),
    ("Phi_F", "phi_f", 6),
]
for label, key, dec in keys:
    vals = [fmt(data["molecules"][m].get(key, 0), dec) for m in molecules]
    lines.append(f"| {label} | " + " | ".join(vals) + " |")

lines.append("")
lines.append("## Formulas")
lines.append("")
lines.append("k_r = f * E_em^2 / 1.499e8 * 1e8  [s-1]")
lines.append("Phi_F = k_r / (k_r + k_IC)")
lines.append("")

# Detailed sections
for mol in molecules:
    d = data["molecules"][mol]
    lines.append(f"## {mol}")
    lines.append("")
    for label, key, unit, dec in [
        ("S0 Energy", "s0_energy", "Eh", 6),
        ("E_em", "s1_energy_cm1", "cm-1", 1),
        ("lambda_em", "lambda_em", "nm", 1),
        ("f_osc", "s1_f_osc", "", 6),
        ("k_r", "k_r", "s-1", 2),
        ("k_IC", "k_ic", "s-1", 2),
        ("Phi_F", "phi_f", "", 6),
    ]:
        val = fmt(d.get(key, 0), dec)
        lines.append(f"- **{label}**: {val} {unit}".strip())

report = "\n".join(lines)

with open("cascade_report.md", "w") as f:
    f.write(report)

print(report)
print("\n" + "=" * 60)
print("Report saved to cascade_report.md")
PYEOF

update_status --phase "complete"
log "Phase 4 finished -- cascade complete."
