#!/usr/bin/env python3
"""Regression test: runner drift retains history but removes current authority."""

from __future__ import annotations

from build_product_baseline import mark_private_reference_stale


def main() -> int:
    case = {
        "execution_contract": {
            "readiness": "ready",
            "reference_run": {
                "status": "passed",
                "run_id": "old-run",
                "verified_at": "2026-08-13T00:00:00+00:00",
                "environment": "old runner",
            },
            "blockers": [],
        },
        "verification": {"last_outcome": "pass"},
    }
    reference = {"run_id": "old-run"}
    report = {
        "finished_at": "2026-08-13T00:00:00+00:00",
        "source": {"implementation_revision": "head-sha"},
    }

    mark_private_reference_stale(
        case,
        reference,
        report,
        "runner hash changed",
        current_head="new-head-sha",
    )

    contract = case["execution_contract"]
    assert contract["readiness"] == "partial"
    assert contract["reference_run"]["status"] == "pending"
    assert contract["reference_run"]["run_id"] == "old-run"
    assert contract["blockers"] == ["runner hash changed"]
    assert case["verification"]["last_outcome"] == "pending"
    assert case["verification"]["implementation_revision"] == "new-head-sha"
    assert "stale private reference old-run" in case["verification"]["status_reason"]
    print("private reference invalidation test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
