#!/usr/bin/env python3
"""Record approval only after a human explicitly approved a displayed review."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from input_review import ReviewError, load_manifest, now, same_snapshot, save_manifest, snapshot


def approve(input_path: Path, manifest_path: Path) -> dict:
    manifest = load_manifest(manifest_path)
    key = str(input_path.resolve())
    record = manifest["inputs"].get(key)
    current = snapshot(input_path, record.get("calculation_type") if record else None)
    if not record or record.get("status") != "REVIEW_REQUIRED":
        raise ReviewError("input is not in REVIEW_REQUIRED state; run input_review.py review first")
    if not same_snapshot(record, current):
        raise ReviewError("input or dependency changed since review; run input_review.py review again")
    if any(not item["exists"] for item in current["dependencies"]):
        raise ReviewError("cannot approve while an external dependency is missing")
    record.update(current)
    record.update({"status": "APPROVED", "approved_at": now(), "approved_by": "human"})
    manifest["inputs"][current["input_path"]] = record
    save_manifest(manifest_path, manifest)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--manifest", default="input_reviews.json")
    args = parser.parse_args()
    try:
        record = approve(Path(args.input), Path(args.manifest))
    except ReviewError as exc:
        print(f"[REVIEW-GATE] APPROVAL REFUSED: {exc}", file=sys.stderr)
        raise SystemExit(2)
    print(f"[REVIEW-GATE] APPROVED: {record['input_path']}")


if __name__ == "__main__":
    main()
