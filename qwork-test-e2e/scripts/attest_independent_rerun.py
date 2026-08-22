#!/usr/bin/env python3
"""Attest a fresh release-gate rerun against registered public references."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import yaml


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def plan_hash(plan: dict[str, Any]) -> str:
    normalized = json.loads(json.dumps(plan))
    normalized.pop("plan_sha256", None)
    normalized.setdefault("checkpoint", {})["current_plan_hash"] = None
    return canonical_hash(normalized)


def timestamp(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def artifact(root: Path, path: Path) -> dict[str, str]:
    resolved = path.resolve()
    relative = resolved.relative_to(root.resolve())
    return {"path": relative.as_posix(), "sha256": sha256(resolved)}


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
    dataset = (args.dataset_skill or repo / ".agents/skills/qwork-test-dataset").resolve()
    plan = load(plan_path)
    state = load(run_root / "runner-state.json")
    preflight = load(run_root / "execution-preflight.json")
    report = load(run_root / "report.json")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    if plan.get("plan_sha256") != plan_hash(plan):
        raise ValueError("current plan hash is invalid")
    if plan.get("implementation_revision") != revision:
        raise ValueError("current plan revision is stale")
    if state.get("plan_sha256") != plan.get("plan_sha256") or state.get("implementation_revision") != revision:
        raise ValueError("current runner state belongs to another plan/revision")
    if preflight.get("plan_sha256") != plan.get("plan_sha256") or preflight.get("implementation_revision") != revision:
        raise ValueError("current preflight belongs to another plan/revision")
    if preflight.get("live_execution_allowed") is not False:
        raise ValueError("independent rerun must forbid live execution")

    items = {str(item["item_id"]): item for item in plan.get("required_items", [])}
    local_items = {
        item_id: item
        for item_id, item in items.items()
        if not (
            item.get("kind") == "case"
            and (item.get("authorization_required") or item.get("external_dependency_required"))
        )
    }
    coordinates = state.get("coordinates") or {}
    if set(coordinates) != set(local_items):
        missing = sorted(set(local_items) - set(coordinates))
        unexpected = sorted(set(coordinates) - set(local_items))
        raise ValueError(f"independent rerun coordinate closure mismatch: missing={missing[:10]} unexpected={unexpected[:10]}")
    failed = sorted(item_id for item_id, value in coordinates.items() if value.get("status") != "pass")
    if failed:
        raise ValueError(f"independent rerun contains failures: {failed[:10]}")

    case_items = [item for item in local_items.values() if item.get("kind") == "case"]
    if not case_items or not all(
        item.get("execution_readiness") == "ready"
        and item.get("reference_run_status") == "passed"
        and item.get("reference_run_id")
        for item in case_items
    ):
        raise ValueError("current plan Cases are not backed by registered passing references")

    registry = yaml.safe_load(
        (dataset / "references/deterministic-reference-runs.yaml").read_text(encoding="utf-8")
    )
    manifests: dict[str, tuple[Path, dict[str, Any], str]] = {}
    prefix = "skill://qwork-test-dataset/"
    for batch in registry.get("public_playwright_batches", []):
        locator = str(batch["manifest"])
        if not locator.startswith(prefix):
            raise ValueError("registered public reference uses a non-Skill locator")
        path = dataset / locator.removeprefix(prefix)
        actual = f"sha256:{sha256(path)}"
        if actual != str(batch["manifest_sha256"]):
            raise ValueError(f"registered public reference manifest drifted: {locator}")
        payload = load(path)
        if payload.get("run_id") != batch.get("run_id"):
            raise ValueError(f"registered public reference identity drifted: {locator}")
        manifests[str(batch["run_id"])] = (path, payload, actual)

    current_plan_hash = str(plan["plan_sha256"])
    current_started = min(timestamp(str(value["started_at"])) for value in coordinates.values())
    reference_plan_hashes: set[str] = set()
    reference_run_ids: set[str] = set()
    reference_manifest_evidence: list[dict[str, str]] = []
    for item in case_items:
        run_id = str(item["reference_run_id"])
        registered = manifests.get(run_id)
        if not registered:
            raise ValueError(f"Case reference run is not a registered public batch: {item['case_id']} {run_id}")
        path, payload, manifest_sha = registered
        reference = payload.get("public_playwright_runs", {}).get(str(item["case_id"]))
        if not reference:
            raise ValueError(f"registered batch omits Case: {item['case_id']}")
        if (
            payload.get("implementation_revision") != revision
            or reference.get("implementation_revision") != revision
            or reference.get("source_contract") != item.get("source_contract")
            or reference.get("route_id") != item.get("route_id")
            or reference.get("command") != item.get("command")
        ):
            raise ValueError(f"registered reference authority differs from current Case: {item['case_id']}")
        reference_plan_hash = str(payload.get("plan_sha256") or "")
        if not reference_plan_hash or reference_plan_hash == current_plan_hash:
            raise ValueError("independent rerun must use a new post-registration plan hash")
        if timestamp(str(reference["finished_at"])) >= current_started:
            raise ValueError("independent rerun started before the registered reference finished")
        reference_plan_hashes.add(reference_plan_hash)
        reference_run_ids.add(run_id)
        evidence = {"path": str(path), "sha256": manifest_sha.removeprefix("sha256:")}
        if evidence not in reference_manifest_evidence:
            reference_manifest_evidence.append(evidence)

    reference_runner_hashes = {
        str(value["sha256"]).removeprefix("sha256:")
        for _, payload, _ in manifests.values()
        for value in payload.get("authority_files", [])
        if value.get("path") == "runner-state.json"
        and payload.get("run_id") in reference_run_ids
    }
    current_runner_hash = sha256(run_root / "runner-state.json")
    if current_runner_hash in reference_runner_hashes:
        raise ValueError("independent rerun reused the registered runner-state artifact")

    attestation = {
        "schema_version": 1,
        "status": "pass",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "implementation_revision": revision,
        "current_run_id": run_root.name,
        "current_plan_sha256": current_plan_hash,
        "current_runner_state_sha256": current_runner_hash,
        "current_preflight_sha256": sha256(run_root / "execution-preflight.json"),
        "reference_run_ids": sorted(reference_run_ids),
        "reference_plan_sha256s": sorted(reference_plan_hashes),
        "reference_manifests": reference_manifest_evidence,
        "proof": {
            "same_implementation_revision": True,
            "same_case_source_contracts": True,
            "post_registration_plan_hash_differs": True,
            "current_run_started_after_references_finished": True,
            "runner_state_artifact_is_distinct": True,
            "all_local_coordinates_passed": True,
            "live_execution_forbidden": True,
        },
    }
    attestation_path = run_root / "independent-rerun-attestation.json"
    attestation_path.write_text(json.dumps(attestation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    external = [value for value in report.get("results", []) if value.get("status") == "external-blocked"]
    invalid = [value for value in report.get("results", []) if value.get("status") not in {"pass", "external-blocked"}]
    if invalid:
        raise ValueError(f"canonical report contains non-passing local results: {[value.get('item_id') for value in invalid[:10]]}")
    gate_status = "external-blocked" if external else "test-ready"
    report["gate_status"] = gate_status
    report["defects"] = []
    report["blockers"] = [f"live authorization boundaries: {len(external)}"] if external else []
    report["independent_rerun"] = {
        "status": "pass",
        "plan_sha256": current_plan_hash,
        "reference_run_ids": sorted(reference_run_ids),
        "evidence": [
            artifact(run_root, run_root / "runner-state.json"),
            artifact(run_root, run_root / "execution-preflight.json"),
            artifact(run_root, attestation_path),
        ],
    }
    report["checkpoint"].update({
        "first_trusted_failure": "none",
        "repair_required_next_action": "none",
        "independent_rerun_status": "pass",
        "final_response_allowed": True,
    })
    report["full_suite_conclusion"] = gate_status
    summary = report.get("plain_language_summary", {})
    summary.update({
        "result_reason": "全部本地必需坐标及登记后的独立复跑通过；仅保留需要独立授权的真实服务边界。",
        "user_impact": "受影响的模型选择与配置路径已在隔离 Electron 环境完成确定性回归。",
        "next_step": (
            "如需验证真实模型质量，按 Case 单独授权提供方、模型和调用预算。"
            if external
            else "保留报告与哈希供审核。"
        ),
    })
    temporary = (run_root / ".report.json.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(run_root / "report.json")
    print(json.dumps({
        "status": "pass",
        "gate_status": gate_status,
        "current_plan_sha256": current_plan_hash,
        "reference_run_ids": sorted(reference_run_ids),
        "local_coordinate_count": len(coordinates),
        "external_blocker_count": len(external),
        "attestation": str(attestation_path),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
