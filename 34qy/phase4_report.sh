#!/bin/bash
#==============================================================================
# Phase 4: Quantum Yield Calculation & Markdown Report
#==============================================================================
source "$(dirname "$0")/shared_functions.sh"

log "=================================================="
log "  PHASE 4: Quantum Yield & Report"
log "=================================================="

python3 << 'PYEOF'
import json

with open("/data/software/orca610/34qy/cascade_status.json") as f:
    data = json.load(f)

molecules = ["LSH-33", "LSH-34"]

for mol in molecules:
    m = data["molecules"][mol]
    f_val = m.get("s1_f_osc") or 0
    e_em = m.get("s1_energy_cm1") or 0
    k_ic = m.get("k_ic") or 0

    if f_val > 0 and e_em > 0:
        k_r = (f_val * e_em**2) / 1.499e8 * 1e8
    else:
        k_r = 0

    if k_r + k_ic > 0:
        phi_f = k_r / (k_r + k_ic)
    else:
        phi_f = 0

    lam = (1e7 / e_em) if e_em > 0 else 0

    m["k_r"] = k_r
    m["phi_f"] = phi_f
    m["lambda_em"] = lam
    data["molecules"][mol] = m

data["phase"] = "complete"

with open("/data/software/orca610/34qy/cascade_status.json", "w") as f:
    json.dump(data, f, indent=2)

d33 = data["molecules"]["LSH-33"]
d34 = data["molecules"]["LSH-34"]

def fmt(val, dec=4):
    if val is None or val == 0:
        return "N/A"
    return f"{val:.{dec}f}"

lines = []
def R(k, v33, v34):
    lines.append(f"| {k} | {v33} | {v34} |")
def R1(k, v):
    lines.append(f"| {k} | {v} |")

lines.append("# LSH-33 (560nm) & LSH-34 (650nm) Photophysical Report")
lines.append("")
lines.append("**Method**: CAM-B3LYP/6-31G(d) | RIJCOSX | D3BJ(S0) | CPCM(MeOH)")
lines.append("**ORCA**: 6.1.0")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Results Summary")
lines.append("")
lines.append("| Parameter | LSH-33 (560nm) | LSH-34 (650nm) |")
lines.append("|------|:---:|:---:|")
R("S0 Energy (Eh)", fmt(d33['s0_energy'],6), fmt(d34['s0_energy'],6))
R("S0 Imag Freq", str(int(d33.get('s0_imag_freq',-1))), str(int(d34.get('s0_imag_freq',-1))))
R("S1 Converged", str(d33.get('s1_converged',False)), str(d34.get('s1_converged',False)))
R("Emission (nm)", fmt(d33['lambda_em'],1), fmt(d34['lambda_em'],1))
R("E_em (cm-1)", fmt(d33['s1_energy_cm1'],1), fmt(d34['s1_energy_cm1'],1))
R("Osc Strength f", fmt(d33['s1_f_osc'],6), fmt(d34['s1_f_osc'],6))
R("k_r (s-1)", fmt(d33.get('k_r',0),2), fmt(d34.get('k_r',0),2))
R("k_IC (s-1)", fmt(d33.get('k_ic',0),2), fmt(d34.get('k_ic',0),2))
b33 = "**"+fmt(d33.get('phi_f',0),6)+"**"
b34 = "**"+fmt(d34.get('phi_f',0),6)+"**"
R("**Phi_F (QY)**", b33, b34)
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Formulas")
lines.append("")
lines.append("k_r = f * E_em^2 / 1.499e8 * 1e8  [s-1]")
lines.append("")
lines.append("Phi_F = k_r / (k_r + k_IC)")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Detailed Data")
lines.append("")

for mol, d, name in [("LSH-33", d33, "C22H18NO, target 560nm"),
                      ("LSH-34", d34, "C26H22NO3, target 650nm")]:
    lines.append(f"### {mol} ({name})")
    lines.append("")
    lines.append("| Property | Value |")
    lines.append("|------|------|")
    R1("S0 Energy", fmt(d['s0_energy'],6)+" Eh")
    R1("S0 Imag Freq", str(int(d.get('s0_imag_freq',-1))))
    R1("S1 Converged", str(d.get('s1_converged',False)))
    R1("E_em", fmt(d['s1_energy_cm1'],1)+" cm-1")
    R1("lambda_em", fmt(d['lambda_em'],1)+" nm")
    R1("Osc Strength f", fmt(d['s1_f_osc'],6))
    R1("k_r", fmt(d.get('k_r',0),2)+" s-1")
    R1("k_IC", fmt(d.get('k_ic',0),2)+" s-1")
    R1("**Phi_F (QY)**", "**"+fmt(d.get('phi_f',0),6)+"**")
    lines.append("")

report = "\n".join(lines)

with open("/data/software/orca610/34qy/cascade_report.md", "w") as f:
    f.write(report)

print(report)
print("\n" + "="*60)
print("Report saved to cascade_report.md")
print("="*60)
PYEOF

update_status --phase "complete"
log "Phase 4 finished -- cascade complete."
