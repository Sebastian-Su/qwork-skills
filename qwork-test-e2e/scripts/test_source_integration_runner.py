#!/usr/bin/env python3
"""Regression test for source integration release-gate classification."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def load_runner():
    path = Path(__file__).with_name("run_release_gate_plan.py")
    spec = importlib.util.spec_from_file_location("qwork_run_release_gate_plan", path)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load run_release_gate_plan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    runner = load_runner()
    case_id = "QW-REQ-SOURCE-INTEGRATION"
    command = (
        "python3 .agents/skills/qwork-test-dataset/scripts/"
        "validate_source_integration_case.py --repo . "
        "--skill-root .agents/skills/qwork-test-dataset "
        f"--case-id {case_id}"
    )
    case = {
        "id": case_id,
        "selection": {"requirement_ids": ["REQ-A", "REQ-B"]},
        "sources": [],
        "execution_contract": {
            "route_id": "qwork.dataset.source-integration.qw-req-source-integration",
            "authorization": {"required": False},
            "launch": {"strategy": "command", "command_or_tool": command},
            "observability": {
                "source_contract": {
                    "repository": "qwork_server",
                    "revision": "a" * 40,
                    "requirement_tests": {"REQ-A": ["TestA"], "REQ-B": ["TestB"]},
                }
            },
        },
    }
    plan = {
        "required_items": [
            {
                "item_id": f"case:{case_id}",
                "kind": "case",
                "case_id": case_id,
                "command": command,
                "route_id": case["execution_contract"]["route_id"],
            }
        ]
    }
    classified = runner.classify(plan, {case_id: case})
    coordinate = classified[f"case:{case_id}"]
    if coordinate.get("category") != "dataset-verifier":
        raise AssertionError(f"unexpected category: {coordinate}")
    if coordinate.get("artifact_name") != "integration-result.json":
        raise AssertionError(f"unexpected artifact: {coordinate}")
    if coordinate.get("source_integration") is not True:
        raise AssertionError(f"source integration marker missing: {coordinate}")

    case["execution_contract"]["observability"]["source_contract"]["requirement_tests"].pop("REQ-B")
    try:
        runner.classify(plan, {case_id: case})
    except ValueError as error:
        if "source integration" not in str(error):
            raise
    else:
        raise AssertionError("runner accepted an incomplete requirement map")

    print("source integration release-gate runner test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
