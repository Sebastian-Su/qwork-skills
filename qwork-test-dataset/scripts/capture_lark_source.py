#!/usr/bin/env python3
"""Capture one Lark doc as a private, hash-bound source snapshot."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--expected-document-id")
    args = parser.parse_args()

    completed = subprocess.run(
        [
            "lark-cli",
            "docs",
            "+fetch",
            "--as",
            "user",
            "--doc",
            args.doc,
            "--detail",
            "with-ids",
            "--doc-format",
            "xml",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        print(completed.stderr or completed.stdout, file=sys.stderr)
        return completed.returncode
    payload = json.loads(completed.stdout)
    document = payload["data"]["document"]
    document_id = str(document["document_id"])
    if args.expected_document_id and document_id != args.expected_document_id:
        raise SystemExit(
            f"document id mismatch: {document_id} != {args.expected_document_id}"
        )
    revision = int(document["revision_id"])
    content = str(document["content"])
    content_bytes = content.encode("utf-8")
    digest = hashlib.sha256(content_bytes).hexdigest()
    snapshot_id = f"revision-{revision}-sha256-{digest[:16]}"
    output = pathlib.Path(args.output_root).resolve() / snapshot_id
    output.mkdir(parents=True, exist_ok=False)
    (output / "document.xml").write_bytes(content_bytes)
    manifest = {
        "schema_version": 1,
        "source_kind": "lark-doc",
        "authority_kind": "normative",
        "authority_domains": ["product", "ui", "architecture", "storage"],
        "document_id": document_id,
        "revision_id": revision,
        "source_locator": args.doc,
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "content_sha256": digest,
        "content_bytes": len(content_bytes),
        "content_path": "document.xml",
        "detail": "with-ids",
        "redaction_status": "source-is-private; credentials-not-present",
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "ok", "snapshot": str(output), **manifest}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
