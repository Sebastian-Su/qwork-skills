#!/usr/bin/env python3
"""Fail closed unless every frozen develop docs/e2e file has one exact disposition."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
ALLOWED = {
    "product-normative",
    "product-normative-structured-oracle",
    "executable-evidence",
    "execution-fixture",
    "release-governance",
    "supporting-evidence",
    "implementation-context",
    "implementation-screenshot-evidence",
    "historical-red-evidence",
    "deduplicated-identical-to-develop",
}


def resolve_skill(locator: str, repo: Path) -> Path:
    if not locator.startswith("skill://"):
        raw = Path(locator)
        return (raw if raw.is_absolute() else repo / raw).resolve()
    remainder = locator.removeprefix("skill://")
    skill, separator, relative = remainder.partition("/")
    if not separator or not skill or not relative:
        raise ValueError(f"invalid skill locator: {locator}")
    return (repo / ".agents" / "skills" / skill / relative).resolve()


def inventory_digest(value: list[Any]) -> str:
    canonical = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--manifest",
        default="skill://qwork-test-dataset/data/datasets/source-dispositions.json",
    )
    args = parser.parse_args()
    repo = args.repo.resolve()
    errors: list[str] = []
    try:
        manifest_path = resolve_skill(args.manifest, repo)
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        closed = as_dict(data.get("closed_world"))
        inventory_path = resolve_skill(str(closed.get("inventory_locator") or ""), repo)
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"source disposition manifest error: {exc}", file=sys.stderr)
        return 1

    if not isinstance(inventory, list):
        errors.append("develop inventory must be an array")
        inventory = []
    expected_hash = str(closed.get("inventory_sha256") or "")
    if not SHA256.fullmatch(expected_hash):
        errors.append("closed_world inventory_sha256 is invalid")
    elif expected_hash != f"sha256:{inventory_digest(inventory)}":
        errors.append("closed_world inventory hash does not match canonical frozen inventory")

    revision = str(data.get("develop_revision") or "")
    expected = {
        str(item.get("path"))
        for item in inventory
        if isinstance(item, dict)
        and str(item.get("path", "")).startswith(("docs/", "e2e/"))
    }
    entries = [
        item
        for item in data.get("dispositions", [])
        if isinstance(item, dict)
        and str(item.get("locator", "")).startswith(f"git:{revision}:")
    ]
    by_path: dict[str, list[dict[str, Any]]] = {}
    for item in entries:
        by_path.setdefault(str(item.get("path") or ""), []).append(item)
        if str(item.get("disposition")) not in ALLOWED:
            errors.append(f"unsupported disposition for {item.get('path')}: {item.get('disposition')}")
        if not str(item.get("reason") or "").strip():
            errors.append(f"disposition lacks reason: {item.get('path')}")
        if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("content_sha256") or "")):
            errors.append(f"disposition lacks content SHA-256: {item.get('path')}")

    duplicate_paths = sorted(path for path, values in by_path.items() if len(values) != 1)
    if duplicate_paths:
        errors.append(f"develop paths require exactly one disposition: {duplicate_paths[:20]}")
    actual = set(by_path)
    if expected != actual:
        errors.append(
            f"develop disposition ledger is not closed: missing={sorted(expected - actual)[:20]} "
            f"extra={sorted(actual - expected)[:20]}"
        )
    for key, expected_value in {
        "expected_develop_docs_e2e_paths": len(expected),
        "disposed_develop_docs_e2e_paths": len(actual),
    }.items():
        if closed.get(key) != expected_value:
            errors.append(f"closed_world {key} must equal {expected_value}")
    if closed.get("status") != "closed":
        errors.append("closed_world status must be closed")

    # Bind each ledger hash back to the frozen Git revision, not merely the JSON inventory.
    for path, values in sorted(by_path.items()):
        try:
            blob = subprocess.run(
                ["git", "show", f"{revision}:{path}"],
                cwd=repo,
                check=True,
                capture_output=True,
            ).stdout
        except subprocess.CalledProcessError:
            errors.append(f"frozen develop blob cannot be read: {path}")
            continue
        actual_hash = hashlib.sha256(blob).hexdigest()
        if actual_hash != values[0].get("content_sha256"):
            errors.append(f"frozen develop blob hash mismatch: {path}")

    if errors:
        print("source disposition closed-world gate failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        f"source disposition closed-world gate complete: {len(expected)}/{len(expected)} develop docs/e2e files"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
