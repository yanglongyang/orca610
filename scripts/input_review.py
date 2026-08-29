#!/usr/bin/env python3
"""Hash-bound, human-in-the-loop review gate for generated ORCA inputs.

This module never approves an input.  ``review`` records a REVIEW_REQUIRED
manifest and prints both a semantic summary and the complete raw input;
``require`` is used by run_orca as the final execution boundary.
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import sys
from pathlib import Path

REVIEW_REQUIRED_EXIT = 3
DEPENDENCY_PATTERNS = (
    ("xyzfile", re.compile(r"^\s*\*\s+xyzfile\s+\S+\s+\S+\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))", re.I)),
    ("moinp", re.compile(r"^\s*%?moinp\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))", re.I)),
    ("gshessian", re.compile(r"^\s*gshessian\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))", re.I)),
    ("eshessian", re.compile(r"^\s*eshessian\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))", re.I)),
)


class ReviewError(RuntimeError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _capture(match: re.Match[str]) -> str:
    return next(value for value in match.groups() if value is not None).strip()


def dependencies(input_path: Path, text: str) -> list[dict]:
    found: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for kind, pattern in DEPENDENCY_PATTERNS:
        for line in text.splitlines():
            match = pattern.match(line)
            if not match:
                continue
            reference = _capture(match)
            resolved = (input_path.parent / reference).resolve() if not Path(reference).is_absolute() else Path(reference)
            key = (kind, str(resolved))
            if key in seen:
                continue
            seen.add(key)
            exists = resolved.is_file()
            found.append({
                "kind": kind,
                "reference": reference,
                "resolved_path": str(resolved),
                "sha256": sha256(resolved) if exists else None,
                "exists": exists,
            })
    return found


def _block(text: str, name: str) -> str:
    match = re.search(rf"%{re.escape(name)}\b(.*?)(?:^\s*end\s*$)", text, re.I | re.M | re.S)
    return match.group(1) if match else ""


def _value(block: str, key: str) -> str | None:
    match = re.search(rf"^\s*{re.escape(key)}\s+([^\s#]+)", block, re.I | re.M)
    return match.group(1) if match else None


def _inline_atom_count(text: str) -> int | None:
    match = re.search(r"^\s*\*\s+xyz\s+\S+\s+\S+\s*$(.*?)^\s*\*\s*$", text, re.I | re.M | re.S)
    if not match:
        return None
    return len([line for line in match.group(1).splitlines() if line.strip()])


def _method_details(method_line: str | None) -> dict:
    """Extract the protocol fields AutoORCA normally puts on the ! line.

    The raw method line remains authoritative; these values exist solely to
    make changes in the functional, basis, and dispersion visible in review.
    """
    tokens = (method_line or "").lstrip("!").split()
    basis = next((token for token in tokens if re.match(r"(?:ma-)?(?:def2|cc-p|aug-|6-)" , token, re.I)), None)
    dispersion = next((token for token in tokens if re.fullmatch(r"D(?:3(?:BJ|ZERO)?|4)", token, re.I)), None)
    functional = next((token for token in tokens if token not in {basis, dispersion} and not re.match(r"(?:TDDFT|TD-DFT|CIS|Opt|Freq|Tight|CPCM|SMD|ESD|RI|Grid|SlowConv|NoAutoStart)", token, re.I)), None)
    return {"functional": functional, "basis": basis, "dispersion": dispersion}


def _metadata(text: str) -> dict[str, str]:
    return {match.group(1).lower(): match.group(2).strip() for match in re.finditer(r"^\s*#\s*@([A-Z0-9_]+):\s*(.*?)\s*$", text, re.I | re.M)}


def _state_marker(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(?:^|[_./-])(s[01])(?:[_./-]|$)", value, re.I)
    return match.group(1).upper() if match else None


def _xyz_atom_count(dep_list: list[dict]) -> int | None:
    xyz = next((item for item in dep_list if item["kind"] == "xyzfile" and item["exists"]), None)
    if not xyz:
        return None
    try:
        return int(Path(xyz["resolved_path"]).read_text().splitlines()[0].strip())
    except (OSError, IndexError, ValueError):
        return None


def semantic_summary(input_path: Path, text: str, dep_list: list[dict], calculation_type: str | None) -> dict:
    method_line = next((line.strip() for line in text.splitlines() if line.lstrip().startswith("!")), None)
    geometry = re.search(r"^\s*\*\s+(xyz|xyzfile)\s+(\S+)\s+(\S+)", text, re.I | re.M)
    tddft, esd, pal = _block(text, "tddft"), _block(text, "esd"), _block(text, "pal")
    maxcore = re.search(r"^\s*%maxcore\s+(\S+)", text, re.I | re.M)
    solvent = re.search(r"\b(?:CPCM|SMD)\([^)]*\)", text, re.I)
    metadata = _metadata(text)
    summary: dict = {
        "input_file": str(input_path), "calculation_type": metadata.get("calculation_type", calculation_type),
        "purpose": next((line[1:].strip() for line in text.splitlines() if line.startswith("#") and not line.lstrip().startswith("# @")), None),
        "method_line": method_line, "geometry_source": "inline xyz" if geometry and geometry.group(1).lower() == "xyz" else None,
        "charge": geometry.group(2) if geometry else None,
        "multiplicity": geometry.group(3) if geometry else None,
        "atom_count": _inline_atom_count(text) or _xyz_atom_count(dep_list),
        "solvent": solvent.group(0) if solvent else None,
        "optimization": bool(re.search(r"\bOpt\b", text, re.I)),
        "frequency": bool(re.search(r"\bFreq\b", text, re.I)),
        "tightopt": bool(re.search(r"\bTightOpt\b", text, re.I)),
        "nprocs": _value(pal, "nprocs"), "maxcore_mb": maxcore.group(1) if maxcore else None,
        "tddft": {key: _value(tddft, key) for key in ("nroots", "iroot", "tda", "followiroot", "donto", "ntostates", "ntothresh", "cpcmeq") if _value(tddft, key) is not None},
        "esd": {key: _value(esd, key) for key in ("gshessian", "eshessian", "usej") if _value(esd, key) is not None},
    }
    summary.update(_method_details(method_line))
    for field in ("functional", "basis", "dispersion", "method_family", "solvent", "solvent_regime", "geometry_source", "target_state"):
        if metadata.get(field):
            summary[field] = metadata[field]
    summary["metadata"] = metadata
    summary["esd"]["nacme"] = _value(tddft, "nacme")
    summary["esd"]["etf"] = _value(tddft, "etf")
    if summary["geometry_source"] is None:
        xyz = next((item["reference"] for item in dep_list if item["kind"] == "xyzfile"), None)
        summary["geometry_source"] = xyz
    return summary


def warnings(summary: dict, dep_list: list[dict]) -> list[str]:
    result = [f"missing dependency: {item['reference']} ({item['kind']})" for item in dep_list if not item["exists"]]
    td = summary["tddft"]
    if td.get("tda", "").lower() == "true":
        result.append("TDA true: confirm that the TDA approximation is intended.")
    if td.get("cpcmeq") is not None:
        result.append(f"CPCMEQ {td['cpcmeq']}: confirm the excited-state solvent regime is intended.")
    elif summary.get("method_family", "").upper() == "TD-DFT":
        result.append("TD-DFT solvent regime is implicit: write CPCMEQ explicitly for AutoORCA provenance.")
    if summary["optimization"] and td and td.get("followiroot", "").lower() != "true":
        result.append("excited-state optimization without FOLLOWIROOT true.")
    if summary.get("calculation_type") == "s1_opt" and not summary.get("target_state"):
        result.append("AutoORCA S1 optimization lacks an approved R0 target-state provenance tag.")
    try:
        if td.get("iroot") and td.get("nroots") and int(td["iroot"]) > int(td["nroots"]):
            result.append("IROOT exceeds NRoots.")
    except ValueError:
        result.append("unable to compare IROOT and NRoots.")
    if td.get("iroot") and td.get("ntostates"):
        roots = {value.strip() for value in td["ntostates"].split(",")}
        if td["iroot"] not in roots:
            result.append("NTOStates does not include the target IROOT.")
    if summary["optimization"] and (calculation_type := summary.get("calculation_type")):
        if "optfreq" in calculation_type.lower() and not summary["frequency"]:
            result.append("expected frequency request is missing for an OptFreq calculation.")
    if "ESD(IC)" in (summary.get("method_line") or "") and (not summary["esd"].get("gshessian") or not summary["esd"].get("eshessian")):
        result.append("ESD(IC) input lacks an explicit GS or ES Hessian.")
    geometry_state = _state_marker(summary.get("geometry_source"))
    expected_state = {"vertical_absorption": "S0", "s1_opt": "S0", "s1_freq": "S1", "vertical_emission": "S1", "esd_ic": "S0"}.get(summary.get("calculation_type"))
    if geometry_state and expected_state and geometry_state != expected_state:
        result.append(f"geometry provenance appears to be {geometry_state}, but {summary['calculation_type']} normally uses {expected_state} geometry.")
    gs_state = _state_marker(summary["esd"].get("gshessian"))
    if geometry_state and gs_state and geometry_state != gs_state:
        result.append(f"geometry ({geometry_state}) and GSHessian ({gs_state}) provenance markers differ.")
    if os.environ.get("AUTOORCA_ALLOW_MIXED_HESSIANS", "false").lower() == "true":
        result.append("mixed-Hessian approximation is enabled; verify and document its scientific justification.")
    if summary["maxcore_mb"] and summary["nprocs"]:
        try:
            requested = float(summary["maxcore_mb"]) * float(summary["nprocs"])
            summary["estimated_maxcore_times_nprocs_mb"] = requested
            ram = float(os.environ.get("AUTOORCA_RAM_MB", "0"))
            if ram and requested >= ram * 0.9:
                result.append("MaxCore × nprocs is at least 90% of AUTOORCA_RAM_MB.")
        except ValueError:
            result.append("unable to estimate MaxCore × nprocs.")
    return result


def protocol_warnings(manifest: dict, current: dict) -> list[str]:
    """Flag changes relative to earlier reviewed project inputs, once each."""
    summary, key = current["summary"], current["input_path"]
    result: list[str] = []
    for other_key, other in manifest.get("inputs", {}).items():
        if other_key == key or not isinstance(other, dict):
            continue
        prior = other.get("summary", {})
        changed = [field for field in ("functional", "basis", "dispersion") if summary.get(field) and prior.get(field) and summary[field] != prior[field]]
        if changed:
            result.append(f"project protocol differs from {Path(other_key).name}: {', '.join(changed)} changed; confirm this is intentional.")
            break
    for other_key, other in manifest.get("inputs", {}).items():
        if other_key == key or not isinstance(other, dict):
            continue
        prior = other.get("summary", {})
        changed = [field for field in ("charge", "multiplicity") if summary.get(field) is not None and prior.get(field) is not None and summary[field] != prior[field]]
        if changed:
            result.append(f"charge/multiplicity differs from {Path(other_key).name}: {', '.join(changed)} changed; confirm the electronic state.")
            break
    return result


def snapshot(input_path: Path, calculation_type: str | None) -> dict:
    input_path = input_path.resolve()
    if not input_path.is_file():
        raise ReviewError(f"input does not exist: {input_path}")
    text = input_path.read_text()
    dep_list = dependencies(input_path, text)
    summary = semantic_summary(input_path, text, dep_list, calculation_type)
    return {"input_path": str(input_path), "input_sha256": sha256(input_path), "dependencies": dep_list, "input_text": text, "summary": summary, "warnings": warnings(summary, dep_list)}


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "inputs": {}}
    data = json.loads(path.read_text())
    data.setdefault("schema_version", 1); data.setdefault("inputs", {})
    return data


def save_manifest(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def resolve_manifest(input_path: Path, supplied: str | None) -> Path:
    """Keep standalone review, approval, and execution on one input-scoped manifest."""
    if supplied:
        return Path(supplied)
    if os.environ.get("INPUT_REVIEW_FILE"):
        return Path(os.environ["INPUT_REVIEW_FILE"])
    return input_path.resolve().parent / "input_reviews.json"


def same_snapshot(record: dict, current: dict) -> bool:
    return record.get("input_sha256") == current["input_sha256"] and record.get("dependencies") == current["dependencies"]


def _render(record: dict, include_raw: bool = True) -> str:
    summary = record["summary"]
    lines = ["PRE-RUN INPUT REVIEW", "", f"Status: {record['status']}", f"File: {summary['input_file']}", f"Purpose: {summary.get('purpose') or summary.get('calculation_type') or 'not recorded'}", f"Method: {summary.get('method_line')}", f"Geometry: {summary.get('geometry_source')} | atoms={summary.get('atom_count')} | charge={summary.get('charge')} multiplicity={summary.get('multiplicity')}"]
    if summary.get("solvent"):
        lines.append(f"Solvent: {summary['solvent']}")
    if summary.get("method_family") or summary.get("solvent_regime") or summary.get("target_state"):
        lines.append(f"Provenance: family={summary.get('method_family')} solvent_regime={summary.get('solvent_regime')} target_state={summary.get('target_state')}")
    lines.append(f"Geometry task: Opt={summary['optimization']} Freq={summary['frequency']} TightOpt={summary['tightopt']}")
    if summary["tddft"]:
        lines.append("TD-DFT: " + ", ".join(f"{k}={v}" for k, v in summary["tddft"].items()))
    if summary["esd"]:
        lines.append("ESD: " + ", ".join(f"{k}={v}" for k, v in summary["esd"].items() if v is not None))
    lines.append(f"Resources: nprocs={summary.get('nprocs')} MaxCore(MB)={summary.get('maxcore_mb')} estimated product(MB)={summary.get('estimated_maxcore_times_nprocs_mb')}")
    lines += [f"Input SHA256: {record['input_sha256']}", "Dependencies:"]
    lines += [f"  - {dep['kind']}: {dep['reference']} | sha256={dep['sha256']} | exists={dep['exists']}" for dep in record["dependencies"]] or ["  - none"]
    lines += ["Warnings:"] + [f"  - {item}" for item in record["warnings"]] if record["warnings"] else ["Warnings: none"]
    if record.get("execution_provenance") == "IMPORTED_UNREVIEWED":
        lines.append("Execution provenance: IMPORTED_UNREVIEWED — this review cannot establish that approval existed before the completed run.")
    if include_raw:
        lines += ["", "--- COMPLETE RAW INPUT ---", record["input_text"], "--- END RAW INPUT ---"]
    return "\n".join(lines)


def review(input_path: Path, manifest_path: Path, calculation_type: str | None, existing_completed_output: bool = False) -> dict:
    current = snapshot(input_path, calculation_type)
    manifest = load_manifest(manifest_path)
    current["warnings"].extend(protocol_warnings(manifest, current))
    key = current["input_path"]
    previous = manifest["inputs"].get(key)
    if previous and previous.get("status") == "APPROVED" and same_snapshot(previous, current):
        return previous
    history = list(previous.get("history", [])) if previous else []
    if previous and not same_snapshot(previous, current):
        diff = "".join(difflib.unified_diff(previous.get("input_text", "").splitlines(True), current["input_text"].splitlines(True), fromfile="previous reviewed input", tofile="current input"))
        history.append({"status": "INVALIDATED", "at": now(), "reason": "input or dependency hash changed", "diff": diff})
    record = {**current, "status": "REVIEW_REQUIRED", "reviewed_at": now(), "calculation_type": calculation_type, "history": history}
    if existing_completed_output:
        record["execution_provenance"] = "IMPORTED_UNREVIEWED"
        record["import_note"] = "A completed output existed before this v3.2 review record; approval is review-for-use, not evidence of pre-run approval."
    manifest["inputs"][key] = record
    save_manifest(manifest_path, manifest)
    return record


def require(input_path: Path, manifest_path: Path, existing_completed_output: bool = False) -> dict:
    manifest = load_manifest(manifest_path)
    key = str(input_path.resolve())
    previous = manifest["inputs"].get(key)
    current = snapshot(input_path, previous.get("calculation_type") if previous else None)
    if previous and previous.get("status") in {"APPROVED", "COMPLETED"} and same_snapshot(previous, current):
        return previous
    record = review(input_path, manifest_path, previous.get("calculation_type") if previous else None, existing_completed_output)
    raise ReviewError(_render(record))


def mark_state(input_path: Path, manifest_path: Path, state: str) -> dict:
    """Internal lifecycle transition used after hash-bound approval succeeds."""
    if state not in {"RUNNING", "COMPLETED"}:
        raise ReviewError(f"unsupported lifecycle state {state!r}")
    manifest = load_manifest(manifest_path)
    key = str(input_path.resolve())
    record = manifest["inputs"].get(key)
    current = snapshot(input_path, record.get("calculation_type") if record else None)
    allowed = {"APPROVED", "COMPLETED"} if state == "RUNNING" else {"RUNNING"}
    if not record or record.get("status") not in allowed or not same_snapshot(record, current):
        raise ReviewError(f"cannot mark {state}: approval is absent, stale, or in the wrong lifecycle state")
    record.update(current)
    record["status"] = state
    record[f"{state.lower()}_at"] = now()
    manifest["inputs"][key] = record
    save_manifest(manifest_path, manifest)
    return record


def reject(input_path: Path, manifest_path: Path) -> dict:
    """Record an explicit human rejection without granting execution rights."""
    manifest = load_manifest(manifest_path)
    key = str(input_path.resolve())
    record = manifest["inputs"].get(key)
    current = snapshot(input_path, record.get("calculation_type") if record else None)
    if not record or record.get("status") != "REVIEW_REQUIRED" or not same_snapshot(record, current):
        raise ReviewError("input is not the current REVIEW_REQUIRED version and cannot be rejected")
    record["status"] = "REJECTED"
    record["rejected_at"] = now()
    record["rejected_by"] = "human"
    manifest["inputs"][key] = record
    save_manifest(manifest_path, manifest)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("review", "require", "reject", "mark-running", "mark-completed"))
    parser.add_argument("input")
    parser.add_argument("--manifest", help="defaults to INPUT_REVIEW_FILE or input directory")
    parser.add_argument("--calculation-type")
    parser.add_argument("--existing-completed-output", action="store_true", help="record an existing completed output as imported rather than pre-approved")
    args = parser.parse_args()
    try:
        path = Path(args.input); manifest = resolve_manifest(path, args.manifest)
        if args.command == "review":
            print(_render(review(path, manifest, args.calculation_type, args.existing_completed_output)))
        elif args.command == "require":
            record = require(path, manifest, args.existing_completed_output)
            print(f"[REVIEW-GATE] APPROVAL VERIFIED: {record['input_path']}")
        elif args.command == "reject":
            record = reject(path, manifest)
            print(f"[REVIEW-GATE] REJECTED: {record['input_path']}")
        else:
            state = "RUNNING" if args.command == "mark-running" else "COMPLETED"
            record = mark_state(path, manifest, state)
            print(f"[REVIEW-GATE] {record['status']}: {record['input_path']}")
    except ReviewError as exc:
        print("[REVIEW-GATE] REVIEW_REQUIRED", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        raise SystemExit(REVIEW_REQUIRED_EXIT)


if __name__ == "__main__":
    main()
