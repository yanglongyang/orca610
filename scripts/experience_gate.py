#!/usr/bin/env python3
"""Persistent experience-memory gate for AutoORCA input generation and reuse."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path

EXPERIENCE_EXIT = 5
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES = ROOT / "knowledge" / "rules"
DEFAULT_TEMPLATES = ROOT / "templates"


class ExperienceError(RuntimeError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rules_dir() -> Path:
    return Path(os.environ.get("AUTOORCA_KNOWLEDGE_RULES", DEFAULT_RULES))


def template_dirs() -> list[Path]:
    values = [Path(os.environ.get("AUTOORCA_TEMPLATE_ARCHIVE", DEFAULT_TEMPLATES)), DEFAULT_TEMPLATES]
    seen: set[Path] = set(); result = []
    for value in values:
        value = value.resolve()
        if value not in seen and value.is_dir(): seen.add(value); result.append(value)
    return result


def load_rules() -> tuple[list[dict], str]:
    rules: list[dict] = []; combined = hashlib.sha256()
    for path in sorted(rules_dir().glob("*.json")):
        combined.update(path.read_bytes())
        rules.append(json.loads(path.read_text()))
    return rules, combined.hexdigest()


def calculation_type(text: str, supplied: str | None) -> str:
    metadata = re.search(r"^\s*#\s*@CALCULATION_TYPE:\s*(.+)$", text, re.I | re.M)
    return metadata.group(1).strip() if metadata else (supplied or "unspecified")


def matching_templates(calc_type: str) -> list[dict]:
    tokens = set(re.findall(r"[a-z0-9]+", calc_type.lower()))
    candidates: list[dict] = []
    for directory in template_dirs():
        for path in directory.rglob("*.inp"):
            text = path.read_text(errors="replace")
            status = re.search(r"^\s*#\s*@STATUS:\s*(.+)$", text, re.I | re.M)
            type_tag = re.search(r"^\s*#\s*@TYPE:\s*(.+)$", text, re.I | re.M)
            haystack = f"{path.name} {type_tag.group(1) if type_tag else ''}".lower()
            if tokens and not all(token in haystack for token in tokens if token not in {"vertical"}):
                continue
            candidates.append({"path": str(path), "status": status.group(1).strip() if status else "UNCLASSIFIED", "type": type_tag.group(1).strip() if type_tag else None})
    return candidates[:10]


def local_observations() -> list[str]:
    directory = Path(os.environ.get("AUTOORCA_EXPERIENCE_CASE_DIR", "experience/cases/failure"))
    if not directory.is_dir(): return []
    return [str(path) for path in sorted(directory.glob("*.json"), reverse=True)[:5]]


def load_manifest(path: Path) -> dict:
    if not path.exists(): return {"schema_version": 1, "inputs": {}}
    data = json.loads(path.read_text()); data.setdefault("schema_version", 1); data.setdefault("inputs", {}); return data


def save_manifest(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(data, indent=2) + "\n")


def evaluate(input_path: Path, calc_type: str | None) -> dict:
    input_path = input_path.resolve()
    if not input_path.is_file(): raise ExperienceError(f"input does not exist: {input_path}")
    text = input_path.read_text(errors="replace")
    rules, rules_hash = load_rules(); failures = []
    for rule in rules:
        for pattern in rule.get("forbidden_patterns", []):
            if re.search(pattern["regex"], text, re.I | re.M):
                failures.append({"rule_id": rule["id"], "evidence_level": rule.get("evidence_level"), "message": pattern["message"], "evidence": rule.get("evidence", []), "correct_pattern": rule.get("correct_pattern", {})})
    actual_type = calculation_type(text, calc_type)
    return {"input_path": str(input_path), "input_sha256": sha256(input_path), "calculation_type": actual_type, "rules_sha256": rules_hash, "consulted_rules": [rule["id"] for rule in rules], "template_candidates": matching_templates(actual_type), "local_observations": local_observations(), "failures": failures, "checked_at": now()}


def check(input_path: Path, manifest_path: Path, calc_type: str | None) -> dict:
    result = evaluate(input_path, calc_type)
    if result["failures"]: raise ExperienceError(render(result))
    manifest = load_manifest(manifest_path); manifest["inputs"][result["input_path"]] = result; save_manifest(manifest_path, manifest)
    return result


def require(input_path: Path, manifest_path: Path) -> dict:
    result = evaluate(input_path, None); manifest = load_manifest(manifest_path)
    record = manifest["inputs"].get(result["input_path"])
    if result["failures"]: raise ExperienceError(render(result))
    if not record or record.get("input_sha256") != result["input_sha256"] or record.get("rules_sha256") != result["rules_sha256"]:
        raise ExperienceError("EXPERIENCE_CHECK_REQUIRED: generate/review this input again so current rules and precedents are consulted.")
    return record


def render(result: dict) -> str:
    lines = ["EXPERIENCE PRE-GENERATION LOOKUP", f"Input: {result['input_path']}", f"Calculation type: {result['calculation_type']}", f"Rules consulted: {', '.join(result['consulted_rules']) or 'none'}"]
    if result["template_candidates"]:
        lines += ["Reference templates (syntax/protocol evidence, not execution approval):"] + [f"  - {item['path']} [{item['status']}]" for item in result["template_candidates"]]
    if result["local_observations"]:
        lines += ["Project-local observations (not generalized rules):"] + [f"  - {path}" for path in result["local_observations"]]
    if result["failures"]:
        lines.append("[EXPERIENCE-GATE] KNOWN INVALID PATTERN")
        for failure in result["failures"]:
            lines += [f"  - {failure['rule_id']} ({failure['evidence_level']}): {failure['message']}", f"    Evidence: {', '.join(failure['evidence'])}", f"    Correction: {failure['correct_pattern']}"]
    else:
        lines.append("[EXPERIENCE-GATE] PASS")
    return "\n".join(lines)


def record_failure(args: argparse.Namespace) -> Path:
    input_path, output_path = Path(args.input).resolve(), Path(args.output).resolve()
    output_text = output_path.read_text(errors="replace") if output_path.exists() else ""
    entry = {"recorded_at": now(), "evidence_level": "LOCAL_OBSERVATION", "input": str(input_path), "input_sha256": sha256(input_path) if input_path.exists() else None, "output": str(output_path), "matched_pattern": args.pattern or None, "output_tail": output_text[-8000:], "note": "Automatically captured project-local failure. It is not a reusable global rule until reviewed and promoted."}
    directory = Path(args.case_dir); directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"failure_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}_{input_path.stem}.json"
    path.write_text(json.dumps(entry, indent=2) + "\n"); return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "require", "record-failure"))
    parser.add_argument("input")
    parser.add_argument("--manifest", default="experience_checks.json")
    parser.add_argument("--calculation-type")
    parser.add_argument("--output")
    parser.add_argument("--pattern")
    parser.add_argument("--case-dir", default="experience/cases/failure")
    args = parser.parse_args()
    try:
        if args.command == "record-failure":
            if not args.output: raise ExperienceError("record-failure requires --output")
            print(f"[EXPERIENCE] local failure recorded: {record_failure(args)}")
        elif args.command == "check": print(render(check(Path(args.input), Path(args.manifest), args.calculation_type)))
        else: print("[EXPERIENCE-GATE] VERIFIED: " + require(Path(args.input), Path(args.manifest))["input_path"])
    except ExperienceError as exc:
        print(str(exc), file=sys.stderr); raise SystemExit(EXPERIENCE_EXIT)


if __name__ == "__main__": main()
