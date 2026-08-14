#!/usr/bin/env python3
"""Fail-closed comparison of one QWork frame against one frozen WorkBuddy frame."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(actual: Path, baseline: Path, max_diff_ratio: float, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    result: dict = {
        "actual": {"path": str(actual), "sha256": f"sha256:{sha256(actual)}"},
        "baseline": {"path": str(baseline), "sha256": f"sha256:{sha256(baseline)}"},
        "max_diff_ratio": max_diff_ratio,
        "status": "pending",
        "failures": [],
    }
    with Image.open(actual).convert("RGBA") as actual_image, Image.open(baseline).convert("RGBA") as baseline_image:
        result["actual"]["dimensions"] = list(actual_image.size)
        result["baseline"]["dimensions"] = list(baseline_image.size)
        if actual_image.size != baseline_image.size:
            result["failures"].append("pixel dimensions differ")
            result["diff_ratio"] = None
        else:
            diff = ImageChops.difference(actual_image, baseline_image)
            different = sum(
                1 for pixel in diff.getdata() if pixel != (0, 0, 0, 0)
            )
            ratio = different / (actual_image.width * actual_image.height)
            diff_path = output / "diff.png"
            diff.save(diff_path)
            result["diff_ratio"] = ratio
            result["diff"] = {
                "path": str(diff_path),
                "sha256": f"sha256:{sha256(diff_path)}",
            }
            if ratio > max_diff_ratio:
                result["failures"].append(
                    f"pixel diff ratio {ratio:.8f} exceeds {max_diff_ratio:.8f}"
                )
    result["status"] = "pass" if not result["failures"] else "fail"
    (output / "report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-diff-ratio", type=float, default=0.01)
    args = parser.parse_args()
    if not 0 <= args.max_diff_ratio <= 1:
        raise ValueError("--max-diff-ratio must be between 0 and 1")
    if not args.actual.is_file():
        raise FileNotFoundError(f"actual frame is missing: {args.actual}")
    if not args.baseline.is_file():
        raise FileNotFoundError(f"WorkBuddy baseline is missing: {args.baseline}")
    result = compare(
        args.actual.resolve(),
        args.baseline.resolve(),
        args.max_diff_ratio,
        args.output.resolve(),
    )
    print(json.dumps({"status": result["status"], "report": str(args.output.resolve() / "report.json")}, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
