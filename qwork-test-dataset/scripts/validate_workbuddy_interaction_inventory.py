#!/usr/bin/env python3
"""Fail-closed validation for the frozen WorkBuddy control inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from collections import Counter
from typing import Any


ACTIONABLE_TAGS = {"a", "button", "input", "select", "textarea"}
ACTIONABLE_ROLES = {
    "button",
    "checkbox",
    "combobox",
    "link",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "option",
    "radio",
    "slider",
    "spinbutton",
    "switch",
    "tab",
    "textbox",
}
CLASSIFICATIONS = {
    "disabled-control",
    "external-capability-blocked",
    "non-actionable-semantic-node",
    "observed-read-only-transition",
    "representative-causality-covered",
    "side-effect-not-exercised",
    "source-case-reference-pending",
    "unlabeled-interaction-gap",
    "unobserved-local-interaction-gap",
}
STATUSES = {"blocked", "covered", "gap", "pending"}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(payload)


def actionable(control: dict[str, Any]) -> bool:
    return str(control.get("tag") or "") in ACTIONABLE_TAGS or str(control.get("role") or "") in ACTIONABLE_ROLES


def fail(message: str) -> None:
    raise ValueError(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill-root", type=pathlib.Path, required=True)
    parser.add_argument(
        "--snapshot",
        default="data/evidence/workbuddy-cdp/5.3.12-surfaces-v4",
    )
    parser.add_argument(
        "--inventory",
        default="data/datasets/workbuddy-interaction-inventory.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.skill_root.resolve()
    snapshot = root / args.snapshot
    inventory_path = root / args.inventory
    if not inventory_path.is_file():
        fail(f"interaction inventory is missing: {inventory_path}")

    manifest_path = snapshot / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))

    if inventory.get("schema_version") != 1:
        fail("inventory schema_version must be 1")
    authority = inventory.get("authority") or {}
    if authority.get("source") != "skill://qwork-test-dataset/data/evidence/workbuddy-cdp/5.3.12-surfaces-v4/manifest.json":
        fail("inventory authority must use the stable Skill URI")
    if authority.get("manifest_sha256") != f"sha256:{sha256_bytes(manifest_bytes)}":
        fail("inventory manifest hash drifted")
    if inventory.get("classification_policy") != "skill://qwork-test-dataset/references/workbuddy-interaction-classification-policy.yaml":
        fail("inventory classification policy is missing or unstable")

    expected: dict[tuple[str, int], dict[str, Any]] = {}
    for record in manifest.get("records", []):
        state = str(record["state"])
        state_payload = json.loads((snapshot / f"{state}.json").read_text(encoding="utf-8"))
        controls = state_payload.get("controls", [])
        if record.get("control_count") != len(controls):
            fail(f"source control_count mismatch for {state}")
        for index, control in enumerate(controls):
            expected[(state, index)] = control

    entries = inventory.get("controls")
    if not isinstance(entries, list):
        fail("inventory controls must be an array")
    if len(entries) != len(expected):
        fail(f"inventory is not closed: expected {len(expected)} controls, got {len(entries)}")

    ids: set[str] = set()
    coordinates: set[tuple[str, int]] = set()
    status_counts: Counter[str] = Counter()
    class_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    actionable_count = 0
    referenced_cases: set[str] = set()

    for entry in entries:
        control_id = str(entry.get("control_id") or "")
        if not control_id.startswith("WBC-") or control_id in ids:
            fail(f"invalid or duplicate control_id: {control_id!r}")
        ids.add(control_id)
        coordinate = (str(entry.get("state") or ""), entry.get("index"))
        if not isinstance(coordinate[1], int) or coordinate in coordinates or coordinate not in expected:
            fail(f"invalid or duplicate source coordinate: {coordinate!r}")
        coordinates.add(coordinate)

        source_control = expected[coordinate]
        if entry.get("control_sha256") != f"sha256:{canonical_hash(source_control)}":
            fail(f"control hash drifted at {coordinate!r}")
        actual_actionable = actionable(source_control)
        if entry.get("actionable") is not actual_actionable:
            fail(f"actionable classification drifted at {coordinate!r}")
        actionable_count += int(actual_actionable)

        classification = str(entry.get("classification") or "")
        status = str(entry.get("status") or "")
        family = str(entry.get("family") or "")
        if classification not in CLASSIFICATIONS or status not in STATUSES or not family:
            fail(f"invalid classification tuple at {coordinate!r}")
        if actual_actionable and classification == "non-actionable-semantic-node":
            fail(f"actionable control was hidden as non-actionable at {coordinate!r}")
        if not actual_actionable and classification != "non-actionable-semantic-node":
            fail(f"non-actionable node was promoted to an interaction at {coordinate!r}")
        if status in {"blocked", "gap", "pending"} and not entry.get("next_action"):
            fail(f"non-covered control lacks next_action at {coordinate!r}")
        if status == "covered" and entry.get("next_action"):
            fail(f"covered control cannot carry next_action at {coordinate!r}")
        if classification == "external-capability-blocked" and status != "blocked":
            fail(f"external blocker must remain blocked at {coordinate!r}")
        if classification in {"unlabeled-interaction-gap", "unobserved-local-interaction-gap"} and status != "gap":
            fail(f"local interaction gap must remain a gap at {coordinate!r}")

        case_ids = entry.get("case_ids") or []
        if not isinstance(case_ids, list) or any(not isinstance(case_id, str) for case_id in case_ids):
            fail(f"case_ids must be a string array at {coordinate!r}")
        referenced_cases.update(case_ids)
        if classification in {"representative-causality-covered", "source-case-reference-pending"} and not case_ids:
            fail(f"Case-backed classification lacks Case IDs at {coordinate!r}")

        label = entry.get("label")
        if label is not None and (not isinstance(label, str) or len(label) > 160):
            fail(f"unsafe label projection at {coordinate!r}")
        if entry.get("label_redacted") and label is not None:
            fail(f"redacted controls must not retain raw labels at {coordinate!r}")

        status_counts[status] += 1
        class_counts[classification] += 1
        family_counts[family] += 1

    if coordinates != set(expected):
        fail("inventory coordinates are not an exact closed-world match")

    case_root = root / "data/datasets/cases"
    available_cases = {path.stem for path in case_root.glob("*.json")}
    missing_cases = sorted(referenced_cases - available_cases)
    if missing_cases:
        fail(f"inventory references missing Cases: {missing_cases}")

    summary = inventory.get("summary") or {}
    expected_summary = {
        "state_count": len(manifest.get("records", [])),
        "control_count": len(entries),
        "actionable_count": actionable_count,
        "non_actionable_count": len(entries) - actionable_count,
        "status_counts": dict(sorted(status_counts.items())),
        "classification_counts": dict(sorted(class_counts.items())),
        "family_counts": dict(sorted(family_counts.items())),
        "unclassified_count": 0,
    }
    if summary != expected_summary:
        fail("inventory summary does not reproduce the control ledger")

    print(json.dumps({
        "status": "pass",
        "states": expected_summary["state_count"],
        "controls": expected_summary["control_count"],
        "actionable": actionable_count,
        "statuses": expected_summary["status_counts"],
        "classifications": expected_summary["classification_counts"],
        "referenced_cases": len(referenced_cases),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
