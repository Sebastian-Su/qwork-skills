#!/usr/bin/env python3
"""Freeze Lark document images into WorkBuddy baselines or QWork evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET


SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def digest(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def image_dimensions(path: pathlib.Path) -> tuple[int, int]:
    """Read the downloaded image's physical pixels, never its Lark display box."""

    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"unsupported or invalid image payload: {path}")
    width, height = struct.unpack(">II", header[16:24])
    if width <= 0 or height <= 0:
        raise ValueError(f"image has non-positive physical dimensions: {path}")
    return width, height


def classify(name: str) -> str:
    lower = name.lower()
    if lower.startswith("qwork-"):
        return "qwork-implementation-evidence"
    return "workbuddy-normative-visual"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--document-xml", required=True)
    parser.add_argument("--baseline-root", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--as", dest="identity", default="user")
    args = parser.parse_args()

    source = pathlib.Path(args.document_xml).resolve()
    # `lark-cli docs +fetch --format xml` emits a sequence of top-level blocks.
    # Wrap the immutable snapshot in-memory rather than rewriting source bytes.
    xml = source.read_text(encoding="utf-8")
    root = ET.fromstring(f"<document>{xml}</document>")
    images = list(root.iter("img"))
    records: list[dict[str, object]] = []
    seen_names: dict[str, int] = {}
    for index, element in enumerate(images, start=1):
        token = (element.attrib.get("src") or "").strip()
        original_name = (element.attrib.get("name") or f"image-{index}.png").strip()
        if not token:
            continue
        safe = SAFE_NAME.sub("-", original_name).strip("-.") or f"image-{index}.png"
        seen_names[safe] = seen_names.get(safe, 0) + 1
        if seen_names[safe] > 1:
            stem = pathlib.Path(safe).stem
            suffix = pathlib.Path(safe).suffix
            safe = f"{stem}-{seen_names[safe]}{suffix}"
        authority = classify(original_name)
        output_root = pathlib.Path(
            args.evidence_root if authority.startswith("qwork-") else args.baseline_root
        ).resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        output = output_root / safe
        command = [
                "lark-cli",
                "docs",
                "+media-download",
                "--as",
                args.identity,
                "--token",
                token,
                "--output",
                f"./{output.name}",
            ]
        if args.profile:
            command.extend(["--profile", args.profile])
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            cwd=output_root,
        )
        if completed.returncode != 0:
            print(completed.stderr or completed.stdout, file=sys.stderr)
            return completed.returncode
        pixel_width, pixel_height = image_dimensions(output)
        display_width = int(element.attrib["width"]) if element.attrib.get("width", "").isdigit() else None
        display_height = int(element.attrib["height"]) if element.attrib.get("height", "").isdigit() else None
        records.append(
            {
                "block_id": element.attrib.get("id"),
                "token": token,
                "original_name": original_name,
                "stored_name": safe,
                "authority_kind": authority,
                "width": pixel_width,
                "height": pixel_height,
                "source_display_width": display_width,
                "source_display_height": display_height,
                "mime": element.attrib.get("mime"),
                "caption": element.attrib.get("caption"),
                "alt": element.attrib.get("alt"),
                "sha256": digest(output),
                "bytes": output.stat().st_size,
                "path": output.name,
            }
        )

    grouped: dict[str, list[dict[str, object]]] = {}
    for record in records:
        grouped.setdefault(str(record["authority_kind"]), []).append(record)
    captured_at = dt.datetime.now(dt.timezone.utc).isoformat()
    for authority, items in grouped.items():
        target = pathlib.Path(
            args.evidence_root if authority.startswith("qwork-") else args.baseline_root
        ).resolve()
        manifest = {
            "schema_version": 1,
            "source_document": source.name,
            "authority_kind": authority,
            "captured_at": captured_at,
            "image_count": len(items),
            "images": items,
        }
        (target / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps({"status": "ok", "image_count": len(records), "groups": {key: len(value) for key, value in grouped.items()}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
