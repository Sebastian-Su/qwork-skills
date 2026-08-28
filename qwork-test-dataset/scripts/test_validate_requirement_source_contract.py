#!/usr/bin/env python3
"""Regression coverage for direct requirement-to-Playwright source binding."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from validate_route_registry import validate_requirement_source_contract


class RequirementSourceContractTest(unittest.TestCase):
    def test_accepts_one_exact_test_at_current_head(self) -> None:
        source = b'test("cloud workspace", async () => { expect(true).toBe(true); });\n'
        head = "a" * 40
        body_hash = "b" * 64
        with tempfile.TemporaryDirectory(prefix="qwork-requirement-route-") as value:
            repo = Path(value)
            spec = repo / "e2e/workspace.spec.ts"
            spec.parent.mkdir()
            spec.write_bytes(source)
            launch = {
                "strategy": "command",
                "command_or_tool": 'npx playwright test e2e/workspace.spec.ts -g "cloud workspace"',
                "source_contract": {
                    "spec": "e2e/workspace.spec.ts",
                    "title": "cloud workspace",
                    "line_start": 1,
                    "line_end": 1,
                    "body_sha256": f"sha256:{body_hash}",
                    "execution_revision": head,
                    "spec_sha256": "sha256:" + hashlib.sha256(source).hexdigest(),
                },
            }
            extracted = json.dumps(
                {
                    "tests": [
                        {
                            "title": "cloud workspace",
                            "line_start": 1,
                            "line_end": 1,
                            "body_sha256": body_hash,
                        }
                    ]
                }
            )

            def run(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes | str]:
                if command[:2] == ["git", "show"]:
                    return subprocess.CompletedProcess(command, 0, stdout=source, stderr=b"")
                return subprocess.CompletedProcess(command, 0, stdout=extracted, stderr="")

            errors: list[str] = []
            with patch("validate_route_registry.subprocess.run", side_effect=run):
                validate_requirement_source_contract(
                    route_id="qwork.requirement.cloud-workspace",
                    launch=launch,
                    repo=repo,
                    head=head,
                    root=repo,
                    errors=errors,
                )
            self.assertEqual(errors, [])

    def test_rejects_a_stale_execution_revision(self) -> None:
        errors: list[str] = []
        validate_requirement_source_contract(
            route_id="qwork.requirement.cloud-workspace",
            launch={
                "strategy": "command",
                "command_or_tool": 'npx playwright test e2e/workspace.spec.ts -g "cloud workspace"',
                "source_contract": {
                    "spec": "e2e/workspace.spec.ts",
                    "title": "cloud workspace",
                    "execution_revision": "b" * 40,
                },
            },
            repo=Path("."),
            head="a" * 40,
            root=Path("."),
            errors=errors,
        )
        self.assertIn("must bind the current repository HEAD", errors[0])


if __name__ == "__main__":
    unittest.main()
