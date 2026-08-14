#!/usr/bin/env python3
"""Regression test: built ESM must resolve dependencies below transient app root."""

from __future__ import annotations

from pathlib import Path


def main() -> int:
    source = Path(__file__).with_name("build_isolated_electron.mjs").read_text(encoding="utf-8")
    if 'const buildRoot = path.join(appRoot, "out")' not in source:
        raise AssertionError("isolated build output is not rooted at app/out")
    if 'fs.symlink(buildRoot, path.join(appRoot, "out"))' in source:
        raise AssertionError("app/out is still a symlink to a dependency-orphaned build root")
    if 'path.join(appRoot, "node_modules")' not in source:
        raise AssertionError("transient app has no project dependency entry")
    if "build_output_is_inside_transient_app" not in source:
        raise AssertionError("build manifest does not attest transient app containment")
    print("isolated build dependency resolution test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
