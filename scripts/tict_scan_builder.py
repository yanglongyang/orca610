#!/usr/bin/env python3
"""Build a conservative ORCA 6.1 S1 dihedral-scan input and classify evidence."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from input_review import ReviewError, _render, review
from experience_gate import ExperienceError, check as experience_check, detected_orca_version, lookup as experience_lookup, render as render_experience


class TictInputError(ValueError):
    pass


def classify_tict(evidence: dict) -> str:
    """Return a conservative TICT label; geometry alone can never support TICT."""
    if not evidence.get("geometry_compared"):
        return "TICT_UNRESOLVED"
    if not evidence.get("substantial_twist"):
        return "TICT_NOT_SUPPORTED"
    electronic = bool(evidence.get("ct_character_increases"))
    oscillator = bool(evidence.get("oscillator_strength_reduces"))
    energetic = bool(evidence.get("twisted_low_energy_region"))
    solvent = bool(evidence.get("polar_state_solvent_stabilization"))
    pathway = bool(evidence.get("plausible_fc_to_twisted_path"))
    support_count = sum((electronic, oscillator, energetic, solvent, pathway))
    if electronic and energetic and support_count >= 3:
        return "TICT_SUPPORTED"
    if support_count >= 1:
        return "TICT_POSSIBLE"
    return "TICT_UNRESOLVED"


def xyz_atom_count(path: str) -> int:
    try:
        first_line = next(line for line in Path(path).read_text().splitlines() if line.strip())
        count = int(first_line.strip())
    except (OSError, StopIteration, ValueError) as exc:
        raise TictInputError(f"cannot read XYZ atom count from {path!r}") from exc
    if count < 4:
        raise TictInputError("XYZ must contain at least four atoms for a dihedral scan")
    return count


def build_input(config: dict) -> str:
    required = ("xyz", "charge", "multiplicity", "dihedral", "scan", "method")
    missing = [key for key in required if config.get(key) in (None, "")]
    if missing:
        raise TictInputError("missing fields: " + ", ".join(missing))
    dihedral = config["dihedral"]
    scan = config["scan"]
    if len(dihedral) != 4 or not isinstance(scan, dict):
        raise TictInputError("dihedral needs four atoms and scan must be an object")
    for key in ("start_deg", "end_deg", "n_steps"):
        if scan.get(key) in (None, ""):
            raise TictInputError(f"scan lacks {key}")
    if int(scan["n_steps"]) < 1:
        raise TictInputError("scan.n_steps must be at least one")
    base = int(config.get("atom_index_base", 1))
    if base not in (0, 1):
        raise TictInputError("atom_index_base must be 0 or 1")
    atoms = [int(atom) - base for atom in dihedral]
    if min(atoms) < 0:
        raise TictInputError("atom indices are invalid for atom_index_base")
    atom_count = xyz_atom_count(config["xyz"])
    if max(atoms) >= atom_count:
        raise TictInputError(
            f"dihedral atom index {max(atoms) + base} exceeds XYZ atom count {atom_count}"
        )
    method = config["method"]
    for key in ("functional", "basis", "dispersion", "solvent", "nroots", "iroot", "tda"):
        if method.get(key) in (None, ""):
            raise TictInputError(f"method lacks {key}")
    ntostates = method.get("nto_states", method["iroot"])
    ntothresh = method.get("nto_threshold", "1e-4")
    cpcmeq = str(method.get("cpcmeq", True)).lower()
    solvent_regime = method.get("solvent_regime", "equilibrium")
    start, end, steps = scan["start_deg"], scan["end_deg"], scan["n_steps"]
    return "\n".join((
        "# @AUTOORCA: 3.4.5",
        f"# @ORCA: {detected_orca_version()}",
        "# @CALCULATION_TYPE: tict_scan",
        "# @METHOD_FAMILY: TD-DFT",
        f"# @FUNCTIONAL: {method['functional']}",
        f"# @BASIS: {method['basis']}",
        f"# @DISPERSION: {method['dispersion']}",
        f"# @SOLVENT: {method['solvent']}",
        f"# @SOLVENT_REGIME: {solvent_regime}",
        f"# @GEOMETRY_SOURCE: {config['xyz']}",
        "# AutoORCA v3.4.5 TICT diagnostic: inspect state identity/NTOs at every scan point.",
        f"! Opt {method['functional']} RIJCOSX {method['basis']} {method['dispersion']} {method['solvent']} TightScf",
        "%geom",
        "  Scan D " + " ".join(map(str, atoms)) + f" = {start}, {end}, {steps} end",
        "end",
        "%tddft",
        f"  nroots {method['nroots']}",
        f"  iroot {method['iroot']}",
        f"  tda {str(method['tda']).lower()}",
        f"  followiroot {str(method.get('followiroot', True)).lower()}",
        f"  cpcmeq {cpcmeq}",
        "  donto true",
        f"  ntostates {ntostates}",
        f"  ntothresh {ntothresh}",
        "end",
        f"* xyzfile {config['charge']} {config['multiplicity']} \"{config['xyz']}\"",
        "",
    ))


def main(config_path: str, output_path: str, manifest_path: str | None = None) -> None:
    try:
        output = build_input(json.loads(Path(config_path).read_text()))
    except (OSError, json.JSONDecodeError, TictInputError) as exc:
        print(f"[TICT] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
    path = Path(output_path)
    try:
        print(render_experience(experience_lookup("tict_scan")))
        path.write_text(output)
        manifest = Path(manifest_path or os.environ.get("INPUT_REVIEW_FILE", path.parent / "input_reviews.json"))
        experience_manifest = Path(os.environ.get("EXPERIENCE_GATE_FILE", path.parent / "experience_checks.json"))
        experience_check(path, experience_manifest, "tict_scan")
        record = review(path, manifest, "tict_scan")
    except (ReviewError, ExperienceError) as exc:
        print(f"[TICT] ERROR: unable to register pre-run checks: {exc}", file=sys.stderr)
        raise SystemExit(2)
    print(_render(record))
    print(f"Wrote {output_path} — REVIEW_REQUIRED; no ORCA job was started.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config")
    parser.add_argument("output")
    parser.add_argument("--manifest", help="use the workflow's INPUT_REVIEW_FILE")
    args = parser.parse_args()
    main(args.config, args.output, args.manifest)
