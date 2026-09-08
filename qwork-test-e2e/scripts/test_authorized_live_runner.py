#!/usr/bin/env python3
"""Regression checks for the separate authorized-live execution boundary."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile


def load_runner():
    path = Path(__file__).with_name("run_authorized_live_case.py")
    spec = importlib.util.spec_from_file_location("qwork_authorized_live_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load authorized-live runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    runner = load_runner()
    with tempfile.TemporaryDirectory(prefix="QWORK-E2E-TEMPORARY-DATA-DO-NOT-COMMIT-live-") as value:
        run_root = Path(value).resolve()
        spec_path = run_root / "software-company.live.spec.ts"
        spec_path.write_text(
            'composer.fill("帮我开发一个贪吃蛇游戏");\nselect("z-ai/glm-5.2");\n',
            encoding="utf-8",
        )
        evidence = run_root / "items/CASE-LIVE/live-evidence"
        state = run_root / "live-state"
        authorization = {
            "schema_version": 1,
            "decision": "authorized",
            "authorized_by": "requesting-user",
            "authorization_source": "current task goal",
            "authorized_at": "2026-09-04T00:00:00+00:00",
            "case_id": "CASE-LIVE",
            "plan_sha256": "plan-a",
            "implementation_revision": "revision-a",
            "authorized_payloads": ["帮我开发一个贪吃蛇游戏"],
            "provider": {"endpoint": "https://capi.n.cn", "model": "z-ai/glm-5.2"},
            "budget": {"max_case_invocations": 1, "timeout_seconds": 720},
            "allowed_network_origins": ["https://capi.n.cn", "https://qwork.360.cn"],
            "allowed_write_roots": [str(state), str(evidence)],
            "environment": {
                "QWORK_EXPERT_TEAM_LIVE": "1",
                "QWORK_LIVE_STATE_HOME": str(state),
                "QWORK_EXPERT_TEAM_EVIDENCE_DIR": str(evidence),
            },
            "cleanup_paths": ["live-state"],
            "evidence_report": "items/CASE-LIVE/live-evidence/report.json",
        }
        plan_item = {
            "item_id": "case:CASE-LIVE",
            "kind": "case",
            "case_id": "CASE-LIVE",
            "route_id": "qwork.playwright.live",
            "command": 'npx playwright test e2e/software-company.live.spec.ts -g "live"',
            "authorization_required": True,
            "source_contract": {"spec": str(spec_path)},
        }
        validated = runner.validate_authorization(
            authorization=authorization,
            plan_item=plan_item,
            run_root=run_root,
            revision="revision-a",
            plan_sha256="plan-a",
        )
        assert validated["timeout_seconds"] == 720
        assert validated["environment"] == authorization["environment"]

        for mutation, expected in [
            ({"decision": "pending"}, "decision"),
            ({"plan_sha256": "plan-b"}, "plan"),
            ({"authorized_payloads": ["另一个请求"]}, "source"),
            ({"provider": {"endpoint": "http://capi.n.cn", "model": "z-ai/glm-5.2"}}, "HTTPS"),
            ({"budget": {"max_case_invocations": 2, "timeout_seconds": 720}}, "one Case invocation"),
            ({"environment": {"QWORK_API_KEY": "secret"}}, "secret"),
            ({"cleanup_paths": ["../outside"]}, "cleanup"),
        ]:
            candidate = {**authorization, **mutation}
            try:
                runner.validate_authorization(
                    authorization=candidate,
                    plan_item=plan_item,
                    run_root=run_root,
                    revision="revision-a",
                    plan_sha256="plan-a",
                )
            except ValueError as error:
                assert expected.lower() in str(error).lower(), (expected, str(error))
            else:
                raise AssertionError(f"unsafe authorization mutation was accepted: {mutation}")

        redacted = runner.redacted_authorization(authorization)
        serialized = json.dumps(redacted, ensure_ascii=False)
        assert "QWORK_API_KEY" not in serialized
        assert redacted["authorized_payload_sha256"]

    print("authorized live runner boundary: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
