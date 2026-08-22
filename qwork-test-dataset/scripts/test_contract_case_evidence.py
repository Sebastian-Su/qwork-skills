#!/usr/bin/env python3
"""Regression test: assertion-only private Cases must not claim UI evidence."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def main() -> int:
    path = Path(__file__).with_name("build_product_baseline.py")
    spec = importlib.util.spec_from_file_location("qwork_build_product_baseline", path)
    assert spec and spec.loader
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    case = builder.default_case(
        "QW-E2E-CONTRACT-ONLY",
        "assertion-only contract",
        "window-runtime",
        "qwork.private-playwright.contract-only",
        "skill://qwork-test-dataset/data/e2e/contract.spec.ts",
        ["business"],
        test_contract={
            "line_start": 1,
            "line_end": 3,
            "body_sha256": "a" * 64,
            "actions": [],
            "helpers": [{"expression": "governor.observe(error)"}],
            "assertions": [{"expression": "expect(limit).toBe(8)"}],
        },
        execution_revision="revision",
        spec_sha256="b" * 64,
    )
    if case.get("execution_type") != "integration" or "ui_acceptance" in case:
        raise AssertionError("assertion-only contract incorrectly declares a UI execution type")
    if case["execution_contract"]["navigation"]["kind"] != "process-protocol":
        raise AssertionError("assertion-only contract incorrectly declares a UI route")
    if case["coverage"]["states_covered"] != ["contract-result"]:
        raise AssertionError("assertion-only contract lacks a non-visual coverage state")
    artifacts = case["execution_contract"]["observability"]["artifacts"]
    if artifacts != ["report.json", "trace.zip"]:
        raise AssertionError(f"contract-only evidence drifted: {artifacts}")
    ui_case = builder.default_case(
        "QW-E2E-UI-HELPER",
        "UI helper contract",
        "expert-market",
        "qwork.private-playwright.ui-helper",
        "skill://qwork-test-dataset/data/e2e/ui-helper.spec.ts",
        ["business", "ui-state"],
        test_contract={
            "line_start": 1,
            "line_end": 3,
            "body_sha256": "c" * 64,
            "actions": [],
            "helpers": [{"expression": "openApp(home)"}],
            "assertions": [{"expression": "expect(card).toBeVisible()"}],
        },
        execution_revision="revision",
        spec_sha256="d" * 64,
    )
    if ui_case.get("execution_type") != "desktop":
        raise AssertionError("openApp helper was not recognized as a UI execution")
    if ui_case["execution_contract"]["navigation"]["kind"] != "ui-route":
        raise AssertionError("openApp helper lost its UI route")
    if ui_case["ui_acceptance"] != {
        "acceptance_mode": "behavior-only",
        "viewport_profiles": [{"id": "darwin-default", "width": 1200, "height": 800, "dpr": 1}],
        "required_screenshot_states": [],
    }:
        raise AssertionError("UI helper did not declare an explicit behavior-only acceptance mode")
    if ui_case["coverage"]["states_covered"] != ["interactive-result"]:
        raise AssertionError("UI helper lost its non-visual interactive result")
    private_visual = builder.default_case(
        "QW-E2E-PRIVATE-VISUAL",
        "private visual route",
        "expert-market",
        "qwork.private-playwright.visual",
        "skill://qwork-test-dataset/data/e2e/private-visual.spec.ts",
        ["business", "ui-state"],
        test_contract={
            "line_start": 1,
            "line_end": 12,
            "body_sha256": "7" * 64,
            "actions": [{"expression": "picker.click()"}],
            "helpers": [
                {"expression": 'attachUiState(page, testInfo, "entry-picker")'},
                {"expression": 'attachUiState(page, testInfo, "transition-menu")'},
                {"expression": 'attachUiState(page, testInfo, "final-picker-selected")'},
            ],
            "assertions": [{"expression": "expect(menu).toBeVisible()"}],
        },
        execution_revision="revision",
        spec_sha256="8" * 64,
    )
    if private_visual["ui_acceptance"]["required_screenshot_states"] != ["entry", "transition", "final-state"]:
        raise AssertionError("private visual Case did not preserve its declared screenshot checkpoints")
    public_functional = builder.default_case(
        "QW-E2E-PUBLIC-FUNCTIONAL",
        "public functional route",
        "models",
        "qwork.playwright.public-functional",
        "e2e/model.spec.ts",
        ["business", "ui-state"],
        test_contract={
            "line_start": 1,
            "line_end": 8,
            "body_sha256": "e" * 64,
            "actions": [{"expression": "picker.click()"}],
            "helpers": [{"expression": "openApp(home)"}],
            "assertions": [{"expression": "expect(menu).toBeVisible()"}],
        },
        execution_revision="revision",
        spec_sha256="f" * 64,
    )
    if public_functional.get("execution_type") != "desktop":
        raise AssertionError("public functional Case lost its desktop execution type")
    if public_functional["ui_acceptance"]["acceptance_mode"] != "behavior-only":
        raise AssertionError("public functional Case did not declare behavior-only UI acceptance")
    if public_functional["ui_acceptance"]["required_screenshot_states"]:
        raise AssertionError("public functional Case fabricated entry/final screenshots")
    if public_functional["coverage"]["states_covered"] != ["interactive-result"]:
        raise AssertionError("public functional Case lost its interactive result")
    public_visual = builder.default_case(
        "QW-E2E-PUBLIC-VISUAL",
        "public visual contract",
        "models",
        "qwork.playwright.public-visual",
        "e2e/model-visual.spec.ts",
        ["ui-visual"],
        test_contract={
            "line_start": 1,
            "line_end": 12,
            "body_sha256": "1" * 64,
            "actions": [{"expression": "picker.click()"}],
            "helpers": [
                {"expression": 'testInfo.outputPath("entry.png")'},
                {"expression": 'testInfo.outputPath("transition.png")'},
                {"expression": 'testInfo.outputPath("final-state.png")'},
            ],
            "assertions": [{"expression": "expect(menu).toBeVisible()"}],
        },
        execution_revision="revision",
        spec_sha256="2" * 64,
    )
    if public_visual["ui_acceptance"]["required_screenshot_states"] != ["entry", "transition", "final-state"]:
        raise AssertionError("public visual Case did not preserve declared screenshots")
    manual_visual = builder.default_case(
        "QW-E2E-MANUAL-VISUAL",
        "manual motion contract",
        "automation",
        "qwork.oracle.manual-motion",
        None,
        ["ui-visual", "ui-state"],
    )
    if manual_visual["ui_acceptance"]["required_screenshot_states"] != ["entry", "transition", "final-state"]:
        raise AssertionError("manual visual requirement lost its future evidence obligations")
    print("assertion-only private Case has no fabricated UI evidence contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
