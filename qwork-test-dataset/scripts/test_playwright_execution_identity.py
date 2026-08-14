#!/usr/bin/env python3
"""Ensure each Playwright Case executes one unique current-revision source."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--skill-root", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    root = args.skill_root.resolve()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, text=True, capture_output=True
    ).stdout.strip()
    coordinates: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    private_coordinates = 0
    current_head_coordinates = 0
    frozen_develop_coordinates = 0
    for case_path in (root / "data/datasets/cases").glob("*.json"):
        case = json.loads(case_path.read_text(encoding="utf-8"))
        route = str(case["execution_contract"]["route_id"])
        if not route.startswith(("qwork.playwright.", "qwork.private-playwright.")):
            continue
        contract = case["execution_contract"]["observability"]["source_contract"]
        coordinates[(contract["spec"], case["title"])].append(case["id"])
        revision = str(contract.get("execution_revision") or "")
        spec = contract["spec"]
        if route.startswith("qwork.private-playwright."):
            if revision != head:
                raise AssertionError(f"{case['id']} private route does not bind current HEAD")
            prefix = "skill://qwork-test-dataset/"
            if not spec.startswith(prefix):
                raise AssertionError(f"{case['id']} private route is not Skill-bound")
            private_path = root / spec.removeprefix(prefix)
            if not private_path.is_file():
                raise AssertionError(f"{case['id']} private spec is missing")
            frozen = private_path.read_bytes()
            actual = "sha256:" + hashlib.sha256(frozen).hexdigest()
            if contract.get("spec_sha256") != actual:
                raise AssertionError(f"{case['id']} private spec hash drifted")
            parsed = subprocess.run(
                ["node", str(root / "scripts/extract_playwright_contracts.mjs"), spec],
                input=frozen.decode("utf-8"),
                text=True,
                check=True,
                capture_output=True,
            )
            test = next(
                (
                    item
                    for item in json.loads(parsed.stdout)["tests"]
                    if item["title"] == case["title"]
                ),
                None,
            )
            if test is None or f"sha256:{test['body_sha256']}" != contract.get("body_sha256"):
                raise AssertionError(f"{case['id']} private test body hash drifted")
            private_coordinates += 1
            current_head_coordinates += 1
            continue
        frozen = subprocess.run(
            ["git", "show", f"{revision}:{spec}"], cwd=repo, check=True, capture_output=True
        ).stdout
        actual = "sha256:" + hashlib.sha256(frozen).hexdigest()
        if contract.get("spec_sha256") != actual:
            raise AssertionError(f"{case['id']} full spec hash does not bind its execution revision")
        if revision == head:
            if not (repo / spec).is_file() or (repo / spec).read_bytes() != frozen:
                raise AssertionError(f"{case['id']} current worktree spec differs from bound HEAD")
            current_head_coordinates += 1
        else:
            blockers = [
                str(value)
                for value in case["execution_contract"].get("blockers", [])
            ]
            if case["execution_contract"].get("readiness") != "partial":
                raise AssertionError(
                    f"{case['id']} non-HEAD route is not marked partial"
                )
            if not any(
                "not present in the current feature HEAD" in value
                for value in blockers
            ):
                raise AssertionError(
                    f"{case['id']} non-HEAD route has no develop drift blocker"
                )
            frozen_develop_coordinates += 1
    duplicates = {key: ids for key, ids in coordinates.items() if len(ids) != 1}
    if duplicates:
        raise AssertionError(f"duplicate Playwright execution coordinates: {duplicates}")
    if private_coordinates <= 0:
        raise AssertionError("private Dataset has no executable Playwright coordinate")
    print(
        "Playwright execution identity: "
        f"{len(coordinates)} unique coordinates, "
        f"{current_head_coordinates} current-HEAD, "
        f"{frozen_develop_coordinates} frozen-develop, "
        f"{private_coordinates} private Dataset coordinates"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
