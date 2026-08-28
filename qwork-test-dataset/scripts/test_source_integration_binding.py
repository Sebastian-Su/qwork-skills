#!/usr/bin/env python3
"""Regression test for fail-closed source integration runner bindings."""

from __future__ import annotations

import importlib.util
from pathlib import Path


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

    print("source integration binding test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
