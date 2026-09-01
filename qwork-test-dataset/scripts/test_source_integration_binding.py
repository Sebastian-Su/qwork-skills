#!/usr/bin/env python3
"""Regression test for fail-closed source integration runner bindings."""

from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile


def load_builder():
    path = Path(__file__).with_name("build_product_baseline.py")
    spec = importlib.util.spec_from_file_location("qwork_build_product_baseline", path)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load build_product_baseline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    builder = load_builder()
    case_id = "QW-REQ-SOURCE-INTEGRATION"
    case = builder.default_case(
        case_id,
        "媒体报价接口产品契约",
        "media-generation",
        "qwork.requirement.source-integration",
        None,
        ["business", "negative"],
    )
    case["selection"]["requirement_ids"] = ["REQ-PRICE", "REQ-NEGATIVE"]
    binding = {
        "case_id": case_id,
        "repository": "qwork_server",
        "revision": "a" * 40,
        "requirement_ids": ["REQ-NEGATIVE", "REQ-PRICE"],
        "packages": ["./internal/media", "./internal/api"],
        "tests": ["TestQuotePrice", "TestQuoteRejectsInvalid"],
        "requirement_tests": {
            "REQ-NEGATIVE": ["TestQuoteRejectsInvalid"],
            "REQ-PRICE": ["TestQuotePrice"],
        },
        "authority_files": [
            {"path": "internal/media/service_test.go", "sha256": "sha256:" + "b" * 64},
        ],
    }

    builder.apply_source_integration_binding(case, binding, "c" * 40)

    contract = case["execution_contract"]
    expected_command = (
        "python3 .agents/skills/qwork-test-dataset/scripts/"
        "validate_source_integration_case.py --repo . "
        "--skill-root .agents/skills/qwork-test-dataset "
        f"--case-id {case_id}"
    )
    if contract["launch"] != {
        "strategy": "command",
        "command_or_tool": expected_command,
        "success_oracle": "every bound source integration test passes at the declared repository revision",
        "failure_action": "preserve the machine-readable test result and repair the product or binding; never substitute static source scans",
    }:
        raise AssertionError(f"source integration launch contract drifted: {contract['launch']}")
    if contract["route_id"] != "qwork.dataset.source-integration.qw-req-source-integration":
        raise AssertionError(f"unexpected route: {contract['route_id']}")
    source = contract["observability"]["source_contract"]
    if source["repository"] != "qwork_server" or source["revision"] != "a" * 40:
        raise AssertionError(f"repository authority was not frozen: {source}")
    if source["requirement_ids"] != ["REQ-NEGATIVE", "REQ-PRICE"]:
        raise AssertionError(f"requirement closure drifted: {source}")
    if sorted(source["requirement_tests"]) != source["requirement_ids"]:
        raise AssertionError(f"requirement test closure drifted: {source}")
    if case["execution_mode"] != "real-process" or contract["readiness"] != "partial":
        raise AssertionError("binding falsely claimed a completed reference run")

    mismatched = dict(binding)
    mismatched["requirement_ids"] = ["REQ-PRICE"]
    try:
        builder.apply_source_integration_binding(case, mismatched, "c" * 40)
    except ValueError as error:
        if "requirement" not in str(error):
            raise
    else:
        raise AssertionError("binding accepted an incomplete requirement set")

    with tempfile.TemporaryDirectory() as directory:
        skill_root = Path(directory)
        reference_root = skill_root / "data/reference-runs/source-integration-v1"
        reference_root.mkdir(parents=True)
        verifier = skill_root / "scripts/validate_source_integration_case.py"
        verifier.parent.mkdir(parents=True)
        verifier.write_text("# frozen verifier\n", encoding="utf-8")
        source_contract = source
        item_id = f"case:{case_id}"
        plan = {
            "plan_sha256": "d" * 64,
            "implementation_revision": "c" * 40,
            "required_items": [{
                "item_id": item_id,
                "case_id": case_id,
                "route_id": contract["route_id"],
                "command": expected_command,
                "source_contract": source_contract,
            }],
        }
        state = {
            "plan_sha256": "d" * 64,
            "implementation_revision": "c" * 40,
            "coordinates": {item_id: {
                "category": "dataset-verifier",
                "status": "pass",
                "exit_code": 0,
                "finished_at": "2026-08-28T00:00:00+00:00",
            }},
        }
        preflight = {
            "plan_sha256": "d" * 64,
            "implementation_revision": "c" * 40,
            "live_execution_allowed": False,
        }
        report = {
            "status": "pass",
            "case_id": case_id,
            "qwork_revision": "c" * 40,
            "expected_revision": "a" * 40,
            "actual_revision": "a" * 40,
            "worktree_clean": True,
            "zero_real_provider_calls": True,
            "tests": [
                {"name": "TestQuotePrice", "status": "pass"},
                {"name": "TestQuoteRejectsInvalid", "status": "pass"},
            ],
            "requirements": [
                {"requirement_id": "REQ-NEGATIVE", "tests": ["TestQuoteRejectsInvalid"], "status": "pass"},
                {"requirement_id": "REQ-PRICE", "tests": ["TestQuotePrice"], "status": "pass"},
            ],
            "cleanup": {"test_process_exited": True, "external_state_created": False},
            "failures": [],
        }

        def write(name: str, value: dict) -> str:
            path = reference_root / name
            path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
            return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

        plan_sha = write("plan.json", plan)
        state_sha = write("runner-state.json", state)
        preflight_sha = write("execution-preflight.json", preflight)
        report_sha = write("integration-result.json", report)
        verifier_sha = "sha256:" + hashlib.sha256(verifier.read_bytes()).hexdigest()
        contract_sha = hashlib.sha256(
            json.dumps(source_contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        prefix = "skill://qwork-test-dataset/data/reference-runs/source-integration-v1/"
        reference = {
            "run_id": "source-integration-v1",
            "report": prefix + "integration-result.json",
            "report_sha256": report_sha,
            "plan": prefix + "plan.json",
            "plan_file_sha256": plan_sha,
            "runner_state": prefix + "runner-state.json",
            "runner_state_sha256": state_sha,
            "preflight": prefix + "execution-preflight.json",
            "preflight_sha256": preflight_sha,
            "verifier_sha256": verifier_sha,
            "source_contract_sha256": contract_sha,
            "implementation_revision": "c" * 40,
            "qwork_server_revision": "a" * 40,
            "plan_sha256": "d" * 64,
            "verified_at": "2026-08-28T00:00:00+00:00",
        }
        builder.apply_source_integration_reference_authority(
            case=case,
            reference=reference,
            skill_root=skill_root,
            head="c" * 40,
        )
        if contract["readiness"] != "ready" or contract["reference_run"]["status"] != "passed":
            raise AssertionError("passing source integration reference was not promoted")

    print("source integration binding test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
