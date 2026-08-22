#!/usr/bin/env python3
"""Refresh Coverage Map source hashes only after every mapped title still resolves."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess

import yaml


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def title_matches(actual: str, expected: str) -> bool:
    if actual == expected:
        return True
    return actual.split("|", 1)[-1].strip() == expected.split("|", 1)[-1].strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=pathlib.Path, required=True)
    parser.add_argument("--skill-root", type=pathlib.Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    repo = args.repo.resolve()
    root = args.skill_root.resolve()
    coverage_path = root / "references/document-case-coverage-map.yaml"
    text = coverage_path.read_text(encoding="utf-8")
    coverage = yaml.safe_load(text)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    extractor = root / "scripts/extract_playwright_contracts.mjs"

    authorities: dict[str, dict[str, str]] = {}
    titles_by_spec: dict[str, list[str]] = {}
    for spec_ref, record in coverage["spec_registry"].items():
        spec = str(record["spec"])
        prefix = "skill://qwork-test-dataset/"
        if spec.startswith(prefix):
            content = (root / spec.removeprefix(prefix)).read_bytes()
        else:
            content = subprocess.run(
                ["git", "show", f"{head}:{spec}"], cwd=repo, check=True, capture_output=True
            ).stdout
        parsed = subprocess.run(
            ["node", str(extractor), spec],
            cwd=repo,
            input=content.decode("utf-8"),
            text=True,
            check=True,
            capture_output=True,
        )
        titles_by_spec[spec_ref] = [str(item["title"]) for item in json.loads(parsed.stdout)["tests"]]
        authorities[spec_ref] = {
            "execution_revision": head,
            "spec_sha256": sha256_bytes(content),
        }

    errors = []
    for target_ref, target in coverage["target_registry"].items():
        spec_ref = str(target["spec_ref"])
        expected = str(target["title"])
        matches = [title for title in titles_by_spec[spec_ref] if title_matches(title, expected)]
        if len(matches) != 1:
            errors.append(f"{target_ref}: expected one title match for {expected!r}, got {matches}")
    if errors:
        raise SystemExit("\n".join(errors))

    current_spec = None
    changed = []
    output_lines = []
    for line in text.splitlines():
        spec_match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if spec_match and spec_match.group(1) in authorities:
            current_spec = spec_match.group(1)
        elif line and not line.startswith(" "):
            current_spec = None
        if current_spec and re.match(r"^    execution_revision:", line):
            expected = f"    execution_revision: {authorities[current_spec]['execution_revision']}"
            if line != expected:
                changed.append(f"{current_spec}.execution_revision")
                line = expected
        elif current_spec and re.match(r"^    spec_sha256:", line):
            expected = f"    spec_sha256: {authorities[current_spec]['spec_sha256']}"
            if line != expected:
                changed.append(f"{current_spec}.spec_sha256")
                line = expected
        output_lines.append(line)
    output = "\n".join(output_lines) + "\n"

    summary = {
        "status": "current" if not changed else ("updated" if args.write else "drift"),
        "head": head,
        "spec_count": len(authorities),
        "target_count": len(coverage["target_registry"]),
        "changed_fields": changed,
    }
    if changed and args.write:
        coverage_path.write_text(output, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if not changed or args.write else 1


if __name__ == "__main__":
    raise SystemExit(main())
