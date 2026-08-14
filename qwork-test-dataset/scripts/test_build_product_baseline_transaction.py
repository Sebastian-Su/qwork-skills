#!/usr/bin/env python3
"""Regression test: a failed compile cannot destroy the last good Dataset."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile


def main() -> int:
    script = pathlib.Path(__file__).with_name("build_product_baseline.py")
    with tempfile.TemporaryDirectory(prefix="qwork-dataset-transaction-") as root_value:
        root = pathlib.Path(root_value)
        output = root / "datasets"
        cases = output / "cases"
        cases.mkdir(parents=True)
        sentinel = cases / "last-good.json"
        sentinel.write_text('{"status":"last-good"}\n', encoding="utf-8")
        dataset = output / "dataset.json"
        dataset.write_text('{"version":"last-good"}\n', encoding="utf-8")

        missing = root / "missing-source"
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--repo",
                str(root),
                "--output-root",
                str(output),
                "--lark-snapshot",
                str(missing),
                "--storage-snapshot",
                str(missing),
                "--visual-manifest",
                str(missing),
                "--cdp-snapshot",
                str(missing),
                "--develop-snapshot",
                str(missing),
                "--head-snapshot",
                str(missing),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            raise AssertionError("invalid build unexpectedly succeeded")
        if sentinel.read_text(encoding="utf-8") != '{"status":"last-good"}\n':
            raise AssertionError("failed build changed the last-good Case")
        if dataset.read_text(encoding="utf-8") != '{"version":"last-good"}\n':
            raise AssertionError("failed build changed the last-good dataset index")
        leftovers = list(root.glob(".datasets.staging-*")) + list(root.glob(".datasets.previous-*"))
        if leftovers:
            raise AssertionError(f"failed build left transaction debris: {leftovers}")
    print("build_product_baseline transaction test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
