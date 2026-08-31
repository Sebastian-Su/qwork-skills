#!/usr/bin/env python3
"""Regression checks for version-bound WorkBuddy Oracle execution."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def load_runner():
    path = Path(__file__).with_name("run_release_gate_plan.py")
    spec = importlib.util.spec_from_file_location("qwork_release_gate_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    runner = load_runner()
    command = (
        "node .agents/skills/qwork-test-dataset/scripts/run_qwork_workbuddy_oracle.mjs "
        ". <run-root>/qwork-workbuddy/surface-market/capture surface-market-技能 "
        "--workbuddy .agents/skills/qwork-test-dataset/data/evidence/workbuddy-cdp/5.3.8-surfaces-v3 && "
        "python3 .agents/skills/qwork-test-dataset/scripts/compare_qwork_workbuddy_oracle.py "
        "--capture <run-root>/qwork-workbuddy/surface-market/capture "
        "--workbuddy .agents/skills/qwork-test-dataset/data/evidence/workbuddy-cdp/5.3.8-surfaces-v3 "
        "--output <run-root>/qwork-workbuddy/surface-market/compare "
        "--max-diff-ratio 0.01 --geometry-tolerance 2 --fail-on-diff"
    )
    binding = runner.workbuddy_oracle_binding(
        {"WORKBUDDY-CDP-5-3-8-V3"}, command
    )
    assert binding == "data/evidence/workbuddy-cdp/5.3.8-surfaces-v3"
    try:
        runner.workbuddy_oracle_binding(
            {"WORKBUDDY-CDP-5-3-12-V4"}, command
        )
    except ValueError as error:
        assert "source/path mismatch" in str(error)
    else:
        raise AssertionError("cross-version WorkBuddy binding was accepted")

    dataset_runner = (
        Path(__file__).resolve().parents[2]
        / "qwork-test-dataset/scripts/run_qwork_workbuddy_oracle.mjs"
    ).read_text(encoding="utf-8")
    assert '"ima知识库": "知识库"' in dataset_runner
    assert '"乐享知识库": "知识库"' in dataset_runner
    assert 'requestedState === "all"' in dataset_runner
    assert 'QWORK_E2E_PROCESS: "1"' in dataset_runner
    assert 'QWORK_E2E_BUILTIN_MARKETPLACE: "plugins-only"' in dataset_runner
    assert "startProjectFixture" in dataset_runner
    assert "expertCatalogFixture" in dataset_runner
    assert '"/expert/api/v1/client/experts/catalog"' in dataset_runner
    assert "inspirationCatalogFixture" in dataset_runner
    assert '"/api/v1/inspirations"' in dataset_runner
    assert "oracleProjectFixtures" in dataset_runner
    assert 'response.end(JSON.stringify({ items: projectItems }))' in dataset_runner
    assert 'response.end(JSON.stringify({ members: [] }))' in dataset_runner
    assert 'response.end(JSON.stringify({ tasks: [] }))' in dataset_runner
    assert "ensureFrozenTheme" in dataset_runner
    assert 'wbManifest.theme_coverage?.expected_theme' in dataset_runner
    assert "ensureFinalState" in dataset_runner
    workbuddy_capture = (
        Path(__file__).resolve().parents[2]
        / "qwork-test-dataset/scripts/capture_workbuddy_surfaces.mjs"
    ).read_text(encoding="utf-8")
    assert "returnToTopSurface" in workbuddy_capture
    print("WorkBuddy Oracle runner binding: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
