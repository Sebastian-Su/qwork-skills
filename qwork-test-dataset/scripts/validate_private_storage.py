#!/usr/bin/env python3
"""Validate the external private Dataset Skill and its project entrypoint."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )


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

    status = run_git(repo, "status", "--short", "--untracked-files=all", "--", relative_skill)
    if status.returncode != 0:
        raise RuntimeError(status.stderr.strip() or "git status failed")
    visible_status = [line for line in status.stdout.splitlines() if line]
    if visible_status:
        raise ValueError(f"private Dataset Skill appears in git status: {visible_status}")

    data_root = skill_root / "data"
    if not data_root.is_dir():
        raise ValueError(f"private Dataset data root does not exist: {data_root}")
    tracked_fixture_root = data_root / "e2e"
    if not tracked_fixture_root.is_dir():
        raise ValueError(f"private Dataset E2E source root does not exist: {tracked_fixture_root}")
    private_state_roots = sorted(
        entry for entry in data_root.iterdir() if entry.name != "e2e"
    )
    ignored_state_roots: list[str] = []
    for state_root in private_state_roots:
        relative_state = state_root.relative_to(source_repo).as_posix()
        data_ignored = run_git(
            source_repo, "check-ignore", "-q", "--no-index", "--", relative_state
        )
        if data_ignored.returncode != 0:
            raise ValueError(
                f"private Dataset mutable data is not ignored by source repository: {relative_state}"
            )
        data_tracked = run_git(source_repo, "ls-files", "--", relative_state)
        if data_tracked.returncode != 0:
            raise RuntimeError(data_tracked.stderr.strip() or "source git ls-files failed")
        tracked_data_files = [line for line in data_tracked.stdout.splitlines() if line]
        if tracked_data_files:
            raise ValueError(
                f"private Dataset mutable data contains tracked files: {tracked_data_files}"
            )
        data_status = run_git(
            source_repo,
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            relative_state,
        )
        if data_status.returncode != 0:
            raise RuntimeError(data_status.stderr.strip() or "source git status failed")
        visible_data_status = [line for line in data_status.stdout.splitlines() if line]
        if visible_data_status:
            raise ValueError(
                f"private Dataset mutable data appears in source git status: {visible_data_status}"
            )
        ignored_state_roots.append(relative_state)

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
        "ignored_mutable_data_roots": ignored_state_roots,
        "data_git_ignored": True,
        "tracked_data_files": [],
        "data_git_status_entries": [],
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
