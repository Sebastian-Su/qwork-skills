#!/usr/bin/env python3
"""Regression test: Playwright resolution flags must not enter Electron apps."""

from __future__ import annotations

from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    launchers = sorted((root / "data/e2e/fixtures").glob("launch*-isolated.ts"))
    if len(launchers) != 3:
        raise AssertionError(f"expected three private Electron launchers, found {len(launchers)}")
    for launcher in launchers:
        source = launcher.read_text(encoding="utf-8")
        if "NODE_OPTIONS: undefined" not in source:
            raise AssertionError(f"{launcher.name} leaks Playwright NODE_OPTIONS into Electron")
        if "ELECTRON_RUN_AS_NODE: undefined" not in source:
            raise AssertionError(f"{launcher.name} does not clear ELECTRON_RUN_AS_NODE")
        if "captureElectronRuntime(app)" not in source:
            raise AssertionError(f"{launcher.name} does not capture Electron runtime logs")
        if '"--enable-logging=stderr"' not in source or "timeout: 20_000" not in source:
            raise AssertionError(f"{launcher.name} lacks bounded fail-closed launch diagnostics")
    print("private Electron environment isolation test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
