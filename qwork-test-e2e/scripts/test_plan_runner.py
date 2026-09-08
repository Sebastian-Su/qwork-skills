#!/usr/bin/env python3
"""Reverse checks for release-plan classification and live isolation."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def load_runner():
    path = Path(__file__).with_name("run_release_gate_plan.py")
    spec = importlib.util.spec_from_file_location("qwork_plan_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    runner = Path(__file__).with_name("run_release_gate_plan.py")
    runner_module = load_runner()
    plan_data = json.loads(args.plan.read_text(encoding="utf-8"))
    dataset = (repo / ".agents/skills/qwork-test-dataset").resolve()
    cases = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((dataset / "data/datasets/cases").glob("*.json"))
    }
    classified = runner_module.classify(plan_data, cases)
    source_coordinate = classified["gate:source-acceptance"]
    source_signature = runner_module.coordinate_signature(source_coordinate)
    with tempfile.TemporaryDirectory(prefix="qwork-plan-runner-") as value:
        root = Path(value) / "QWORK-E2E-TEMPORARY-DATA-DO-NOT-COMMIT" / "PLAN-RUNNER"
        result = subprocess.run([sys.executable, str(runner), "--repo", str(repo), "--plan", str(args.plan.resolve()), "--run-root", str(root), "--preflight-only"], cwd=repo, text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        preflight = json.loads((root / "execution-preflight.json").read_text(encoding="utf-8"))
        classification = preflight["classification"]
        if sum(classification.values()) != preflight["required_item_count"]:
            raise RuntimeError("classification is not closed over every required item")
        if classification.get("live-authorization", 0) <= 0:
            raise RuntimeError("full plan did not isolate any live-authorized Case")
        revision_drift_count = sum(
            1
            for item in plan_data["required_items"]
            if item.get("kind") == "case" and item.get("revision_drift") is True
        )
        if classification.get("runner-gap", 0) < revision_drift_count:
            raise RuntimeError("cross-revision E2E coordinates were not isolated as runner gaps")
        planned_ids = {
            str(item["item_id"])
            for item in plan_data["required_items"]
        }
        required_dataset_gates = {
            "gate:document-case-coverage",
            "gate:structured-oracle-coverage",
            "gate:workbuddy-interaction-inventory",
            "gate:live-case-authorization",
            "gate:governance",
        }
        if not required_dataset_gates <= planned_ids:
            raise RuntimeError(
                "full plan omitted Dataset governance gates: "
                + ", ".join(sorted(required_dataset_gates - planned_ids))
            )
        if preflight["live_execution_allowed"] is not False or preflight["shell_evaluation_allowed"] is not False:
            raise RuntimeError("runner preflight permits live or shell execution")
        state = {"schema_version": 2, "plan_sha256": preflight["plan_sha256"], "implementation_revision": preflight["implementation_revision"], "coordinates": {"gate:source-acceptance": {"category": "gate", "coordinate_sha256": source_signature, "status": "running"}}}
        (root / "runner-state.json").write_text(json.dumps(state), encoding="utf-8")
        blocked = subprocess.run([sys.executable, str(runner), "--repo", str(repo), "--plan", str(args.plan.resolve()), "--run-root", str(root), "--preflight-only"], cwd=repo, text=True, capture_output=True)
        if blocked.returncode == 0 or "non-terminal prior coordinates" not in blocked.stderr:
            raise RuntimeError("running coordinate did not stop the batch before execution")
        state["coordinates"] = {"case:synthetic": {"category": "gate", "status": "pass"}}
        (root / "runner-state.json").write_text(json.dumps(state), encoding="utf-8")
        unknown = subprocess.run([sys.executable, str(runner), "--repo", str(repo), "--plan", str(args.plan.resolve()), "--run-root", str(root), "--preflight-only"], cwd=repo, text=True, capture_output=True)
        if unknown.returncode == 0 or "unknown coordinate" not in unknown.stderr:
            raise RuntimeError("unknown prior coordinate did not stop the batch before execution")
        logs = root / "logs"
        logs.mkdir(exist_ok=True)
        stdout = logs / "gate-source-acceptance.stdout.log"
        stderr = logs / "gate-source-acceptance.stderr.log"
        stdout.write_text("real output\n", encoding="utf-8")
        stderr.write_text("", encoding="utf-8")
        state["coordinates"] = {
            "gate:source-acceptance": {
                "category": "gate",
                "coordinate_sha256": source_signature,
                "status": "pass",
                "exit_code": 0,
                "stdout": str(stdout.relative_to(root)),
                "stdout_sha256": "0" * 64,
                "stderr": str(stderr.relative_to(root)),
                "stderr_sha256": "0" * 64,
                "artifacts": [],
            }
        }
        (root / "runner-state.json").write_text(json.dumps(state), encoding="utf-8")
        tampered = subprocess.run([sys.executable, str(runner), "--repo", str(repo), "--plan", str(args.plan.resolve()), "--run-root", str(root), "--preflight-only"], cwd=repo, text=True, capture_output=True)
        if tampered.returncode == 0 or "runner evidence hash mismatch" not in tampered.stderr:
            raise RuntimeError("tampered prior evidence did not stop the batch before execution")
        print(json.dumps({"status": "ok", "classification": classification, "required_items": preflight["required_item_count"], "revision_drift_runner_gaps": revision_drift_count, "live_and_shell_disabled": True, "running_coordinate_fail_closed": True, "unknown_coordinate_fail_closed": True, "tampered_evidence_fail_closed": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
