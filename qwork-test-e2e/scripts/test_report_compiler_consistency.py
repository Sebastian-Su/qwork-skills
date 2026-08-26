#!/usr/bin/env python3
"""Ensure visual evidence gaps produce one consistent terminal status."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    script = Path(__file__).with_name("compile_release_gate_report.py")
    with tempfile.TemporaryDirectory(prefix="qwork-report-compiler-") as value:
        root = Path(value)
        repo = root / "repo"
        dataset = root / "dataset"
        run = root / "QWORK-E2E-TEMPORARY-DATA-DO-NOT-COMMIT" / "REPORT-COMPILER"
        case_id = "CASE-UI-MISSING-VISUAL"
        behavior_case_id = "CASE-UI-BEHAVIOR-ONLY-FAIL"
        drift_case_id = "CASE-DEVELOP-REVISION-DRIFT"
        plan = {
            "plan_sha256": "a" * 64,
            "implementation_revision": "b" * 40,
            "selected_case_ids": [case_id, behavior_case_id, drift_case_id],
            "required_items": [
                {"item_id": f"case:{case_id}", "kind": "case", "case_id": case_id},
                {"item_id": f"case:{behavior_case_id}", "kind": "case", "case_id": behavior_case_id},
                {
                    "item_id": f"case:{drift_case_id}",
                    "kind": "case",
                    "case_id": drift_case_id,
                    "command": "manual-blocked",
                    "revision_drift": True,
                },
            ],
        }
        case = {
            "id": case_id,
            "title": "visual evidence status consistency",
            "execution_contract": {
                "route_id": "route:test",
                "authorization": {"required": False},
                "launch": {"strategy": "playwright"},
                "navigation": {"kind": "ui-route"},
            },
            "ui_acceptance": {"required_screenshot_states": ["entry", "final-state"]},
        }
        write(run / "plan.json", plan)
        write(run / "execution-preflight.json", {"executed_model_calls": 0})
        write(run / "runner-state.json", {
            "coordinates": {
                f"case:{case_id}": {"status": "pass", "stdout": "stdout.log", "stderr": "stderr.log"},
                f"case:{behavior_case_id}": {"status": "fail", "stdout": "stdout.log", "stderr": "stderr.log"},
            }
        })
        run.mkdir(parents=True, exist_ok=True)
        (run / "stdout.log").write_text("pass\n", encoding="utf-8")
        (run / "stderr.log").write_text("", encoding="utf-8")
        write(dataset / "data/datasets/cases" / f"{case_id}.json", case)
        behavior_case = json.loads(json.dumps(case))
        behavior_case["id"] = behavior_case_id
        behavior_case["title"] = "behavior-only UI failure"
        behavior_case["ui_acceptance"] = {"required_screenshot_states": []}
        write(dataset / "data/datasets/cases" / f"{behavior_case_id}.json", behavior_case)
        drift_case = json.loads(json.dumps(case))
        drift_case["id"] = drift_case_id
        drift_case["title"] = "accepted develop E2E absent from feature HEAD"
        drift_case["execution_contract"]["launch"] = {
            "strategy": "command",
            "command_or_tool": "npx playwright test e2e/develop-only.spec.ts -g accepted",
        }
        write(dataset / "data/datasets/cases" / f"{drift_case_id}.json", drift_case)
        repo.mkdir(parents=True)
        result = subprocess.run([
            sys.executable, str(script), "--repo", str(repo), "--plan", str(run / "plan.json"),
            "--run-root", str(run), "--dataset-skill", str(dataset),
        ], text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        report = json.loads((run / "QWORK-E2E-REPORT.json").read_text(encoding="utf-8"))
        statuses = {
            report["results"][0]["status"],
            report["cases"][0]["status"],
            report["case_results"][0]["status"],
        }
        if statuses != {"inconclusive"}:
            raise AssertionError(f"visual-gap statuses diverged: {statuses}")
        if report["results"][0]["failure_classification"] != "evidence":
            raise AssertionError("visual gap was not classified as evidence")
        if report["results"][1]["status"] != "fail":
            raise AssertionError("behavior-only UI failure did not remain a product failure")
        behavior_human = next(value for value in report["cases"] if value["id"] == behavior_case_id)
        if behavior_human["visual_evidence_gap"]:
            raise AssertionError("behavior-only UI failure incorrectly required a screenshot")
        drift_result = next(value for value in report["results"] if value["item_id"] == f"case:{drift_case_id}")
        if drift_result["status"] != "runner-gap":
            raise AssertionError("cross-revision Case was not reported as a runner gap")
        next_step = report["plain_language_summary"]["next_step"]
        if "1 个 Case 补齐本地 runner" not in next_step or "776" in next_step:
            raise AssertionError(f"next step did not use dynamic runner-gap counts: {next_step}")
        print("report compiler visual-status consistency: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
