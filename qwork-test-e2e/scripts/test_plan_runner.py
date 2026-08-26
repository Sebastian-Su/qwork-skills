#!/usr/bin/env python3
"""Reverse checks for release-plan classification and live isolation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    runner = Path(__file__).with_name("run_release_gate_plan.py")
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
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        revision_drift_count = sum(
            1
            for item in plan["required_items"]
            if item.get("kind") == "case" and item.get("revision_drift") is True
        )
        if classification.get("runner-gap", 0) < revision_drift_count:
            raise RuntimeError("cross-revision E2E coordinates were not isolated as runner gaps")
        planned_ids = {
            str(item["item_id"])
            for item in plan["required_items"]
        }
        required_dataset_gates = {
            "gate:document-case-coverage",
            "gate:structured-oracle-coverage",
            "gate:workbuddy-interaction-inventory",
            "gate:live-case-authorization",
        }
        if not required_dataset_gates <= planned_ids:
            raise RuntimeError(
                "full plan omitted Dataset governance gates: "
                + ", ".join(sorted(required_dataset_gates - planned_ids))
            )
        if preflight["live_execution_allowed"] is not False or preflight["shell_evaluation_allowed"] is not False:
            raise RuntimeError("runner preflight permits live or shell execution")
        state = {"schema_version": 1, "plan_sha256": preflight["plan_sha256"], "implementation_revision": preflight["implementation_revision"], "coordinates": {"gate:source-acceptance": {"category": "gate", "status": "running"}}}
        (root / "runner-state.json").write_text(json.dumps(state), encoding="utf-8")
        blocked = subprocess.run([sys.executable, str(runner), "--repo", str(repo), "--plan", str(args.plan.resolve()), "--run-root", str(root), "--preflight-only"], cwd=repo, text=True, capture_output=True)
        if blocked.returncode == 0 or "non-terminal prior coordinates" not in blocked.stderr:
            raise RuntimeError("running coordinate did not stop the batch before execution")
        state["coordinates"] = {"case:synthetic": {"category": "gate", "status": "pass"}}
        (root / "runner-state.json").write_text(json.dumps(state), encoding="utf-8")
        unknown = subprocess.run([sys.executable, str(runner), "--repo", str(repo), "--plan", str(args.plan.resolve()), "--run-root", str(root), "--preflight-only"], cwd=repo, text=True, capture_output=True)
        if unknown.returncode == 0 or "unknown coordinate" not in unknown.stderr:
            raise RuntimeError("unknown prior coordinate did not stop the batch before execution")
        print(json.dumps({"status": "ok", "classification": classification, "required_items": preflight["required_item_count"], "revision_drift_runner_gaps": revision_drift_count, "live_and_shell_disabled": True, "running_coordinate_fail_closed": True, "unknown_coordinate_fail_closed": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
