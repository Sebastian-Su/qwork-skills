#!/usr/bin/env python3
"""Authorized live results must replace only their exact external blocker."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    script = Path(__file__).with_name("compile_release_gate_report.py")
    with tempfile.TemporaryDirectory(prefix="QWORK-E2E-TEMPORARY-DATA-DO-NOT-COMMIT-live-report-") as value:
        root = Path(value)
        repo, dataset = root / "repo", root / "dataset"
        run = root / "QWORK-E2E-TEMPORARY-DATA-DO-NOT-COMMIT" / "run"
        repo.mkdir()
        case_id = "CASE-LIVE"
        (repo / "e2e").mkdir()
        (repo / "e2e/software-company.live.spec.ts").write_text(
            'composer.fill("帮我开发一个贪吃蛇游戏"); select("z-ai/glm-5.2");\n',
            encoding="utf-8",
        )
        report_path = run / f"items/{case_id}/live-evidence/report.json"
        write(report_path, {"status": "pass", "model": "z-ai/glm-5.2"})
        authorization_path = run / "authorizations/CASE-LIVE.json"
        write(authorization_path, {
            "schema_version": 1,
            "decision": "authorized",
            "authorized_by": "requesting-user",
            "authorization_source": "current task goal",
            "authorized_at": "2026-09-04T00:00:00+00:00",
            "case_id": case_id,
            "plan_sha256": "plan-a",
            "implementation_revision": "revision-a",
            "authorized_payloads": ["帮我开发一个贪吃蛇游戏"],
            "provider": {"endpoint": "https://capi.n.cn", "model": "z-ai/glm-5.2"},
            "budget": {"max_case_invocations": 1, "timeout_seconds": 720},
            "allowed_network_origins": ["https://capi.n.cn"],
            "allowed_write_roots": [str(run / "live-state"), str(report_path.parent)],
            "environment": {
                "QWORK_EXPERT_TEAM_LIVE": "1",
                "QWORK_LIVE_STATE_HOME": str(run / "live-state"),
                "QWORK_EXPERT_TEAM_EVIDENCE_DIR": str(report_path.parent),
            },
            "cleanup_paths": ["live-state"],
            "evidence_report": str(report_path.relative_to(run)),
        })
        command = 'npx playwright test e2e/software-company.live.spec.ts -g "live"'
        source_contract = {"spec": "e2e/software-company.live.spec.ts"}
        write(run / "authorized-live-results.json", {
            "schema_version": 1,
            "plan_sha256": "plan-a",
            "implementation_revision": "revision-a",
            "coordinates": {
                f"case:{case_id}": {
                    "category": "live-authorization",
                    "status": "pass",
                    "case_id": case_id,
                    "route_id": "qwork.playwright.live",
                    "command": command,
                    "source_contract": source_contract,
                    "exit_code": 0,
                    "started_at": "2026-09-04T00:00:01+00:00",
                    "finished_at": "2026-09-04T00:01:00+00:00",
                    "cleanup_status": "pass",
                    "authorization": {
                        "path": str(authorization_path.relative_to(run)),
                        "sha256": sha256(authorization_path),
                    },
                    "artifacts": [{"path": str(report_path.relative_to(run)), "sha256": sha256(report_path)}],
                }
            },
        })
        write(run / "runner-state.json", {
            "schema_version": 2,
            "plan_sha256": "plan-a",
            "implementation_revision": "revision-a",
            "coordinates": {},
        })
        write(run / "execution-preflight.json", {"plan_sha256": "plan-a", "implementation_revision": "revision-a"})
        write(run / "plan.json", {
            "plan_sha256": "plan-a",
            "implementation_revision": "revision-a",
            "selected_case_ids": [case_id],
            "required_items": [{
                "item_id": f"case:{case_id}",
                "kind": "case",
                "case_id": case_id,
                "route_id": "qwork.playwright.live",
                "command": command,
                "authorization_required": True,
                "external_dependency_required": False,
                "source_contract": source_contract,
            }],
        })
        write(dataset / f"data/datasets/cases/{case_id}.json", {
            "id": case_id,
            "title": "live",
            "execution_contract": {
                "route_id": "qwork.playwright.live",
                "authorization": {"required": True},
                "launch": {"strategy": "command"},
                "navigation": {"kind": "ui-route"},
            },
            "ui_acceptance": {"required_screenshot_states": []},
        })
        result = subprocess.run([
            sys.executable, str(script), "--repo", str(repo), "--plan", str(run / "plan.json"),
            "--run-root", str(run), "--dataset-skill", str(dataset),
        ], text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        report = json.loads((run / "QWORK-E2E-REPORT.json").read_text(encoding="utf-8"))
        coordinate = report["results"][0]
        assert coordinate["status"] == "pass", coordinate
        assert coordinate["cleanup_status"] == "pass"
        assert not [item for item in report["results"] if item["status"] == "external-blocked"]

    print("authorized live report bridge: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
