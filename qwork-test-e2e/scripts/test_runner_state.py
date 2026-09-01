#!/usr/bin/env python3
"""Focused regression checks for release-runner state preservation."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile


def load_runner():
    path = Path(__file__).with_name("run_release_gate_plan.py")
    spec = importlib.util.spec_from_file_location("qwork_release_gate_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load release-gate runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    runner = load_runner()
    delegated_cases = {
        "REQ-CASE": {
            "sources": [],
            "execution_contract": {
                "route_id": "qwork.requirement.prd.req-1",
                "authorization": {"required": False},
                "launch": {
                    "strategy": "command",
                    "command_or_tool": 'npx playwright test e2e/workspace.spec.ts -g "workspace path"',
                    "delegate_case_id": "PLAYWRIGHT-CASE",
                },
                "observability": {"source_contract": None},
            },
        },
        "PLAYWRIGHT-CASE": {
            "title": "workspace path",
            "sources": [],
            "execution_contract": {
                "route_id": "qwork.playwright.e2e-workspace-spec-ts.12345678",
                "launch": {
                    "strategy": "command",
                    "command_or_tool": 'npx playwright test e2e/workspace.spec.ts -g "workspace path"',
                },
                "observability": {
                    "source_contract": {"spec": "e2e/workspace.spec.ts"}
                },
            },
        },
    }
    delegated = runner.classify(
        {
            "implementation_revision": "head",
            "required_items": [{
                "item_id": "case:REQ-CASE",
                "kind": "case",
                "case_id": "REQ-CASE",
                "command": 'npx playwright test e2e/workspace.spec.ts -g "workspace path"',
                "route_id": "qwork.requirement.prd.req-1",
                "revision_drift": False,
                "external_dependency_required": False,
            }],
        },
        delegated_cases,
    )
    assert delegated["case:REQ-CASE"]["category"] == "deterministic-playwright"
    assert delegated["case:REQ-CASE"]["delegate_case_id"] == "PLAYWRIGHT-CASE"
    direct = runner.classify(
        {
            "implementation_revision": "head",
            "required_items": [{
                "item_id": "case:REQ-DIRECT",
                "kind": "case",
                "case_id": "REQ-DIRECT",
                "command": 'npx playwright test e2e/workspace.spec.ts -g "cloud workspace"',
                "route_id": "qwork.requirement.prd.req-direct",
                "revision_drift": False,
                "external_dependency_required": False,
            }],
        },
        {
            "REQ-DIRECT": {
                "sources": [],
                "execution_contract": {
                    "route_id": "qwork.requirement.prd.req-direct",
                    "authorization": {"required": False},
                    "launch": {
                        "strategy": "command",
                        "command_or_tool": 'npx playwright test e2e/workspace.spec.ts -g "cloud workspace"',
                        "source_contract": {
                            "spec": "e2e/workspace.spec.ts",
                            "title": "cloud workspace",
                            "execution_revision": "head",
                            "body_sha256": "sha256:" + "a" * 64,
                            "spec_sha256": "sha256:" + "b" * 64,
                        },
                    },
                    "observability": {"source_contract": None},
                },
            }
        },
    )
    assert direct["case:REQ-DIRECT"]["category"] == "deterministic-playwright"
    try:
        runner.classify(
            {
                "implementation_revision": "head",
                "required_items": [{
                    "item_id": "case:REQ-DIRECT",
                    "kind": "case",
                    "case_id": "REQ-DIRECT",
                    "command": "npx playwright test",
                    "route_id": "qwork.requirement.prd.req-direct",
                    "revision_drift": False,
                    "external_dependency_required": False,
                }],
            },
            {
                "REQ-DIRECT": {
                    "sources": [],
                    "execution_contract": {
                        "route_id": "qwork.requirement.prd.req-direct",
                        "authorization": {"required": False},
                        "launch": {
                            "strategy": "command",
                            "command_or_tool": "npx playwright test",
                            "source_contract": {},
                        },
                        "observability": {"source_contract": None},
                    },
                }
            },
        )
    except ValueError as error:
        assert "requirement Playwright contract mismatch" in str(error)
    else:
        raise AssertionError("malformed requirement route was accepted")
    coordinates = {
        "gate:first": {"category": "gate"},
        "case:second": {"category": "deterministic-playwright"},
    }
    prior = {
        "schema_version": 1,
        "plan_sha256": "plan-a",
        "implementation_revision": "revision-a",
        "coordinates": {
            "gate:first": {
                "category": "gate",
                "status": "pass",
                "stdout_sha256": "a" * 64,
                "stderr_sha256": "b" * 64,
            }
        },
    }
    prepared = runner.prepare_state(
        prior=prior,
        plan_sha256="plan-a",
        implementation_revision="revision-a",
        classified_coordinates=coordinates,
    )
    assert prepared["coordinates"]["gate:first"] == prior["coordinates"]["gate:first"]
    assert "case:second" not in prepared["coordinates"]
    assert runner.coordinate_requires_loopback("gate:unit-integration", coordinates["gate:first"])
    assert runner.coordinate_requires_loopback("case:second", coordinates["case:second"])
    assert not runner.coordinate_requires_loopback("gate:typecheck", {"category": "gate"})
    assert runner.infer_visual_state("expert-final-after-restart.png", failed=False) == "final-state"
    assert runner.infer_visual_state("expert-after-important-mutation.png", failed=False) == "after-important-mutation"

    with tempfile.TemporaryDirectory(prefix="qwork-dataset-verifier-") as value:
        run_root = Path(value)
        steps, artifacts = runner.coordinate_steps(
            Path("/repo"),
            run_root,
            {
                "category": "dataset-verifier",
                "case_id": "CASE-1",
                "argv": ["python3", "verifier.py", "--case-id", "CASE-1"],
            },
            Path("/dataset"),
        )
        expected = run_root / "items" / "CASE-1" / "storage-case-result.json"
        assert artifacts == [expected]
        assert steps == [[
            "python3", "verifier.py", "--case-id", "CASE-1",
            "--output", str(expected),
        ]]

        structured_steps, structured_artifacts = runner.coordinate_steps(
            Path("/repo"),
            run_root,
            {
                "category": "dataset-verifier",
                "case_id": "CASE-2",
                "argv": ["python3", "source-verifier.py", "--case-id", "CASE-2"],
                "artifact_name": "structured-source-result.json",
            },
            Path("/dataset"),
        )
        structured_expected = run_root / "items" / "CASE-2" / "structured-source-result.json"
        assert structured_artifacts == [structured_expected]
        assert structured_steps == [[
            "python3", "source-verifier.py", "--case-id", "CASE-2",
            "--output", str(structured_expected),
        ]]

        private_steps, private_artifacts = runner.coordinate_steps(
            Path("/repo"),
            run_root,
            {
                "category": "deterministic-playwright",
                "case_id": "CASE-PRIVATE",
                "argv": [
                    "node",
                    ".agents/skills/qwork-test-dataset/scripts/run_private_playwright_case.mjs",
                    "--repo",
                    ".",
                    "--case-id",
                    "CASE-PRIVATE",
                    "--case-title",
                    "private title",
                ],
                "private_playwright": True,
            },
            Path("/dataset"),
        )
        private_root = (
            run_root
            / "PRIVATE-EVIDENCE"
            / runner.private_run_namespace(run_root)
            / "CASE-PRIVATE"
        )
        assert private_steps == [[
            "node",
            ".agents/skills/qwork-test-dataset/scripts/run_private_playwright_case.mjs",
            "--repo",
            ".",
            "--case-id",
            "CASE-PRIVATE",
            "--case-title",
            "private title",
            "--run-root",
            str(private_root),
        ]]
        assert private_artifacts == [
            private_root / "report.json",
            private_root / "build-manifest.json",
        ]

    for mutation, expected in [
        ({"plan_sha256": "plan-b"}, "another plan"),
        ({"implementation_revision": "revision-b"}, "another revision"),
        ({"coordinates": {"unknown": {"status": "pass", "category": "gate"}}}, "unknown coordinate"),
        ({"coordinates": {"gate:first": {"status": "pass", "category": "runner-gap"}}}, "category drift"),
    ]:
        candidate = {**prior, **mutation}
        try:
            runner.prepare_state(
                prior=candidate,
                plan_sha256="plan-a",
                implementation_revision="revision-a",
                classified_coordinates=coordinates,
            )
        except ValueError as error:
            assert expected in str(error), (expected, str(error))
        else:
            raise AssertionError(f"state mutation was accepted: {mutation}")

    print("runner state preservation: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
