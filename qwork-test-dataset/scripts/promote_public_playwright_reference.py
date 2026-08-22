#!/usr/bin/env python3
"""Freeze one passing public Playwright release-gate run for manual registration."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any


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


def copy_hashed(source_root: Path, destination_root: Path, relative: str, expected: str) -> dict[str, str]:
    source = (source_root / relative).resolve()
    source.relative_to(source_root)
    if not source.is_file():
        raise ValueError(f"reference artifact is missing: {relative}")
    actual = sha256(source)
    if actual != expected.removeprefix("sha256:"):
        raise ValueError(f"reference artifact hash drifted: {relative}")
    destination = destination_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {"path": relative, "sha256": f"sha256:{actual}"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--skill-root", type=Path)
    args = parser.parse_args()

    repo = args.repo.resolve()
    plan_path = args.plan.resolve()
    run_root = args.run_root.resolve()
    skill_root = (args.skill_root or Path(__file__).resolve().parent.parent).resolve()
    destination = skill_root / "data/runs" / args.run_id
    if destination.exists():
        raise ValueError(f"reference destination already exists: {destination}")

    plan = load(plan_path)
    state = load(run_root / "runner-state.json")
    preflight = load(run_root / "execution-preflight.json")
    current_revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    if plan.get("plan_sha256") != plan_hash(plan):
        raise ValueError("plan hash is invalid")
    if plan.get("implementation_revision") != current_revision:
        raise ValueError("plan does not target the current implementation revision")
    if state.get("plan_sha256") != plan.get("plan_sha256") or state.get("implementation_revision") != current_revision:
        raise ValueError("runner state does not belong to this plan/revision")
    if preflight.get("plan_sha256") != plan.get("plan_sha256") or preflight.get("implementation_revision") != current_revision:
        raise ValueError("preflight does not belong to this plan/revision")
    if preflight.get("live_execution_allowed") is not False:
        raise ValueError("public reference run must forbid live execution")

    coordinates = state.get("coordinates")
    if not isinstance(coordinates, dict):
        raise ValueError("runner state coordinates must be an object")
    items = {str(item["item_id"]): item for item in plan.get("required_items", [])}
    cases = {
        path.stem: load(path)
        for path in (skill_root / "data/datasets/cases").glob("*.json")
    }
    expected_local = {
        item_id
        for item_id, item in items.items()
        if not (
            item.get("kind") == "case"
            and (item.get("authorization_required") or item.get("external_dependency_required"))
        )
    }
    missing = sorted(expected_local - set(coordinates))
    failed = sorted(
        item_id for item_id in expected_local
        if item_id in coordinates and coordinates[item_id].get("status") != "pass"
    )
    if missing or failed:
        raise ValueError(f"reference run is not fully passing: missing={missing[:10]} failed={failed[:10]}")
    unexpected_live = sorted(
        item_id for item_id in coordinates
        if items.get(item_id, {}).get("authorization_required")
    )
    if unexpected_live:
        raise ValueError(f"reference run executed live-authorized coordinates: {unexpected_live[:10]}")

    destination.mkdir(parents=True)
    authority_files = []
    for name, source in (
        ("plan.json", plan_path),
        ("runner-state.json", run_root / "runner-state.json"),
        ("execution-preflight.json", run_root / "execution-preflight.json"),
    ):
        target = destination / name
        shutil.copy2(source, target)
        authority_files.append({"path": name, "sha256": f"sha256:{sha256(target)}"})

    promoted: dict[str, Any] = {}
    for item_id, item in sorted(items.items()):
        if (
            item.get("kind") != "case"
            or item.get("authorization_required")
            or item.get("external_dependency_required")
        ):
            continue
        case_id = str(item["case_id"])
        case = cases.get(case_id)
        coordinate = coordinates.get(item_id)
        if not case or not coordinate:
            raise ValueError(f"missing current Case or coordinate: {case_id}")
        contract = case["execution_contract"]
        if not str(contract["route_id"]).startswith("qwork.playwright."):
            continue
        if coordinate.get("category") != "deterministic-playwright" or coordinate.get("exit_code") != 0:
            raise ValueError(f"public Playwright coordinate is not a deterministic pass: {case_id}")
        source_contract = contract.get("observability", {}).get("source_contract") or {}
        if item.get("source_contract") != source_contract:
            raise ValueError(f"source contract drifted since the run: {case_id}")
        if item.get("route_id") != contract.get("route_id") or item.get("command") != contract.get("launch", {}).get("command_or_tool"):
            raise ValueError(f"route or command drifted since the run: {case_id}")

        copied: list[dict[str, str]] = []
        candidates = []
        for key in ("stdout", "stderr"):
            if coordinate.get(key):
                candidates.append({"path": coordinate[key], "sha256": coordinate.get(f"{key}_sha256")})
        candidates.extend(coordinate.get("artifacts") or [])
        seen: set[str] = set()
        for artifact in candidates:
            relative = str(artifact.get("path") or "")
            expected = str(artifact.get("sha256") or "")
            if not relative or not expected or relative in seen:
                continue
            seen.add(relative)
            copied.append(copy_hashed(run_root, destination, relative, expected))

        manifest_relative = f"items/{case_id}/evidence-manifest.json"
        manifest = load(run_root / manifest_relative)
        if manifest.get("case_id") != case_id or manifest.get("status") != "pass":
            raise ValueError(f"evidence manifest identity/status mismatch: {case_id}")
        evidence_entries = manifest.get("entries") or []
        screenshot_states = {
            str(value.get("state"))
            for value in evidence_entries
            if value.get("kind") == "screenshot"
        }
        required_states = list(item.get("required_screenshot_states") or [])
        missing_states = sorted(set(required_states) - screenshot_states)
        if missing_states:
            raise ValueError(f"reference screenshots are incomplete: {case_id} {missing_states}")
        for evidence in evidence_entries:
            relative = str(evidence.get("path") or "")
            expected = str(evidence.get("sha256") or "")
            if not relative or not expected or relative in seen:
                continue
            seen.add(relative)
            copied.append(copy_hashed(run_root, destination, relative, expected))
        if manifest_relative not in seen:
            copied.append(copy_hashed(run_root, destination, manifest_relative, sha256(run_root / manifest_relative)))

        promoted[case_id] = {
            "run_id": args.run_id,
            "implementation_revision": current_revision,
            "plan_sha256": str(plan["plan_sha256"]),
            "route_id": str(item["route_id"]),
            "command": str(item["command"]),
            "source_contract": source_contract,
            "required_screenshot_states": required_states,
            "finished_at": str(coordinate["finished_at"]),
            "artifacts": copied,
        }

    manifest = {
        "schema_version": 1,
        "run_id": args.run_id,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "implementation_revision": current_revision,
        "plan_sha256": str(plan["plan_sha256"]),
        "zero_real_model_calls": True,
        "authority_files": authority_files,
        "public_playwright_runs": promoted,
    }
    manifest_path = destination / "public-playwright-reference.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "promotion-candidate",
        "run_id": args.run_id,
        "case_count": len(promoted),
        "manifest": f"skill://qwork-test-dataset/data/runs/{args.run_id}/public-playwright-reference.json",
        "manifest_sha256": f"sha256:{sha256(manifest_path)}",
        "implementation_revision": current_revision,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
