#!/usr/bin/env python3
"""Fail closed while rendering the canonical E2E report and visual evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

from external_artifact_storage import REPORT_HTML_NAME, REPORT_JSON_NAME, validate_external_run_root

RENDERER_PATH = Path(__file__).with_name("render_e2e_report.py")
RENDERER_SPEC = importlib.util.spec_from_file_location("project_e2e_report_renderer", RENDERER_PATH)
if RENDERER_SPEC is None or RENDERER_SPEC.loader is None:
    raise RuntimeError("cannot load render_e2e_report.py")
RENDERER = importlib.util.module_from_spec(RENDERER_SPEC)
RENDERER_SPEC.loader.exec_module(RENDERER)
render = RENDERER.render
validate_cases = RENDERER.validate_cases

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} root must be a mapping")
    return value


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def resolve_relative(path_value: str, root: Path) -> Path:
    candidate = Path(path_value)
    if candidate.is_absolute():
        raise ValueError(f"report artifact path must be relative: {path_value}")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"report artifact escapes run root: {path_value}") from exc
    return resolved


def unique_index(values: Any, key: str, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(values, list):
        raise ValueError(f"{label} must be a list")
    result: dict[str, dict[str, Any]] = {}
    for value in values:
        if not isinstance(value, dict) or not isinstance(value.get(key), str):
            raise ValueError(f"{label} contains an invalid {key}")
        item_id = value[key]
        if item_id in result:
            raise ValueError(f"{label} contains duplicate {key}: {item_id}")
        result[item_id] = value
    return result


def validate_plan_linkage(report: dict[str, Any], plan: dict[str, Any]) -> None:
    if report.get("plan_sha256") != plan.get("plan_sha256"):
        raise ValueError("visual report plan_sha256 does not match the current plan")
    if report.get("implementation_revision") != plan.get("implementation_revision"):
        raise ValueError("visual report implementation_revision does not match the current plan")
    human_cases = unique_index(report.get("cases"), "id", "cases")
    machine_cases = unique_index(report.get("case_results"), "case_id", "case_results")
    selected = {str(value) for value in plan.get("selected_case_ids", [])}
    missing_human = sorted(selected - human_cases.keys())
    missing_machine = sorted(selected - machine_cases.keys())
    if missing_human:
        raise ValueError("human report is missing selected cases: " + ", ".join(missing_human))
    if missing_machine:
        raise ValueError("machine report is missing selected cases: " + ", ".join(missing_machine))


def validate_visual_inventory(report: dict[str, Any], root: Path) -> tuple[int, list[str]]:
    cases = validate_cases(report, root)
    referenced: set[Path] = set()
    screenshot_count = 0
    for case in cases:
        evidence_entries = case.get("evidence", [])
        if not isinstance(evidence_entries, list):
            continue
        for evidence in evidence_entries:
            if not isinstance(evidence, dict) or str(evidence.get("kind", "")).lower() != "screenshot":
                continue
            screenshot_count += 1
            referenced.add(resolve_relative(str(evidence["path"]), root))

    exclusions: set[Path] = set()
    for exclusion in report.get("visual_artifact_exclusions", []):
        if not isinstance(exclusion, dict) or not exclusion.get("path") or not exclusion.get("reason"):
            raise ValueError("visual_artifact_exclusions require path and reason")
        exclusions.add(resolve_relative(str(exclusion["path"]), root))

    discovered = {
        path.resolve() for path in root.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    }
    orphaned = sorted(str(path.relative_to(root)) for path in discovered - referenced - exclusions)
    if orphaned:
        raise ValueError("unreferenced screenshot artifact: " + ", ".join(orphaned))
    missing_exclusions = sorted(str(path.relative_to(root)) for path in exclusions - discovered)
    if missing_exclusions:
        raise ValueError("visual artifact exclusion does not exist: " + ", ".join(missing_exclusions))
    return screenshot_count, sorted(str(path.relative_to(root)) for path in referenced)


def finalize_report(
    *,
    report_path: Path,
    output_path: Path,
    artifact_root: Path,
    plan_path: Path | None = None,
) -> dict[str, Any]:
    skill_root = Path(__file__).resolve().parent.parent
    root = validate_external_run_root(
        artifact_root,
        protected_roots=[skill_root],
    )
    report_path = report_path.resolve()
    output_path = output_path.resolve()
    if report_path != root / REPORT_JSON_NAME:
        raise ValueError(f"canonical machine and human input must be <run-root>/{REPORT_JSON_NAME}")
    try:
        output_path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{REPORT_HTML_NAME} escapes run root") from exc

    report = load_json(report_path)
    if plan_path is not None:
        validate_plan_linkage(report, load_json(plan_path.resolve()))
    screenshot_count, screenshot_paths = validate_visual_inventory(report, root)
    rendered = render(report, root)
    output_path.write_text(rendered, encoding="utf-8")
    embedded_count = rendered.count("data:image/")
    if embedded_count != screenshot_count:
        raise ValueError(f"self-contained report embedded {embedded_count} screenshots, expected {screenshot_count}")
    return {
        "status": "pass",
        "report_json": str(report_path.relative_to(root)),
        "report_json_sha256": sha256_file(report_path),
        "report_html": str(output_path.relative_to(root)),
        "report_html_sha256": sha256_file(output_path),
        "screenshot_count": screenshot_count,
        "screenshot_paths": screenshot_paths,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--plan", type=Path)
    args = parser.parse_args()
    result = finalize_report(
        report_path=args.input,
        output_path=args.output,
        artifact_root=args.artifact_root,
        plan_path=args.plan,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
