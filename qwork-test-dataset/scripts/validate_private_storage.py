#!/usr/bin/env python3
"""Validate the external private Dataset Skill and its project entrypoint."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


VERSIONED_DATA_ROOTS = {
    "benchmarks",
    "datasets",
    "e2e",
    "evidence",
    "reference-runs",
    "sources",
}
LFS_SUFFIXES = {".jpeg", ".jpg", ".png", ".trace", ".webp", ".zip"}


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def visible_status(repo: Path, relative_path: str) -> list[str]:
    result = run_git(
        repo,
        "status",
        "--short",
        "--untracked-files=all",
        "--",
        relative_path,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status failed")
    return [line for line in result.stdout.splitlines() if line]


def resolve_without_escape(candidate: Path, skill_root: Path) -> Path:
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(skill_root)
    except ValueError as exc:
        raise ValueError(f"path escapes private Dataset Skill: {candidate}") from exc
    return resolved


def git_root(path: Path) -> Path:
    result = run_git(path, "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        raise ValueError(f"not inside a Git repository: {path}")
    return Path(result.stdout.strip()).resolve(strict=True)


def validate(repo: Path, skill_name: str, paths: list[Path]) -> dict[str, object]:
    repo = repo.resolve(strict=True)
    if run_git(repo, "rev-parse", "--show-toplevel").returncode != 0:
        raise ValueError(f"not a Git repository: {repo}")

    skill_entry = repo / ".agents" / "skills" / skill_name
    if not skill_entry.is_dir():
        raise ValueError(f"private Dataset Skill does not exist: {skill_entry}")
    if not skill_entry.is_symlink():
        raise ValueError(
            f"private Dataset Skill must be a relative link into its private repository: {skill_entry}"
        )
    raw_link = os.readlink(skill_entry)
    if Path(raw_link).is_absolute():
        raise ValueError(f"private Dataset Skill link must be relative: {skill_entry} -> {raw_link}")
    skill_root = skill_entry.resolve(strict=True)
    source_repo = git_root(skill_root)
    if source_repo == repo:
        raise ValueError("private Dataset Skill entity must not live in the team repository")
    resolve_without_escape(skill_root, source_repo)

    relative_skill = skill_entry.relative_to(repo).as_posix()
    ignored = run_git(repo, "check-ignore", "-q", "--no-index", "--", relative_skill)
    if ignored.returncode != 0:
        raise ValueError(f"private Dataset Skill is not ignored: {relative_skill}")

    tracked = run_git(repo, "ls-files", "--", relative_skill)
    if tracked.returncode != 0:
        raise RuntimeError(tracked.stderr.strip() or "git ls-files failed")
    tracked_files = [line for line in tracked.stdout.splitlines() if line]
    if tracked_files:
        raise ValueError(f"private Dataset Skill contains tracked files: {tracked_files}")

    skill_status = visible_status(repo, relative_skill)
    if skill_status:
        raise ValueError(f"private Dataset Skill appears in git status: {skill_status}")

    data_root = skill_root / "data"
    if not data_root.is_dir():
        raise ValueError(f"private Dataset data root does not exist: {data_root}")
    tracked_fixture_root = data_root / "e2e"
    if not tracked_fixture_root.is_dir():
        raise ValueError(f"private Dataset E2E source root does not exist: {tracked_fixture_root}")
    data_roots = {entry.name: entry for entry in data_root.iterdir()}
    unexpected_data_roots = sorted(set(data_roots) - VERSIONED_DATA_ROOTS)
    if unexpected_data_roots:
        unexpected_path = (data_root / unexpected_data_roots[0]).relative_to(source_repo)
        raise ValueError(
            f"Dataset runtime data must be outside source repository: {unexpected_path}"
        )
    versioned_data_roots: list[str] = []
    versioned_data_file_count = 0
    lfs_file_count = 0
    for root_name in sorted(VERSIONED_DATA_ROOTS):
        state_root = data_root / root_name
        relative_state = state_root.relative_to(source_repo).as_posix()
        if not state_root.is_dir():
            raise ValueError(
                f"versioned Dataset root is missing or not a directory: {relative_state}"
            )
        visible_data_status = visible_status(source_repo, relative_state)
        if visible_data_status:
            raise ValueError(
                f"versioned Dataset data is not clean in source repository: {visible_data_status}"
            )
        tracked_result = run_git(source_repo, "ls-files", "-z", "--", relative_state)
        if tracked_result.returncode != 0:
            raise RuntimeError(tracked_result.stderr.strip() or "source git ls-files failed")
        tracked_files = {path for path in tracked_result.stdout.split("\0") if path}
        actual_files = {
            entry.relative_to(source_repo).as_posix()
            for entry in state_root.rglob("*")
            if entry.is_file() or entry.is_symlink()
        }
        untracked_files = sorted(actual_files - tracked_files)
        if untracked_files:
            raise ValueError(
                "versioned Dataset data contains untracked or ignored files: "
                f"{untracked_files}"
            )
        for relative_file in sorted(actual_files):
            if Path(relative_file).suffix.lower() not in LFS_SUFFIXES:
                continue
            attribute = run_git(
                source_repo,
                "check-attr",
                "filter",
                "--",
                relative_file,
            )
            if attribute.returncode != 0:
                raise RuntimeError(attribute.stderr.strip() or "git check-attr failed")
            if attribute.stdout.rsplit(": ", 1)[-1].strip() != "lfs":
                raise ValueError(
                    f"versioned Dataset binary must use Git LFS: {relative_file}"
                )
            lfs_file_count += 1
        versioned_data_roots.append(relative_state)
        versioned_data_file_count += len(tracked_files)

    checked_paths = []
    for path in paths:
        candidate = path if path.is_absolute() else repo / path
        checked_paths.append(str(resolve_without_escape(candidate, skill_root)))

    escaped_symlinks = []
    for entry in data_root.rglob("*"):
        if entry.is_symlink():
            try:
                entry.resolve(strict=False).relative_to(skill_root)
            except ValueError:
                escaped_symlinks.append(str(entry))
    if escaped_symlinks:
        raise ValueError(f"Skill data contains escaping symlinks: {escaped_symlinks}")

    return {
        "status": "ok",
        "repository": str(repo),
        "skill": skill_name,
        "skill_entry": str(skill_entry),
        "skill_link": raw_link,
        "skill_root": str(skill_root),
        "source_repository": str(source_repo),
        "git_ignored": True,
        "tracked_files": [],
        "git_status_entries": [],
        "tracked_fixture_root": str(tracked_fixture_root),
        "versioned_data_roots": versioned_data_roots,
        "versioned_data_file_count": versioned_data_file_count,
        "lfs_file_count": lfs_file_count,
        "checked_paths": checked_paths,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--skill", required=True)
    parser.add_argument("--path", type=Path, action="append", default=[])
    args = parser.parse_args()
    try:
        result = validate(args.repo, args.skill, args.path)
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
