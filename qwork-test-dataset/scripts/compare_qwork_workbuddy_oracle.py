#!/usr/bin/env python3
"""Compare QWork capture evidence to frozen WorkBuddy screenshots and semantic boxes."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops


SKILL_ROOT = Path(__file__).resolve().parent.parent


def evidence_ref(path: Path) -> str:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(SKILL_ROOT)
    except ValueError:
        return str(resolved)
    return f"skill://qwork-test-dataset/{relative.as_posix()}"


def control_key(item: dict[str, Any]) -> str:
    parts = [str(item.get(key) or "").strip() for key in ("role", "ariaLabel", "title", "text")]
    return "\0".join(parts)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixel_diff_stats(
    candidate: Image.Image,
    reference: Image.Image,
    *,
    channel_threshold: int,
) -> dict[str, float]:
    diff = ImageChops.difference(candidate, reference)
    histogram = diff.histogram()
    total_pixels = candidate.width * candidate.height
    total_channels = total_pixels * len(diff.getbands())
    absolute_error = sum(
        (index % 256) * count for index, count in enumerate(histogram)
    )
    channel_maximum = diff.split()[0]
    for channel in diff.split()[1:]:
        channel_maximum = ImageChops.lighter(channel_maximum, channel)
    maximum_histogram = channel_maximum.histogram()
    return {
        "exact_diff_ratio": sum(maximum_histogram[1:]) / total_pixels,
        "significant_diff_ratio": (
            sum(maximum_histogram[channel_threshold + 1 :]) / total_pixels
        ),
        "mean_absolute_channel_error": absolute_error / total_channels,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--workbuddy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-diff-ratio", type=float, default=0.01)
    parser.add_argument("--pixel-channel-threshold", type=int, default=8)
    parser.add_argument("--geometry-tolerance", type=float, default=2.0)
    parser.add_argument(
        "--fail-on-diff",
        action="store_true",
        help="exit non-zero when any state fails the pixel, geometry, or navigation Oracle",
    )
    args = parser.parse_args()
    capture = args.capture.resolve()
    workbuddy = args.workbuddy.resolve()
    args.output.resolve().mkdir(parents=True, exist_ok=True)
    captured = json.loads((capture / "capture-manifest.json").read_text(encoding="utf-8"))
    wb_manifest = json.loads((workbuddy / "manifest.json").read_text(encoding="utf-8"))
    wb_by_state = {item["state"]: item for item in wb_manifest["records"]}
    results = []
    for item in captured["results"]:
        state = item["state"]
        result: dict[str, Any] = {"state": state, "status": "pending", "failures": []}
        if item["status"] != "captured":
            result.update({"status": "fail", "failure_classification": "navigation/product-gap", "failures": [item.get("error") or "state was not captured"]})
            results.append(result)
            continue
        wb = wb_by_state[state]
        q_dir = capture / state
        q_json = json.loads((q_dir / "final-state.json").read_text(encoding="utf-8"))
        wb_json = json.loads((workbuddy / f"{state}.json").read_text(encoding="utf-8"))
        q_png = q_dir / "final-state.png"
        wb_png = workbuddy / wb["screenshot"]
        with Image.open(q_png).convert("RGBA") as q_image, Image.open(wb_png).convert("RGBA") as wb_image:
            result["image_dimensions"] = {"qwork": list(q_image.size), "workbuddy": list(wb_image.size)}
            if q_image.size != wb_image.size:
                result["failures"].append("screenshot pixel dimensions differ")
                pixel = {"status": "not-comparable", "reason": "dimension mismatch"}
            else:
                diff = ImageChops.difference(q_image, wb_image)
                stats = pixel_diff_stats(
                    q_image,
                    wb_image,
                    channel_threshold=args.pixel_channel_threshold,
                )
                ratio = stats["significant_diff_ratio"]
                diff_path = args.output.resolve() / f"{state}-diff.png"
                diff.save(diff_path)
                pixel = {"status": "pass" if ratio <= args.max_diff_ratio else "fail", "diff_ratio": ratio, "exact_diff_ratio": stats["exact_diff_ratio"], "mean_absolute_channel_error": stats["mean_absolute_channel_error"], "channel_threshold": args.pixel_channel_threshold, "threshold": args.max_diff_ratio, "diff_image": evidence_ref(diff_path), "diff_image_sha256": f"sha256:{sha256_file(diff_path)}"}
                if pixel["status"] == "fail": result["failures"].append(f"pixel diff ratio {ratio:.6f} exceeds {args.max_diff_ratio:.6f}")
        result["pixel"] = pixel
        wb_keys: dict[str, list[dict[str, Any]]] = defaultdict(list)
        q_keys: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for control in wb_json["controls"]: wb_keys[control_key(control)].append(control)
        for control in q_json["controls"]: q_keys[control_key(control)].append(control)
        comparable = sorted(key for key in wb_keys if key.strip("\0") and len(wb_keys[key]) == 1 and len(q_keys.get(key, [])) == 1)
        deltas = []
        for key in comparable:
            wb_box, q_box = wb_keys[key][0]["box"], q_keys[key][0]["box"]
            delta = {field: q_box[field] - wb_box[field] for field in ("x", "y", "width", "height")}
            if any(abs(value) > args.geometry_tolerance for value in delta.values()):
                deltas.append({"key": key, "workbuddy": wb_box, "qwork": q_box, "delta": delta})
        geometry = {"status": "pass" if not deltas else "fail", "tolerance_css_px": args.geometry_tolerance, "unique_comparable_controls": len(comparable), "workbuddy_unique_unmatched": sum(len(values) == 1 and len(q_keys.get(key, [])) == 0 for key, values in wb_keys.items()), "qwork_unique_unmatched": sum(len(values) == 1 and len(wb_keys.get(key, [])) == 0 for key, values in q_keys.items()), "out_of_tolerance_count": len(deltas), "out_of_tolerance": deltas[:200]}
        result["geometry"] = geometry
        if geometry["status"] == "fail": result["failures"].append(f"{len(deltas)} unique semantic control boxes exceed ±{args.geometry_tolerance:g} CSS px")
        result["status"] = "pass" if not result["failures"] else "fail"
        result["failure_classification"] = None if result["status"] == "pass" else "ui-visual-geometry"
        result["evidence"] = {"qwork_png": evidence_ref(q_png), "qwork_sha256": f"sha256:{sha256_file(q_png)}", "workbuddy_png": evidence_ref(wb_png), "workbuddy_sha256": f"sha256:{sha256_file(wb_png)}"}
        results.append(result)
    report = {"schema_version": 1, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "policy": {"max_diff_ratio": args.max_diff_ratio, "pixel_channel_threshold": args.pixel_channel_threshold, "geometry_tolerance_css_px": args.geometry_tolerance, "dynamic_masks": []}, "state_count": len(results), "passed": sum(item["status"] == "pass" for item in results), "failed": sum(item["status"] == "fail" for item in results), "results": results}
    report_path = args.output.resolve() / "oracle-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "report": str(report_path), "states": len(results), "passed": report["passed"], "failed": report["failed"]}, ensure_ascii=False))
    return 1 if args.fail_on_diff and report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
