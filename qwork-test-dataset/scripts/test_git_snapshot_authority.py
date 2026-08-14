#!/usr/bin/env python3
"""Regression test: Git source snapshots are revision and hash bound."""

from __future__ import annotations

import hashlib
import json
import pathlib
import tempfile

from build_product_baseline import load_git_snapshot


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="qwork-git-snapshot-") as root_value:
        root = pathlib.Path(root_value)
        inventory = [{"path": "docs/product.md", "blob_sha1": "abc", "size": 1}]
        normalized = json.dumps(
            inventory, ensure_ascii=False, separators=(",", ":")
        ).encode()
        manifest = {
            "source_id": "qwork-current-head",
            "revision": "head-sha",
            "inventory_sha256": hashlib.sha256(normalized).hexdigest(),
            "entry_count": 1,
        }
        (root / "inventory.json").write_text(
            json.dumps(inventory, ensure_ascii=False), encoding="utf-8"
        )
        (root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )

        loaded_manifest, loaded_inventory = load_git_snapshot(
            root,
            expected_revision="head-sha",
            expected_source_id="qwork-current-head",
        )
        assert loaded_manifest == manifest
        assert loaded_inventory == inventory

        manifest["inventory_sha256"] = "0" * 64
        (root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )
        try:
            load_git_snapshot(
                root,
                expected_revision="head-sha",
                expected_source_id="qwork-current-head",
            )
        except ValueError as exc:
            assert "inventory hash mismatch" in str(exc)
        else:
            raise AssertionError("tampered snapshot unexpectedly passed")

    print("git snapshot authority test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
