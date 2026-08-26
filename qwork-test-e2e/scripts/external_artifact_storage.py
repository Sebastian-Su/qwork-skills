#!/usr/bin/env python3
"""Fail-closed filesystem boundary for QWork E2E temporary runs."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable


TEMP_ROOT_NAME = "QWORK-E2E-TEMPORARY-DATA-DO-NOT-COMMIT"
REPORT_JSON_NAME = "QWORK-E2E-REPORT.json"
REPORT_HTML_NAME = "QWORK-E2E-REPORT.html"


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _existing_ancestor(path: Path) -> Path:
    current = path
    while not current.exists():
        parent = current.parent
        if parent == current:
            break
        current = parent
    return current.resolve()


def _git_root(path: Path) -> Path | None:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=_existing_ancestor(path),
        text=True,
        capture_output=True,
    )
    return Path(result.stdout.strip()).resolve() if result.returncode == 0 else None


def validate_external_run_root(
    value: Path, *, protected_roots: Iterable[Path]
) -> Path:
    if not value.is_absolute():
        raise ValueError("QWork E2E run root must be an absolute path")
    resolved = value.resolve()
    protected = [root.resolve() for root in protected_roots]
    git_root = _git_root(resolved)
    if any(_is_within(resolved, root) for root in protected) or (
        git_root is not None and _is_within(resolved, git_root)
    ):
        raise ValueError("QWork E2E run root resolves inside a protected Git or Skill root")
    marker_ancestors = [resolved, *resolved.parents]
    marker = next((path for path in marker_ancestors if path.name == TEMP_ROOT_NAME), None)
    if marker is None or marker == resolved:
        raise ValueError(f"QWork E2E run root must be below {TEMP_ROOT_NAME}")
    return resolved
