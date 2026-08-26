#!/usr/bin/env python3
"""Reverse tests for the QWork release-gate planner/evaluator final lock."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--base", default="develop")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    repo = args.repo.resolve()
    skill = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="qwork-release-gate-") as value:
        root = Path(value) / "QWORK-E2E-TEMPORARY-DATA-DO-NOT-COMMIT" / "RELEASE-GATE"
        plan_path = root / "plan.json"
        planned = run([sys.executable, str(skill / "scripts/build_release_gate_plan.py"), "--repo", str(repo), "--base", args.base, "--head", args.head, "--scope", "full", "--output", str(plan_path)], repo)
        if planned.returncode:
            raise RuntimeError(planned.stderr or planned.stdout)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        dataset_root = (repo / ".agents/skills/qwork-test-dataset").resolve()
        case_files = {
            path.stem: json.loads(path.read_text(encoding="utf-8"))
            for path in (dataset_root / "data/datasets/cases").glob("*.json")
        }
        drift_case_ids = {
            case_id
            for case_id, case in case_files.items()
            if (
                (case.get("execution_contract", {}).get("observability", {}).get("source_contract") or {}).get("execution_revision")
                not in {None, plan["implementation_revision"]}
            )
        }
        stale_runnable = []
        classified_drift = set()
        for item in plan["required_items"]:
            if item.get("kind") != "case":
                continue
            if item.get("case_id") in drift_case_ids:
                classified_drift.add(item["case_id"])
                if item.get("command") != "manual-blocked" or item.get("execution_readiness") == "ready":
                    stale_runnable.append(item["item_id"])
        if classified_drift != drift_case_ids:
            raise RuntimeError("planner did not preserve the complete cross-revision Case set")
        if stale_runnable:
            raise RuntimeError(
                "planner exposed source tests from another revision as runnable in the current checkout: "
                + ", ".join(stale_runnable[:20])
            )
        report = {
            "project": "qwork",
            "run_id": "reverse-missing-results",
            "title": "QWork release gate reverse test",
            "generated_at": plan["created_at"],
            "gate_status": "repair-required",
            "plan_sha256": plan["plan_sha256"],
            "implementation_revision": plan["implementation_revision"],
            "plain_language_summary": {
                "what_was_tested": ["门禁对缺失结果能否 fail closed"],
                "what_was_not_tested": ["产品功能未在此反向夹具中执行"],
                "result_reason": "该夹具故意不提供必需结果。",
                "user_impact": "验证不完整证据不会被包装成可以提测。",
                "next_step": "执行所有必需项并保存证据。",
            },
            "scope": {"included": ["release gate reverse test"], "excluded": ["product execution"]},
            "environment": {"implementation_revision": plan["implementation_revision"]},
            "results": [],
            "cases": [{"id": case_id, "title": case_id, "status": "pending", "executor": "electron-cdp", "ui": True, "ui_attempted": False, "required_screenshot_states": ["entry", "transition", "final-state"], "evidence": []} for case_id in plan["selected_case_ids"]],
            "case_results": [{"case_id": case_id, "status": "pending"} for case_id in plan["selected_case_ids"]],
            "commands": [],
            "defects": [],
            "blockers": [],
            "residual_risks": [],
            "cleanup": {"status": "pending", "details": "reverse test intentionally incomplete"},
            "independent_rerun": {"status": "pending"},
            "checkpoint": {
                "current_implementation_revision": plan["implementation_revision"],
                "current_plan_hash": plan["plan_sha256"],
                "first_trusted_failure": "missing required results",
                "repair_required_next_action": "execute every required item and record current evidence",
                "cleanup_status": "pending",
                "independent_rerun_status": "pending",
                "final_response_allowed": False,
            },
        }
        (root / "QWORK-E2E-REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        evaluated = run([sys.executable, str(skill / "scripts/evaluate_release_gate.py"), "--repo", str(repo), "--plan", str(plan_path), "--run-root", str(root)], repo)
        try:
            verdict = json.loads(evaluated.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"evaluator did not return JSON: {evaluated.stdout}\n{evaluated.stderr}") from error
        if evaluated.returncode == 0 or verdict.get("gate_status") != "repair-required" or verdict.get("final_response_allowed") is not False:
            raise RuntimeError(f"missing results did not fail closed: {verdict}")
        failures = verdict.get("all_failures") or []
        if not any("missing required results" in str(item) for item in failures):
            raise RuntimeError(f"missing result reason absent: {verdict}")
        if not any("execution contract is not reference-run ready" in str(item) for item in failures):
            raise RuntimeError(f"partial Case readiness was not rejected: {verdict}")
        print(json.dumps({"status": "ok", "reverse_fixture": "missing-results-and-partial-readiness", "gate_status": verdict["gate_status"], "final_response_allowed": verdict["final_response_allowed"], "selected_cases": len(plan["selected_case_ids"]), "required_items": len(plan["required_items"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
