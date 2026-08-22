#!/usr/bin/env python3
"""Freeze a WorkBuddy installation as hashes and metadata without copying code."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import plistlib
from typing import Any


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(root: pathlib.Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def tree_sha256(root: pathlib.Path) -> str:
    digest = hashlib.sha256()
    for record in inventory(root):
        digest.update(record["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(record["bytes"]).encode("ascii"))
        digest.update(b"\0")
        digest.update(record["sha256"].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def build_manifest(
    *,
    app: pathlib.Path,
    extracted: pathlib.Path,
    extraction_status: str,
    extraction_note: str,
    captured_at: str | None = None,
) -> dict[str, Any]:
    app = app.resolve()
    extracted = extracted.resolve()
    plist_path = app / "Contents" / "Info.plist"
    asar_path = app / "Contents" / "Resources" / "app.asar"
    if not plist_path.is_file() or not asar_path.is_file():
        raise FileNotFoundError(f"not a WorkBuddy app bundle: {app}")
    if not extracted.is_dir():
        raise FileNotFoundError(f"extracted directory does not exist: {extracted}")

    with plist_path.open("rb") as stream:
        plist = plistlib.load(stream)
    version = str(plist.get("CFBundleShortVersionString", ""))
    if not version:
        raise ValueError("CFBundleShortVersionString is missing")

    all_files = inventory(extracted)
    integrity = (
        plist.get("ElectronAsarIntegrity", {}).get("Resources/app.asar")
        if isinstance(plist.get("ElectronAsarIntegrity"), dict)
        else None
    )
    timestamp = captured_at or dt.datetime.now(dt.timezone.utc).isoformat()
    return {
        "schema_version": 1,
        "source_kind": "installed-electron-bundle",
        "authority_kind": "normative",
        "authority_domains": ["product", "ui", "architecture", "runtime"],
        "product": {"name": "WorkBuddy", "version": version},
        "bundle": {
            "identifier": str(plist.get("CFBundleIdentifier", "")),
            "build_version": str(plist.get("CFBundleVersion", "")),
        },
        "captured_at": timestamp,
        "app_asar": {
            "source_locator": str(asar_path),
            "bytes": asar_path.stat().st_size,
            "sha256": sha256_file(asar_path),
            "integrity": integrity,
        },
        "extraction": {
            "source_locator": str(extracted),
            "status": extraction_status,
            "note": extraction_note,
            "file_count": len(all_files),
            "bytes": sum(record["bytes"] for record in all_files),
            "tree_sha256": tree_sha256(extracted),
            "files": all_files,
        },
        "redaction_status": "hashes-and-paths-only; source-bytes-not-copied",
        "clean_room_rule": (
            "This manifest may define observable product contracts. It must not be used "
            "to copy proprietary implementation or asset bytes into QWork."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=pathlib.Path, required=True)
    parser.add_argument("--extracted", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--extraction-status", choices=("complete", "partial"), required=True)
    parser.add_argument("--extraction-note", required=True)
    args = parser.parse_args()

    manifest = build_manifest(
        app=args.app,
        extracted=args.extracted,
        extraction_status=args.extraction_status,
        extraction_note=args.extraction_note,
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite immutable manifest: {output}")
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(output),
                "version": manifest["product"]["version"],
                "app_asar_sha256": manifest["app_asar"]["sha256"],
                "extraction_status": manifest["extraction"]["status"],
                "extracted_file_count": manifest["extraction"]["file_count"],
                "extracted_tree_sha256": manifest["extraction"]["tree_sha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
