#!/usr/bin/env python3
"""Storage boundary regression tests for QWork E2E runs and reports."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from external_artifact_storage import (
    REPORT_HTML_NAME,
    REPORT_JSON_NAME,
    TEMP_ROOT_NAME,
    validate_external_run_root,
)


def expect_failure(action, message: str) -> None:
    try:
        action()
    except ValueError as error:
        assert message in str(error), str(error)
    else:
        raise AssertionError(f"expected failure containing {message!r}")


def main() -> int:
    assert REPORT_JSON_NAME == "QWORK-E2E-REPORT.json"
    assert REPORT_HTML_NAME == "QWORK-E2E-REPORT.html"
    with tempfile.TemporaryDirectory(prefix="qwork-e2e-storage-") as value:
        root = Path(value)
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        skill = root / "skill"
        skill.mkdir()

        external = root / TEMP_ROOT_NAME
        run_root = external / "FULL-20260826-001"
        assert validate_external_run_root(run_root, protected_roots=[repo, skill]) == run_root.resolve()

        expect_failure(
            lambda: validate_external_run_root(repo / "test-artifacts/e2e/run", protected_roots=[repo, skill]),
            "protected Git or Skill root",
        )
        expect_failure(
            lambda: validate_external_run_root(skill / "data/runs/run", protected_roots=[repo, skill]),
            "protected Git or Skill root",
        )

        escape = external / "ESCAPE"
        external.mkdir()
        escape.symlink_to(repo, target_is_directory=True)
        expect_failure(
            lambda: validate_external_run_root(escape / "run", protected_roots=[repo, skill]),
            "protected Git or Skill root",
        )

    print("external E2E artifact storage test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
