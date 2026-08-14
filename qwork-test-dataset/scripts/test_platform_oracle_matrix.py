#!/usr/bin/env python3
"""Validate the closed 30-pointer platform/visual Oracle matrix."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git_json(repo: Path, revision: str, path: str) -> dict:
    raw = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(raw)


def main() -> int:
    skill_root = Path(__file__).resolve().parents[1]
    repo = Path.cwd().resolve()
    matrix = json.loads(
        (skill_root / "references/platform-oracle-matrix.json").read_text(encoding="utf-8")
    )
    requirements = matrix["requirements"]
    coordinates = {(item["source"], item["pointer"]) for item in requirements}
    if len(requirements) != 30 or len(coordinates) != 30:
        raise AssertionError(
            f"platform matrix must contain exactly 30 unique source pointers, got {len(requirements)}/{len(coordinates)}"
        )

    sidebar = git_json(repo, "develop", "e2e/oracles/workbuddy-5.3.5-sidebar-account.json")
    shell = git_json(repo, "develop", "e2e/oracles/workbuddy-5.3.5-shell-home.json")
    expected: set[tuple[str, str]] = {
        *(('sidebar_account', f'/coverage/requiredBeforePlatformCompletion/{index}') for index, _ in enumerate(sidebar['coverage']['requiredBeforePlatformCompletion'])),
        ('sidebar_account', '/sidebar/collapsed/darwinFullscreenToggleX'),
        *(('shell_home', f'/coverage/requiredBeforePixelCompletion/{index}') for index, _ in enumerate(shell['coverage']['requiredBeforePixelCompletion'])),
        *(('shell_home', f'/platform/darwin/fullscreenCollapsedToggle/{field}') for field in ('height', 'width', 'x', 'y')),
        *(('shell_home', f'/platform/darwin/fullscreenExpandedToggle/{field}') for field in ('height', 'width', 'x', 'y')),
        ('shell_home', '/platform/darwin/fullscreenTrafficLightOffset'),
        ('shell_home', '/platform/darwin/shortcutModifier'),
        ('shell_home', '/platform/darwin/titleBarStyle'),
        ('shell_home', '/platform/win32/pixelGoldenDpiPercent'),
        ('shell_home', '/platform/win32/shortcutModifier'),
        ('shell_home', '/platform/win32/showTrafficLightSafeArea'),
        ('shell_home', '/platform/win32/smokeDpiPercent'),
        ('shell_home', '/platform/win32/titleBarStyle'),
    }
    if coordinates != expected:
        raise AssertionError(
            f"platform matrix pointer closure drifted: missing={sorted(expected - coordinates)} extra={sorted(coordinates - expected)}"
        )

    captures = matrix["captures"]
    capture_ids = {item["id"] for item in captures}
    if len(captures) != 14 or len(capture_ids) != 14:
        raise AssertionError("platform visual capture matrix must contain 14 unique concrete states")
    state_sets = matrix["state_sets"]
    if state_sets != {
        "shell-home": ["shell-home"],
        "sidebar-all-states": [
            "shell-home",
            "sidebar-hover",
            "sidebar-collapsed",
            "search-dialog",
            "filter-popover",
            "account-menu",
        ],
    }:
        raise AssertionError("platform visual state sets drifted")
    if sum(len(state_sets[item["state_set"]]) for item in captures) != 44:
        raise AssertionError("platform matrix must expand to exactly 44 frame coordinates")
    missing = [item["id"] for item in captures if item["baseline_root"] is None]
    if len(missing) != 14:
        raise AssertionError("an unapproved baseline entered the matrix without a source-bound promotion")

    builder = load_module("build_product_baseline", skill_root / "scripts/build_product_baseline.py")
    if builder.target_platforms_for_title("Case @darwin") != ["darwin"]:
        raise AssertionError("@darwin Case did not compile to a Darwin-only route")
    if builder.target_platforms_for_title("Case @win32-125") != ["win32"]:
        raise AssertionError("@win32 Case did not compile to a Windows-only route")
    if builder.target_platforms_for_title("untagged Case") != ["darwin", "win32", "linux"]:
        raise AssertionError("untagged Case lost the default platform matrix")

    comparator = load_module("compare_visual_frame", skill_root / "scripts/compare_visual_frame.py")
    with tempfile.TemporaryDirectory(prefix="qwork-frame-compare-") as value:
        root = Path(value)
        baseline = root / "baseline.png"
        same = root / "same.png"
        changed = root / "changed.png"
        Image.new("RGBA", (4, 4), (255, 255, 255, 255)).save(baseline)
        Image.new("RGBA", (4, 4), (255, 255, 255, 255)).save(same)
        Image.new("RGBA", (4, 4), (0, 0, 0, 255)).save(changed)
        if comparator.compare(same, baseline, 0.01, root / "same-report")["status"] != "pass":
            raise AssertionError("identical visual frames did not pass")
        if comparator.compare(changed, baseline, 0.01, root / "changed-report")["status"] != "fail":
            raise AssertionError("different visual frames did not fail")

    print("platform Oracle matrix: 30 pointers / 14 capture coordinates / 44 fail-closed frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
