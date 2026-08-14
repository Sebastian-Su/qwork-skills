#!/usr/bin/env python3
"""Regression checks for explicit structured WorkBuddy Oracle coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import yaml


AUTOMATION_SOURCE = "WORKBUDDY-ORACLE-5-3-5-WORKBUDDY-5-3-5-AUTOMATION"
SIDEBAR_SOURCE = "WORKBUDDY-ORACLE-5-3-5-WORKBUDDY-5-3-5-SIDEBAR-ACCOUNT"
SHELL_HOME_SOURCE = "WORKBUDDY-ORACLE-5-3-5-WORKBUDDY-5-3-5-SHELL-HOME"
EXPECTED_COUNTS = {
    AUTOMATION_SOURCE: (77, 0),
    SIDEBAR_SOURCE: (74, 0),
    SHELL_HOME_SOURCE: (84, 0),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.skill_root.resolve()
    mapping = yaml.safe_load(
        (root / "references/structured-oracle-coverage-map.yaml").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads(
        (root / "data/datasets/source-acceptance.json").read_text(encoding="utf-8")
    )
    accepted_by_id = {item["source_id"]: item for item in manifest["sources"]}
    case_dir = root / "data/datasets/cases"
    cases = [json.loads(path.read_text(encoding="utf-8")) for path in case_dir.glob("*.json")]
    summaries = []
    for source_id, expected_counts in EXPECTED_COUNTS.items():
        source = mapping["sources"][source_id]
        mappings = source["mappings"]
        covered = [pointer for item in mappings for pointer in item["covered_pointers"]]
        gaps = source["gap_pointers"]
        if (len(covered), len(gaps)) != expected_counts:
            raise AssertionError(
                f"{source_id} coverage counts must be {expected_counts}, got {(len(covered), len(gaps))}"
            )
        if len(covered) != len(set(covered)) or len(gaps) != len(set(gaps)):
            raise AssertionError(f"{source_id} has duplicate pointers")
        if set(covered) & set(gaps):
            raise AssertionError(f"{source_id} covered and gap pointers overlap")
        accepted = accepted_by_id[source_id]
        product = {
            atom["locator"].removeprefix("json-pointer:")
            for atom in accepted["inventory"]["atoms"]
            if not atom.get("evidence_only")
        }
        if set(covered) | set(gaps) != product:
            raise AssertionError(f"{source_id} Coverage Map is not closed over product pointers")
        revision = accepted["revision"]
        for item in mappings:
            target = item["target"]
            expected_hashes = {
                (target["execution_revision"], target["spec"]): target["spec_sha256"],
                (revision, accepted["locator"].split(":", 2)[2]): target["oracle_sha256"],
            }
            if target.get("helper"):
                expected_hashes[(target["execution_revision"], target["helper"])] = target["helper_sha256"]
            for (dependency_revision, path), expected in expected_hashes.items():
                if path.startswith("skill://qwork-test-dataset/"):
                    blob = (root / path.removeprefix("skill://qwork-test-dataset/")).read_bytes()
                else:
                    blob = subprocess.run(
                        ["git", "show", f"{dependency_revision}:{path}"], check=True, capture_output=True
                    ).stdout
                actual = "sha256:" + hashlib.sha256(blob).hexdigest()
                if actual != expected:
                    raise AssertionError(f"coverage dependency hash drifted: {path}")
            target_case = next(case for case in cases if case["id"] == target["case_id"])
            target_pointers = {
                source_item["locator"].removeprefix("json-pointer:")
                for source_item in target_case.get("sources", [])
                if source_item.get("source_id") == source_id
                and source_item.get("locator", "").startswith("json-pointer:")
                and source_item["locator"].removeprefix("json-pointer:") in product
            }
            if target_pointers != set(item["covered_pointers"]):
                raise AssertionError(f"{target['case_id']} source ledger differs from mapped pointers")
        target_ids = {item["target"]["case_id"] for item in mappings}
        non_target_pointers = {
            source_item["locator"].removeprefix("json-pointer:")
            for case in cases
            if case["id"] not in target_ids
            for source_item in case.get("sources", [])
            if source_item.get("source_id") == source_id
            and source_item.get("locator", "").startswith("json-pointer:")
            and source_item["locator"].removeprefix("json-pointer:") in product
        }
        if non_target_pointers != set(gaps):
            raise AssertionError(f"{source_id} non-target source ledger differs from gaps")
        summaries.append(f"{len(covered)} covered / {len(gaps)} gaps")
    print("structured Oracle coverage maps: " + "; ".join(summaries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
