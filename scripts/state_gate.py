#!/usr/bin/env python3
"""Human state-selection and post-optimization state-identity gates for AutoORCA."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

GATE_EXIT = 4


class StateGateError(RuntimeError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def digest(path: Path) -> str:
    if not path.is_file():
        raise StateGateError(f"required file is missing: {path}")
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normal_output(path: Path) -> None:
    if "ORCA TERMINATED NORMALLY" not in path.read_text(errors="replace"):
        raise StateGateError(f"output is not a normal ORCA completion: {path}")


def nroots(input_path: Path) -> int:
    text = input_path.read_text(errors="replace")
    block = re.search(r"%tddft\b(.*?)\bend\b", text, re.I | re.S)
    match = re.search(r"^\s*nroots\s+(\d+)", block.group(1) if block else "", re.I | re.M)
    if not match:
        raise StateGateError(f"cannot validate state root: TDDFT nroots is missing in {input_path}")
    return int(match.group(1))


def load(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "species": {}}
    data = json.loads(path.read_text())
    data.setdefault("schema_version", 1); data.setdefault("species", {})
    return data


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def fingerprints(*paths: Path) -> dict[str, dict[str, str]]:
    return {str(path.resolve()): {"sha256": digest(path.resolve())} for path in paths}


def select(args: argparse.Namespace) -> dict:
    vertical_input, vertical_output = Path(args.vertical_input), Path(args.vertical_output)
    normal_output(vertical_output)
    root_count = nroots(vertical_input)
    if args.root < 1 or args.root > root_count:
        raise StateGateError(f"selected root {args.root} is outside vertical TDDFT nroots=1..{root_count}")
    data = load(Path(args.manifest))
    entry = data["species"].setdefault(args.species, {})
    entry["selection"] = {
        "status": "STATE_SELECTION_APPROVED", "selected_root": args.root,
        "state_character": args.state_character,
        "selection_basis": args.selection_basis,
        "approved_by": "human", "approved_at": now(),
        "vertical_nroots": root_count,
        "vertical_fingerprints": fingerprints(vertical_input, vertical_output),
    }
    save(Path(args.manifest), data)
    return entry["selection"]


def confirm(args: argparse.Namespace) -> dict:
    opt_input, opt_output = Path(args.opt_input), Path(args.opt_output)
    normal_output(opt_output)
    data = load(Path(args.manifest))
    entry = data["species"].setdefault(args.species, {})
    selection = entry.get("selection")
    if not selection or selection.get("status") != "STATE_SELECTION_APPROVED":
        raise StateGateError("state selection is missing; select the R0 target state first")
    root_count = nroots(opt_input)
    if args.final_root < 1 or args.final_root > root_count:
        raise StateGateError(f"confirmed final root {args.final_root} is outside S1 optimization TDDFT nroots=1..{root_count}")
    entry["identity"] = {
        "status": "STATE_IDENTITY_MATCH", "final_root": args.final_root,
        "state_character": args.state_character,
        "evidence": args.evidence, "approved_by": "human", "approved_at": now(),
        "selection_root": selection["selected_root"],
        "opt_nroots": root_count,
        "opt_fingerprints": fingerprints(opt_input, opt_output),
    }
    save(Path(args.manifest), data)
    return entry["identity"]


def require_selection(args: argparse.Namespace) -> dict:
    data = load(Path(args.manifest)); entry = data["species"].get(args.species, {})
    selection = entry.get("selection")
    expected = fingerprints(Path(args.vertical_input), Path(args.vertical_output))
    if not selection or selection.get("status") != "STATE_SELECTION_APPROVED" or selection.get("vertical_fingerprints") != expected:
        raise StateGateError("STATE_SELECTION_REQUIRED: inspect R0 roots/NTOs/oscillator strengths, then explicitly select one state")
    return selection


def require_identity(args: argparse.Namespace) -> dict:
    data = load(Path(args.manifest)); entry = data["species"].get(args.species, {})
    identity = entry.get("identity")
    expected = fingerprints(Path(args.opt_input), Path(args.opt_output))
    if not identity or identity.get("status") != "STATE_IDENTITY_MATCH" or identity.get("opt_fingerprints") != expected:
        raise StateGateError("STATE_IDENTITY_REQUIRED: inspect final S1 state/NTO evidence, then explicitly confirm identity")
    return identity


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("select", "require-selection", "confirm", "require-identity"))
    parser.add_argument("--manifest", default="state_gates.json")
    parser.add_argument("--species", required=True)
    parser.add_argument("--vertical-input")
    parser.add_argument("--vertical-output")
    parser.add_argument("--root", type=int)
    parser.add_argument("--state-character")
    parser.add_argument("--selection-basis", action="append", default=[])
    parser.add_argument("--opt-input")
    parser.add_argument("--opt-output")
    parser.add_argument("--final-root", type=int)
    parser.add_argument("--evidence", action="append", default=[])
    args = parser.parse_args()
    try:
        if args.command == "select":
            if not args.root or not args.state_character or not args.selection_basis: raise StateGateError("select requires --root, --state-character, and at least one --selection-basis")
            result = select(args)
        elif args.command == "require-selection": result = require_selection(args)
        elif args.command == "confirm":
            if not args.final_root or not args.state_character or not args.evidence: raise StateGateError("confirm requires --final-root, --state-character, and at least one --evidence")
            result = confirm(args)
        else: result = require_identity(args)
        print(json.dumps(result, indent=2))
    except StateGateError as exc:
        print(f"[STATE-GATE] {exc}", file=sys.stderr)
        raise SystemExit(GATE_EXIT)


if __name__ == "__main__":
    main()
