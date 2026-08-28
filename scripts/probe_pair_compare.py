#!/usr/bin/env python3
"""Validate and compare matched fluorescence-probe calculations.

The input is a JSON document containing ``species_results`` and a two-member
``pair``.  It deliberately compares observables, not absolute total energies
of chemically different species.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

EV_TO_CM1 = 8065.54429

COMMON_PROTOCOL_KEYS = (
    "functional", "basis", "dispersion", "solvent_model", "solvent",
    "solvent_regime", "cpcmeq", "numerical_settings",
)
STAGE_PROTOCOL_KEYS = {
    "s0_geometry": COMMON_PROTOCOL_KEYS + ("method_family",),
    "absorption": COMMON_PROTOCOL_KEYS + ("method_family", "tda", "excited_state_method"),
    "s1_geometry": COMMON_PROTOCOL_KEYS + ("method_family", "tda", "excited_state_method"),
    "emission": COMMON_PROTOCOL_KEYS + ("method_family", "tda", "excited_state_method"),
}


class ProbePairError(ValueError):
    """Raised when a probe/product comparison is not controlled."""


def _missing(value: object) -> bool:
    return value is None or value == ""


def protocol_issues(first: dict, second: dict) -> list[str]:
    """Return all unmatched phase-specific protocol fields for a species pair."""
    issues: list[str] = []
    for stage, keys in STAGE_PROTOCOL_KEYS.items():
        a_stage, b_stage = first.get(stage), second.get(stage)
        if not isinstance(a_stage, dict) or not isinstance(b_stage, dict):
            issues.append(f"missing phase protocol {stage!r}")
            continue
        for key in keys:
            a, b = a_stage.get(key), b_stage.get(key)
            if _missing(a) or _missing(b):
                issues.append(f"{stage} lacks protocol field {key!r}")
            elif a != b:
                issues.append(f"{stage}.{key}: {a!r} != {b!r}")
    return issues


def stokes_metrics(observables: dict) -> dict:
    """Return Stokes-shift values only when both transition energies exist."""
    abs_ev = observables.get("absorption_eV")
    em_ev = observables.get("emission_eV")
    if abs_ev is None or em_ev is None:
        return {}
    shift_ev = float(abs_ev) - float(em_ev)
    result = {"eV": shift_ev, "cm-1": shift_ev * EV_TO_CM1}
    if observables.get("absorption_nm") is not None and observables.get("emission_nm") is not None:
        # Wavelength subtraction is display-only; it is not an energy metric.
        result["nm_display_only"] = float(observables["emission_nm"]) - float(observables["absorption_nm"])
    return result


def _delta(second: dict, first: dict, key: str) -> float | None:
    if first.get(key) is None or second.get(key) is None:
        return None
    return float(second[key]) - float(first[key])


def validated_e00(observables: dict) -> dict:
    """Accept E00 only when it explicitly inherits a passing four-point gate."""
    record = observables.get("E00")
    if not isinstance(record, dict):
        return {"status": "NOT_VALIDATED", "reason": "missing structured E00 record"}
    if record.get("energy_cycle_gate") != "PASS":
        return {"status": "NOT_VALIDATED", "reason": "energy_cycle_gate is not PASS"}
    if record.get("eV") is None or not record.get("source"):
        return {"status": "NOT_VALIDATED", "reason": "E00 requires eV and source"}
    return {"status": "VALIDATED", "eV": float(record["eV"]), "source": record["source"]}


def compare_pair(data: dict) -> dict:
    results = {entry.get("id"): entry for entry in data.get("species_results", [])}
    pair = data.get("pair", {})
    first_id, second_id = pair.get("reference"), pair.get("comparison")
    if not first_id or not second_id or first_id == second_id:
        raise ProbePairError("pair must name two different species as reference and comparison")
    if first_id not in results or second_id not in results:
        raise ProbePairError("pair references species absent from species_results")

    first, second = results[first_id], results[second_id]
    issues = protocol_issues(first.get("protocol", {}), second.get("protocol", {}))
    if issues:
        raise ProbePairError("unmatched probe-pair protocol: " + "; ".join(issues))

    a, b = first.get("observables", {}), second.get("observables", {})
    first_e00, second_e00 = validated_e00(a), validated_e00(b)
    e00_delta = (
        second_e00["eV"] - first_e00["eV"]
        if first_e00["status"] == second_e00["status"] == "VALIDATED"
        else None
    )
    return {
        "comparison_gate": "PASS",
        "reference": first_id,
        "comparison": second_id,
        "stage_protocols": first["protocol"],
        "reference_observables": a,
        "comparison_observables": b,
        "reference_stokes": stokes_metrics(a),
        "comparison_stokes": stokes_metrics(b),
        "validated_E00": {"reference": first_e00, "comparison": second_e00},
        "deltas_comparison_minus_reference": {
            "E_abs_eV": _delta(b, a, "absorption_eV"),
            "lambda_abs_nm": _delta(b, a, "absorption_nm"),
            "f_abs": _delta(b, a, "absorption_f"),
            "E_em_eV": _delta(b, a, "emission_eV"),
            "lambda_em_nm": _delta(b, a, "emission_nm"),
            "f_em": _delta(b, a, "emission_f"),
            "E00_eV": e00_delta,
            "stokes_eV": _delta(stokes_metrics(b), stokes_metrics(a), "eV"),
            "stokes_cm-1": _delta(stokes_metrics(b), stokes_metrics(a), "cm-1"),
            "stokes_nm_display_only": _delta(
                stokes_metrics(b), stokes_metrics(a), "nm_display_only"
            ),
        },
        "interpretation_limits": [
            "HOMO-LUMO gaps are supporting descriptors, not optical gaps.",
            "Do not treat total-energy differences between chemically different species as reaction energies without a balanced thermochemical cycle.",
        ],
    }


def main(path: str) -> None:
    try:
        result = compare_pair(json.loads(Path(path).read_text()))
    except (OSError, json.JSONDecodeError, ProbePairError) as exc:
        print(f"[PROBE-PAIR] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {Path(sys.argv[0]).name} probe_pair_results.json", file=sys.stderr)
        raise SystemExit(2)
    main(sys.argv[1])
