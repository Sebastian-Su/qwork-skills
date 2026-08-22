#!/usr/bin/env python3
"""Validate reviewed document atoms that require multiple executable Cases."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
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
    module_spec = importlib.util.spec_from_file_location(
        "qwork_dataset_builder", root / "scripts/build_product_baseline.py"
    )
    if module_spec is None or module_spec.loader is None:
        raise AssertionError("Dataset builder cannot be loaded")
    builder = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(builder)
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
    mapped_requirement_targets: dict[str, set[str]] = {}
    mapped_targets = 0
    for source_id, source_map in coverage["sources"].items():
        source_locator = str(source_map.get("source_locator") or "")
        source_parts = source_locator.split(":", 2)
        source_path = source_parts[2] if len(source_parts) == 3 else ""
        resolved_source_id = source_id
        source = sources.get(source_id)
        if source is None and source_id.startswith("QHEAD-DOC-"):
            resolved_source_id = f"QDEV-DOC-{builder.stable_slug(source_path)}"
            source = sources.get(resolved_source_id)
        if source is None:
            current_revision = str(manifest.get("develop_revision") or "")
            exists = subprocess.run(
                ["git", "cat-file", "-e", f"{current_revision}:{source_path}"],
                check=False,
                capture_output=True,
            )
            if exists.returncode != 0:
                continue
            raise AssertionError(f"source is missing: {source_id}")
        historic_content = (
            subprocess.run(
                ["git", "show", f"{source_parts[1]}:{source_path}"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            if len(source_parts) == 3
            else ""
        )
        historic_atoms = builder.markdown_atoms(source_id, historic_content)
        current_atoms = list(source["inventory"]["atoms"])
        for mapping in source_map["mappings"]:
            atom = builder.relocate_document_atom(
                current_atoms=current_atoms,
                historic_atoms=historic_atoms,
                locator=str(mapping["atom_locator"]),
                atom_sha256=str(mapping["atom_sha256"]),
            )
            if atom is None:
                raise AssertionError(
                    f"document atom drifted: {(source_id, mapping['atom_locator'])}"
                )
            locator = str(atom["locator"])
            atom_key = (resolved_source_id, locator)
            mapped_atoms.add(atom_key)

            matching_requirements = [
                item
                for item in requirements
                if any(
                    source_atom["source_id"] == resolved_source_id
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
            mapped_requirements.add(requirement_id)

            target_configs = []
            for target_id in mapping["target_ids"]:
                target = dict(target_registry[target_id])
                spec = spec_registry[target.pop("spec_ref")]
                target_config = {**spec, **target}
                if target_config["case_id"] not in cases:
                    expected_suffix = str(target_config["title"]).split("|", 1)[-1].strip()
                    renamed = [
                        candidate
                        for candidate in cases.values()
                        if str(candidate["title"]).split("|", 1)[-1].strip()
                        == expected_suffix
                        and str(
                            candidate["execution_contract"]["observability"]
                            ["source_contract"]["spec"]
                        )
                        == str(target_config["spec"])
                    ]
                    if len(renamed) != 1:
                        raise AssertionError(
                            f"renamed target is missing or ambiguous: {target_config['case_id']}"
                        )
                    target_config["case_id"] = renamed[0]["id"]
                target_configs.append(target_config)
            target_ids = [target["case_id"] for target in target_configs]
            if len(target_ids) != len(set(target_ids)):
                raise AssertionError(f"duplicate target Case: {atom_key}")
            mapped_requirement_targets.setdefault(requirement_id, set()).update(target_ids)

            acceptance_ids = set(mapping["acceptance_ids"])
            observed_acceptance_ids: set[str] = set()
            for target_config in target_configs:
                target = cases[target_config["case_id"]]
                contract = target["execution_contract"]["observability"][
                    "source_contract"
                ]
                for field in ("spec", "spec_sha256"):
                    if str(contract[field]) != str(target_config[field]):
                        raise AssertionError(
                            f"target contract drifted: {target_config['case_id']} {field}"
                        )
                if target["title"].split("|", 1)[-1].strip() != str(
                    target_config["title"]
                ).split("|", 1)[-1].strip():
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

    requirement_by_id = {item["requirement_id"]: item for item in requirements}
    for requirement_id, target_ids in mapped_requirement_targets.items():
        if set(requirement_by_id[requirement_id]["case_ids"]) != target_ids:
            raise AssertionError(
                f"requirement target ledger differs from Coverage Map: {requirement_id}"
            )

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
