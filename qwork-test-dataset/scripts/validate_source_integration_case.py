#!/usr/bin/env python3
"""Run one fail-closed cross-repository integration Case."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_server(repo: Path) -> Path:
    candidates: list[Path] = []
    override = os.environ.get("QWORK_SERVER_DIR", "").strip()
    if override:
        candidates.append(Path(override).expanduser())
    common_git = Path(
        git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
    )
    main_checkout = common_git.parent if common_git.name == ".git" else common_git
    candidates.append(main_checkout.parent / "qwork_server")
    for candidate in candidates:
        resolved = candidate.resolve()
        if (resolved / "cmd/dev-api").is_dir():
            return resolved
    raise ValueError(
        "qwork_server checkout is unavailable; set QWORK_SERVER_DIR to the exact bound revision"
    )


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--skill-root", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repo = args.repo.resolve()
    skill_root = args.skill_root.resolve()
    case_path = skill_root / "data/datasets/cases" / f"{args.case_id}.json"
    case = load(case_path)
    contract = case.get("execution_contract") or {}
    route = str(contract.get("route_id") or "")
    source = (contract.get("observability") or {}).get("source_contract") or {}
    failures: list[str] = []
    if case.get("id") != args.case_id:
        failures.append("Case ID does not match the requested coordinate")
    if not route.startswith("qwork.dataset.source-integration."):
        failures.append("Case is not a source integration route")
    if source.get("repository") != "qwork_server":
        failures.append("only qwork_server is an allowed source integration repository")

    expected_requirements = sorted(
        str(value) for value in case.get("selection", {}).get("requirement_ids") or []
    )
    source_requirements = sorted(
        str(value) for value in source.get("requirement_ids") or []
    )
    requirement_tests = {
        str(requirement_id): [str(test) for test in tests]
        for requirement_id, tests in (source.get("requirement_tests") or {}).items()
    }
    tests = [str(value) for value in source.get("tests") or []]
    packages = [str(value) for value in source.get("packages") or []]
    if source_requirements != expected_requirements:
        failures.append("source integration requirement set does not close the Case")
    if sorted(requirement_tests) != expected_requirements:
        failures.append("requirement-to-test map does not close the Case")
    if any(not mapped or any(test not in tests for test in mapped) for mapped in requirement_tests.values()):
        failures.append("requirement-to-test map references missing or empty tests")
    if not tests or len(tests) != len(set(tests)) or not packages:
        failures.append("source integration package/test list is missing or duplicated")

    server = resolve_server(repo)
    actual_revision = git(server, "rev-parse", "HEAD").strip()
    expected_revision = str(source.get("revision") or "")
    if actual_revision != expected_revision:
        failures.append(
            f"qwork_server revision drift: {actual_revision} != {expected_revision}"
        )
    status_entries = [line for line in git(server, "status", "--porcelain").splitlines() if line]
    if status_entries:
        failures.append("qwork_server worktree is not clean")

    authority_results = []
    for authority in source.get("authority_files") or []:
        relative = str(authority.get("path") or "")
        expected = str(authority.get("sha256") or "")
        path = (server / relative).resolve()
        inside = False
        try:
            path.relative_to(server)
            inside = True
        except ValueError:
            pass
        actual = sha256(path) if inside and path.is_file() else None
        matched = actual == expected
        authority_results.append(
            {"path": relative, "expected_sha256": expected, "actual_sha256": actual, "matched": matched}
        )
        if not matched:
            failures.append(f"authority file drift: {relative}")

    test_results: dict[str, str] = {test: "not-run" for test in tests}
    command = [
        "go",
        "test",
        "-json",
        *packages,
        "-run",
        "^(" + "|".join(re.escape(test) for test in tests) + ")$",
        "-count=1",
    ]
    stdout = ""
    stderr = ""
    exit_code = 1
    if not failures:
        result = subprocess.run(command, cwd=server, text=True, capture_output=True)
        stdout, stderr, exit_code = result.stdout, result.stderr, result.returncode
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            test = str(event.get("Test") or "")
            action = str(event.get("Action") or "")
            if test in test_results and action in {"pass", "fail", "skip"}:
                test_results[test] = action
        missing = [test for test, status in test_results.items() if status == "not-run"]
        nonpassing = [test for test, status in test_results.items() if status != "pass"]
        if exit_code:
            failures.append(f"go test exited with {exit_code}")
        if missing:
            failures.append("bound tests were not observed: " + ", ".join(missing))
        if nonpassing:
            failures.append("bound tests did not pass: " + ", ".join(nonpassing))

    requirement_results = [
        {
            "requirement_id": requirement_id,
            "tests": mapped,
            "status": (
                "pass"
                if mapped and all(test_results.get(test) == "pass" for test in mapped)
                else "fail"
            ),
        }
        for requirement_id, mapped in sorted(requirement_tests.items())
    ]
    if any(item["status"] != "pass" for item in requirement_results):
        failures.append("one or more Requirements lack passing test evidence")

    report = {
        "schema_version": 1,
        "case_id": args.case_id,
        "status": "pass" if not failures else "fail",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "qwork_revision": git(repo, "rev-parse", "HEAD").strip(),
        "repository": "qwork_server",
        "repository_path": str(server),
        "expected_revision": expected_revision,
        "actual_revision": actual_revision,
        "worktree_clean": not status_entries,
        "authority_files": authority_results,
        "command": command,
        "exit_code": exit_code,
        "tests": [
            {"name": test, "status": status} for test, status in test_results.items()
        ],
        "requirements": requirement_results,
        "zero_real_provider_calls": True,
        "isolation": "in-memory qwork_server router/service fixtures",
        "cleanup": {"test_process_exited": True, "external_state_created": False},
        "failures": list(dict.fromkeys(failures)),
        "stdout_sha256": "sha256:" + hashlib.sha256(stdout.encode()).hexdigest(),
        "stderr_sha256": "sha256:" + hashlib.sha256(stderr.encode()).hexdigest(),
    }
    write_report(args.output.resolve(), report)
    print(json.dumps({"status": report["status"], "case_id": args.case_id, "output": str(args.output), "failures": report["failures"]}, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
