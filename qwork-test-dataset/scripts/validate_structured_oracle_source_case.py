#!/usr/bin/env python3
"""Verify one evidence-only structured Oracle Case against its frozen Git blob."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


SOURCE_PREFIX = "WORKBUDDY-ORACLE-5-3-5-"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_scalar_sha256(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def resolve_pointer(value: Any, pointer: str) -> Any:
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise ValueError(f"invalid JSON Pointer: {pointer}")
    current = value
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not token.isdigit() or int(token) >= len(current):
                raise KeyError(pointer)
            current = current[int(token)]
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            raise KeyError(pointer)
    return current


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--skill-root", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    root = args.skill_root.resolve()
    case = load(root / "data/datasets/cases" / f"{args.case_id}.json")
    manifest = load(root / "data/datasets/source-acceptance.json")
    source_by_id = {str(item["source_id"]): item for item in manifest["sources"]}
    atom_by_id = {
        str(atom["atom_id"]): atom
        for source in manifest["sources"]
        for atom in source["inventory"]["atoms"]
    }
    required_atoms = sorted({
        str(atom_id)
        for requirement in case.get("derived_requirements", [])
        for atom_id in requirement.get("source_atom_ids", [])
    })
    errors: list[str] = []
    source_ids = {
        atom_id.split(":PTR:", 1)[0]
        for atom_id in required_atoms
        if ":PTR:" in atom_id
    }
    if len(source_ids) != 1 or not all(value.startswith(SOURCE_PREFIX) for value in source_ids):
        errors.append("Case must bind evidence-only pointer atoms from exactly one structured Oracle source")
    source_id = next(iter(source_ids), "")
    source = source_by_id.get(source_id)
    if not source:
        errors.append(f"accepted source is missing: {source_id!r}")
        source = {}
    if not required_atoms:
        errors.append("Case has no structured source atoms")
    for atom_id in required_atoms:
        atom = atom_by_id.get(atom_id)
        if not atom:
            errors.append(f"source atom is missing: {atom_id}")
        elif atom.get("facet") != "evidence-provenance" or not atom.get("evidence_only"):
            errors.append(f"source atom is not evidence-only provenance: {atom_id}")

    locator = str(source.get("locator") or "")
    revision = str(source.get("revision") or "")
    expected_prefix = f"git:{revision}:"
    path = locator.removeprefix(expected_prefix) if locator.startswith(expected_prefix) else ""
    blob = b""
    if not revision or not path:
        errors.append("structured source has no exact Git revision/path locator")
    else:
        result = subprocess.run(
            ["git", "show", f"{revision}:{path}"],
            cwd=repo,
            capture_output=True,
        )
        if result.returncode:
            errors.append(f"frozen Git blob cannot be read: {revision}:{path}")
        else:
            blob = result.stdout
            actual_source_hash = "sha256:" + hashlib.sha256(blob).hexdigest()
            if actual_source_hash != source.get("content_hash"):
                errors.append("frozen Git blob hash differs from accepted source ledger")

    document: Any = None
    if blob:
        try:
            document = json.loads(blob)
        except json.JSONDecodeError as error:
            errors.append(f"structured source is not valid JSON: {error}")
    results: list[dict[str, Any]] = []
    if document is not None:
        for atom_id in required_atoms:
            atom = atom_by_id.get(atom_id)
            if not atom:
                continue
            locator_value = str(atom.get("locator") or "")
            pointer = locator_value.removeprefix("json-pointer:") if locator_value.startswith("json-pointer:") else ""
            status = "pass"
            actual_hash: str | None = None
            try:
                scalar = resolve_pointer(document, pointer)
                if isinstance(scalar, (dict, list)):
                    raise ValueError("pointer does not resolve to a scalar")
                actual_hash = canonical_scalar_sha256(scalar)
                if actual_hash != atom.get("extracted_value_hash"):
                    raise ValueError("canonical scalar hash differs")
            except (KeyError, ValueError) as error:
                status = "fail"
                errors.append(f"{atom_id}: {error}")
            results.append({
                "atom_id": atom_id,
                "json_pointer": pointer,
                "expected_value_sha256": atom.get("extracted_value_hash"),
                "actual_value_sha256": actual_hash,
                "status": status,
            })

    payload = {
        "schema_version": 1,
        "case_id": args.case_id,
        "source_id": source_id,
        "source_locator": locator,
        "source_content_sha256": source.get("content_hash"),
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
        print(json.dumps({
            key: value for key, value in payload.items() if key not in {"results", "errors"}
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
        print(f"structured Oracle source verifier unavailable: {error}", file=sys.stderr)
        raise SystemExit(2)
