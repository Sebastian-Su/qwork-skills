#!/usr/bin/env python3
"""Refresh structured Oracle target hashes after exact test-title validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess

import yaml


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def source_bytes(repo: pathlib.Path, root: pathlib.Path, head: str, locator: str) -> bytes:
    prefix = "skill://qwork-test-dataset/"
    if locator.startswith(prefix):
        return (root / locator.removeprefix(prefix)).read_bytes()
    return subprocess.run(
        ["git", "show", f"{head}:{locator}"], cwd=repo, check=True, capture_output=True
    ).stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=pathlib.Path, required=True)
    parser.add_argument("--skill-root", type=pathlib.Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    root = args.skill_root.resolve()
    mapping_path = root / "references/structured-oracle-coverage-map.yaml"
    text = mapping_path.read_text(encoding="utf-8")
    mapping = yaml.safe_load(text)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    extractor = root / "scripts/extract_playwright_contracts.mjs"

    replacements: dict[str, str] = {}
    target_count = 0
    for source in mapping["sources"].values():
        source_locator = str(source["source_locator"])
        if not source_locator.startswith("git:"):
            raise SystemExit(
                f"unsupported structured Oracle source locator: {source_locator!r}"
            )
        _, source_revision, source_path = source_locator.split(":", 2)
        oracle_sha256 = sha256_bytes(source_bytes(repo, root, head, source_path))
        replacements[source_revision] = head
        for item in source["mappings"]:
            target_count += 1
            target = item["target"]
            spec = str(target["spec"])
            content = source_bytes(repo, root, head, spec)
            parsed = subprocess.run(
                ["node", str(extractor), spec],
                cwd=repo,
                input=content.decode("utf-8"),
                text=True,
                check=True,
                capture_output=True,
            )
            titles = [str(record["title"]) for record in json.loads(parsed.stdout)["tests"]]
            if titles.count(str(target["title"])) != 1:
                raise SystemExit(
                    f"{target['case_id']}: exact target title is missing or ambiguous: {target['title']!r}"
                )
            replacements[str(target["execution_revision"])] = head
            replacements[str(target["spec_sha256"])] = sha256_bytes(content)
            replacements[str(target["oracle_sha256"])] = oracle_sha256
            if target.get("helper"):
                helper = str(target["helper"])
                replacements[str(target["helper_sha256"])] = sha256_bytes(
                    source_bytes(repo, root, head, helper)
                )

    changed_values = [old for old, new in replacements.items() if old != new and old in text]
    output = text
    for old, new in replacements.items():
        output = output.replace(old, new)
    summary = {
        "status": "current" if not changed_values else ("updated" if args.write else "drift"),
        "head": head,
        "target_count": target_count,
        "changed_value_count": len(changed_values),
    }
    if changed_values and args.write:
        mapping_path.write_text(output, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if not changed_values or args.write else 1


if __name__ == "__main__":
    raise SystemExit(main())
