#!/usr/bin/env python3
"""Validate hash-bound results produced by the separate authorized-live runner."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


LIVE_RESULTS_NAME = "authorized-live-results.json"
SECRET_MARKERS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "COOKIE", "CREDENTIAL")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def relative_path(root: Path, value: object, label: str, *, must_exist: bool = False) -> Path:
    relative = Path(str(value or ""))
    if relative.is_absolute() or not relative.parts:
        raise ValueError(f"{label} must be a non-empty path relative to the run root")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"{label} escapes the run root") from error
    if must_exist and not resolved.is_file():
        raise ValueError(f"{label} is missing: {relative}")
    return resolved


def path_within(root: Path, value: object, label: str) -> Path:
    resolved = Path(str(value or "")).expanduser().resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"{label} must stay inside the run root") from error
    if resolved == root.resolve():
        raise ValueError(f"{label} cannot be the run root")
    return resolved


def https_origin(value: object, label: str) -> str:
    parsed = urlsplit(str(value or ""))
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError(f"{label} must be an HTTPS origin or endpoint without credentials")
    return f"https://{parsed.netloc}"


def validate_authorization(
    *,
    authorization: dict[str, Any],
    plan_item: dict[str, Any],
    run_root: Path,
    revision: str,
    plan_sha256: str,
    repo: Path | None = None,
) -> dict[str, Any]:
    if authorization.get("schema_version") != 1:
        raise ValueError("authorization schema_version must be 1")
    if authorization.get("decision") != "authorized":
        raise ValueError("authorization decision must be authorized")
    if authorization.get("authorized_by") != "requesting-user":
        raise ValueError("authorization must come from the requesting user")
    if not str(authorization.get("authorization_source") or "").strip():
        raise ValueError("authorization source is required")
    if not str(authorization.get("authorized_at") or "").strip():
        raise ValueError("authorization timestamp is required")
    if authorization.get("case_id") != plan_item.get("case_id"):
        raise ValueError("authorization Case does not match the plan item")
    if authorization.get("plan_sha256") != plan_sha256:
        raise ValueError("authorization plan hash does not match")
    if authorization.get("implementation_revision") != revision:
        raise ValueError("authorization implementation revision does not match")
    if plan_item.get("kind") != "case" or plan_item.get("authorization_required") is not True:
        raise ValueError("plan item is not an authorization-required Case")

    provider = authorization.get("provider")
    if not isinstance(provider, dict):
        raise ValueError("authorization provider is required")
    provider_origin = https_origin(provider.get("endpoint"), "provider endpoint")
    model = str(provider.get("model") or "").strip()
    if not model:
        raise ValueError("authorization provider model is required")

    origins = authorization.get("allowed_network_origins")
    if not isinstance(origins, list) or not origins:
        raise ValueError("authorization allowed_network_origins must be non-empty")
    normalized_origins = [https_origin(value, "allowed network origin") for value in origins]
    if provider_origin not in normalized_origins:
        raise ValueError("provider endpoint is outside the authorized network origins")

    budget = authorization.get("budget")
    if not isinstance(budget, dict) or budget.get("max_case_invocations") != 1:
        raise ValueError("authorization must permit exactly one Case invocation")
    timeout_seconds = budget.get("timeout_seconds")
    if not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 900:
        raise ValueError("authorization timeout must be between 1 and 900 seconds")

    payloads = authorization.get("authorized_payloads")
    if not isinstance(payloads, list) or not payloads or any(not isinstance(value, str) or not value for value in payloads):
        raise ValueError("authorization must name every external payload")
    source_contract = plan_item.get("source_contract") or {}
    source_locator = source_contract.get("spec")
    source_path = Path(str(source_locator or ""))
    if not source_path.is_absolute():
        if repo is None:
            raise ValueError("relative source contract requires a repository root")
        source_path = (repo / source_path).resolve()
    if not source_path.is_file():
        raise ValueError("authorization source contract is not readable")
    source_text = source_path.read_text(encoding="utf-8")
    if any(value not in source_text for value in payloads) or model not in source_text:
        raise ValueError("authorized payload or model is absent from the frozen Case source")

    write_roots = authorization.get("allowed_write_roots")
    if not isinstance(write_roots, list) or not write_roots:
        raise ValueError("authorization allowed_write_roots must be non-empty")
    resolved_write_roots = [path_within(run_root, value, "authorized write root") for value in write_roots]

    environment = authorization.get("environment")
    if not isinstance(environment, dict) or not environment:
        raise ValueError("authorization environment must be non-empty")
    for name, value in environment.items():
        if not isinstance(name, str) or not name.startswith("QWORK_") or not isinstance(value, str):
            raise ValueError("authorization environment accepts only string QWORK_* entries")
        if any(marker in name.upper() for marker in SECRET_MARKERS):
            raise ValueError("authorization environment must not contain secret values")
    for name in ("QWORK_LIVE_STATE_HOME", "QWORK_EXPERT_TEAM_EVIDENCE_DIR"):
        if name not in environment:
            continue
        candidate = path_within(run_root, environment[name], name)
        if not any(candidate == root or root in candidate.parents for root in resolved_write_roots):
            raise ValueError(f"{name} is outside authorized write roots")

    cleanup_values = authorization.get("cleanup_paths")
    if not isinstance(cleanup_values, list) or not cleanup_values:
        raise ValueError("authorization cleanup paths must be non-empty")
    cleanup_paths = [relative_path(run_root, value, "cleanup path") for value in cleanup_values]
    evidence_report = relative_path(run_root, authorization.get("evidence_report"), "evidence report")
    if any(path == evidence_report or path in evidence_report.parents for path in cleanup_paths):
        raise ValueError("cleanup path would remove the retained evidence report")

    return {
        "timeout_seconds": timeout_seconds,
        "environment": dict(environment),
        "cleanup_paths": cleanup_paths,
        "evidence_report": evidence_report,
        "provider": {"endpoint": str(provider["endpoint"]), "model": model},
        "authorized_payload_sha256": [sha256_text(value) for value in payloads],
    }


def redacted_authorization(authorization: dict[str, Any]) -> dict[str, Any]:
    payloads = authorization.get("authorized_payloads") or []
    return {
        "schema_version": authorization.get("schema_version"),
        "decision": authorization.get("decision"),
        "authorized_by": authorization.get("authorized_by"),
        "authorization_source": authorization.get("authorization_source"),
        "authorized_at": authorization.get("authorized_at"),
        "case_id": authorization.get("case_id"),
        "plan_sha256": authorization.get("plan_sha256"),
        "implementation_revision": authorization.get("implementation_revision"),
        "authorized_payload_sha256": [sha256_text(str(value)) for value in payloads],
        "provider": authorization.get("provider"),
        "budget": authorization.get("budget"),
        "allowed_network_origins": authorization.get("allowed_network_origins"),
        "allowed_write_roots": authorization.get("allowed_write_roots"),
        "environment_keys": sorted((authorization.get("environment") or {}).keys()),
        "cleanup_paths": authorization.get("cleanup_paths"),
        "evidence_report": authorization.get("evidence_report"),
    }


def validate_artifact(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an artifact object")
    path = relative_path(root, value.get("path"), label, must_exist=True)
    expected = str(value.get("sha256") or "").removeprefix("sha256:").lower()
    if len(expected) != 64 or sha256_file(path) != expected:
        raise ValueError(f"{label} hash mismatch")
    return path


def load_authorized_live_coordinates(
    *,
    run_root: Path,
    plan: dict[str, Any],
    repo: Path,
) -> dict[str, dict[str, Any]]:
    path = run_root / LIVE_RESULTS_NAME
    if not path.is_file():
        return {}
    payload = load(path)
    if (
        payload.get("schema_version") != 1
        or payload.get("plan_sha256") != plan.get("plan_sha256")
        or payload.get("implementation_revision") != plan.get("implementation_revision")
    ):
        raise ValueError("authorized live result belongs to another plan or revision")
    items = {str(item.get("item_id")): item for item in plan.get("required_items", [])}
    coordinates = payload.get("coordinates")
    if not isinstance(coordinates, dict):
        raise ValueError("authorized live result coordinates must be an object")
    validated: dict[str, dict[str, Any]] = {}
    for item_id, coordinate in coordinates.items():
        item = items.get(str(item_id))
        if not item or item.get("kind") != "case" or item.get("authorization_required") is not True:
            raise ValueError(f"authorized live result contains an unexpected coordinate: {item_id}")
        if not isinstance(coordinate, dict):
            raise ValueError(f"authorized live coordinate is invalid: {item_id}")
        if (
            coordinate.get("category") != "live-authorization"
            or coordinate.get("status") not in {"pass", "fail"}
            or coordinate.get("case_id") != item.get("case_id")
            or coordinate.get("route_id") != item.get("route_id")
            or coordinate.get("command") != item.get("command")
            or coordinate.get("source_contract") != item.get("source_contract")
            or coordinate.get("exit_code") not in {0, 1}
            or coordinate.get("cleanup_status") != "pass"
            or not coordinate.get("started_at")
            or not coordinate.get("finished_at")
        ):
            raise ValueError(f"authorized live coordinate authority mismatch: {item_id}")
        if (coordinate.get("status") == "pass") != (coordinate.get("exit_code") == 0):
            raise ValueError(f"authorized live coordinate status/exit mismatch: {item_id}")
        authorization_ref = coordinate.get("authorization")
        authorization_path = validate_artifact(run_root, authorization_ref, f"{item_id} authorization")
        authorization = load(authorization_path)
        validate_authorization(
            authorization=authorization,
            plan_item=item,
            run_root=run_root,
            revision=str(plan["implementation_revision"]),
            plan_sha256=str(plan["plan_sha256"]),
            repo=repo,
        )
        artifacts = coordinate.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError(f"authorized live coordinate has no artifacts: {item_id}")
        for index, artifact in enumerate(artifacts):
            validate_artifact(run_root, artifact, f"{item_id} artifact {index}")
        validated[str(item_id)] = coordinate
    return validated
