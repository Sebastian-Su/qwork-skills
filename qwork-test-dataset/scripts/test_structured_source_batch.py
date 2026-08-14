#!/usr/bin/env python3
"""Focused regression tests for the structured Oracle source batch runner."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile

from run_structured_oracle_source_batch import render_report_html, validate_resume_state


def expect_failure(action, message: str) -> None:
    try:
        action()
    except ValueError as error:
        assert message in str(error), str(error)
    else:
        raise AssertionError(f"expected failure containing {message!r}")


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        evidence = root / "cases" / "CASE-1" / "structured-source-result.json"
        contract = {"case_ids": ["CASE-1"]}
        contract_sha256 = hashlib.sha256(
            json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        state = {
            "run_id": root.name,
            "contract": contract,
            "contract_sha256": contract_sha256,
            "cases": [{"case_id": "CASE-1", "status": "pending", "attempt": 0}],
        }
        validate_resume_state(state, contract_sha256, root)

        evidence.parent.mkdir(parents=True)
        evidence.write_text("{}\n", encoding="utf-8")
        expect_failure(
            lambda: validate_resume_state(state, contract_sha256, root),
            "pending Case already has evidence",
        )
        evidence.unlink()

        running = json.loads(json.dumps(state))
        running["cases"][0]["status"] = "running"
        expect_failure(
            lambda: validate_resume_state(running, contract_sha256, root),
            "manual evidence audit",
        )
        expect_failure(
            lambda: validate_resume_state(state, "different-contract", root),
            "contract drifted",
        )

        report = {
            "title": "QWork WorkBuddy 结构化 Oracle 来源聚焦验证",
            "gate_status": "repair-required",
            "plain_language_summary": {
                "what_was_tested": ["两个只读结构化来源 Case"],
                "what_was_not_tested": ["完整产品全量 E2E"],
                "result_reason": "选中 Case 通过，但完整发布门禁未运行。",
                "user_impact": "本批次不改变用户数据。",
                "next_step": "审核晋升候选后继续下一批。",
            },
            "focused_conclusion": "2/2 通过",
            "full_suite_conclusion": "未运行",
            "cases": [
                {
                    "id": "CASE-1",
                    "title": "示例 Case",
                    "status": "pass",
                    "actual": "1/1 原子通过",
                    "evidence": [{"path": "cases/CASE-1/structured-source-result.json"}],
                }
            ],
        }
        html = render_report_html(report)
        assert "暂时不能提测" in html
        assert "两个只读结构化来源 Case" in html
        assert "cases/CASE-1/structured-source-result.json" in html
        assert "file://" not in html

    print("structured source batch test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
