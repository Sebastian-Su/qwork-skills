#!/usr/bin/env python3
"""Validate every QWork private Case against schema v3 and cross-file indexes."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys

import yaml


def playwright_identity_command(root: pathlib.Path, repo: pathlib.Path) -> list[str]:
    return [
        sys.executable,
        str(root / "scripts/test_playwright_execution_identity.py"),
        "--repo",
        str(repo),
        "--skill-root",
        str(root),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--skill-root", required=True)
    args = parser.parse_args()
    repo = pathlib.Path(args.repo).resolve()
    root = pathlib.Path(args.skill_root).resolve()
    schema = yaml.safe_load((root / "references/case-schema.yaml").read_text(encoding="utf-8"))
    manifest = json.loads((root / "data/datasets/source-acceptance.json").read_text(encoding="utf-8"))
    dataset = json.loads((root / "data/datasets/dataset.json").read_text(encoding="utf-8"))
    cohorts = json.loads((root / "data/datasets/cohorts.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    cases = {}
    for path in sorted((root / "data/datasets/cases").glob("*.json")):
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            errors.append(f"{path.name}: invalid JSON: {error}")
            continue
        case_id = str(case.get("id") or "")
        if not case_id or case_id in cases:
            errors.append(f"{path.name}: missing or duplicate case id {case_id!r}")
            continue
        cases[case_id] = case
        if case.get("schema_version") != 3:
            errors.append(f"{case_id}: schema_version must be 3")
        if jsonschema:
            for error in jsonschema.Draft202012Validator(schema).iter_errors(case):
                location = ".".join(str(value) for value in error.absolute_path)
                errors.append(f"{case_id}:{location}: {error.message}")
        required = set(case.get("selection", {}).get("requirement_ids", []))
        derived = {item.get("requirement_id") for item in case.get("derived_requirements", [])}
        oracle_requirements = {item.get("requirement_id") for item in case.get("oracles", [])}
        if required != derived or required != oracle_requirements:
            errors.append(f"{case_id}: selection, derived requirements and oracles differ")
        execution = case.get("execution_contract", {})
        if execution.get("readiness") == "ready" and execution.get("reference_run", {}).get("status") != "passed":
            errors.append(f"{case_id}: ready without passed reference run")
        if execution.get("reference_run", {}).get("status") == "failed":
            if execution.get("readiness") == "ready":
                errors.append(f"{case_id}: failed reference run cannot be ready")
            if case.get("verification", {}).get("last_outcome") != "fail":
                errors.append(f"{case_id}: failed reference run must retain fail product outcome")
            if not execution.get("blockers"):
                errors.append(f"{case_id}: failed reference run needs a repair blocker")
        if execution.get("readiness") != "ready" and not execution.get("blockers"):
            errors.append(f"{case_id}: non-ready case needs explicit blockers")
    manifest_ids = {item["case_id"] for item in manifest.get("cases", [])}
    dataset_ids = {item["case_id"] for item in dataset.get("items", [])}
    full_ids = set(manifest.get("suite_index", {}).get("full_case_ids", []))
    if set(cases) != manifest_ids:
        errors.append("case files differ from source-acceptance cases")
    if set(cases) != dataset_ids:
        errors.append("case files differ from dataset items")
    if set(cases) != full_ids:
        errors.append("case files differ from full suite index")
    manifest_cohorts = manifest.get("cohort_index", {})
    file_cohorts = {item.get("cohort_id"): item for item in cohorts.get("cohorts", [])}
    suite_cohorts = manifest.get("suite_index", {}).get("cohort_to_cases", {})
    if set(manifest_cohorts) != set(file_cohorts) or set(manifest_cohorts) != set(suite_cohorts):
        errors.append("cohort manifest, cohorts.json and suite index IDs differ")
    for cohort_id, record in manifest_cohorts.items():
        members = sorted(set(record.get("case_ids", [])))
        expected_hash = "sha256:" + hashlib.sha256(
            json.dumps(members, separators=(",", ":")).encode()
        ).hexdigest()
        if set(members) - set(cases):
            errors.append(f"cohort {cohort_id} contains unknown Cases")
        if record.get("case_count") != len(members) or record.get("membership_sha256") != expected_hash:
            errors.append(f"cohort {cohort_id} count/hash does not match exact membership")
        if file_cohorts.get(cohort_id) != {"cohort_id": cohort_id, **record}:
            errors.append(f"cohort {cohort_id} differs between manifest and cohorts.json")
        if sorted(set(suite_cohorts.get(cohort_id, []))) != members:
            errors.append(f"cohort {cohort_id} differs between manifest and suite index")
    live_members = set(manifest_cohorts.get("live-external-authorization", {}).get("case_ids", []))
    deterministic_members = set(manifest_cohorts.get("deterministic-no-live-authorization", {}).get("case_ids", []))
    for case_id, case in cases.items():
        route = str(case.get("execution_contract", {}).get("route_id") or "")
        title = str(case.get("title") or "")
        source_contract = case.get("execution_contract", {}).get("observability", {}).get("source_contract")
        spec = str(source_contract.get("spec") or "") if isinstance(source_contract, dict) else ""
        marked_live = (
            route.startswith("qwork.playwright.")
            and (
                ".live.spec.ts" in spec
                or "-live.spec.ts" in spec
                or "auth-real-login" in spec
                or "@live" in title.lower()
            )
        )
        authorization_required = bool(case.get("execution_contract", {}).get("authorization", {}).get("required"))
        if marked_live and not authorization_required:
            errors.append(f"{case_id}: live-marked Playwright Case does not require authorization")
        if marked_live and case_id not in live_members:
            errors.append(f"{case_id}: live-marked Playwright Case is absent from live-external-authorization")
        if marked_live and case_id in deterministic_members:
            errors.append(f"{case_id}: live-marked Playwright Case leaked into deterministic cohort")
    structured_coverage = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/test_structured_oracle_coverage.py"),
            "--skill-root",
            str(root),
        ],
        text=True,
        capture_output=True,
    )
    if structured_coverage.returncode:
        errors.append(
            "structured Oracle Coverage Map invalid: "
            + (structured_coverage.stderr or structured_coverage.stdout).strip()
        )
    playwright_identity = subprocess.run(
        playwright_identity_command(root, repo),
        text=True,
        capture_output=True,
    )
    if playwright_identity.returncode:
        errors.append(
            "Playwright execution identity invalid: "
            + (playwright_identity.stderr or playwright_identity.stdout).strip()
        )
    if errors:
        print("qwork private dataset invalid:", file=sys.stderr)
        for error in errors[:300]:
            print(f"- {error}", file=sys.stderr)
        if len(errors) > 300:
            print(f"- ... {len(errors) - 300} more", file=sys.stderr)
        return 1
    print(json.dumps({
        "status": "ok",
        "case_count": len(cases),
        "schema_engine": "jsonschema" if jsonschema else "structural-fallback",
        "source_atom_count": manifest["coverage_summary"]["source_atoms"],
        "requirement_count": manifest["coverage_summary"]["requirements"],
        "blocked_requirement_count": manifest["coverage_summary"]["blocked_requirement_count"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
