#!/usr/bin/env python3
"""Promotion must copy only reusable, registered E2E evidence into Dataset Git storage."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from promote_reference_evidence import promote_reference_evidence


def expect_failure(action, message: str) -> None:
    try:
        action()
    except ValueError as error:
        assert message in str(error), str(error)
    else:
        raise AssertionError(f"expected failure containing {message!r}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="qwork-e2e-promotion-") as value:
        root = Path(value)
        source = root / "QWORK-E2E-TEMPORARY-DATA-DO-NOT-COMMIT" / "RUN-1"
        source.mkdir(parents=True)
        (source / "QWORK-E2E-REPORT.json").write_text("{}\n", encoding="utf-8")
        (source / "QWORK-E2E-REPORT.html").write_text("<html></html>\n", encoding="utf-8")
        (source / "evidence-manifest.json").write_text(json.dumps({
            "schema_version": 1,
            "run_id": "RUN-1",
            "files": [
                "QWORK-E2E-REPORT.json",
                "QWORK-E2E-REPORT.html",
                "screenshots/final-state.png",
            ],
        }), encoding="utf-8")
        screenshot = source / "screenshots/final-state.png"
        screenshot.parent.mkdir()
        screenshot.write_bytes(b"png")
        build = source / "build"
        build.mkdir()
        (build / "index.js.map").write_text("source map", encoding="utf-8")

        dataset = root / "dataset"
        target = promote_reference_evidence(
            source=source,
            dataset_root=dataset,
            reference_id="CASE-1-RUN-1",
        )
        promoted = sorted(path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file())
        assert promoted == [
            "PROMOTION-MANIFEST.json",
            "QWORK-E2E-REPORT.html",
            "QWORK-E2E-REPORT.json",
            "evidence-manifest.json",
            "screenshots/final-state.png",
        ]
        assert not (target / "build").exists()

        (source / "evidence-manifest.json").write_text(json.dumps({
            "schema_version": 1,
            "run_id": "RUN-1",
            "files": ["build/index.js.map"],
        }), encoding="utf-8")
        expect_failure(
            lambda: promote_reference_evidence(
                source=source,
                dataset_root=dataset,
                reference_id="CASE-1-RUN-2",
            ),
            "not promotable",
        )

    print("reference evidence promotion test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
