#!/usr/bin/env python3
"""Validate source atoms, UI/business acceptance gates, and suite selectors."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


SHA256 = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
UI_CATEGORIES = {
    "ui-structure",
    "ui-geometry",
    "ui-visual",
    "ui-content",
    "ui-state",
    "ui-interaction",
    "responsive",
    "accessibility",
}
UI_EXECUTION_TYPES = {"web", "desktop", "hybrid"}
REQUIRED_SELECTION_MODES = {"requirement", "category", "cohort", "full", "affected"}
FACET_CATEGORIES = {
    "business-rule": {"business"},
    "acceptance-criterion": {"business"},
    "negative-rule": {"negative"},
    "role-permission": {"permission"},
    "state-transition": {"state", "recovery", "ui-state", "ui-interaction"},
    "data-side-effect": {"data"},
    "error-copy": {"error", "ui-content"},
    "non-functional": {"performance", "reliability"},
    "ui-structure": {"ui-structure"},
    "ui-geometry": {"ui-geometry"},
    "ui-visual": {"ui-visual"},
    "ui-content": {"ui-content"},
    "ui-state": {"ui-state"},
    "ui-interaction": {"ui-interaction"},
    "responsive": {"responsive"},
    "accessibility": {"accessibility"},
    "evidence-provenance": {"evidence-integrity"},
}


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def has_numeric_keys(value: dict[str, Any], keys: set[str]) -> bool:
    return keys.issubset(value) and all(is_number(value[key]) for key in keys)


def resolve_manifest(locator: str, repo: Path) -> Path:
    if locator.startswith("skill://"):
        remainder = locator[len("skill://") :]
        skill_name, separator, relative = remainder.partition("/")
        if not skill_name or not separator or not relative:
            raise ValueError(f"invalid skill locator: {locator}")
        candidate = repo / ".agents" / "skills" / skill_name / relative
    else:
        raw = Path(locator)
        candidate = raw if raw.is_absolute() else repo / raw
    resolved = candidate.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"source acceptance manifest not found: {locator}")
    return resolved


def git_root(start: Path) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start,
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip()).resolve()


def validate(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append("schema_version must equal 1")

    sources = [as_dict(item) for item in as_list(data.get("sources"))]
    requirements = [as_dict(item) for item in as_list(data.get("requirements"))]
    cases = [as_dict(item) for item in as_list(data.get("cases"))]
    suite_index = as_dict(data.get("suite_index"))
    if not sources:
        errors.append("sources must not be empty")
    if not requirements:
        errors.append("requirements must not be empty")
    if not cases:
        errors.append("cases must not be empty")

    def unique_index(items: list[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for item in items:
            value = str(item.get(key) or "").strip()
            if not value:
                errors.append(f"{label} missing {key}")
            elif value in result:
                errors.append(f"duplicate {label} {key}: {value}")
            else:
                result[value] = item
        return result

    source_by_id = unique_index(sources, "source_id", "source")
    requirement_by_id = unique_index(requirements, "requirement_id", "requirement")
    case_by_id = unique_index(cases, "case_id", "case")

    atom_by_id: dict[str, dict[str, Any]] = {}
    atom_source: dict[str, str] = {}
    for source_id, source in source_by_id.items():
        inventory = as_dict(source.get("inventory"))
        for raw_atom in as_list(inventory.get("atoms")):
            atom = as_dict(raw_atom)
            atom_id = str(atom.get("atom_id") or "").strip()
            if not atom_id:
                errors.append(f"source {source_id} has inventory atom without atom_id")
            elif atom_id in atom_by_id:
                errors.append(f"duplicate source atom atom_id: {atom_id}")
            else:
                atom_by_id[atom_id] = atom
                atom_source[atom_id] = source_id

    requirement_sources: dict[str, set[str]] = defaultdict(set)
    source_requirements: dict[str, set[str]] = defaultdict(set)
    requirement_cases: dict[str, set[str]] = defaultdict(set)
    category_cases: dict[str, set[str]] = defaultdict(set)

    for requirement_id, requirement in requirement_by_id.items():
        priority = str(requirement.get("priority") or "")
        status = str(requirement.get("coverage_status") or "")
        categories = {str(value) for value in as_list(requirement.get("categories")) if str(value)}
        source_atoms = [as_dict(item) for item in as_list(requirement.get("source_atoms"))]
        case_ids = {str(value) for value in as_list(requirement.get("case_ids")) if str(value)}
        oracles = [as_dict(item) for item in as_list(requirement.get("oracles"))]
        oracle_atom_ids = {
            str(atom_id)
            for oracle in oracles
            for atom_id in as_list(oracle.get("source_atom_ids"))
            if str(atom_id)
        }
        if priority not in {"P0", "P1", "P2", "P3"}:
            errors.append(f"requirement {requirement_id} has invalid priority")
        if status not in {"covered", "not_applicable", "blocked", "stale"}:
            errors.append(f"requirement {requirement_id} has invalid coverage_status")
        if priority in {"P0", "P1"} and status not in {"covered", "not_applicable"}:
            errors.append(f"P0/P1 requirement {requirement_id} is not covered")
        if status == "not_applicable" and not str(requirement.get("status_reason") or "").strip():
            errors.append(f"not_applicable requirement {requirement_id} requires status_reason")
        if not categories:
            errors.append(f"requirement {requirement_id} has no categories")
        if not source_atoms:
            errors.append(f"requirement {requirement_id} has no source_atoms")
        for atom in source_atoms:
            source_id = str(atom.get("source_id") or "")
            locator = str(atom.get("locator") or "")
            atom_id = str(atom.get("atom_id") or "")
            if source_id not in source_by_id or not locator or not atom_id:
                errors.append(f"requirement {requirement_id} has invalid source atom reference")
                continue
            atom_record = atom_by_id.get(atom_id)
            if atom_record is None or atom_source.get(atom_id) != source_id:
                errors.append(f"requirement {requirement_id} references atom outside source inventory: {atom_id}")
                continue
            if locator != str(atom_record.get("locator") or ""):
                errors.append(f"requirement {requirement_id} atom {atom_id} locator differs from inventory")
            facet = str(atom_record.get("facet") or "")
            accepted_categories = FACET_CATEGORIES.get(facet)
            if not accepted_categories or not (accepted_categories & categories):
                errors.append(
                    f"requirement {requirement_id} does not compile atom {atom_id} facet {facet} "
                    "into a matching category"
                )
            if status == "covered" and atom_id not in oracle_atom_ids:
                errors.append(f"covered requirement {requirement_id} atom {atom_id} is not linked to an oracle")
            requirement_sources[requirement_id].add(source_id)
            source_requirements[source_id].add(requirement_id)
        referenced_atom_ids = {str(atom.get("atom_id") or "") for atom in source_atoms}
        unknown_oracle_atoms = oracle_atom_ids - referenced_atom_ids
        if unknown_oracle_atoms:
            errors.append(
                f"requirement {requirement_id} oracles reference unrelated atoms: "
                + ", ".join(sorted(unknown_oracle_atoms))
            )
        if status == "covered":
            if not case_ids:
                errors.append(f"covered requirement {requirement_id} has no cases")
            if not oracles:
                errors.append(f"covered requirement {requirement_id} has no oracles")
        for case_id in case_ids:
            requirement_cases[requirement_id].add(case_id)
            if case_id not in case_by_id:
                errors.append(f"requirement {requirement_id} references unknown case {case_id}")

        ui_requirement = bool(categories & UI_CATEGORIES) or str(requirement.get("surface")) == "ui"
        linked_cases = [case_by_id[cid] for cid in case_ids if cid in case_by_id]
        linked_categories = {
            str(category)
            for case in linked_cases
            for category in as_list(case.get("categories"))
            if str(category)
        }
        missing_case_categories = categories - linked_categories
        if status == "covered" and missing_case_categories:
            errors.append(
                f"requirement {requirement_id} categories missing from linked cases: "
                + ", ".join(sorted(missing_case_categories))
            )
        if status == "covered" and ui_requirement and not any(
            str(case.get("execution_type")) in UI_EXECUTION_TYPES and str(case.get("route_id") or "").strip()
            for case in linked_cases
        ):
            errors.append(f"UI requirement {requirement_id} lacks a real UI case and route")

        if "ui-geometry" in categories:
            geometry = [oracle for oracle in oracles if oracle.get("type") == "ui-geometry"]
            for oracle in geometry:
                expected = as_dict(oracle.get("expected"))
                relative = as_dict(oracle.get("relative"))
                viewport = as_dict(oracle.get("viewport"))
                linked_geometry_atoms = [
                    atom_by_id[atom_id]
                    for atom_id in as_list(oracle.get("source_atom_ids"))
                    if atom_id in atom_by_id and atom_by_id[atom_id].get("facet") == "ui-geometry"
                ]
                if (
                    not str(oracle.get("target") or "").strip()
                    or not str(oracle.get("coordinate_space") or "").strip()
                    or not has_numeric_keys(viewport, {"width", "height", "dpr"})
                    or viewport["width"] <= 0
                    or viewport["height"] <= 0
                    or viewport["dpr"] <= 0
                    or not is_number(oracle.get("tolerance_css_px"))
                    or oracle.get("tolerance_css_px", -1) < 0
                    or not linked_geometry_atoms
                ):
                    errors.append(f"ui-geometry requirement {requirement_id} has incomplete geometry oracle")
                    continue
                for atom in linked_geometry_atoms:
                    kind = atom.get("measurement_kind")
                    if kind == "absolute-box" and not has_numeric_keys(
                        expected, {"x", "y", "width", "height"}
                    ):
                        errors.append(
                            f"ui-geometry atom {atom.get('atom_id')} requires expected x/y/width/height"
                        )
                    elif kind == "size" and not has_numeric_keys(expected, {"width", "height"}):
                        errors.append(f"ui-geometry atom {atom.get('atom_id')} requires expected width/height")
                    elif kind in {"spacing", "relative-position"} and not {
                        "anchor_target",
                        "relation",
                        "expected_css_px",
                    }.issubset(relative):
                        errors.append(
                            f"ui-geometry atom {atom.get('atom_id')} requires relative geometry expectation"
                        )
                    if kind in {"absolute-box", "size"} and (
                        expected.get("width", 0) <= 0 or expected.get("height", 0) <= 0
                    ):
                        errors.append(f"ui-geometry atom {atom.get('atom_id')} has non-positive size")
                    if kind in {"spacing", "relative-position"} and not is_number(
                        relative.get("expected_css_px")
                    ):
                        errors.append(f"ui-geometry atom {atom.get('atom_id')} has non-numeric relative value")
            if not geometry:
                errors.append(f"ui-geometry requirement {requirement_id} lacks ui-geometry oracle")

        if "ui-visual" in categories:
            visuals = [oracle for oracle in oracles if oracle.get("type") == "visual"]
            computed_styles = [
                oracle for oracle in oracles if oracle.get("type") == "computed-style"
            ]
            for oracle in visuals:
                baseline = as_dict(oracle.get("baseline"))
                comparison = as_dict(oracle.get("comparison"))
                viewport = as_dict(oracle.get("viewport"))
                if (
                    not str(baseline.get("locator") or "").strip()
                    or not SHA256.match(str(baseline.get("sha256") or ""))
                    or not has_numeric_keys(viewport, {"width", "height", "dpr"})
                    or not is_number(comparison.get("max_diff_ratio"))
                    or not 0 <= comparison.get("max_diff_ratio", -1) <= 1
                    or not isinstance(comparison.get("mask_regions"), list)
                ):
                    errors.append(f"ui-visual requirement {requirement_id} has incomplete visual oracle")
            for oracle in computed_styles:
                if (
                    not str(oracle.get("target") or "").strip()
                    or not str(oracle.get("expected_expression") or "").strip()
                    or not SHA256.match(str(oracle.get("source_sha256") or ""))
                ):
                    errors.append(
                        f"ui-visual requirement {requirement_id} has incomplete computed-style oracle"
                    )
            if not visuals and not computed_styles:
                errors.append(
                    f"ui-visual requirement {requirement_id} lacks visual or computed-style oracle"
                )

    for source_id, source in source_by_id.items():
        authority = str(source.get("authority_kind") or "")
        approval = str(source.get("approval_status") or "")
        inventory = as_dict(source.get("inventory"))
        atoms = [as_dict(value) for value in as_list(inventory.get("atoms"))]
        atom_ids = {str(atom.get("atom_id")) for atom in atoms if str(atom.get("atom_id") or "")}
        facets = {str(value) for value in as_list(source.get("content_facets")) if str(value)}
        if authority not in {"normative", "evidence", "context-only"}:
            errors.append(f"source {source_id} has invalid authority_kind")
        if not str(source.get("authority_domain") or "").strip():
            errors.append(f"source {source_id} has no authority_domain")
        if not str(source.get("locator") or "").strip():
            errors.append(f"source {source_id} has no stable locator")
        if not str(source.get("revision") or "").strip():
            errors.append(f"source {source_id} has no revision")
        if not SHA256.match(str(source.get("content_hash") or "")):
            errors.append(f"source {source_id} has invalid content_hash")
        if authority == "normative":
            if approval not in {"approved", "frozen"}:
                errors.append(f"normative source {source_id} is not approved or frozen")
            if inventory.get("extraction_status") != "complete":
                errors.append(f"normative source {source_id} atom extraction is incomplete")
            if not atom_ids:
                errors.append(f"normative source {source_id} has no atomic requirements")
            if not facets:
                errors.append(f"normative source {source_id} has no content_facets")
        atom_facets: set[str] = set()
        for atom in atoms:
            atom_id = str(atom.get("atom_id") or "")
            facet = str(atom.get("facet") or "")
            atom_facets.add(facet)
            if facet not in FACET_CATEGORIES:
                errors.append(f"source atom {atom_id} has unsupported facet: {facet}")
            if not str(atom.get("locator") or "").strip():
                errors.append(f"source atom {atom_id} has no stable locator")
            if not SHA256.match(str(atom.get("extracted_value_hash") or "")):
                errors.append(f"source atom {atom_id} has invalid extracted_value_hash")
            if facet == "ui-geometry" and atom.get("measurement_kind") not in {
                "absolute-box",
                "size",
                "spacing",
                "relative-position",
            }:
                errors.append(f"ui-geometry atom {atom_id} has invalid measurement_kind")
        if facets != atom_facets:
            errors.append(f"source {source_id} content_facets must exactly match inventory atom facets")
        mapped_atom_ids = {
            str(atom.get("atom_id"))
            for requirement_id in source_requirements.get(source_id, set())
            for raw_atom in as_list(requirement_by_id[requirement_id].get("source_atoms"))
            for atom in [as_dict(raw_atom)]
            if as_dict(atom).get("source_id") == source_id
        }
        missing_atoms = atom_ids - mapped_atom_ids
        if missing_atoms:
            errors.append(f"source {source_id} has unmapped atoms: {', '.join(sorted(missing_atoms))}")
        unexpected_atoms = mapped_atom_ids - atom_ids
        if unexpected_atoms:
            errors.append(
                f"source {source_id} requirements reference atoms outside inventory: "
                + ", ".join(sorted(unexpected_atoms))
            )
        requirement_categories = {
            str(category)
            for requirement_id in source_requirements.get(source_id, set())
            for category in as_list(requirement_by_id[requirement_id].get("categories"))
        }
        for facet in facets:
            accepted = FACET_CATEGORIES.get(facet)
            if not accepted:
                errors.append(f"source {source_id} has unsupported content facet: {facet}")
            elif not (accepted & requirement_categories):
                errors.append(f"source {source_id} facet {facet} has no matching acceptance category")

    for case_id, case in case_by_id.items():
        requirement_ids = {str(value) for value in as_list(case.get("requirement_ids")) if str(value)}
        categories = {str(value) for value in as_list(case.get("categories")) if str(value)}
        if not requirement_ids:
            errors.append(f"case {case_id} is orphaned from requirements")
        for requirement_id in requirement_ids:
            if requirement_id not in requirement_by_id:
                errors.append(f"case {case_id} references unknown requirement {requirement_id}")
            elif case_id not in requirement_cases.get(requirement_id, set()):
                errors.append(f"case {case_id} is missing from requirement {requirement_id} case_ids")
        if not categories:
            errors.append(f"case {case_id} has no categories")
        for category in categories:
            category_cases[category].add(case_id)
        if str(case.get("execution_type")) in UI_EXECUTION_TYPES:
            checkpoints = {str(value) for value in as_list(case.get("required_screenshot_states"))}
            acceptance_mode = str(case.get("ui_acceptance_mode") or "")
            if acceptance_mode not in {"behavior-only", "visual-checkpoints"}:
                errors.append(f"UI case {case_id} has no explicit UI acceptance mode")
            elif acceptance_mode == "behavior-only" and checkpoints:
                errors.append(f"behavior-only UI case {case_id} cannot require screenshot checkpoints")
            elif acceptance_mode == "visual-checkpoints" and not {"entry", "final-state"}.issubset(checkpoints):
                errors.append(f"visual UI case {case_id} requires entry and final-state screenshots")
            if not str(case.get("route_id") or "").strip():
                errors.append(f"UI case {case_id} has no route_id")

    modes = {str(value) for value in as_list(suite_index.get("selection_modes"))}
    if not REQUIRED_SELECTION_MODES.issubset(modes):
        errors.append("suite_index must support requirement, category, full, and affected selection")
    declared_requirement_cases = {
        str(key): {str(value) for value in as_list(values)}
        for key, values in as_dict(suite_index.get("requirement_to_cases")).items()
    }
    expected_requirement_cases = {
        requirement_id: case_ids
        for requirement_id, case_ids in requirement_cases.items()
        if requirement_by_id.get(requirement_id, {}).get("coverage_status") == "covered"
    }
    if declared_requirement_cases != expected_requirement_cases:
        errors.append("suite_index requirement_to_cases does not exactly match covered requirements")
    declared_category_cases = {
        str(key): {str(value) for value in as_list(values)}
        for key, values in as_dict(suite_index.get("category_to_cases")).items()
    }
    if declared_category_cases != dict(category_cases):
        errors.append("suite_index category_to_cases does not exactly match case categories")
    declared_cohort_cases = {
        str(key): {str(value) for value in as_list(values)}
        for key, values in as_dict(suite_index.get("cohort_to_cases")).items()
    }
    cohort_index = as_dict(data.get("cohort_index"))
    expected_cohort_cases: dict[str, set[str]] = {}
    for cohort_id, raw in cohort_index.items():
        record = as_dict(raw)
        members = {str(value) for value in as_list(record.get("case_ids"))}
        if record.get("case_count") != len(members):
            errors.append(f"cohort {cohort_id} case_count must equal exact unique membership")
        if not SHA256.match(str(record.get("membership_sha256") or "")):
            errors.append(f"cohort {cohort_id} has invalid membership_sha256")
        canonical_members = json.dumps(sorted(members), separators=(",", ":")).encode()
        expected_membership_hash = f"sha256:{hashlib.sha256(canonical_members).hexdigest()}"
        if record.get("membership_sha256") != expected_membership_hash:
            errors.append(f"cohort {cohort_id} membership_sha256 does not match exact members")
        if not members.issubset(case_by_id):
            errors.append(f"cohort {cohort_id} contains unknown Cases")
        expected_cohort_cases[str(cohort_id)] = members
    if declared_cohort_cases != expected_cohort_cases:
        errors.append("suite_index cohort_to_cases does not exactly match cohort_index")
    full_case_ids = {str(value) for value in as_list(suite_index.get("full_case_ids"))}
    if full_case_ids != set(case_by_id):
        errors.append("suite_index full_case_ids must contain every active case exactly once")

    summary = as_dict(data.get("coverage_summary"))
    actual_summary = {
        "source_atoms": sum(
            len(as_list(as_dict(source.get("inventory")).get("atoms"))) for source in sources
        ),
        "requirements": len(requirement_by_id),
        "cases": len(case_by_id),
        "unmapped_source_atoms": sum(
            len(
                {
                    str(as_dict(value).get("atom_id"))
                    for value in as_list(as_dict(source.get("inventory")).get("atoms"))
                    if str(as_dict(value).get("atom_id") or "")
                }
                - {
                    str(atom.get("atom_id"))
                    for requirement_id in source_requirements.get(str(source.get("source_id")), set())
                    for raw_atom in as_list(requirement_by_id[requirement_id].get("source_atoms"))
                    for atom in [as_dict(raw_atom)]
                    if as_dict(atom).get("source_id") == source.get("source_id")
                }
            )
            for source in sources
        ),
        "uncovered_p0_p1": sum(
            1
            for requirement in requirements
            if requirement.get("priority") in {"P0", "P1"}
            and requirement.get("coverage_status") not in {"covered", "not_applicable"}
        ),
        "orphan_cases": sum(1 for case in cases if not as_list(case.get("requirement_ids"))),
    }
    for key, value in actual_summary.items():
        if summary.get(key) != value:
            errors.append(f"coverage_summary {key} must equal {value}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="JSON path or skill:// locator")
    parser.add_argument("--repo", type=Path, help="Repository root; defaults to git root")
    args = parser.parse_args()
    try:
        if args.repo:
            repo = args.repo.resolve()
        elif args.manifest.startswith("skill://"):
            repo = git_root(Path.cwd())
        else:
            try:
                repo = git_root(Path.cwd())
            except subprocess.CalledProcessError:
                repo = Path.cwd().resolve()
        manifest_path = resolve_manifest(args.manifest, repo)
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"source acceptance manifest error: {exc}", file=sys.stderr)
        return 1
    if not isinstance(data, dict):
        print("source acceptance manifest must be a JSON object", file=sys.stderr)
        return 1
    errors = validate(data)
    if errors:
        print("source-derived acceptance gate is incomplete:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"source-derived acceptance gate complete: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
