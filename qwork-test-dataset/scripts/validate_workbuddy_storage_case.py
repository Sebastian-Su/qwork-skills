#!/usr/bin/env python3
"""Validate one WorkBuddy storage Case against the closed-world migration dispositions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.skill_root.resolve()
    case_path = root / "data/datasets/cases" / f"{args.case_id}.json"
    disposition_path = root / "data/datasets/workbuddy-storage-dispositions.json"
    source_root = root / "data/sources/workbuddy-storage/inventory-sha256-e394d3122cf66681"
    case = load(case_path)
    manifest = load(disposition_path)
    inventory = load(source_root / "inventory.json")
    source_manifest = load(source_root / "manifest.json")

    errors: list[str] = []
    authority_keys = (
        "policy_version",
        "source_inventory_sha256",
        "source_canonical_sha256",
        "source_entry_count",
        "source_atom_count",
        "record_count",
        "rules",
        "counts",
        "records",
    )
    disposition_authority = {key: manifest.get(key) for key in authority_keys}
    if manifest.get("canonical_sha256") != canonical_sha256(disposition_authority):
        errors.append("disposition canonical authority hash drifted")
    if manifest.get("source_inventory_sha256") != source_manifest.get("inventory_sha256"):
        errors.append("disposition source inventory hash drifted")
    if manifest.get("source_entry_count") != len(inventory):
        errors.append("disposition source entry count drifted")
    if manifest.get("source_canonical_sha256") != canonical_sha256(inventory):
        errors.append("disposition canonical inventory bytes drifted")
    records = manifest.get("records")
    if not isinstance(records, list):
        raise ValueError("storage disposition records must be an array")
    by_atom: dict[str, dict[str, Any]] = {}
    for record in records:
        atom_id = str(record.get("atom_id") or "")
        if not atom_id or atom_id in by_atom:
            errors.append(f"missing or duplicate disposition atom: {atom_id!r}")
        by_atom[atom_id] = record

    required_atoms = sorted({
        str(atom_id)
        for requirement in case.get("derived_requirements", [])
        for atom_id in requirement.get("source_atom_ids", [])
    })
    if not required_atoms or not all(value.startswith("WORKBUDDY-STORAGE:") for value in required_atoms):
        errors.append("Case is not an exact WorkBuddy storage atom set")
    missing = sorted(set(required_atoms) - set(by_atom))
    if missing:
        errors.append(f"Case atoms missing dispositions: {missing[:20]}")

    results = []
    for atom_id in required_atoms:
        record = by_atom.get(atom_id)
        if not record:
            continue
        decision = str(record.get("decision_status") or "")
        implementation = str(record.get("implementation_status") or "")
        passed = decision == "resolved" and implementation in {"verified", "not-required"}
        if not passed:
            errors.append(
                f"{atom_id}: decision={decision or 'missing'} implementation={implementation or 'missing'} "
                f"next_action={record.get('next_action') or 'missing'}"
            )
        results.append({
            "atom_id": atom_id,
            "record_kind": record.get("record_kind"),
            "source_locator": record.get("source_locator"),
            "treatment": record.get("treatment"),
            "final_action": record.get("final_action"),
            "decision_status": decision,
            "implementation_status": implementation,
            "status": "pass" if passed else "fail",
        })
    payload = {
        "schema_version": 1,
        "case_id": args.case_id,
        "source_inventory_sha256": manifest.get("source_inventory_sha256"),
        "disposition_canonical_sha256": manifest.get("canonical_sha256"),
        "required_atom_count": len(required_atoms),
        "passed_atom_count": sum(item["status"] == "pass" for item in results),
        "failed_atom_count": sum(item["status"] == "fail" for item in results),
        "status": "pass" if not errors else "fail",
        "results": results,
        "errors": errors,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Keep release-gate logs bounded when a Case covers hundreds or thousands
    # of frozen inventory atoms. The complete result remains available at the
    # explicitly requested output path; stdout is only the runner summary.
    if args.output:
        print(json.dumps({
            key: value
            for key, value in payload.items()
            if key not in {"results", "errors"}
        } | {
            "error_count": len(errors),
            "first_error": errors[0] if errors else None,
        }, ensure_ascii=False))
    else:
        print(json.dumps(payload, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
        print(f"storage Case verifier unavailable: {error}", file=sys.stderr)
        raise SystemExit(2)
