#!/usr/bin/env python3
"""Capture a privacy-minimized WorkBuddy storage inventory and SQLite schema."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import sqlite3
import stat


SENSITIVE_NAMES = ("token", "cookie", "credential", "secret", "password", "keychain")
TEXT_EXTENSIONS = {".json", ".jsonl", ".md", ".txt", ".yaml", ".yml", ".log"}
SQLITE_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}
USER_GENERATED_ROOTS = {
    "artifact-index",
    "audit-log",
    "local_storage",
    "logs",
    "memory",
    "plans",
    "project-resources",
    "projects",
    "sessions",
    "shell-snapshots",
    "tasks",
    "traces",
    "workspace",
}


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def privacy_path(relative: str) -> tuple[str, bool]:
    """Keep product-owned paths; pseudonymize user-generated path segments."""
    parts = pathlib.PurePosixPath(relative).parts
    if not parts or parts[0] not in USER_GENERATED_ROOTS:
        return relative, False
    protected = [parts[0]]
    for segment in parts[1:]:
        suffixes = "".join(pathlib.PurePosixPath(segment).suffixes)
        digest = hashlib.sha256(segment.encode()).hexdigest()[:12]
        protected.append(f"segment-{digest}{suffixes}")
    return "/".join(protected), True


def sqlite_schema(path: pathlib.Path) -> dict[str, object] | None:
    try:
        uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True)
        rows = connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE type IN ('table','index','view','trigger') ORDER BY type,name"
        ).fetchall()
        connection.close()
        normalized = []
        for kind, name, table, sql in rows:
            normalized.append(
                {
                    "type": kind,
                    "name": name,
                    "table": table,
                    "sql_sha256": hashlib.sha256((sql or "").encode()).hexdigest(),
                    "columns": sqlite_columns(path, name) if kind == "table" else [],
                }
            )
        return {"objects": normalized, "object_count": len(normalized)}
    except (sqlite3.Error, OSError):
        return None


def sqlite_columns(path: pathlib.Path, table: str) -> list[dict[str, object]]:
    try:
        uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True)
        escaped = table.replace('"', '""')
        rows = connection.execute(f'PRAGMA table_info("{escaped}")').fetchall()
        connection.close()
        return [
            {"name": row[1], "type": row[2], "not_null": bool(row[3]), "pk": bool(row[5])}
            for row in rows
        ]
    except sqlite3.Error:
        return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()
    source = pathlib.Path(args.source_root).expanduser().resolve()
    if not source.is_dir():
        raise SystemExit(f"missing WorkBuddy storage root: {source}")
    entries = []
    for root, dirs, files in os.walk(source, followlinks=False):
        root_path = pathlib.Path(root)
        dirs[:] = sorted(d for d in dirs if not (root_path / d).is_symlink())
        for name in sorted(files):
            path = root_path / name
            raw_relative = path.relative_to(source).as_posix()
            relative, path_pseudonymized = privacy_path(raw_relative)
            try:
                info = path.lstat()
            except OSError:
                continue
            if not stat.S_ISREG(info.st_mode):
                entries.append({"path": relative, "kind": "non-regular", "size": info.st_size})
                continue
            lower = raw_relative.lower()
            sensitive = any(token in lower for token in SENSITIVE_NAMES)
            entry: dict[str, object] = {
                "path": relative,
                "path_pseudonymized": path_pseudonymized,
                "kind": "file",
                "size": info.st_size,
                "extension": path.suffix.lower(),
                "sensitive_name": sensitive,
                "content_copied": False,
            }
            if not sensitive:
                entry["sha256"] = sha256(path)
            else:
                entry["sha256"] = None
            if not sensitive and path.suffix.lower() in SQLITE_EXTENSIONS:
                entry["sqlite_schema"] = sqlite_schema(path)
            if path.suffix.lower() in TEXT_EXTENSIONS:
                entry["content_policy"] = "metadata-and-hash-only"
            entries.append(entry)
    normalized = json.dumps(entries, ensure_ascii=False, separators=(",", ":")).encode()
    digest = hashlib.sha256(normalized).hexdigest()
    snapshot_id = f"inventory-sha256-{digest[:16]}"
    output = pathlib.Path(args.output_root).resolve() / snapshot_id
    output.mkdir(parents=True, exist_ok=False)
    (output / "inventory.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": 1,
        "source_kind": "workbuddy-local-storage",
        "authority_kind": "normative-by-user-direction-and-product-evidence",
        "stable_locator": "~/.workbuddy/",
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "inventory_sha256": digest,
        "entry_count": len(entries),
        "sqlite_file_count": sum(1 for entry in entries if entry.get("sqlite_schema")),
        "sensitive_name_count": sum(1 for entry in entries if entry.get("sensitive_name")),
        "user_generated_roots": sorted(USER_GENERATED_ROOTS),
        "content_policy": "metadata/hash/schema only; user-generated path segments pseudonymized; no user content or credentials copied",
        "inventory_path": "inventory.json",
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "ok", "snapshot": str(output), **manifest}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
