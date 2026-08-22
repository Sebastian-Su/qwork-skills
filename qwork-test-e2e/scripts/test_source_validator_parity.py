#!/usr/bin/env python3
"""Ensure the project adapter accepts every contract accepted by its Dataset."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


def run(command: list[str], repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=repo, text=True, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    dataset = repo / ".agents/skills/qwork-test-dataset"
    adapter = Path(__file__).resolve().parent.parent
    manifest = "skill://qwork-test-dataset/data/datasets/source-acceptance.json"

    authoritative = run(
        [
            sys.executable,
            str(dataset / "scripts/validate_source_acceptance.py"),
            "--repo",
            str(repo),
            "--manifest",
            manifest,
        ],
        repo,
    )
    if authoritative.returncode:
        raise RuntimeError(
            "Dataset authority rejected its own manifest:\n"
            + authoritative.stdout
            + authoritative.stderr
        )

    projected = run(
        [
            sys.executable,
            str(adapter / "scripts/validate_source_acceptance.py"),
            "--repo",
            str(repo),
            "--manifest",
            manifest,
        ],
        repo,
    )
    if projected.returncode:
        raise RuntimeError(
            "project source validator drifted from Dataset authority:\n"
            + projected.stdout
            + projected.stderr
        )

    print("source validator parity: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
