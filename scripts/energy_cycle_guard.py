#!/usr/bin/env python3
"""Validate and evaluate a four-point S0/S1 energy cycle.

Input JSON example is in examples/energy_cycle.example.json.
The script intentionally refuses to combine inconsistent method fingerprints.
"""
from __future__ import annotations
import json
import math
import sys
from pathlib import Path

EH_TO_EV = 27.211386245988
EV_NM = 1239.8419843320026

REQUIRED_POINTS = ("E0_R0", "E1_R0", "E0_R1", "E1_R1")
SHARED_FINGERPRINT_KEYS = (
    "functional",
    "basis",
    "dispersion",
    "solvent_model",
    "solvent",
    "solvent_regime",
    "relativistic",
    "charge",
    "multiplicity",
)
GROUND_STATE_KEYS = ("method_family",)
EXCITED_STATE_KEYS = ("method_family", "tda", "excited_state_method")


def fail(msg: str, code: int = 2) -> None:
    print(f"[ENERGY-GATE] ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def method_diff(points: dict) -> list[str]:
    issues: list[str] = []
    methods = {name: points[name].get("method", {}) for name in REQUIRED_POINTS}

    # Every shared descriptor must be stated on every leg.  Merely having the
    # same omitted value would otherwise be incorrectly accepted as consistency.
    for name, method in methods.items():
        for key in SHARED_FINGERPRINT_KEYS:
            if method.get(key) in (None, ""):
                issues.append(f"{name} lacks shared fingerprint field {key!r}")

    ref = methods["E0_R0"]
    for name in REQUIRED_POINTS[1:]:
        cur = methods[name]
        for key in SHARED_FINGERPRINT_KEYS:
            if ref.get(key) != cur.get(key):
                issues.append(
                    f"{key}: {REQUIRED_POINTS[0]}={ref.get(key)!r}, {name}={cur.get(key)!r}"
                )

    # DFT is the normal method family for S0 legs and TD-DFT for S1 legs.  They
    # must be internally consistent by state, but must not be forced equal
    # across states merely because their energies are combined in one cycle.
    for first, second, keys, label in (
        ("E0_R0", "E0_R1", GROUND_STATE_KEYS, "ground-state"),
        ("E1_R0", "E1_R1", EXCITED_STATE_KEYS, "excited-state"),
    ):
        for key in keys:
            first_value = methods[first].get(key)
            second_value = methods[second].get(key)
            if first_value in (None, "") or second_value in (None, ""):
                issues.append(
                    f"{label} pair lacks required field {key!r}: "
                    f"{first}={first_value!r}, {second}={second_value!r}"
                )
            elif first_value != second_value:
                issues.append(
                    f"{label} {key}: {first}={first_value!r}, {second}={second_value!r}"
                )
    return issues


def wavelength_nm(ev: float) -> float | None:
    return EV_NM / ev if ev > 0 else None


def main(path: str) -> None:
    data = json.loads(Path(path).read_text())
    pts = data.get("energies", {})
    missing = [p for p in REQUIRED_POINTS if p not in pts]
    if missing:
        fail("missing energy points: " + ", ".join(missing))
    for p in REQUIRED_POINTS:
        if "value_eh" not in pts[p]:
            fail(f"{p} lacks value_eh")

    issues = method_diff(pts)
    if issues:
        print("[ENERGY-GATE] Method fingerprints are inconsistent:", file=sys.stderr)
        for x in issues:
            print("  - " + x, file=sys.stderr)
        fail("refusing to construct Ead/E00/reorganization energies from mixed energy levels")

    e0r0 = float(pts["E0_R0"]["value_eh"])
    e1r0 = float(pts["E1_R0"]["value_eh"])
    e0r1 = float(pts["E0_R1"]["value_eh"])
    e1r1 = float(pts["E1_R1"]["value_eh"])

    values_eh = {
        "E_abs": e1r0 - e0r0,
        "E_em": e1r1 - e0r1,
        "E_ad": e1r1 - e0r0,
        "lambda_e": e1r0 - e1r1,
        "lambda_g": e0r1 - e0r0,
    }
    zpe = data.get("zpe", {})
    if "S0_R0_eh" in zpe and "S1_R1_eh" in zpe:
        values_eh["E00"] = values_eh["E_ad"] + float(zpe["S1_R1_eh"]) - float(zpe["S0_R0_eh"])

    tol = float(data.get("sanity_tolerance_ev", 0.01))
    ev = {k: v * EH_TO_EV for k, v in values_eh.items()}
    sanity: list[str] = []
    if ev["E_abs"] + tol < ev["E_ad"]:
        sanity.append("E_abs < E_ad")
    if ev["E_ad"] + tol < ev["E_em"]:
        sanity.append("E_ad < E_em")
    if ev["lambda_e"] < -tol:
        sanity.append("lambda_e < 0")
    if ev["lambda_g"] < -tol:
        sanity.append("lambda_g < 0")
    closure = ev["E_abs"] - ev["E_em"] - ev["lambda_e"] - ev["lambda_g"]
    if abs(closure) > tol:
        sanity.append(f"cycle closure error = {closure:+.6f} eV")

    out = {
        "method_gate": "PASS",
        "values": {
            k: {"eV": v, "nm": wavelength_nm(v) if k in {"E_abs", "E_em", "E_ad", "E00"} else None}
            for k, v in ev.items()
        },
        "cycle_closure_eV": closure,
        "sanity": "PASS" if not sanity else "WARNING",
        "sanity_issues": sanity,
    }
    print(json.dumps(out, indent=2))
    if sanity:
        raise SystemExit(1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {Path(sys.argv[0]).name} energy_cycle.json", file=sys.stderr)
        raise SystemExit(2)
    main(sys.argv[1])
