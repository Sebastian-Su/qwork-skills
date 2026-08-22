#!/usr/bin/env python3
"""Evaluate one canonical QWork E2E report against its frozen release-gate plan."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ALLOWED_EXTERNAL = {
    "new-permission-or-credential",
    "unavailable-external-account-service-or-device",
    "paid-production-or-destructive-authorization",
    "irreversible-action-authorization",
    "unresolved-product-policy-figma-or-api-semantics",
}
LOCAL_CLASSES = {"product", "test", "environment", "data", "oracle", "runner", "fixture", "locator", "skill", "evidence"}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def plan_hash(plan: dict[str, Any]) -> str:
    normalized = json.loads(json.dumps(plan))
    normalized.pop("plan_sha256", None)
    normalized.setdefault("checkpoint", {})["current_plan_hash"] = None
    return canonical_hash(normalized)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def tree_hash(root: Path) -> str:
    entries = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if (
            not path.is_file()
            or "__pycache__" in relative.parts
            or path.name == ".DS_Store"
            or relative.parts[:2] == ("data", "runs")
        ):
            continue
        entries.append({"path": relative.as_posix(), "sha256": sha256_file(path), "size": path.stat().st_size})
    return canonical_hash({"files": entries})


def index(values: Any, key: str, label: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(values, list):
        errors.append(f"{label} must be a list")
        return {}
    result = {}
    for item in values:
        if not isinstance(item, dict) or not isinstance(item.get(key), str):
            errors.append(f"{label} contains an invalid {key}")
            continue
        item_id = item[key]
        if item_id in result:
            errors.append(f"{label} contains duplicate {key}: {item_id}")
        result[item_id] = item
    return result


def validate_artifacts(result: dict[str, Any], root: Path, errors: list[str]) -> None:
    evidence = result.get("artifacts")
    if not isinstance(evidence, list) or not evidence:
        errors.append(f"{result.get('item_id')}: PASS requires at least one hashed artifact")
        return
    for artifact in evidence:
        if not isinstance(artifact, dict) or not artifact.get("path") or not artifact.get("sha256"):
            errors.append(f"{result.get('item_id')}: artifact requires path and sha256")
            continue
        candidate = Path(str(artifact["path"]))
        if candidate.is_absolute():
            errors.append(f"{result.get('item_id')}: artifact path must be relative")
            continue
        resolved = (root / candidate).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            errors.append(f"{result.get('item_id')}: artifact escapes run root")
            continue
        if not resolved.is_file():
            errors.append(f"{result.get('item_id')}: artifact is missing: {candidate}")
            continue
        expected = str(artifact["sha256"]).removeprefix("sha256:").lower()
        if sha256_file(resolved) != expected:
            errors.append(f"{result.get('item_id')}: artifact hash mismatch: {candidate}")


def run_finalizer(skill_root: Path, report: Path, run_root: Path, plan: Path) -> tuple[dict[str, Any] | None, str | None]:
    command = [
        sys.executable,
        str(skill_root / "scripts/finalize_e2e_report.py"),
        "--input", str(report),
        "--output", str(run_root / "report.html"),
        "--artifact-root", str(run_root),
        "--plan", str(plan),
    ]
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        return None, (result.stderr or result.stdout or "report finalizer failed").strip()
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError as error:
        return None, f"report finalizer returned invalid JSON: {error}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--dataset-skill", type=Path)
    args = parser.parse_args()

    repo = args.repo.resolve()
    plan_path = args.plan.resolve()
    run_root = args.run_root.resolve()
    report_path = run_root / "report.json"
    skill_root = Path(__file__).resolve().parent.parent
    dataset_root = (args.dataset_skill or repo / ".agents/skills/qwork-test-dataset").resolve()
    errors: list[str] = []
    external: list[dict[str, Any]] = []

    try:
        plan, report = load(plan_path), load(report_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"gate_status": "repair-required", "failure_classification": "evidence", "first_trusted_failure": str(error), "repair_required_next_action": "create the canonical report.json for the current plan", "final_response_allowed": False}, ensure_ascii=False))
        return 1

    expected_plan_hash = plan_hash(plan)
    if plan.get("plan_sha256") != expected_plan_hash:
        errors.append("plan_sha256 is stale or invalid")
    if report.get("plan_sha256") != plan.get("plan_sha256"):
        errors.append("report plan_sha256 does not match plan")
    current_revision = git(repo, "rev-parse", "HEAD").strip()
    if current_revision != plan.get("implementation_revision") or report.get("implementation_revision") != current_revision:
        errors.append("current implementation revision does not match plan/report")

    authority = plan.get("asset_authority", {})
    manifest_path = dataset_root / "data/datasets/source-acceptance.json"
    dataset_path = dataset_root / "data/datasets/dataset.json"
    disposition_path = dataset_root / "data/datasets/source-dispositions.json"
    current_hashes = {
        "source_acceptance_sha256": sha256_file(manifest_path),
        "source_dispositions_sha256": sha256_file(disposition_path),
        "dataset_manifest_sha256": sha256_file(dataset_path),
        "dataset_tree_sha256": tree_hash(dataset_root),
        "project_e2e_skill_tree_sha256": tree_hash(skill_root),
        "route_registry_sha256": sha256_file(dataset_root / "references/route-registry.yaml"),
        "locator_registry_sha256": sha256_file(dataset_root / "references/locator-registry.yaml"),
    }
    for key, value in current_hashes.items():
        if authority.get(key) != value:
            errors.append(f"authority drift: {key}; rebuild the plan")

    # Source acceptance runs before result interpretation. A local validation gap outranks external blockers.
    source_command = [sys.executable, str(skill_root / "scripts/validate_source_acceptance.py"), "--repo", str(repo), "--manifest", "skill://qwork-test-dataset/data/datasets/source-acceptance.json"]
    source_result = subprocess.run(source_command, text=True, capture_output=True)
    if source_result.returncode:
        errors.append("source acceptance validation failed: " + (source_result.stderr or source_result.stdout).strip()[:1000])
    disposition_result = subprocess.run(
        [sys.executable, str(dataset_root / "scripts/validate_source_dispositions.py"), "--repo", str(repo), "--manifest", "skill://qwork-test-dataset/data/datasets/source-dispositions.json"],
        text=True,
        capture_output=True,
    )
    if disposition_result.returncode:
        errors.append("source disposition validation failed: " + (disposition_result.stderr or disposition_result.stdout).strip()[:1000])
    route_result = subprocess.run(
        [sys.executable, str(dataset_root / "scripts/validate_route_registry.py"), "--repo", str(repo), "--skill-root", str(dataset_root)],
        text=True,
        capture_output=True,
    )
    if route_result.returncode:
        errors.append("route registry validation failed: " + (route_result.stderr or route_result.stdout).strip()[:1000])

    finalization, finalization_error = run_finalizer(skill_root, report_path, run_root, plan_path)
    if finalization_error:
        errors.append("visual-report-finalization-failed: " + finalization_error[:1000])

    required = index(plan.get("required_items"), "item_id", "required_items", errors)
    results = index(report.get("results"), "item_id", "results", errors)
    for item_id, item in required.items():
        if (
            item.get("kind") == "case"
            and not item.get("authorization_required")
            and not item.get("external_dependency_required")
        ):
            if item.get("execution_readiness") != "ready" or item.get("reference_run_status") != "passed":
                errors.append(f"{item_id}: Case execution contract is not reference-run ready")
    missing = sorted(set(required) - set(results))
    unexpected = sorted(set(results) - set(required))
    if missing:
        errors.append("missing required results: " + ", ".join(missing[:30]))
    if unexpected:
        errors.append("unexpected results not in plan: " + ", ".join(unexpected[:30]))

    for item_id, result in results.items():
        if item_id not in required:
            continue
        status = str(result.get("status") or "").lower()
        if result.get("plan_sha256") != plan.get("plan_sha256") or result.get("implementation_revision") != current_revision:
            errors.append(f"{item_id}: stale plan or implementation revision")
        if status == "pass":
            if result.get("cleanup_status") != "pass":
                errors.append(f"{item_id}: cleanup is not pass")
            validate_artifacts(result, run_root, errors)
        elif status == "external-blocked":
            blocker = str(result.get("blocker_class") or "")
            if blocker not in ALLOWED_EXTERNAL:
                errors.append(f"{item_id}: invalid external blocker class {blocker!r}")
            elif not result.get("exclusion_checks") or not result.get("unlock_action"):
                errors.append(f"{item_id}: external blocker requires exclusion_checks and unlock_action")
            else:
                external.append(result)
        elif status in {"skip", "skipped", "known_gap", "not_applicable", "pending", "inconclusive", ""}:
            errors.append(f"{item_id}: required result cannot be {status or 'missing-status'}")
        else:
            classification = str(result.get("failure_classification") or "product")
            if classification not in LOCAL_CLASSES:
                classification = "product"
            errors.append(f"{item_id}: {classification} failure: {result.get('message') or status}")

    report_cases = index(report.get("cases"), "id", "cases", errors)
    machine_cases = index(report.get("case_results"), "case_id", "case_results", errors)
    for case_id in plan.get("selected_case_ids", []):
        item = results.get(f"case:{case_id}")
        human = report_cases.get(case_id)
        machine = machine_cases.get(case_id)
        if not item or not human or not machine:
            continue
        statuses = {str(item.get("status", "")).lower(), str(human.get("status", "")).lower(), str(machine.get("status", "")).lower()}
        if len(statuses) != 1:
            errors.append(f"{case_id}: result/case_results/human case status mismatch")

    cleanup = report.get("cleanup") if isinstance(report.get("cleanup"), dict) else {}
    independent = report.get("independent_rerun") if isinstance(report.get("independent_rerun"), dict) else {}
    if cleanup.get("status") != "pass" or not cleanup.get("evidence"):
        errors.append("global cleanup is not proven pass")
    if independent.get("status") != "pass" or independent.get("plan_sha256") != plan.get("plan_sha256") or not independent.get("evidence"):
        errors.append("independent fresh-context rerun is not proven pass")
    else:
        validate_artifacts(
            {"item_id": "independent-rerun", "artifacts": independent.get("evidence")},
            run_root,
            errors,
        )
        reference_run_ids = {
            str(item.get("reference_run_id"))
            for item in required.values()
            if item.get("kind") == "case"
            and not item.get("authorization_required")
            and not item.get("external_dependency_required")
            and item.get("reference_run_id")
        }
        if report.get("run_id") in reference_run_ids:
            errors.append("independent rerun reuses a registered reference run id")
        attestation_artifacts = [
            value
            for value in independent.get("evidence", [])
            if str(value.get("path") or "").endswith("independent-rerun-attestation.json")
        ]
        if len(attestation_artifacts) != 1:
            errors.append("independent rerun requires one hash-bound attestation")
        else:
            attestation_path = run_root / str(attestation_artifacts[0]["path"])
            attestation = load(attestation_path)
            proof = attestation.get("proof") if isinstance(attestation.get("proof"), dict) else {}
            required_proof = {
                "same_implementation_revision",
                "same_case_source_contracts",
                "post_registration_plan_hash_differs",
                "current_run_started_after_references_finished",
                "runner_state_artifact_is_distinct",
                "all_local_coordinates_passed",
                "live_execution_forbidden",
            }
            if (
                attestation.get("status") != "pass"
                or attestation.get("implementation_revision") != current_revision
                or attestation.get("current_run_id") != report.get("run_id")
                or attestation.get("current_plan_sha256") != plan.get("plan_sha256")
                or set(attestation.get("reference_run_ids") or []) != reference_run_ids
                or not attestation.get("reference_plan_sha256s")
                or plan.get("plan_sha256") in set(attestation.get("reference_plan_sha256s") or [])
                or attestation.get("current_runner_state_sha256") != sha256_file(run_root / "runner-state.json")
                or attestation.get("current_preflight_sha256") != sha256_file(run_root / "execution-preflight.json")
                or any(proof.get(key) is not True for key in required_proof)
            ):
                errors.append("independent rerun attestation authority mismatch")

    if errors:
        expected_gate = "repair-required"
        next_action = str(report.get("checkpoint", {}).get("repair_required_next_action") or "repair the first trusted local failure, rebuild the plan, and rerun every required item")
        expected_final_allowed = False
    elif external:
        expected_gate = "external-blocked"
        next_action = str(external[0]["unlock_action"])
        expected_final_allowed = True
    else:
        expected_gate = "test-ready"
        next_action = "none; retain the finalized report and hashes for review"
        expected_final_allowed = True

    checkpoint = report.get("checkpoint") if isinstance(report.get("checkpoint"), dict) else {}
    if report.get("gate_status") != expected_gate:
        errors.append(f"report gate_status must be {expected_gate}")
    if checkpoint.get("current_implementation_revision") != current_revision or checkpoint.get("current_plan_hash") != plan.get("plan_sha256"):
        errors.append("continuation checkpoint revision/hash mismatch")
    if bool(checkpoint.get("final_response_allowed")) != expected_final_allowed:
        errors.append(f"final_response_allowed must be {str(expected_final_allowed).lower()}")
    if expected_gate == "repair-required" and not str(checkpoint.get("repair_required_next_action") or "").strip():
        errors.append("repair-required needs a nonempty repair_required_next_action")

    # Contract mismatches discovered above remain repair-required even if all primary results passed.
    if errors:
        verdict = {
            "gate_status": "repair-required",
            "failure_classification": "evidence",
            "first_trusted_failure": errors[0],
            "all_failures": errors,
            "repair_required_next_action": next_action,
            "cleanup_status": cleanup.get("status", "missing"),
            "independent_rerun_status": independent.get("status", "missing"),
            "final_response_allowed": False,
            "report_finalization": finalization,
        }
        print(json.dumps(verdict, ensure_ascii=False, indent=2))
        return 1

    verdict = {
        "gate_status": expected_gate,
        "required_item_count": len(required),
        "selected_case_count": len(plan.get("selected_case_ids", [])),
        "external_blockers": external,
        "next_action": next_action,
        "cleanup_status": cleanup.get("status"),
        "independent_rerun_status": independent.get("status"),
        "final_response_allowed": expected_final_allowed,
        "report_finalization": finalization,
    }
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
