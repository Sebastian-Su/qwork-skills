#!/usr/bin/env python3
"""Focused regression tests for the WorkBuddy bundle manifest collector."""

from __future__ import annotations

import importlib.util
import plistlib
import tempfile
from pathlib import Path


def load_collector():
    path = Path(__file__).with_name("build_workbuddy_bundle_manifest.py")
    spec = importlib.util.spec_from_file_location("workbuddy_bundle_manifest", path)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load build_workbuddy_bundle_manifest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    collector = load_collector()
    with tempfile.TemporaryDirectory(prefix="workbuddy-bundle-manifest-") as root:
        root_path = Path(root)
        app = root_path / "WorkBuddy.app"
        resources = app / "Contents" / "Resources"
        resources.mkdir(parents=True)
        (app / "Contents" / "Info.plist").write_bytes(
            plistlib.dumps(
                {
                    "CFBundleIdentifier": "com.workbuddy.workbuddy",
                    "CFBundleShortVersionString": "5.3.14",
                    "CFBundleVersion": "5.3.14",
                    "ElectronAsarIntegrity": {
                        "Resources/app.asar": {
                            "algorithm": "SHA256",
                            "hash": "plist-integrity-hash",
                        }
                    },
                }
            )
        )
        (resources / "app.asar").write_bytes(b"immutable-asar")

        extracted = root_path / "app-asar"
        renderer = extracted / "renderer"
        renderer.mkdir(parents=True)
        (renderer / "index.html").write_text("<main>oracle</main>", encoding="utf-8")
        (renderer / "assets").mkdir()
        (renderer / "assets" / "main.js").write_text("void 0;", encoding="utf-8")

        manifest = collector.build_manifest(
            app=app,
            extracted=extracted,
            extraction_status="partial",
            extraction_note="unpacked platform files are absent",
            captured_at="2026-08-22T00:00:00+00:00",
        )

        if manifest["product"] != {"name": "WorkBuddy", "version": "5.3.14"}:
            raise AssertionError(f"wrong product identity: {manifest['product']}")
        if manifest["app_asar"]["sha256"] != collector.sha256_file(resources / "app.asar"):
            raise AssertionError("raw app.asar hash was not frozen")
        if manifest["app_asar"]["integrity"] != {
            "algorithm": "SHA256",
            "hash": "plist-integrity-hash",
        }:
            raise AssertionError("Electron asar integrity metadata was not preserved")
        extraction = manifest["extraction"]
        if extraction["status"] != "partial" or extraction["file_count"] != 2:
            raise AssertionError(f"wrong extraction summary: {extraction}")
        if extraction["tree_sha256"] != collector.tree_sha256(extracted):
            raise AssertionError("extracted renderer tree hash is not reproducible")
        if any("oracle" in record for record in extraction["files"]):
            raise AssertionError("manifest leaked source file contents")
        if [record["path"] for record in extraction["files"]] != [
            "renderer/assets/main.js",
            "renderer/index.html",
        ]:
            raise AssertionError("file inventory is not stable and sorted")

    print("workbuddy bundle manifest collector: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
