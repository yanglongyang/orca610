#!/usr/bin/env python3
"""Create an evidence-ranked fluorescence-probe Markdown and JSON report.

This is intentionally a reporting layer.  It records supplied ORCA-native
observables and does not invent NTO, charge-transfer, or Multiwfn quantities.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

VALID_ICT_LABELS = {"LOCAL", "PARTIAL_CT", "STRONG_CT", "MIXED", "UNRESOLVED"}
VALID_MECHANISM_VERDICTS = {"SUPPORTED", "PLAUSIBLE", "INSUFFICIENT", "CONTRADICTED"}


def multiwfn_status() -> dict:
    requested = os.environ.get("MULTIWFN_BIN", "").strip()
    requested_path = Path(requested).expanduser() if requested else None
    executable = (
        str(requested_path)
        if requested_path and requested_path.is_file() and os.access(requested_path, os.X_OK)
        else shutil.which(requested) if requested else shutil.which("Multiwfn") or shutil.which("multiwfn")
    )
    return {
        "status": "AVAILABLE_NOT_RUN" if executable else "NOT_RUN",
        "binary": executable or None,
        "note": "No Multiwfn command is executed automatically; provide validated results explicitly.",
    }


def classify_ict(record: dict) -> dict:
    """Keep qualitative and quantitative CT claims visibly separate."""
    label = record.get("qualitative_label", "UNRESOLVED")
    if label not in VALID_ICT_LABELS:
        raise ValueError(f"invalid qualitative ICT label {label!r}")
    state_verified = bool(record.get("state_identity_verified"))
    nto_evidence = bool(record.get("donor_description") and record.get("acceptor_description"))
    quantitative = record.get("hole_electron") or {}
    quantitative_status = quantitative.get("status", "NOT_RUN")
    return {
        "species": record.get("species"),
        "state": record.get("state"),
        "state_identity_verified": state_verified,
        "qualitative_label": label if state_verified and nto_evidence else "UNRESOLVED",
        "qualitative_evidence_available": state_verified and nto_evidence,
        "quantitative_ct_status": quantitative_status,
        "leading_nto_occupation": record.get("leading_nto_occupation"),
        "secondary_nto_occupation": record.get("secondary_nto_occupation"),
        "donor_description": record.get("donor_description"),
        "acceptor_description": record.get("acceptor_description"),
    }


def classify_mechanism(evidence: list[dict]) -> str:
    """Require more than a canonical-orbital descriptor for a strong claim."""
    meaningful = [
        item for item in evidence
        if item.get("descriptor") not in {"homo_lumo_gap", "canonical_orbital_image"}
    ]
    supporting = [item for item in meaningful if item.get("assessment") in {"supportive", "strong"}]
    strong = [item for item in meaningful if item.get("assessment") == "strong"]
    contradicting = [item for item in meaningful if item.get("assessment") == "contradictory"]
    if strong and len(supporting) >= 2:
        return "SUPPORTED"
    if contradicting and not supporting:
        return "CONTRADICTED"
    if supporting:
        return "PLAUSIBLE"
    return "INSUFFICIENT"


def build_report(data: dict) -> tuple[dict, str]:
    pair = data.get("pair_comparison", {})
    if pair and pair.get("comparison_gate") != "PASS":
        raise ValueError("pair_comparison must have passed its protocol gate")
    ict_records = [classify_ict(record) for record in data.get("nto_evidence", [])]
    hypotheses = []
    for item in data.get("mechanism_hypotheses", []):
        hypotheses.append({
            "hypothesis": item.get("hypothesis", "UNSPECIFIED"),
            "verdict": classify_mechanism(item.get("evidence", [])),
            "evidence": item.get("evidence", []),
        })
    payload = {
        "project": data.get("project", "UNNAMED_PROJECT"),
        "species": data.get("species", []),
        "method_provenance": data.get("method_provenance", {}),
        "pair_comparison": pair,
        "nto_ict_analysis": ict_records,
        "hole_electron_analysis": data.get("hole_electron_analysis", multiwfn_status()),
        "solvent_response": data.get("solvent_response", {"status": "NOT_RUN"}),
        "tict_analysis": data.get("tict_analysis", {"status": "NOT_RUN"}),
        "mechanistic_interpretation": hypotheses,
        "limitations": [
            "Oscillator strength alone does not determine fluorescence quantum yield.",
            "A HOMO-LUMO gap is not an optical gap and cannot alone establish ICT or a spectral mechanism.",
            "A twisted S1 geometry alone cannot establish TICT.",
            "Probe/product total electronic energies are not reaction energies without a balanced thermochemical cycle.",
        ],
    }
    lines = [
        "# Fluorescence Probe Photophysics Report", "",
        f"Project: `{payload['project']}`", "",
        "## 1. Species", "", "```json", json.dumps(payload["species"], indent=2), "```", "",
        "## 2. Method provenance", "", "```json", json.dumps(payload["method_provenance"], indent=2), "```", "",
        "## 3. Probe vs fluorophore comparison", "", "```json", json.dumps(pair, indent=2), "```", "",
        "## 4. NTO / ICT evidence", "", "```json", json.dumps(ict_records, indent=2), "```", "",
        "## 5. Hole-electron analysis", "", "```json", json.dumps(payload["hole_electron_analysis"], indent=2), "```", "",
        "## 6. Solvent response", "", "```json", json.dumps(payload["solvent_response"], indent=2), "```", "",
        "## 7. TICT analysis", "", "```json", json.dumps(payload["tict_analysis"], indent=2), "```", "",
        "## 8. Mechanistic interpretation", "", "```json", json.dumps(hypotheses, indent=2), "```", "",
        "## 9. Method limitations", "",
    ]
    lines.extend(f"- {item}" for item in payload["limitations"])
    lines += ["", "## 10. Recommended experimental comparisons", "", "- Compare absorption/emission spectra under the same solvent and concentration regime.", "- Use lifetime and quantum-yield data to distinguish radiative and non-radiative changes.", ""]
    return payload, "\n".join(lines)


def main(input_path: str, output_dir: str) -> None:
    try:
        payload, markdown = build_report(json.loads(Path(input_path).read_text()))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[PROBE-REPORT] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / "fluorescence_probe_report.json").write_text(json.dumps(payload, indent=2) + "\n")
    (target / "fluorescence_probe_report.md").write_text(markdown)
    print(f"Wrote {target / 'fluorescence_probe_report.md'}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {Path(sys.argv[0]).name} report_input.json output_directory", file=sys.stderr)
        raise SystemExit(2)
    main(sys.argv[1], sys.argv[2])
