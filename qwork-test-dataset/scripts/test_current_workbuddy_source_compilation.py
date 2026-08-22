#!/usr/bin/env python3
"""Regression tests for version-derived WorkBuddy source identities and motion atoms."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path


def load_builder():
    sys.modules.setdefault("yaml", types.SimpleNamespace())
    path = Path(__file__).with_name("build_product_baseline.py")
    spec = importlib.util.spec_from_file_location("qwork_dataset_builder_current_source", path)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load build_product_baseline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    builder = load_builder()
    if builder.lark_source_identity({"document_id": "OJkRduSQmoxIMtx6KIbcoMYDnRf", "revision_id": 6}) != "WORKBUDDY-FEISHU-OJKR-REV6":
        raise AssertionError("Lark source identity is not derived from document and revision")
    if builder.cdp_source_identity({"version": "5.3.14"}, Path("5.3.14-surfaces-v2")) != "WORKBUDDY-CDP-5-3-14-V2":
        raise AssertionError("CDP source identity is not derived from product version and snapshot revision")
    if builder.motion_source_identity({"version": "5.3.14"}, Path("5.3.14-v1")) != "WORKBUDDY-MOTION-5-3-14-V1":
        raise AssertionError("motion source identity is not derived from product version and snapshot revision")
    command = builder.workbuddy_oracle_launch_command(
        Path("/skill"),
        Path("/skill/data/evidence/workbuddy-cdp/5.3.14-surfaces-v2"),
        "surface-market-技能",
    )
    expected_reference = (
        ".agents/skills/qwork-test-dataset/data/evidence/"
        "workbuddy-cdp/5.3.14-surfaces-v2"
    )
    if command.count(expected_reference) != 2:
        raise AssertionError("capture and compare steps must bind the same current CDP source")
    if f'--workbuddy {expected_reference} &&' not in command:
        raise AssertionError("capture command does not receive the frozen WorkBuddy source")

    with tempfile.TemporaryDirectory(prefix="workbuddy-motion-source-") as root:
        snapshot = Path(root)
        payload = {
            "id": "static-theme-motion-contract",
            "payload": {
                "viewport": {"width": 1680, "height": 1084, "dpr": 2},
                "theme": {
                    "selector_rules": [
                        {
                            "selector": 'body[data-vscode-theme-name="IDE Dark"]',
                            "declarations": {"--cb-bg": "#1f1f1f"},
                        }
                    ]
                },
                "keyframes": [
                    {
                        "name": "fade",
                        "frames": [
                            {"key": "from", "declarations": {"opacity": "0"}},
                            {"key": "to", "declarations": {"opacity": "1"}},
                        ],
                    }
                ],
                "motion_candidates": [
                    {
                        "path": "body>main>button",
                        "transition": {"property": "opacity", "duration": "0.2s", "delay": "0s", "timing_function": "ease"},
                        "animation": {"name": "none", "duration": "0s"},
                    }
                ],
            },
        }
        (snapshot / "static-theme-motion-contract.json").write_text(json.dumps(payload), encoding="utf-8")
        manifest = {
            "version": "5.3.14",
            "viewport": {"width": 1680, "height": 1084, "dpr": 2},
            "records": [
                {
                    "id": "static-theme-motion-contract",
                    "observation": "static-observation",
                    "file": "static-theme-motion-contract.json",
                    "payload_sha256": builder.sha256_text(json.dumps(payload["payload"], ensure_ascii=False, separators=(",", ":"))),
                }
            ],
        }
        atoms, metadata = builder.motion_atoms("WORKBUDDY-MOTION-5-3-14-V1", snapshot, manifest)
        facets = {atom["facet"] for atom in atoms}
        if not {"ui-visual", "ui-interaction"}.issubset(facets):
            raise AssertionError(f"theme and motion facets were not both compiled: {facets}")
        labels = "\n".join(str(atom["label"]) for atom in atoms)
        for expected in ("IDE Dark", "--cb-bg=#1f1f1f", "fade", "duration=0.2s"):
            if expected not in labels:
                raise AssertionError(f"motion contract omitted exact value: {expected}")
        if set(metadata) != {str(atom["atom_id"]) for atom in atoms}:
            raise AssertionError("every motion atom must retain source metadata")

    print("current WorkBuddy source compilation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
