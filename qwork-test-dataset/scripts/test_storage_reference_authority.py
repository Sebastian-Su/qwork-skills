#!/usr/bin/env python3
"""Focused regression test for deterministic WorkBuddy storage authority."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile

from build_product_baseline import apply_storage_reference_authority


def sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        report_path = root / "storage-case-result.json"
        runner_path = root / "runner.py"
        runner_path.write_text("# deterministic runner\n", encoding="utf-8")
        report = {
            "schema_version": 1,
            "case_id": "CASE-1",
            "source_inventory_sha256": "inventory-sha",
            "disposition_canonical_sha256": "disposition-sha",
            "required_atom_count": 2,
            "passed_atom_count": 2,
            "failed_atom_count": 0,
            "status": "pass",
            "results": [
                {"atom_id": "WORKBUDDY-STORAGE:A", "status": "pass"},
                {"atom_id": "WORKBUDDY-STORAGE:B", "status": "pass"},
            ],
            "errors": [],
        }
        report_path.write_text(json.dumps(report), encoding="utf-8")
        reference = {
            "run_id": "storage-reference-1",
            "report": str(report_path),
            "report_sha256": sha256(report_path),
            "runner_sha256": sha256(runner_path),
            "disposition_canonical_sha256": "disposition-sha",
            "implementation_revision": "head-sha",
            "verified_at": "2026-08-14T00:00:00+00:00",
        }
        case = {
            "id": "CASE-1",
            "derived_requirements": [
                {"source_atom_ids": ["WORKBUDDY-STORAGE:A", "WORKBUDDY-STORAGE:B"]}
            ],
            "execution_contract": {
                "route_id": "qwork.dataset.workbuddy-storage.case-1",
                "readiness": "partial",
                "reference_run": {"status": "pending"},
                "blockers": ["pending"],
                "observability": {"artifacts": ["storage-case-result.json"]},
            },
            "verification": {"last_outcome": "pending"},
        }

        apply_storage_reference_authority(
            case=case,
            reference=reference,
            skill_root=root,
            runner_path=runner_path,
            expected_inventory_sha256="inventory-sha",
            expected_disposition_sha256="disposition-sha",
            head="head-sha",
        )
        contract = case["execution_contract"]
        assert contract["readiness"] == "ready"
        assert contract["reference_run"]["status"] == "passed"
        assert contract["blockers"] == []
        assert case["verification"]["last_outcome"] == "pass"

        stale_reference = dict(reference, runner_sha256="sha256:stale")
        try:
            apply_storage_reference_authority(
                case=case,
                reference=stale_reference,
                skill_root=root,
                runner_path=runner_path,
                expected_inventory_sha256="inventory-sha",
                expected_disposition_sha256="disposition-sha",
                head="head-sha",
            )
        except ValueError as error:
            assert "runner hash drifted" in str(error)
        else:
            raise AssertionError("runner drift must fail closed")

    print("storage reference authority test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
