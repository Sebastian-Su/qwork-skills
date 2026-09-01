#!/usr/bin/env python3
"""Regression tests for the private Dataset storage boundary."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from validate_private_storage import validate


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


class ValidatePrivateStorageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.team_repo = root / "qwork"
        self.skill_repo = root / "qwork-skills"
        self.skill_root = self.skill_repo / "qwork-test-dataset"

        self.team_repo.mkdir()
        self.skill_root.mkdir(parents=True)
        git(self.team_repo, "init")
        git(self.skill_repo, "init")

        (self.team_repo / ".gitignore").write_text("/.agents/skills/qwork-test-dataset\n", encoding="utf-8")
        (self.skill_root / ".gitignore").write_text(
            "/data/*\n"
            "!/data/benchmarks/\n"
            "!/data/benchmarks/**\n"
            "!/data/datasets/\n"
            "!/data/datasets/**\n"
            "!/data/e2e/\n"
            "!/data/e2e/**\n"
            "!/data/evidence/\n"
            "!/data/evidence/**\n"
            "!/data/reference-runs/\n"
            "!/data/reference-runs/**\n"
            "!/data/sources/\n"
            "!/data/sources/**\n",
            encoding="utf-8",
        )
        (self.skill_repo / ".gitattributes").write_text(
            "qwork-test-dataset/data/**/*.png filter=lfs diff=lfs merge=lfs -text\n"
            "qwork-test-dataset/data/**/*.trace filter=lfs diff=lfs merge=lfs -text\n",
            encoding="utf-8",
        )
        for relative_path in (
            "data/benchmarks/manifest.json",
            "data/benchmarks/ui-visual/reference.png",
            "data/datasets/source-acceptance.json",
            "data/e2e/functional-contracts.spec.ts",
            "data/evidence/manifest.json",
            "data/reference-runs/reference/report.json",
            "data/reference-runs/reference/execution.trace",
            "data/sources/source/manifest.json",
        ):
            path = self.skill_root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(
                b"binary fixture\n" if path.suffix in {".png", ".trace"} else b"{}\n"
            )

        git(self.skill_repo, "add", "qwork-test-dataset")
        git(self.skill_repo, "-c", "user.name=QWork Test", "-c", "user.email=qwork@example.invalid", "commit", "-m", "test fixture")

        skill_entry = self.team_repo / ".agents" / "skills" / "qwork-test-dataset"
        skill_entry.parent.mkdir(parents=True)
        skill_entry.symlink_to(Path(os.path.relpath(self.skill_root, skill_entry.parent)))
        git(self.team_repo, "add", ".gitignore")
        git(self.team_repo, "-c", "user.name=QWork Test", "-c", "user.email=qwork@example.invalid", "commit", "-m", "test fixture")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def assert_rejects_without_lfs(self, attributes: str, relative_file: str) -> None:
        (self.skill_repo / ".gitattributes").write_text(attributes, encoding="utf-8")
        git(self.skill_repo, "add", ".gitattributes", relative_file)
        git(
            self.skill_repo,
            "-c",
            "user.name=QWork Test",
            "-c",
            "user.email=qwork@example.invalid",
            "commit",
            "-m",
            "remove lfs attribute",
        )

        filename = re.escape(Path(relative_file).name)
        with self.assertRaisesRegex(ValueError, f"Git LFS.*{filename}"):
            validate(self.team_repo, "qwork-test-dataset", [])

    def test_accepts_clean_versioned_dataset_assets(self) -> None:
        result = validate(
            self.team_repo,
            "qwork-test-dataset",
            [self.team_repo / ".agents/skills/qwork-test-dataset/data/datasets/source-acceptance.json"],
        )

        self.assertEqual(result["status"], "ok")
        self.assertIn(
            "qwork-test-dataset/data/datasets",
            result["versioned_data_roots"],
        )
        self.assertEqual(result["lfs_file_count"], 2)

    def test_rejects_missing_versioned_root(self) -> None:
        shutil.rmtree(self.skill_root / "data/sources")

        with self.assertRaisesRegex(ValueError, "versioned Dataset root.*data/sources"):
            validate(self.team_repo, "qwork-test-dataset", [])

    def test_rejects_ignored_runtime_data_inside_repository(self) -> None:
        runtime_file = self.skill_root / "data/runs/run.json"
        runtime_file.parent.mkdir(parents=True)
        runtime_file.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "runtime data must be outside.*data/runs"):
            validate(self.team_repo, "qwork-test-dataset", [])

    def test_rejects_ignored_file_inside_versioned_root(self) -> None:
        with (self.skill_root / ".gitignore").open("a", encoding="utf-8") as ignore_file:
            ignore_file.write("/data/datasets/ignored.json\n")
        ignored_file = self.skill_root / "data/datasets/ignored.json"
        ignored_file.write_text("{}\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "untracked or ignored files.*ignored.json"):
            validate(self.team_repo, "qwork-test-dataset", [])

    def test_rejects_binary_without_lfs_attribute(self) -> None:
        self.assert_rejects_without_lfs(
            "",
            "qwork-test-dataset/data/benchmarks/ui-visual/reference.png",
        )

    def test_rejects_trace_without_lfs_attribute(self) -> None:
        self.assert_rejects_without_lfs(
            "qwork-test-dataset/data/**/*.png filter=lfs diff=lfs merge=lfs -text\n",
            "qwork-test-dataset/data/reference-runs/reference/execution.trace",
        )


if __name__ == "__main__":
    unittest.main()
