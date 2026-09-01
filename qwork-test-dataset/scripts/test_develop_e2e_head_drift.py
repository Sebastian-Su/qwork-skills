#!/usr/bin/env python3
"""Regression test for develop-only E2E coordinates in the private baseline."""

from __future__ import annotations

from build_product_baseline import resolve_develop_e2e_execution


def contract(label: str, body: str) -> dict:
    return {
        "label": label,
        "test_contract": {"body_sha256": body},
    }


def main() -> int:
    develop_atom = contract("new develop journey", "develop-body")
    selected, revision, spec_hash, blockers = resolve_develop_e2e_execution(
        title="new develop journey",
        develop_atom=develop_atom,
        develop_revision="develop-sha",
        develop_content_sha256="develop-spec-sha",
        head_entry=None,
        head_revision="feature-sha",
    )
    assert selected is develop_atom
    assert revision == "develop-sha"
    assert spec_hash == "develop-spec-sha"
    assert len(blockers) == 1 and "not present" in blockers[0]

    head_atom = contract("new develop journey", "head-body")
    selected, revision, spec_hash, blockers = resolve_develop_e2e_execution(
        title="new develop journey",
        develop_atom=develop_atom,
        develop_revision="develop-sha",
        develop_content_sha256="develop-spec-sha",
        head_entry={"atoms": [head_atom], "content_sha256": "head-spec-sha"},
        head_revision="feature-sha",
    )
    assert selected is head_atom
    assert revision == "feature-sha"
    assert spec_hash == "head-spec-sha"
    assert blockers == []

    renamed_head_atom = contract("renamed current journey", "develop-body")
    selected, revision, spec_hash, blockers = resolve_develop_e2e_execution(
        title="new develop journey",
        develop_atom=develop_atom,
        develop_revision="develop-sha",
        develop_content_sha256="develop-spec-sha",
        head_entry={"atoms": [renamed_head_atom], "content_sha256": "head-spec-sha"},
        head_revision="feature-sha",
    )
    assert selected is renamed_head_atom
    assert revision == "feature-sha"
    assert spec_hash == "head-spec-sha"
    assert blockers == []
    print("develop E2E HEAD drift test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
