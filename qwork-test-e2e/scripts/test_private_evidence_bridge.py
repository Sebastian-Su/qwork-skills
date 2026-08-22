#!/usr/bin/env python3
"""Verify private Electron evidence stays in Dataset storage and only an attestation is exported."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile


def main() -> int:
    runner_path = Path(__file__).with_name("run_release_gate_plan.py")
    spec = importlib.util.spec_from_file_location("qwork_release_runner", runner_path)
    assert spec and spec.loader
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    with tempfile.TemporaryDirectory(prefix="qwork-private-bridge-") as value:
        root = Path(value)
        first_namespace = runner.private_run_namespace(root / "full-v6/run")
        second_namespace = runner.private_run_namespace(root / "full-v7/run")
        if first_namespace == second_namespace:
            raise RuntimeError("distinct release-gate plans share a private evidence namespace")
        if first_namespace != runner.private_run_namespace(root / "full-v6/run"):
            raise RuntimeError("private evidence namespace is not deterministic")
        private_root = root / "dataset/data/runs/release-gate-execution/run/case"
        public_root = root / "public"
        private_root.mkdir(parents=True)
        (private_root / "build-manifest.json").write_text(
            json.dumps({"source_revision": "revision"}), encoding="utf-8"
        )
        (private_root / "report.json").write_text(
            json.dumps({
                "case_id": "case",
                "status": "fail",
                "zero_real_model_calls": True,
                "isolated_qwork_home": True,
                "source": {"spec": "skill://private.spec.ts"},
                "cleanup": {"home_removed": True, "app_closed": True, "assembly_removed": True},
                "evidence": {"integrity": "complete", "screenshots": [
                    {"path": "playwright-results/test-failed-1.png", "state": "assertion-failure", "sha256": "sha256:" + "a" * 64},
                ], "traces": [{}]},
            }),
            encoding="utf-8",
        )
        attestation = runner.write_private_attestation(
            run_root=public_root,
            coordinate={"case_id": "case"},
            private_artifacts=[private_root / "report.json", private_root / "build-manifest.json"],
        )
        exported = json.loads(attestation.read_text(encoding="utf-8"))
        if exported["status"] != "fail" or exported["private_evidence"]["screenshot_count"] != 1:
            raise RuntimeError("private terminal evidence was not faithfully attested")
        states = {value["state"] for value in exported["private_evidence"]["visual_checkpoints"]}
        if states != {"assertion-failure"}:
            raise RuntimeError(f"private visual checkpoint attestation is incomplete: {sorted(states)}")
        public_files = {path.name for path in public_root.rglob("*") if path.is_file()}
        if public_files != {"private-attestation.json"}:
            raise RuntimeError(f"raw private evidence escaped into public run: {sorted(public_files)}")
        contract_root = root / "dataset/data/runs/release-gate-execution/run/contract"
        contract_root.mkdir(parents=True)
        (contract_root / "build-manifest.json").write_text(
            json.dumps({"source_revision": "revision"}), encoding="utf-8"
        )
        (contract_root / "report.json").write_text(
            json.dumps({
                "case_id": "contract",
                "status": "pass",
                "zero_real_model_calls": True,
                "isolated_qwork_home": True,
                "source": {"spec": "skill://contract.spec.ts"},
                "cleanup": {"home_removed": True, "app_closed": True, "assembly_removed": True},
                "evidence": {"integrity": "complete", "screenshots": [], "traces": [{}]},
            }),
            encoding="utf-8",
        )
        contract_attestation = runner.write_private_attestation(
            run_root=public_root,
            coordinate={"case_id": "contract", "required_screenshot_states": []},
            private_artifacts=[contract_root / "report.json", contract_root / "build-manifest.json"],
        )
        contract_exported = json.loads(contract_attestation.read_text(encoding="utf-8"))
        if contract_exported["private_evidence"]["screenshot_count"] != 0:
            raise RuntimeError("contract-only private evidence fabricated a screenshot")
        command = (
            "node .agents/skills/qwork-test-dataset/scripts/run_private_playwright_case.mjs "
            "--repo . --case-id contract --case-title contract-only"
        )
        classified = runner.classify(
            {"required_items": [{
                "item_id": "case:contract",
                "kind": "case",
                "case_id": "contract",
                "command": command,
                "route_id": "qwork.private-playwright.contract-spec.contract",
                "required_screenshot_states": [],
            }]},
            {"contract": {
                "id": "contract",
                "title": "contract-only",
                "sources": [],
                "execution_contract": {
                    "route_id": "qwork.private-playwright.contract-spec.contract",
                    "launch": {"strategy": "command", "command_or_tool": command},
                    "authorization": {"required": False},
                    "observability": {"source_contract": {
                        "spec": "skill://qwork-test-dataset/data/e2e/contract.spec.ts",
                    }},
                },
            }},
        )
        if classified["case:contract"].get("required_screenshot_states") != []:
            raise RuntimeError("contract-only empty screenshot contract was not preserved")
        print(json.dumps({"status": "ok", "public_files": sorted(public_files), "raw_evidence_private": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
