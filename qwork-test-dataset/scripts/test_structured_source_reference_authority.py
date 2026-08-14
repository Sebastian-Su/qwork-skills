#!/usr/bin/env python3
"""Focused regression test for deterministic structured source authority."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile

from build_product_baseline import (
    apply_structured_source_reference_authority,
    expand_deterministic_reference_batches,
)


def sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        report_path = root / "structured-source-result.json"
        runner_path = root / "runner.py"
        runner_path.write_text("# deterministic runner\n", encoding="utf-8")
        report = {
            "schema_version": 1,
            "case_id": "CASE-1",
            "source_id": "WORKBUDDY-ORACLE-5-3-5-SOURCE",
            "source_locator": "git:source-rev:e2e/oracles/source.json",
            "source_content_sha256": "sha256:source",
            "required_atom_count": 2,
            "passed_atom_count": 2,
            "failed_atom_count": 0,
            "status": "pass",
            "results": [
                {"atom_id": "WORKBUDDY-ORACLE-5-3-5-SOURCE:PTR:A", "status": "pass"},
                {"atom_id": "WORKBUDDY-ORACLE-5-3-5-SOURCE:PTR:B", "status": "pass"},
            ],
            "errors": [],
        }
        report_path.write_text(json.dumps(report), encoding="utf-8")
        reference = {
            "run_id": "structured-reference-1",
            "report": str(report_path),
            "report_sha256": sha256(report_path),
            "runner_sha256": sha256(runner_path),
            "source_inventory_canonical_sha256": "source-inventory-sha",
            "implementation_revision": "head-sha",
            "verified_at": "2026-08-14T00:00:00+00:00",
        }
        case = {
            "id": "CASE-1",
            "sources": [
                {
                    "source_id": "WORKBUDDY-ORACLE-5-3-5-SOURCE",
                    "stable_source_id": "git:source-rev:e2e/oracles/source.json",
                    "content_hash": "sha256:source",
                }
            ],
            "derived_requirements": [
                {
                    "source_atom_ids": [
                        "WORKBUDDY-ORACLE-5-3-5-SOURCE:PTR:A",
                        "WORKBUDDY-ORACLE-5-3-5-SOURCE:PTR:B",
                    ]
                }
            ],
            "execution_contract": {
                "route_id": "qwork.dataset.structured-oracle-source.case-1",
                "readiness": "partial",
                "reference_run": {"status": "pending"},
                "blockers": ["pending"],
                "observability": {"artifacts": ["structured-source-result.json"]},
            },
            "verification": {"last_outcome": "pending"},
        }

        apply_structured_source_reference_authority(
            case=case,
            reference=reference,
            skill_root=root,
            runner_path=runner_path,
            expected_source_inventory_sha256="source-inventory-sha",
            head="head-sha",
        )
        contract = case["execution_contract"]
        assert contract["readiness"] == "ready"
        assert contract["reference_run"]["status"] == "passed"
        assert contract["blockers"] == []
        assert case["verification"]["last_outcome"] == "pass"

        stale_reference = dict(reference, runner_sha256="sha256:stale")
        apply_structured_source_reference_authority(
            case=case,
            reference=stale_reference,
            skill_root=root,
            runner_path=runner_path,
            expected_source_inventory_sha256="source-inventory-sha",
            head="head-sha",
        )
        contract = case["execution_contract"]
        assert contract["readiness"] == "partial"
        assert contract["reference_run"]["status"] == "pending"
        assert case["verification"]["last_outcome"] == "pending"
        assert "runner hash drifted" in contract["blockers"][0]

        revision_reference = dict(reference, implementation_revision="old-head")
        apply_structured_source_reference_authority(
            case=case,
            reference=revision_reference,
            skill_root=root,
            runner_path=runner_path,
            expected_source_inventory_sha256="source-inventory-sha",
            head="new-head",
        )
        assert case["execution_contract"]["readiness"] == "partial"
        assert case["verification"]["implementation_revision"] == "new-head"
        assert "old-head" in case["execution_contract"]["blockers"][0]

        batch_manifest = root / "promotion-candidates.json"
        batch_manifest.write_text(json.dumps({
            "schema_version": 1,
            "run_id": "batch-1",
            "contract_sha256": "contract-sha",
            "structured_source_runs": {"CASE-1": reference},
            "failed_structured_source_runs": {},
        }), encoding="utf-8")
        registry = {
            "structured_source_batches": [{
                "run_id": "batch-1",
                "manifest": "skill://qwork-test-dataset/promotion-candidates.json",
                "manifest_sha256": sha256(batch_manifest),
                "contract_sha256": "contract-sha",
            }],
            "structured_source_runs": {},
            "failed_structured_source_runs": {},
        }
        expand_deterministic_reference_batches(registry, root)
        assert registry["structured_source_runs"] == {"CASE-1": reference}

        registry["structured_source_batches"][0]["manifest_sha256"] = "sha256:stale"
        try:
            expand_deterministic_reference_batches(registry, root)
        except ValueError as error:
            assert "manifest hash drifted" in str(error)
        else:
            raise AssertionError("batch manifest drift must fail closed")

    print("structured source reference authority test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
