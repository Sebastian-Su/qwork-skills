#!/usr/bin/env python3
"""Execute one user-authorized live Case without weakening the local release runner."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
from typing import Any

from authorized_live_result import (
    LIVE_RESULTS_NAME,
    load,
    redacted_authorization,
    sha256_file,
    validate_authorization,
)
from external_artifact_storage import validate_external_run_root
from run_release_gate_plan import classify, plan_hash, validate_authority


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def artifact(root: Path, path: Path) -> dict[str, str]:
    resolved = path.resolve()
    resolved.relative_to(root.resolve())
    return {"path": str(resolved.relative_to(root.resolve())), "sha256": sha256_file(resolved)}


def collect_artifacts(run_root: Path, item_root: Path, authorization_path: Path) -> list[dict[str, str]]:
    excluded = {authorization_path.resolve(), (run_root / LIVE_RESULTS_NAME).resolve()}
    paths = sorted(
        path for path in item_root.rglob("*")
        if path.is_file() and path.resolve() not in excluded
    )
    return [artifact(run_root, path) for path in paths]


def execute_process(
    argv: list[str], *, cwd: Path, environment: dict[str, str], timeout_seconds: int
) -> tuple[int, str, str, str | None]:
    windows = os.name == "nt"
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=not windows,
        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if windows else 0),
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return process.returncode, stdout, stderr, None
    except subprocess.TimeoutExpired:
        if windows:
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            if windows:
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        return 1, stdout, stderr + "\nauthorized live Case timed out\n", "authorized live Case timed out"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--dataset-skill", type=Path)
    parser.add_argument("--seed-state", type=Path)
    args = parser.parse_args()

    repo = args.repo.resolve()
    dataset = (args.dataset_skill or repo / ".agents/skills/qwork-test-dataset").resolve()
    skill = Path(__file__).resolve().parent.parent
    run_root = validate_external_run_root(args.run_root, protected_roots=[repo, dataset, skill])
    plan = load(args.plan.resolve())
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    if plan.get("plan_sha256") != plan_hash(plan):
        raise ValueError("plan_sha256 is stale or invalid")
    if plan.get("implementation_revision") != revision:
        raise ValueError("plan targets another implementation revision")
    validate_authority(repo, plan, dataset, skill)

    cases = {path.stem: load(path) for path in sorted((dataset / "data/datasets/cases").glob("*.json"))}
    item_id = f"case:{args.case_id}"
    items = {str(item["item_id"]): item for item in plan.get("required_items", [])}
    item = items.get(item_id)
    if not item:
        raise ValueError(f"Case is absent from the frozen plan: {args.case_id}")
    coordinate = classify(plan, cases).get(item_id)
    if not coordinate or coordinate.get("category") != "live-authorization":
        raise ValueError("Case is not classified as live-authorization")

    authorization_path = args.authorization.resolve()
    authorization_path.relative_to(run_root)
    authorization = load(authorization_path)
    validated = validate_authorization(
        authorization=authorization,
        plan_item=item,
        run_root=run_root,
        revision=revision,
        plan_sha256=str(plan["plan_sha256"]),
        repo=repo,
    )
    results_path = run_root / LIVE_RESULTS_NAME
    if results_path.exists():
        raise ValueError("authorized live result already exists; a second invocation is forbidden")

    environment = {**os.environ, **validated["environment"]}
    item_root = run_root / "items" / args.case_id
    logs = item_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    output_dir = item_root / "playwright-output"
    json_report = item_root / "playwright-report.json"
    environment["QWORK_PLAYWRIGHT_JSON_FILE"] = str(json_report)
    state_home = Path(validated["environment"].get("QWORK_LIVE_STATE_HOME", "")).resolve()
    if args.seed_state:
        seed = args.seed_state.resolve()
        if not seed.is_dir():
            raise ValueError("seed state is not a readable directory")
        if state_home.exists():
            raise ValueError("authorized live state already exists")
        shutil.copytree(seed, state_home)
    Path(validated["environment"].get("QWORK_EXPERT_TEAM_EVIDENCE_DIR", item_root)).mkdir(
        parents=True, exist_ok=True
    )

    base_argv = shlex.split(str(item["command"]))
    executed_argv = [*base_argv, "--output", str(output_dir), "--trace", "on"]
    stdout_path, stderr_path = logs / "stdout.log", logs / "stderr.log"
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    exit_code = 1
    failure: str | None = None
    try:
        exit_code, stdout, stderr, failure = execute_process(
            executed_argv,
            cwd=repo,
            environment=environment,
            timeout_seconds=int(validated["timeout_seconds"]),
        )
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
    except Exception as error:
        stderr_path.write_text(f"authorized live Case could not start: {error}\n", encoding="utf-8")
        stdout_path.write_text("", encoding="utf-8")
        failure = f"authorized live Case could not start: {error}"
    finally:
        for cleanup_path in validated["cleanup_paths"]:
            if cleanup_path.is_dir():
                shutil.rmtree(cleanup_path)
            elif cleanup_path.exists():
                cleanup_path.unlink()

    evidence_report = validated["evidence_report"]
    if exit_code == 0:
        if not evidence_report.is_file():
            failure = "live Case passed without its evidence report"
            exit_code = 1
        else:
            report = load(evidence_report)
            selected_model = str(report.get("model") or "")
            if report.get("status") != "pass" or validated["provider"]["model"].lower() not in selected_model.lower():
                failure = "live evidence does not prove the authorized provider model"
                exit_code = 1

    finished = dt.datetime.now(dt.timezone.utc).isoformat()
    redacted_path = run_root / "authorizations" / f"{args.case_id}.redacted.json"
    atomic_json(redacted_path, redacted_authorization(authorization))
    retained = collect_artifacts(run_root, item_root, authorization_path)
    retained.extend([artifact(run_root, authorization_path), artifact(run_root, redacted_path)])
    live_coordinate: dict[str, Any] = {
        "category": "live-authorization",
        "status": "pass" if exit_code == 0 else "fail",
        "case_id": args.case_id,
        "route_id": item.get("route_id"),
        "command": item.get("command"),
        "executed_argv": executed_argv,
        "source_contract": item.get("source_contract"),
        "exit_code": 0 if exit_code == 0 else 1,
        "started_at": started,
        "finished_at": finished,
        "cleanup_status": "pass",
        "authorization": artifact(run_root, authorization_path),
        "artifacts": retained,
    }
    if failure:
        live_coordinate["error"] = failure
    payload = {
        "schema_version": 1,
        "plan_sha256": plan["plan_sha256"],
        "implementation_revision": revision,
        "coordinates": {item_id: live_coordinate},
    }
    atomic_json(results_path, payload)
    print(json.dumps({
        "status": live_coordinate["status"],
        "case_id": args.case_id,
        "result": str(results_path),
        "cleanup_status": "pass",
        "artifact_count": len(retained),
    }, ensure_ascii=False))
    return 0 if exit_code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
