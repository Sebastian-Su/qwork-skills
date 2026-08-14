#!/usr/bin/env python3
"""Regression: an external Dataset Skill must resolve QWork's TypeScript dependency."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    script_root = Path(__file__).resolve().parent
    extractor = script_root / "extract_playwright_contracts.mjs"
    bare_import = re.compile(
        r"(?:from\s+|import\s*\()\s*['\"]((?!node:|[./])[^'\"]+)['\"]"
    )
    package_call = re.compile(r"requireFromProject\(['\"]([^'\"]+)['\"]\)")
    allowed_bare = {
        "electron-isolated-build.config.ts": {"@vitejs/plugin-react", "electron-vite"},
    }
    packages: set[str] = set()
    violations: list[str] = []
    for script in sorted([*script_root.glob("*.mjs"), *script_root.glob("*.ts")]):
        content = script.read_text(encoding="utf-8")
        imported = set(bare_import.findall(content))
        unexpected = sorted(imported - allowed_bare.get(script.name, set()))
        if unexpected:
            violations.append(f"{script.name}: {unexpected}")
        packages.update(imported)
        packages.update(package_call.findall(content))
    if violations:
        raise AssertionError(f"external Skill scripts contain bare package imports: {violations}")
    helper = (script_root / "project-require.mjs").as_uri()
    dependency_probe = subprocess.run(
        [
            "node",
            "--input-type=module",
            "--eval",
            (
                f"import {{ requireFromProject }} from {json.dumps(helper)}; "
                "for (const name of JSON.parse(process.argv[1])) requireFromProject(name);"
            ),
            json.dumps(sorted(packages)),
        ],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    if dependency_probe.returncode != 0:
        raise AssertionError(dependency_probe.stderr.strip() or "dependency probe failed")
    project_entry = repo / ".agents/skills/qwork-test-dataset"
    if project_entry.resolve(strict=True) != script_root.parent:
        raise AssertionError(f"unexpected project Skill entry: {project_entry}")
    node_options = f"{os.environ.get('NODE_OPTIONS', '')} --preserve-symlinks".strip()
    list_probe = subprocess.run(
        [
            str(repo / "node_modules/.bin/playwright"),
            "test",
            "--config",
            str(project_entry / "scripts/playwright-private.config.ts"),
            "--list",
        ],
        cwd=repo,
        env={
            **os.environ,
            "NODE_OPTIONS": node_options,
            "QWORK_E2E_APP_ROOT": "/tmp/qwork-private-list-probe",
        },
        text=True,
        capture_output=True,
    )
    if list_probe.returncode != 0 or "Total:" not in list_probe.stdout:
        raise AssertionError(
            list_probe.stderr.strip() or list_probe.stdout.strip() or "private Playwright list failed"
        )
    source = """import { expect, test } from '@playwright/test';
test('external Skill dependency resolution', async ({ page }) => {
  await page.getByRole('button', { name: 'Run' }).click();
  await expect(page.getByText('Done')).toBeVisible();
});
"""
    result = subprocess.run(
        ["node", str(extractor), "e2e/external-skill-resolution.spec.ts"],
        cwd=repo,
        input=source,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip() or "extractor failed without stderr")
    payload = json.loads(result.stdout)
    tests = payload.get("tests", [])
    if len(tests) != 1 or tests[0].get("title") != "external Skill dependency resolution":
        raise AssertionError(f"unexpected extraction result: {payload}")
    if len(tests[0].get("actions", [])) != 1 or len(tests[0].get("assertions", [])) != 1:
        raise AssertionError(f"action/assertion contract was not extracted: {tests[0]}")
    print(
        "external Skill Node dependency resolution: pass "
        f"({len(packages)} project packages, {len(violations)} bare imports, private Playwright listed)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
