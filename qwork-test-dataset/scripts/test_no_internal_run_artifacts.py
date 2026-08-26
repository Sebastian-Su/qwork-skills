#!/usr/bin/env python3
"""Reject executable Case artifacts that point back into the Dataset Skill."""

from __future__ import annotations

from pathlib import Path


FORBIDDEN = "skill://qwork-test-dataset/data/runs/<run-id>/app + Electron"
REQUIRED = "external-run://QWORK-E2E-TEMPORARY-DATA-DO-NOT-COMMIT/<run-id>/app + Electron"


def main() -> int:
    skill = Path(__file__).resolve().parent.parent
    targets = [
        skill / "scripts/build_product_baseline.py",
        skill / "references/route-registry.yaml",
        *(skill / "data/datasets/cases").glob("*.json"),
    ]
    violations = [str(path.relative_to(skill)) for path in targets if FORBIDDEN in path.read_text(encoding="utf-8")]
    if violations:
        raise AssertionError(f"executable artifacts still target Dataset data/runs: {violations}")
    if REQUIRED not in (skill / "scripts/build_product_baseline.py").read_text(encoding="utf-8"):
        raise AssertionError("baseline generator does not emit the external temporary run locator")
    print("no internal run artifacts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
