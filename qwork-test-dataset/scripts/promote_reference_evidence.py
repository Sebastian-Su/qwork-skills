#!/usr/bin/env python3
"""Promote a reviewed minimal E2E evidence bundle into tracked Dataset storage."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from external_artifact_storage import validate_external_output_root


REFERENCE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
ROOT_FILES = {
    "QWORK-E2E-REPORT.json",
    "QWORK-E2E-REPORT.html",
    "evidence-manifest.json",
    "build-manifest.json",
    "playwright-report.json",
    "playwright.stderr.log",
    "electron-runtime.log",
}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _promotable(relative: Path) -> bool:
    if relative.is_absolute() or ".." in relative.parts or "build" in relative.parts:
        return False
    if len(relative.parts) == 1:
        return relative.name in ROOT_FILES
    if relative.parts[0] == "screenshots":
        return relative.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    if relative.parts[0] == "playwright-results":
        return relative.name == "trace.zip" or relative.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    return False


def promote_reference_evidence(*, source: Path, dataset_root: Path, reference_id: str) -> Path:
    if not REFERENCE_ID.fullmatch(reference_id):
        raise ValueError("reference id may contain only letters, numbers, dot, underscore and hyphen")
    source = validate_external_output_root(source, protected_roots=[dataset_root])
    manifest_path = source / "evidence-manifest.json"
    manifest = _load(manifest_path)
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("evidence manifest must list at least one promotable file")
    selected = [Path(str(value)) for value in files]
    if Path("evidence-manifest.json") not in selected:
        selected.append(Path("evidence-manifest.json"))
    for relative in selected:
        if not _promotable(relative):
            raise ValueError(f"evidence is not promotable: {relative.as_posix()}")
        candidate = (source / relative).resolve()
        try:
            candidate.relative_to(source)
        except ValueError as exc:
            raise ValueError(f"evidence escapes source run: {relative.as_posix()}") from exc
        if not candidate.is_file():
            raise ValueError(f"promotable evidence is missing: {relative.as_posix()}")

    target = dataset_root.resolve() / "data/reference-runs" / reference_id
    if target.exists():
        raise ValueError(f"reference target already exists: {target}")
    target.mkdir(parents=True)
    entries = []
    for relative in sorted(set(selected), key=lambda value: value.as_posix()):
        source_file = source / relative
        target_file = target / relative
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)
        entries.append({
            "path": relative.as_posix(),
            "sha256": f"sha256:{hashlib.sha256(target_file.read_bytes()).hexdigest()}",
        })
    (target / "PROMOTION-MANIFEST.json").write_text(
        json.dumps({
            "schema_version": 1,
            "reference_id": reference_id,
            "source_run_id": manifest.get("run_id"),
            "files": entries,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--reference-id", required=True)
    args = parser.parse_args()
    target = promote_reference_evidence(
        source=args.source,
        dataset_root=args.dataset_root,
        reference_id=args.reference_id,
    )
    print(json.dumps({"status": "ok", "target": str(target)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
