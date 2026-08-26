#!/usr/bin/env python3
"""Shared fail-closed boundary for Dataset execution output."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable


TEMP_ROOT_NAME = "QWORK-E2E-TEMPORARY-DATA-DO-NOT-COMMIT"


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _existing_ancestor(path: Path) -> Path:
    current = path
    while not current.exists() and current.parent != current:
        current = current.parent
    return current.resolve()


def validate_external_output_root(value: Path, *, protected_roots: Iterable[Path]) -> Path:
    if not value.is_absolute():
        raise ValueError("Dataset output must be an absolute path")
    resolved = value.resolve()
    protected = [root.resolve() for root in protected_roots]
    git = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=_existing_ancestor(resolved),
        text=True,
        capture_output=True,
    )
    git_root = Path(git.stdout.strip()).resolve() if git.returncode == 0 else None
    if any(_within(resolved, root) for root in protected) or (
        git_root is not None and _within(resolved, git_root)
    ):
        raise ValueError("Dataset output resolves inside a protected Git or Skill root")
    marker = next((path for path in [resolved, *resolved.parents] if path.name == TEMP_ROOT_NAME), None)
    if marker is None or marker == resolved:
        raise ValueError(f"Dataset output must be below {TEMP_ROOT_NAME}")
    return resolved
