#!/usr/bin/env python3
"""Capture a Git tree's product/test source inventory without checkout."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import subprocess


PREFIXES = (
    "docs/",
    "e2e/",
    "src/",
    "scripts/",
    "evals/",
)


def git(*args: str, text: bool = True) -> str | bytes:
    completed = subprocess.run(
        ["git", *args], check=True, capture_output=True, text=text
    )
    return completed.stdout


def classify(path: str) -> list[str]:
    facets: list[str] = []
    lower = path.lower()
    if path.startswith("docs/"):
        facets.append("documentation")
    if path.startswith("e2e/"):
        facets.append("e2e")
    if any(token in lower for token in ("snapshot", "oracle", "golden")):
        facets.append("visual-oracle")
    if any(token in lower for token in ("fixture", "fake-sidecar")):
        facets.append("fixture")
    if path.startswith("src/renderer/"):
        facets.append("ui-implementation-evidence")
    if path.startswith("src/main/"):
        facets.append("desktop-runtime-evidence")
    if path.startswith("src/shared/"):
        facets.append("protocol-evidence")
    if any(token in lower for token in ("repository", "storage", "state", "settings")):
        facets.append("persistence-evidence")
    if lower.endswith((".test.ts", ".test.tsx", ".spec.ts")):
        facets.append("test")
    return sorted(set(facets))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--source-id", default="qwork-develop")
    parser.add_argument("--authority-kind", default="evidence")
    parser.add_argument("--freshness-blocker")
    args = parser.parse_args()

    revision = str(git("rev-parse", args.revision)).strip()
    lines = str(git("ls-tree", "-r", "-l", revision)).splitlines()
    entries = []
    for line in lines:
        meta, path = line.split("\t", 1)
        if not path.startswith(PREFIXES):
            continue
        mode, kind, blob, size = meta.split()
        facets = classify(path)
        if not facets:
            continue
        entries.append(
            {
                "path": path,
                "mode": mode,
                "kind": kind,
                "blob_sha1": blob,
                "size": int(size) if size != "-" else None,
                "facets": facets,
            }
        )
    normalized = json.dumps(entries, ensure_ascii=False, separators=(",", ":")).encode()
    digest = hashlib.sha256(normalized).hexdigest()
    snapshot_id = f"git-{revision[:12]}-sha256-{digest[:16]}"
    output = pathlib.Path(args.output_root).resolve() / snapshot_id
    output.mkdir(parents=True, exist_ok=False)
    (output / "inventory.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    counts: dict[str, int] = {}
    for entry in entries:
        for facet in entry["facets"]:
            counts[facet] = counts.get(facet, 0) + 1
    manifest = {
        "schema_version": 1,
        "source_id": args.source_id,
        "source_kind": "git-tree",
        "authority_kind": args.authority_kind,
        "revision": revision,
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "inventory_sha256": digest,
        "entry_count": len(entries),
        "facet_counts": counts,
        "freshness_status": "blocked" if args.freshness_blocker else "current",
        "freshness_blocker": args.freshness_blocker,
        "inventory_path": "inventory.json",
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "ok", "snapshot": str(output), **manifest}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
