#!/usr/bin/env python3
"""Regression test for source-bound causal steps in generated document Cases."""

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
    case = builder.default_case(
        "QW-REQ-CAUSAL-CONTRACT",
        "docs/qwork-expert-team-prd.md · FR-SUMMON-002 选择不等于创建 产品契约",
        "expert-market",
        "qwork.requirement.causal-contract",
        None,
        ["business", "ui-interaction"],
    )
    case["derived_requirements"] = [
        {
            "requirement_id": "REQ-HOME",
            "rule": "页面回到或保持 QWork 首页。",
            "content_facets": ["business-rule"],
        },
        {
            "requirement_id": "REQ-NO-MODEL",
            "rule": "不调用 `create_session`，不发起模型请求。",
            "content_facets": ["negative-rule"],
        },
    ]
    case["oracles"] = [
        {
            "requirement_id": "REQ-HOME",
            "type": "ui",
            "assertion": "页面回到或保持 QWork 首页。",
        },
        {
            "requirement_id": "REQ-NO-MODEL",
            "type": "event",
            "assertion": "不调用 `create_session`，不发起模型请求。",
        },
    ]

    original_readiness = case["execution_contract"]["readiness"]
    original_launch = case["execution_contract"]["launch"]["strategy"]
    builder.compile_source_bound_causal_contract(case)

    actions = [step["action"] for step in case["steps"]]
    joined_actions = "\n".join(actions)
    if actions == ["launch isolated QWork Electron", case["title"]]:
        raise AssertionError("document Case still consists of launch plus its title")
    if "capture the pre-trigger baseline" not in joined_actions:
        raise AssertionError("document Case lacks an explicit pre-trigger baseline")
    if "perform the source-defined scenario trigger" not in joined_actions:
        raise AssertionError("document Case lacks an explicit causal trigger")
    for requirement_id, assertion in (
        ("REQ-HOME", "页面回到或保持 QWork 首页。"),
        ("REQ-NO-MODEL", "不调用 `create_session`，不发起模型请求。"),
    ):
        if requirement_id not in joined_actions or assertion not in joined_actions:
            raise AssertionError(f"missing source-bound probe step for {requirement_id}")
        if assertion not in case["expected_outcomes"]:
            raise AssertionError(f"missing exact expected outcome for {requirement_id}")
        if not any(
            requirement_id in outcome and assertion in outcome
            for outcome in case["forbidden_outcomes"]
        ):
            raise AssertionError(f"missing explicit counterfactual failure for {requirement_id}")

    probes = case.get("causal_probe_plan")
    if not isinstance(probes, list) or len(probes) != 2:
        raise AssertionError("causal probe plan is not one-to-one with the Case oracles")
    if {probe["requirement_id"] for probe in probes} != {"REQ-HOME", "REQ-NO-MODEL"}:
        raise AssertionError("causal probe plan requirement closure drifted")
    if any(not probe.get("given") or not probe.get("when") or not probe.get("then") for probe in probes):
        raise AssertionError("causal probe plan lacks Given/When/Then")

    navigation = case["execution_contract"]["navigation"]
    if navigation["steps"] != case["steps"][1:]:
        raise AssertionError("execution navigation drifted from the compiled Case steps")
    if case["execution_contract"]["readiness"] != original_readiness:
        raise AssertionError("causal compilation falsely changed reference-run readiness")
    if case["execution_contract"]["launch"]["strategy"] != original_launch:
        raise AssertionError("causal compilation falsely implemented a missing runner")

    print("document Case causal contract test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
