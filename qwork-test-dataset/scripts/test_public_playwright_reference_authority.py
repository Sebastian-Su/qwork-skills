#!/usr/bin/env python3
"""Regression test for hash-bound public Playwright reference authority."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile

from build_product_baseline import apply_public_playwright_reference_authority


def write(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def main() -> int:
    revision = "a" * 40
    case_id = "QW-E2E-PUBLIC-REFERENCE"
    run_id = "public-reference-run"
    plan_hash = "b" * 64
    command = 'npx playwright test e2e/example.spec.ts -g "works"'
    source_contract = {
        "spec": "e2e/example.spec.ts",
        "line_start": 1,
        "line_end": 10,
        "body_sha256": "sha256:" + "c" * 64,
        "assertion_count": 1,
        "action_count": 1,
        "execution_revision": revision,
        "spec_sha256": "sha256:" + "d" * 64,
    }
    with tempfile.TemporaryDirectory(prefix="qwork-public-reference-") as value:
        skill = Path(value)
        root = skill / "data/runs" / run_id
        item_id = f"case:{case_id}"
        plan = {
            "plan_sha256": plan_hash,
            "implementation_revision": revision,
            "required_items": [{
                "item_id": item_id,
                "kind": "case",
                "case_id": case_id,
                "route_id": "qwork.playwright.example",
                "command": command,
                "source_contract": source_contract,
                "required_screenshot_states": ["entry", "final-state"],
            }],
        }
        state = {
            "plan_sha256": plan_hash,
            "implementation_revision": revision,
            "coordinates": {item_id: {
                "category": "deterministic-playwright",
                "status": "pass",
                "exit_code": 0,
                "finished_at": "2026-08-19T00:00:00+00:00",
            }},
        }
        preflight = {
            "plan_sha256": plan_hash,
            "implementation_revision": revision,
            "live_execution_allowed": False,
        }
        evidence = {
            "schema_version": 1,
            "case_id": case_id,
            "status": "pass",
            "entries": [
                {"kind": "screenshot", "state": "entry"},
                {"kind": "screenshot", "state": "final-state"},
            ],
        }
        plan_sha = write(root / "plan.json", plan)
        state_sha = write(root / "runner-state.json", state)
        preflight_sha = write(root / "execution-preflight.json", preflight)
        evidence_path = root / f"items/{case_id}/evidence-manifest.json"
        evidence_sha = write(evidence_path, evidence)
        manifest_path = root / "public-playwright-reference.json"
        write(manifest_path, {"schema_version": 1})

        case = {
            "id": case_id,
            "execution_contract": {
                "readiness": "partial",
                "route_id": "qwork.playwright.example",
                "launch": {"command_or_tool": command},
                "observability": {"source_contract": source_contract},
                "reference_run": {"status": "pending"},
                "blockers": ["reference run pending"],
            },
            "ui_acceptance": {"required_screenshot_states": ["entry", "final-state"]},
            "verification": {"last_outcome": "pending"},
        }
        reference = {
            "run_id": run_id,
            "implementation_revision": revision,
            "plan_sha256": plan_hash,
            "route_id": "qwork.playwright.example",
            "command": command,
            "source_contract": source_contract,
            "required_screenshot_states": ["entry", "final-state"],
            "finished_at": "2026-08-19T00:00:00+00:00",
            "artifacts": [{"path": f"items/{case_id}/evidence-manifest.json", "sha256": evidence_sha}],
            "batch_manifest": f"skill://qwork-test-dataset/data/runs/{run_id}/public-playwright-reference.json",
            "batch_manifest_sha256": "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "authority_files": [
                {"path": "plan.json", "sha256": plan_sha},
                {"path": "runner-state.json", "sha256": state_sha},
                {"path": "execution-preflight.json", "sha256": preflight_sha},
            ],
        }
        apply_public_playwright_reference_authority(
            case=case, reference=reference, skill_root=skill, head=revision
        )
        assert case["execution_contract"]["readiness"] == "ready"
        assert case["execution_contract"]["reference_run"]["status"] == "passed"

        evidence_path.write_text("{}\n", encoding="utf-8")
        try:
            apply_public_playwright_reference_authority(
                case=case, reference=reference, skill_root=skill, head=revision
            )
        except ValueError as error:
            assert "hash drifted" in str(error)
        else:
            raise AssertionError("mutated public reference evidence was accepted")
    print("public Playwright reference authority test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
