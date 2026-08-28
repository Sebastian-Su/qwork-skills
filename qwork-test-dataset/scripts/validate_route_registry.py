#!/usr/bin/env python3
"""Validate exact Case/route closure and source-bound Playwright contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def resolve_skill_ref(root: Path, value: str) -> Path:
    prefix = "skill://qwork-test-dataset/"
    if not value.startswith(prefix):
        raise ValueError(f"not a qwork-test-dataset Skill URI: {value}")
    return root / value.removeprefix(prefix)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--skill-root", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    root = args.skill_root.resolve()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    registry = yaml.safe_load((root / "references/route-registry.yaml").read_text(encoding="utf-8"))
    routes = registry.get("routes") if isinstance(registry, dict) else None
    if not isinstance(routes, dict):
        print("route registry has no route map", file=sys.stderr)
        return 1
    errors: list[str] = []
    cases: dict[str, dict[str, Any]] = {}
    for path in sorted((root / "data/datasets/cases").glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        cases[str(case["id"])] = case
    case_routes = {str(case["execution_contract"]["route_id"]): case for case in cases.values()}
    if set(case_routes) != set(routes):
        errors.append(
            f"route registry mismatch: missing={sorted(set(case_routes)-set(routes))[:20]} "
            f"extra={sorted(set(routes)-set(case_routes))[:20]}"
        )
    if registry.get("route_count") != len(routes) or len(routes) != len(cases):
        errors.append("route_count, registry routes and Case count must match exactly")

    revision_cache: dict[str, str] = {}
    for route_id, case in sorted(case_routes.items()):
        route = routes.get(route_id, {})
        if route.get("case_id") != case["id"]:
            errors.append(f"route {route_id} binds the wrong Case")
        contract = case["execution_contract"]
        if route.get("launch") != contract["launch"] or route.get("navigation") != contract["navigation"]:
            errors.append(f"route {route_id} does not exactly mirror the Case execution contract")
        source_contract = contract["observability"].get("source_contract")
        if route_id.startswith(("qwork.playwright.", "qwork.private-playwright.")):
            if not isinstance(source_contract, dict):
                errors.append(f"Playwright route {route_id} has no source contract")
                continue
            if not SHA256.fullmatch(str(source_contract.get("body_sha256") or "")):
                errors.append(f"Playwright route {route_id} has invalid body hash")
            if int(source_contract.get("assertion_count") or 0) <= 0:
                errors.append(f"Playwright route {route_id} has no assertion")
            spec = str(source_contract.get("spec") or "")
            if route_id.startswith("qwork.private-playwright."):
                runner = (
                    "run_private_team_terminal_case.mjs"
                    if spec.endswith("/team-terminal-matrix.spec.ts")
                    else "run_private_tool_failure_case.mjs"
                    if spec.endswith("/tool-failure-causality.spec.ts")
                    else "run_private_sidebar_oracle_case.mjs"
                    if spec.endswith("/sidebar-account-oracle-completeness.spec.ts")
                    else "run_private_shell_oracle_case.mjs"
                    if spec.endswith("/shell-home-oracle-completeness.spec.ts")
                    else "run_private_automation_oracle_case.mjs"
                    if spec.endswith("/automation-oracle-gap-completeness.spec.ts")
                    else "run_private_playwright_case.mjs"
                )
                expected_command = (
                    "node .agents/skills/qwork-test-dataset/scripts/"
                    f"{runner} --repo . --case-id {case['id']} --case-title "
                    + json.dumps(case["title"], ensure_ascii=False)
                )
                if contract["launch"].get("command_or_tool") != expected_command:
                    errors.append(f"private Playwright route {route_id} command drifted")
                try:
                    private_path = resolve_skill_ref(root, spec)
                except ValueError as error:
                    errors.append(f"private Playwright route {route_id}: {error}")
                    continue
                if not private_path.is_file():
                    errors.append(f"private Playwright route {route_id} source is missing")
                    continue
                spec_bytes = private_path.read_bytes()
                expected_spec_hash = "sha256:" + hashlib.sha256(spec_bytes).hexdigest()
                if source_contract.get("spec_sha256") != expected_spec_hash:
                    errors.append(f"private Playwright route {route_id} full spec hash drifted")
                parsed = subprocess.run(
                    ["node", str(root / "scripts/extract_playwright_contracts.mjs"), spec],
                    input=spec_bytes.decode("utf-8"),
                    text=True,
                    capture_output=True,
                )
                if parsed.returncode:
                    errors.append(f"private Playwright route {route_id} source extraction failed")
                    continue
                tests = json.loads(parsed.stdout)["tests"]
                test = next((item for item in tests if item["title"] == case["title"]), None)
                if not test:
                    errors.append(f"private Playwright route {route_id} title does not select one source test")
                elif f"sha256:{test['body_sha256']}" != source_contract["body_sha256"]:
                    errors.append(f"private Playwright route {route_id} source body hash drifted")
                for supporting in source_contract.get("supporting_contracts", []):
                    supporting_path = str(supporting.get("path") or "")
                    try:
                        if supporting_path.startswith("skill://qwork-test-dataset/"):
                            supporting_bytes = resolve_skill_ref(root, supporting_path).read_bytes()
                        elif supporting_path.startswith("repo://"):
                            relative = supporting_path.removeprefix("repo://")
                            revision = str(supporting.get("revision") or "")
                            result = subprocess.run(
                                ["git", "show", f"{revision}:{relative}"],
                                cwd=repo,
                                capture_output=True,
                            )
                            if result.returncode:
                                raise ValueError(f"Git source cannot be read: {revision}:{relative}")
                            supporting_bytes = result.stdout
                            if (repo / relative).read_bytes() != supporting_bytes:
                                raise ValueError(f"worktree source differs from {revision}:{relative}")
                        elif not Path(supporting_path).is_absolute():
                            revision = str(supporting.get("revision") or "")
                            result = subprocess.run(
                                ["git", "show", f"{revision}:{supporting_path}"],
                                cwd=repo,
                                capture_output=True,
                            )
                            if result.returncode:
                                raise ValueError(
                                    f"Git source cannot be read: {revision}:{supporting_path}"
                                )
                            supporting_bytes = result.stdout
                            if (repo / supporting_path).read_bytes() != supporting_bytes:
                                raise ValueError(
                                    f"worktree source differs from {revision}:{supporting_path}"
                                )
                        else:
                            raise ValueError(f"unsupported supporting locator: {supporting_path}")
                    except (OSError, ValueError) as error:
                        errors.append(f"private Playwright route {route_id}: {error}")
                        continue
                    actual = "sha256:" + hashlib.sha256(supporting_bytes).hexdigest()
                    if actual != supporting.get("sha256"):
                        errors.append(f"private Playwright route {route_id} supporting hash drifted: {supporting_path}")
                continue
            if not str(contract["launch"].get("command_or_tool") or "").startswith("npx playwright test "):
                errors.append(f"Playwright route {route_id} has no exact Playwright command")
            source = next((item for item in case.get("sources", []) if item.get("stable_source_id", "").endswith(f":{spec}")), None)
            if not source:
                errors.append(f"Playwright route {route_id} cannot resolve its Git source")
                continue
            revision = str(source_contract.get("execution_revision") or "")
            if not re.fullmatch(r"[0-9a-f]{40}", revision):
                errors.append(f"Playwright route {route_id} has no execution revision")
                continue
            key = f"{revision}:{spec}"
            if key not in revision_cache:
                result = subprocess.run(
                    ["git", "show", key], cwd=repo, text=True, capture_output=True
                )
                if result.returncode:
                    errors.append(f"Playwright route {route_id} source cannot be read: {key}")
                    continue
                revision_cache[key] = result.stdout
            spec_bytes = revision_cache[key].encode("utf-8")
            expected_spec_hash = "sha256:" + hashlib.sha256(spec_bytes).hexdigest()
            if source_contract.get("spec_sha256") != expected_spec_hash:
                errors.append(f"Playwright route {route_id} full spec hash drifted")
            worktree_path = repo / spec
            worktree_matches = (
                worktree_path.is_file() and worktree_path.read_bytes() == spec_bytes
            )
            if revision == head:
                if not worktree_matches:
                    errors.append(
                        f"Playwright route {route_id} worktree spec differs from its execution revision"
                    )
            else:
                blockers = [str(value) for value in contract.get("blockers", [])]
                if contract.get("readiness") != "partial":
                    errors.append(
                        f"Playwright route {route_id} binds a non-HEAD revision without partial readiness"
                    )
                if not any(
                    "not present in the current feature HEAD" in value
                    for value in blockers
                ):
                    errors.append(
                        f"Playwright route {route_id} binds a non-HEAD revision without an explicit develop drift blocker"
                    )
            extractor = root / "scripts/extract_playwright_contracts.mjs"
            parsed = subprocess.run(
                ["node", str(extractor), spec],
                input=revision_cache[key],
                text=True,
                capture_output=True,
            )
            if parsed.returncode:
                errors.append(f"Playwright route {route_id} source extraction failed")
                continue
            tests = json.loads(parsed.stdout)["tests"]
            test = next((item for item in tests if item["title"] == case["title"]), None)
            if not test:
                errors.append(f"Playwright route {route_id} title does not select one source test")
            elif f"sha256:{test['body_sha256']}" != source_contract["body_sha256"]:
                errors.append(f"Playwright route {route_id} source body hash drifted")
            for supporting in source_contract.get("supporting_contracts", []):
                supporting_path = str(supporting.get("path") or "")
                supporting_revision = str(supporting.get("revision") or "")
                supporting_key = f"{supporting_revision}:{supporting_path}"
                result = subprocess.run(
                    ["git", "show", supporting_key], cwd=repo, capture_output=True
                )
                if result.returncode:
                    errors.append(
                        f"Playwright route {route_id} supporting contract cannot be read: {supporting_key}"
                    )
                    continue
                actual = "sha256:" + hashlib.sha256(result.stdout).hexdigest()
                if actual != supporting.get("sha256"):
                    errors.append(
                        f"Playwright route {route_id} supporting contract hash drifted: {supporting_path}"
                    )
        else:
            source_ids = {str(item.get("source_id")) for item in case.get("sources", [])}
            if route_id.startswith("qwork.dataset.workbuddy-storage."):
                expected = (
                    "python3 .agents/skills/qwork-test-dataset/scripts/validate_workbuddy_storage_case.py "
                    f"--skill-root .agents/skills/qwork-test-dataset --case-id {case['id']}"
                )
                if source_ids != {"WORKBUDDY-STORAGE-LOCAL"}:
                    errors.append(f"storage verifier route {route_id} is not source-exclusive")
                if contract["launch"].get("strategy") != "command" or contract["launch"].get("command_or_tool") != expected:
                    errors.append(f"storage verifier route {route_id} command drifted")
                if case.get("execution_type") != "integration" or case.get("ui_acceptance") is not None:
                    errors.append(f"storage verifier route {route_id} must be non-UI integration")
            elif route_id.startswith("qwork.dataset.structured-oracle-source."):
                expected = (
                    "python3 .agents/skills/qwork-test-dataset/scripts/"
                    "validate_structured_oracle_source_case.py "
                    f"--repo . --skill-root .agents/skills/qwork-test-dataset --case-id {case['id']}"
                )
                if not source_ids or not all(
                    value.startswith("WORKBUDDY-ORACLE-5-3-5-") for value in source_ids
                ):
                    errors.append(f"structured source verifier route {route_id} has an unrelated source")
                atom_facets = {
                    category
                    for requirement in case.get("derived_requirements", [])
                    for category in requirement.get("acceptance_categories", [])
                }
                if atom_facets != {"evidence-integrity"}:
                    errors.append(f"structured source verifier route {route_id} mixes product requirements")
                if contract["launch"].get("strategy") != "command" or contract["launch"].get("command_or_tool") != expected:
                    errors.append(f"structured source verifier route {route_id} command drifted")
                if case.get("execution_type") != "integration" or case.get("ui_acceptance") is not None:
                    errors.append(f"structured source verifier route {route_id} must be non-UI integration")
            elif route_id.startswith("qwork.dataset.source-integration."):
                expected = (
                    "python3 .agents/skills/qwork-test-dataset/scripts/"
                    "validate_source_integration_case.py --repo . "
                    "--skill-root .agents/skills/qwork-test-dataset "
                    f"--case-id {case['id']}"
                )
                source = contract.get("observability", {}).get("source_contract") or {}
                requirement_ids = sorted(str(value) for value in case.get("selection", {}).get("requirement_ids") or [])
                mapped_requirement_ids = sorted(str(value) for value in (source.get("requirement_tests") or {}))
                if contract["launch"].get("strategy") != "command" or contract["launch"].get("command_or_tool") != expected:
                    errors.append(f"source integration route {route_id} command drifted")
                if source.get("repository") != "qwork_server" or not re.fullmatch(r"[0-9a-f]{40}", str(source.get("revision") or "")):
                    errors.append(f"source integration route {route_id} repository authority drifted")
                if mapped_requirement_ids != requirement_ids:
                    errors.append(f"source integration route {route_id} requirement map is incomplete")
                if case.get("execution_type") != "integration" or case.get("ui_acceptance") is not None:
                    errors.append(f"source integration route {route_id} must be non-UI integration")
            elif any(
                re.fullmatch(r"WORKBUDDY-CDP-\d+(?:-\d+)+-V\d+", source_id)
                for source_id in source_ids
            ):
                cdp_source_ids = {
                    source_id
                    for source_id in source_ids
                    if re.fullmatch(r"WORKBUDDY-CDP-\d+(?:-\d+)+-V\d+", source_id)
                }
                if source_ids != cdp_source_ids or len(cdp_source_ids) != 1:
                    errors.append(
                        f"WorkBuddy CDP route {route_id} must bind one source-exclusive CDP snapshot"
                    )
                oracle = contract["observability"].get("oracle_contract")
                if not isinstance(oracle, dict):
                    errors.append(f"WorkBuddy CDP route {route_id} has no Oracle contract")
                    continue
                if contract["launch"].get("strategy") != "command" or "--fail-on-diff" not in str(contract["launch"].get("command_or_tool")):
                    errors.append(f"WorkBuddy CDP route {route_id} is not fail-closed")
                if contract["reference_run"].get("status") == "pending":
                    for tool_key, tool_path in (
                        ("runner_sha256", root / "scripts/run_qwork_workbuddy_oracle.mjs"),
                        ("comparator_sha256", root / "scripts/compare_qwork_workbuddy_oracle.py"),
                    ):
                        actual = "sha256:" + __import__("hashlib").sha256(tool_path.read_bytes()).hexdigest()
                        if oracle.get(tool_key) != actual:
                            errors.append(f"WorkBuddy CDP route {route_id} {tool_key} drifted")
                    continue
                for ref_key, hash_key in (("reference_report", "reference_report_sha256"), ("capture_manifest", "capture_manifest_sha256")):
                    try:
                        artifact = resolve_skill_ref(root, str(oracle[ref_key]))
                    except (KeyError, ValueError) as error:
                        errors.append(f"WorkBuddy CDP route {route_id}: {error}")
                        continue
                    actual = "sha256:" + __import__("hashlib").sha256(artifact.read_bytes()).hexdigest()
                    if actual != oracle.get(hash_key):
                        errors.append(f"WorkBuddy CDP route {route_id} {ref_key} hash drifted")
                report = json.loads(resolve_skill_ref(root, str(oracle["reference_report"])).read_text(encoding="utf-8"))
                result = next((item for item in report["results"] if item["state"] == oracle["state"]), None)
                expected_status = "passed" if result and result["status"] == "pass" else "failed"
                if contract["reference_run"].get("status") != expected_status:
                    errors.append(f"WorkBuddy CDP route {route_id} reference status contradicts report")
            elif contract["launch"].get("strategy") != "manual-blocked":
                errors.append(f"source requirement route {route_id} cannot claim an unimplemented runner")

    if errors:
        print("route registry gate failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        f"route registry gate complete: {len(routes)} routes, "
        f"{sum(route.startswith(('qwork.playwright.', 'qwork.private-playwright.')) for route in routes)} source-bound Playwright tests"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
