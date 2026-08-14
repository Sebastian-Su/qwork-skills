#!/usr/bin/env python3
"""Validate reviewed document atoms that require multiple executable Cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import yaml


def sha256_source(root: Path, revision: str, path: str) -> str:
    prefix = "skill://qwork-test-dataset/"
    if path.startswith(prefix):
        return "sha256:" + hashlib.sha256(
            (root / path.removeprefix(prefix)).read_bytes()
        ).hexdigest()
    blob = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        check=True,
        capture_output=True,
    ).stdout
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.skill_root.resolve()
    coverage_path = root / "references/document-case-coverage-map.yaml"
    if not coverage_path.is_file():
        raise AssertionError("document Case Coverage Map is missing")

    coverage = yaml.safe_load(coverage_path.read_text(encoding="utf-8"))
    target_registry = coverage["target_registry"]
    spec_registry = coverage["spec_registry"]
    manifest = json.loads(
        (root / "data/datasets/source-acceptance.json").read_text(encoding="utf-8")
    )
    sources = {item["source_id"]: item for item in manifest["sources"]}
    requirements = manifest["requirements"]
    case_dir = root / "data/datasets/cases"
    cases = {
        case["id"]: case
        for path in case_dir.glob("*.json")
        for case in [json.loads(path.read_text(encoding="utf-8"))]
    }

    mapped_atoms: set[tuple[str, str]] = set()
    mapped_requirements: set[str] = set()
    mapped_targets = 0
    for source_id, source_map in coverage["sources"].items():
        source = sources[source_id]
        if source["locator"] != source_map["source_locator"]:
            raise AssertionError(f"source locator drifted: {source_id}")
        if source["content_hash"] != source_map["source_sha256"]:
            raise AssertionError(f"source hash drifted: {source_id}")
        atoms = {
            atom["locator"]: atom for atom in source["inventory"]["atoms"]
        }
        for mapping in source_map["mappings"]:
            locator = mapping["atom_locator"]
            atom_key = (source_id, locator)
            if atom_key in mapped_atoms:
                raise AssertionError(f"document atom mapped twice: {atom_key}")
            mapped_atoms.add(atom_key)
            atom = atoms[locator]
            if atom["extracted_value_hash"] != mapping["atom_sha256"]:
                raise AssertionError(f"document atom hash drifted: {atom_key}")

            matching_requirements = [
                item
                for item in requirements
                if any(
                    source_atom["source_id"] == source_id
                    and source_atom["locator"] == locator
                    for source_atom in item["source_atoms"]
                )
            ]
            if len(matching_requirements) != 1:
                raise AssertionError(
                    f"document atom must resolve to one requirement: {atom_key}"
                )
            requirement = matching_requirements[0]
            requirement_id = requirement["requirement_id"]
            if requirement_id in mapped_requirements:
                raise AssertionError(
                    f"canonical requirement mapped twice: {requirement_id}"
                )
            mapped_requirements.add(requirement_id)

            target_configs = []
            for target_id in mapping["target_ids"]:
                target = dict(target_registry[target_id])
                spec = spec_registry[target.pop("spec_ref")]
                target_configs.append({**spec, **target})
            target_ids = [target["case_id"] for target in target_configs]
            if len(target_ids) != len(set(target_ids)):
                raise AssertionError(f"duplicate target Case: {atom_key}")
            if requirement["case_ids"] != sorted(target_ids):
                raise AssertionError(
                    f"requirement target ledger differs from Coverage Map: {requirement_id}"
                )

            acceptance_ids = set(mapping["acceptance_ids"])
            observed_acceptance_ids: set[str] = set()
            for target_config in target_configs:
                target = cases[target_config["case_id"]]
                contract = target["execution_contract"]["observability"][
                    "source_contract"
                ]
                for field in (
                    "execution_revision",
                    "spec",
                    "spec_sha256",
                ):
                    if str(contract[field]) != str(target_config[field]):
                        raise AssertionError(
                            f"target contract drifted: {target_config['case_id']} {field}"
                        )
                if target["title"] != target_config["title"]:
                    raise AssertionError(
                        f"target title drifted: {target_config['case_id']}"
                    )
                if sha256_source(
                    root,
                    target_config["execution_revision"],
                    target_config["spec"],
                ) != target_config["spec_sha256"]:
                    raise AssertionError(
                        f"target spec hash drifted: {target_config['case_id']}"
                    )
                target_acceptance_ids = set(target_config["acceptance_ids"])
                if not target_acceptance_ids or not target_acceptance_ids <= acceptance_ids:
                    raise AssertionError(
                        f"target acceptance IDs are outside atom expansion: {target_config['case_id']}"
                    )
                observed_acceptance_ids.update(target_acceptance_ids)
                if requirement_id not in target["selection"]["requirement_ids"]:
                    raise AssertionError(
                        f"target lacks mapped requirement: {target_config['case_id']}"
                    )
                source_ledger = {
                    (item["source_id"], item["locator"])
                    for item in target["sources"]
                }
                if atom_key not in source_ledger:
                    raise AssertionError(
                        f"target lacks source atom: {target_config['case_id']}"
                    )
            if observed_acceptance_ids != acceptance_ids:
                raise AssertionError(
                    f"acceptance expansion is not closed: {atom_key}"
                )
            mapped_targets += len(target_ids)

    # Acceptance IDs in a test title are only a locator hint. They are not
    # proof that the test body covers the document's complete Given/When/Then
    # and forbidden outcome. A reviewed source atom must therefore either be
    # present in this map or remain on a source-bound gap Case; it must never
    # inherit an executable Playwright route merely because the strings match.
    for requirement in requirements:
        reviewed_atoms = {
            (item["source_id"], item["locator"])
            for item in requirement["source_atoms"]
            if item["source_id"] in coverage["sources"]
        }
        if not reviewed_atoms or reviewed_atoms & mapped_atoms:
            continue
        executable_targets = []
        for case_id in requirement["case_ids"]:
            source_contract = (
                cases[case_id]
                .get("execution_contract", {})
                .get("observability", {})
                .get("source_contract")
            )
            if source_contract:
                executable_targets.append(case_id)
        if executable_targets:
            raise AssertionError(
                "unreviewed document atom inherited executable Case by "
                f"identifier similarity: {requirement['requirement_id']} -> "
                f"{sorted(executable_targets)}"
            )

    print(
        "document Case coverage maps: "
        f"{len(mapped_atoms)} atoms / {len(mapped_requirements)} requirements / "
        f"{mapped_targets} target bindings"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
