#!/usr/bin/env python3
"""Regression checks for behavior-only and visual-checkpoint report contracts."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("render_e2e_report.py")
SPEC = importlib.util.spec_from_file_location("render_e2e_report", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load render_e2e_report.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ValidateCasesContractTest(unittest.TestCase):
    def test_behavior_only_ui_pass_allows_empty_visual_states(self) -> None:
        report = {
            "gate_status": "repair-required",
            "cases": [
                {
                    "id": "behavior-only",
                    "status": "pass",
                    "executor": "electron-cdp",
                    "ui": True,
                    "ui_attempted": True,
                    "required_screenshot_states": [],
                    "evidence": [],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(MODULE.validate_cases(report, Path(directory))[0]["id"], "behavior-only")

    def test_visual_checkpoint_pass_still_requires_declared_screenshots(self) -> None:
        report = {
            "gate_status": "repair-required",
            "cases": [
                {
                    "id": "visual-checkpoints",
                    "status": "pass",
                    "executor": "electron-cdp",
                    "ui": True,
                    "ui_attempted": True,
                    "required_screenshot_states": ["entry", "final-state"],
                    "evidence": [],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "missing screenshots"):
                MODULE.validate_cases(report, Path(directory))

    def test_attempted_ui_case_must_declare_acceptance_state_list(self) -> None:
        report = {
            "gate_status": "repair-required",
            "cases": [
                {
                    "id": "missing-mode",
                    "status": "fail",
                    "executor": "electron-cdp",
                    "ui": True,
                    "ui_attempted": True,
                    "evidence": [],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "must declare required_screenshot_states"):
                MODULE.validate_cases(report, Path(directory))


if __name__ == "__main__":
    unittest.main()
