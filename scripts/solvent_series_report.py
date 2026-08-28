#!/usr/bin/env python3
"""Validate controlled solvent-series data and emit solvent shifts."""
from __future__ import annotations

import json
import sys
from pathlib import Path


class SolventSeriesError(ValueError):
    pass


CONTROLLED_KEYS = (
    "functional", "basis", "dispersion", "solvent_model", "solvent_regime",
    "cpcmeq", "tda", "excited_state_method", "state_identity", "numerical_settings",
    "transition_kind", "geometry_surface",
)
REQUIRED_ENTRY_KEYS = ("solvent", "epsilon", "geometry_solvent", "energy_solvent", "geometry_id", "transition_eV")


def validate_series(data: dict) -> list[dict]:
    protocol = data.get("protocol")
    entries = data.get("entries", [])
    if protocol not in {"fixed_geometry", "solvent_relaxed"}:
        raise SolventSeriesError("protocol must be 'fixed_geometry' or 'solvent_relaxed'")
    if len(entries) < 2:
        raise SolventSeriesError("at least two solvent entries are required")
    reference = entries[0]
    for entry in entries:
        for key in REQUIRED_ENTRY_KEYS:
            if entry.get(key) in (None, ""):
                raise SolventSeriesError(f"every entry requires {key}")
        for key in CONTROLLED_KEYS:
            if entry.get(key) in (None, ""):
                raise SolventSeriesError(f"every entry requires {key}")
            if entry[key] != reference[key]:
                raise SolventSeriesError(f"{key} differs across the series")
    geometries = {entry.get("geometry_id") for entry in entries}
    if protocol == "fixed_geometry" and (None in geometries or len(geometries) != 1):
        raise SolventSeriesError("fixed_geometry protocol requires one shared geometry_id")
    if protocol == "solvent_relaxed" and not data.get("allow_geometry_solvent_mismatch", False):
        mismatches = [
            entry["solvent"] for entry in entries
            if entry["geometry_solvent"] != entry["solvent"]
        ]
        if mismatches:
            raise SolventSeriesError(
                "solvent_relaxed protocol requires geometry_solvent to match solvent; "
                "set allow_geometry_solvent_mismatch only for a documented composite protocol"
            )
    return entries


def summarize_series(data: dict) -> dict:
    entries = validate_series(data)
    reference = entries[0]
    ref_e = float(reference["transition_eV"])
    result = []
    for entry in entries:
        shift = float(entry["transition_eV"]) - ref_e
        result.append({
            "solvent": entry["solvent"],
            "epsilon": entry["epsilon"],
            "geometry_solvent": entry["geometry_solvent"],
            "energy_solvent": entry["energy_solvent"],
            "transition_kind": entry["transition_kind"],
            "geometry_surface": entry["geometry_surface"],
            "transition_eV": float(entry["transition_eV"]),
            "wavelength_nm": 1239.8419843320026 / float(entry["transition_eV"]),
            "shift_eV_from_reference": shift,
            "shift_nm_from_reference": 1239.8419843320026 / float(entry["transition_eV"]) - 1239.8419843320026 / ref_e,
            "geometry_id": entry["geometry_id"],
        })
    return {
        "solvent_gate": "PASS",
        "protocol": data["protocol"],
        "reference_solvent": reference["solvent"],
        "interpretation": (
            "electronic response at one shared geometry"
            if data["protocol"] == "fixed_geometry"
            else "combined electronic and solvent-specific geometry response"
        ),
        "entries": result,
    }


def main(path: str) -> None:
    try:
        result = summarize_series(json.loads(Path(path).read_text()))
    except (OSError, json.JSONDecodeError, SolventSeriesError) as exc:
        print(f"[SOLVENT-SERIES] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {Path(sys.argv[0]).name} solvent_series.json", file=sys.stderr)
        raise SystemExit(2)
    main(sys.argv[1])
