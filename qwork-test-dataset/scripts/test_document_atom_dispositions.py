#!/usr/bin/env python3
"""Validate hash-locked non-product document atom dispositions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.skill_root.resolve()
    policy_path = root / "references/document-atom-dispositions.yaml"
    if not policy_path.is_file():
        raise AssertionError("document atom disposition policy is missing")

    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    manifest = json.loads(
        (root / "data/datasets/source-acceptance.json").read_text(encoding="utf-8")
    )
    sources = {item["source_id"]: item for item in manifest["sources"]}
    requirements = manifest["requirements"]
    cases = {
        case["id"]: case
        for path in (root / "data/datasets/cases").glob("*.json")
        for case in [json.loads(path.read_text(encoding="utf-8"))]
    }

    configured_atoms: dict[tuple[str, str], dict] = {}
    for source_id, source_policy in policy["sources"].items():
        source = sources[source_id]
        if source["locator"] != source_policy["source_locator"]:
            raise AssertionError(f"disposition source locator drifted: {source_id}")
        if source["content_hash"] != source_policy["source_sha256"]:
            raise AssertionError(f"disposition source hash drifted: {source_id}")
        atoms = {item["locator"]: item for item in source["inventory"]["atoms"]}
        for entry in source_policy["atoms"]:
            key = (source_id, entry["atom_locator"])
            if key in configured_atoms:
                raise AssertionError(f"document atom disposition duplicated: {key}")
            atom = atoms[entry["atom_locator"]]
            if atom["extracted_value_hash"] != entry["atom_sha256"]:
                raise AssertionError(f"document atom disposition drifted: {key}")
            configured_atoms[key] = entry

    disposed_requirements = 0
    for requirement in requirements:
        atom_keys = {
            (item["source_id"], item["locator"])
            for item in requirement["source_atoms"]
        }
        configured = atom_keys & configured_atoms.keys()
        if not configured:
            continue
        if configured != atom_keys:
            raise AssertionError(
                f"canonical requirement is only partly disposed: {requirement['requirement_id']}"
            )
        reasons = {configured_atoms[key]["status_reason"] for key in configured}
        if len(reasons) != 1:
            raise AssertionError(
                f"canonical disposition reasons differ: {requirement['requirement_id']}"
            )
        if requirement["coverage_status"] != "not_applicable":
            raise AssertionError(
                f"disposed requirement is not not_applicable: {requirement['requirement_id']}"
            )
        if requirement.get("status_reason") != next(iter(reasons)):
            raise AssertionError(
                f"disposed requirement reason drifted: {requirement['requirement_id']}"
            )
        if requirement["case_ids"] or requirement["oracles"]:
            raise AssertionError(
                f"disposed requirement retained executable claims: {requirement['requirement_id']}"
            )
        if any(
            requirement["requirement_id"] in case["selection"]["requirement_ids"]
            for case in cases.values()
        ):
            raise AssertionError(
                f"disposed requirement retained a Case ledger: {requirement['requirement_id']}"
            )
        disposed_requirements += 1

    if disposed_requirements == 0:
        raise AssertionError("document atom disposition policy matched no requirements")
    print(f"document atom dispositions: {len(configured_atoms)} atoms / {disposed_requirements} requirements")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
