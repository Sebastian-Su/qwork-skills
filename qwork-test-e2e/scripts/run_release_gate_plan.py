#!/usr/bin/env python3
"""Preflight and execute a frozen QWork release-gate plan without shell evaluation."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
from typing import Any

from external_artifact_storage import validate_external_run_root


GATE_COMMANDS = {
    "gate:source-acceptance": "python3 .agents/skills/qwork-test-e2e/scripts/validate_source_acceptance.py --repo . --manifest skill://qwork-test-dataset/data/datasets/source-acceptance.json",
    "gate:source-dispositions": "python3 .agents/skills/qwork-test-dataset/scripts/validate_source_dispositions.py --repo . --manifest skill://qwork-test-dataset/data/datasets/source-dispositions.json",
    "gate:route-registry": "python3 .agents/skills/qwork-test-dataset/scripts/validate_route_registry.py --repo . --skill-root .agents/skills/qwork-test-dataset",
    "gate:dataset-private-storage": "python3 .agents/skills/qwork-test-dataset/scripts/validate_private_storage.py --repo . --skill qwork-test-dataset --path .agents/skills/qwork-test-dataset/data/datasets/source-acceptance.json",
    "gate:dataset-schema": "node .agents/skills/qwork-test-dataset/scripts/validate_cases_ajv.mjs",
    "gate:document-case-coverage": "python3 .agents/skills/qwork-test-dataset/scripts/test_document_case_coverage.py --skill-root .agents/skills/qwork-test-dataset",
    "gate:structured-oracle-coverage": "python3 .agents/skills/qwork-test-dataset/scripts/test_structured_oracle_coverage.py --skill-root .agents/skills/qwork-test-dataset",
    "gate:workbuddy-interaction-inventory": "python3 .agents/skills/qwork-test-dataset/scripts/validate_workbuddy_interaction_inventory.py --skill-root .agents/skills/qwork-test-dataset",
    "gate:live-case-authorization": "python3 .agents/skills/qwork-test-dataset/scripts/test_live_case_authorization.py --skill-root .agents/skills/qwork-test-dataset",
    "gate:typecheck": "npm run typecheck",
    "gate:unit-integration": "npm test",
    "gate:coverage": "npm run test:coverage -- --coverage.thresholds.autoUpdate=false",
    "gate:electron-build": "npx electron-vite build",
}
LOCAL_CATEGORIES = {"gate", "dataset-verifier", "deterministic-playwright", "workbuddy-oracle"}
TERMINAL_COORDINATES = {"pass", "fail"}
LOOPBACK_GATE_ITEMS = {"gate:unit-integration", "gate:coverage"}
WORKBUDDY_CDP_SOURCE = re.compile(r"^WORKBUDDY-CDP-(\d+(?:-\d+)+)-V(\d+)$")
WORKBUDDY_REFERENCE_PREFIX = ".agents/skills/qwork-test-dataset/"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def plan_hash(plan: dict[str, Any]) -> str:
    normalized = json.loads(json.dumps(plan))
    normalized.pop("plan_sha256", None)
    normalized.setdefault("checkpoint", {})["current_plan_hash"] = None
    return canonical_hash(normalized)


def tree_hash(root: Path) -> str:
    entries = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if (
            not path.is_file()
            or "__pycache__" in relative.parts
            or path.name == ".DS_Store"
            or relative.parts[:2] == ("data", "runs")
        ):
            continue
        entries.append({"path": relative.as_posix(), "sha256": sha256_file(path), "size": path.stat().st_size})
    return canonical_hash({"files": entries})


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def resolve_qwork_server_dir(repo: Path) -> Path | None:
    override = os.environ.get("QWORK_SERVER_DIR", "").strip()
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override).expanduser())
    common_git = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    main_checkout = common_git.parent if common_git.name == ".git" else common_git
    candidates.append(main_checkout.parent / "qwork_server")
    for candidate in candidates:
        resolved = candidate.resolve()
        if (resolved / "cmd/dev-api").is_dir():
            return resolved
    return None


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def safe_name(value: str) -> str:
    return "".join(character if character.isalnum() or character in "._-" else "-" for character in value)


def private_run_namespace(run_root: Path) -> str:
    resolved = run_root.resolve()
    digest = hashlib.sha256(str(resolved).encode()).hexdigest()[:12]
    return f"{safe_name(resolved.parent.name)}-{safe_name(resolved.name)}-{digest}"


def workbuddy_oracle_binding(source_ids: set[str], command: str) -> str:
    matched = [value for value in source_ids if WORKBUDDY_CDP_SOURCE.fullmatch(value)]
    if len(matched) != 1:
        raise ValueError("WorkBuddy Oracle Case must bind exactly one versioned CDP source")
    source_match = WORKBUDDY_CDP_SOURCE.fullmatch(matched[0])
    assert source_match is not None
    expected = (
        f"{WORKBUDDY_REFERENCE_PREFIX}data/evidence/workbuddy-cdp/"
        f"{source_match.group(1).replace('-', '.')}-surfaces-v{source_match.group(2)}"
    )
    argv = shlex.split(command)
    references = [argv[index + 1] for index, value in enumerate(argv[:-1]) if value == "--workbuddy"]
    if references != [expected, expected]:
        raise ValueError("WorkBuddy Oracle source/path mismatch")
    if "&&" not in argv or argv[-1] != "--fail-on-diff":
        raise ValueError("WorkBuddy Oracle command is not fail closed")
    return expected.removeprefix(WORKBUDDY_REFERENCE_PREFIX)


def probe_loopback() -> dict[str, Any]:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", 0))
        host, port = probe.getsockname()
        return {"available": True, "host": host, "ephemeral_port": port}
    except OSError as error:
        return {
            "available": False,
            "host": "127.0.0.1",
            "error_code": error.errno,
            "error": str(error),
        }
    finally:
        probe.close()


def coordinate_requires_loopback(item_id: str, coordinate: dict[str, Any]) -> bool:
    return item_id in LOOPBACK_GATE_ITEMS or coordinate.get("category") == "deterministic-playwright"


def prepare_state(
    *,
    prior: dict[str, Any] | None,
    plan_sha256: str,
    implementation_revision: str,
    classified_coordinates: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if prior is None:
        return {
            "schema_version": 1,
            "plan_sha256": plan_sha256,
            "implementation_revision": implementation_revision,
            "coordinates": {},
        }
    if prior.get("plan_sha256") != plan_sha256:
        raise ValueError("runner state belongs to another plan")
    if prior.get("implementation_revision") != implementation_revision:
        raise ValueError("runner state belongs to another revision")
    prior_coordinates = prior.get("coordinates")
    if not isinstance(prior_coordinates, dict):
        raise ValueError("runner state coordinates must be an object")
    for item_id, value in prior_coordinates.items():
        coordinate = classified_coordinates.get(item_id)
        if coordinate is None:
            raise ValueError(f"runner state contains unknown coordinate: {item_id}")
        if not isinstance(value, dict):
            raise ValueError(f"runner coordinate must be an object: {item_id}")
        if value.get("category") != coordinate.get("category"):
            raise ValueError(f"runner coordinate category drift: {item_id}")
        if value.get("status") not in TERMINAL_COORDINATES:
            raise ValueError(f"non-terminal prior coordinates require manual audit: {item_id}")
    return json.loads(json.dumps(prior))


def validate_authority(repo: Path, plan: dict[str, Any], dataset: Path, skill: Path) -> None:
    if plan.get("plan_sha256") != plan_hash(plan):
        raise ValueError("plan_sha256 is stale or invalid")
    revision = git(repo, "rev-parse", "HEAD").strip()
    if revision != plan.get("implementation_revision") or revision != plan.get("current_checkout_revision"):
        raise ValueError("current checkout revision does not match the frozen plan")
    authority = plan.get("asset_authority", {})
    current = {
        "source_acceptance_sha256": sha256_file(dataset / "data/datasets/source-acceptance.json"),
        "source_dispositions_sha256": sha256_file(dataset / "data/datasets/source-dispositions.json"),
        "dataset_manifest_sha256": sha256_file(dataset / "data/datasets/dataset.json"),
        "dataset_tree_sha256": tree_hash(dataset),
        "project_e2e_skill_tree_sha256": tree_hash(skill),
        "route_registry_sha256": sha256_file(dataset / "references/route-registry.yaml"),
        "locator_registry_sha256": sha256_file(dataset / "references/locator-registry.yaml"),
    }
    drift = [key for key, value in current.items() if authority.get(key) != value]
    if drift:
        raise ValueError("plan authority drift; rebuild before execution: " + ", ".join(drift))


def classify(plan: dict[str, Any], cases: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    coordinates: dict[str, dict[str, Any]] = {}
    for item in plan.get("required_items", []):
        item_id = str(item.get("item_id") or "")
        if not item_id or item_id in coordinates:
            raise ValueError(f"missing or duplicate required item id: {item_id!r}")
        command = str(item.get("command") or "")
        if item.get("kind") != "case":
            if GATE_COMMANDS.get(item_id) != command:
                raise ValueError(f"unknown or drifted gate command: {item_id}")
            coordinates[item_id] = {"category": "gate", "command": command, "argv": shlex.split(command)}
            continue
        case_id = str(item.get("case_id") or "")
        case = cases.get(case_id)
        if not case:
            raise ValueError(f"plan references unknown Case: {case_id}")
        contract = case["execution_contract"]
        if item.get("revision_drift"):
            source = contract.get("observability", {}).get("source_contract") or {}
            execution_revision = source.get("execution_revision")
            if (
                command != "manual-blocked"
                or not execution_revision
                or execution_revision == plan.get("implementation_revision")
                or item.get("source_contract") != source
                or item.get("execution_readiness") != "partial"
            ):
                raise ValueError(f"invalid cross-revision runner-gap contract: {case_id}")
            coordinates[item_id] = {
                "category": "runner-gap",
                "command": command,
                "case_id": case_id,
                "reason": "execution-revision-drift",
                "execution_revision": execution_revision,
            }
            continue
        if command != str(contract["launch"].get("command_or_tool") or "manual-blocked"):
            raise ValueError(f"plan command drift for {case_id}")
        if item.get("route_id") != contract.get("route_id"):
            raise ValueError(f"plan route drift for {case_id}")
        source_ids = {str(source.get("source_id")) for source in case.get("sources", [])}
        if item.get("external_dependency_required"):
            dependency = str(item.get("external_dependency") or "")
            if (
                dependency not in {
                    "qwork_server/cmd/dev-api checkout",
                    "macOS native fullscreen GUI session",
                }
                and not dependency.startswith("platform runner:")
            ):
                raise ValueError(f"unknown external dependency contract: {case_id}")
            coordinates[item_id] = {
                "category": "external-dependency",
                "command": command,
                "case_id": case_id,
                "dependency": dependency,
            }
        elif contract["authorization"].get("required"):
            coordinates[item_id] = {"category": "live-authorization", "command": command, "case_id": case_id}
        elif contract["launch"].get("strategy") == "manual-blocked":
            coordinates[item_id] = {"category": "runner-gap", "command": command, "case_id": case_id}
        elif any(WORKBUDDY_CDP_SOURCE.fullmatch(value) for value in source_ids):
            oracle = contract["observability"].get("oracle_contract")
            if not isinstance(oracle, dict):
                raise ValueError(f"WorkBuddy Oracle Case is not fail closed: {case_id}")
            reference = workbuddy_oracle_binding(source_ids, command)
            coordinates[item_id] = {"category": "workbuddy-oracle", "command": command, "case_id": case_id, "state": str(oracle["state"]), "threshold": float(oracle["max_diff_ratio"]), "geometry_tolerance": float(oracle["geometry_tolerance_css_px"]), "workbuddy_reference": reference}
        elif str(contract["route_id"]).startswith("qwork.dataset.workbuddy-storage."):
            expected = (
                "python3 .agents/skills/qwork-test-dataset/scripts/validate_workbuddy_storage_case.py "
                f"--skill-root .agents/skills/qwork-test-dataset --case-id {case_id}"
            )
            if command != expected or source_ids != {"WORKBUDDY-STORAGE-LOCAL"}:
                raise ValueError(f"WorkBuddy storage verifier contract drift: {case_id}")
            coordinates[item_id] = {"category": "dataset-verifier", "command": command, "argv": shlex.split(command), "case_id": case_id, "artifact_name": "storage-case-result.json"}
        elif str(contract["route_id"]).startswith("qwork.dataset.structured-oracle-source."):
            expected = (
                "python3 .agents/skills/qwork-test-dataset/scripts/"
                "validate_structured_oracle_source_case.py "
                f"--repo . --skill-root .agents/skills/qwork-test-dataset --case-id {case_id}"
            )
            if command != expected or not source_ids or not all(
                value.startswith("WORKBUDDY-ORACLE-5-3-5-") for value in source_ids
            ):
                raise ValueError(f"structured Oracle source verifier contract drift: {case_id}")
            coordinates[item_id] = {
                "category": "dataset-verifier",
                "command": command,
                "argv": shlex.split(command),
                "case_id": case_id,
                "artifact_name": "structured-source-result.json",
            }
        elif str(contract["route_id"]).startswith("qwork.playwright."):
            argv = shlex.split(command)
            source = contract["observability"].get("source_contract")
            if len(argv) != 6 or argv[:3] != ["npx", "playwright", "test"] or argv[4] != "-g":
                raise ValueError(f"Playwright command is not an exact argv contract: {case_id}")
            if not isinstance(source, dict) or argv[3] != source.get("spec") or argv[5] != case["title"]:
                raise ValueError(f"Playwright command/source contract mismatch: {case_id}")
            coordinates[item_id] = {"category": "deterministic-playwright", "command": command, "argv": argv, "case_id": case_id}
        elif str(contract["route_id"]).startswith("qwork.private-playwright."):
            argv = shlex.split(command)
            source = contract["observability"].get("source_contract")
            spec = str(source.get("spec") or "") if isinstance(source, dict) else ""
            runner = (
                "run_private_team_terminal_case.mjs"
                if spec.endswith("/team-terminal-matrix.spec.ts")
                else "run_private_tool_failure_case.mjs"
                if spec.endswith("/tool-failure-causality.spec.ts")
                else "run_private_sidebar_oracle_case.mjs"
                if spec.endswith("/sidebar-account-oracle-completeness.spec.ts")
                else "run_private_shell_oracle_case.mjs"
                if spec.endswith("/shell-home-oracle-completeness.spec.ts")
                else "run_private_automation_oracle_case.mjs"
                if spec.endswith("/automation-oracle-gap-completeness.spec.ts")
                else "run_private_playwright_case.mjs"
            )
            expected_prefix = [
                "node",
                f".agents/skills/qwork-test-dataset/scripts/{runner}",
                "--repo",
                ".",
                "--case-id",
                case_id,
                "--case-title",
            ]
            if len(argv) != 8 or argv[:7] != expected_prefix or argv[7] != case["title"]:
                raise ValueError(f"private Playwright command is not an exact argv contract: {case_id}")
            if not isinstance(source, dict) or not spec.startswith(
                "skill://qwork-test-dataset/data/e2e/"
            ):
                raise ValueError(f"private Playwright source contract mismatch: {case_id}")
            coordinates[item_id] = {
                "category": "deterministic-playwright",
                "command": command,
                "argv": argv,
                "case_id": case_id,
                "private_playwright": True,
                "required_screenshot_states": item.get("required_screenshot_states", []),
            }
        elif str(contract["route_id"]).startswith("qwork.requirement."):
            argv = shlex.split(command)
            if (
                len(argv) != 6
                or argv[:3] != ["npx", "playwright", "test"]
                or argv[4] != "-g"
            ):
                raise ValueError(f"requirement Playwright contract mismatch: {case_id}")
            delegate_id = str(contract["launch"].get("delegate_case_id") or "")
            direct_source = contract["launch"].get("source_contract")
            if delegate_id and direct_source:
                raise ValueError(f"requirement Playwright contract mismatch: {case_id}")
            if delegate_id:
                delegate = cases.get(delegate_id)
                delegate_contract = (
                    delegate.get("execution_contract", {})
                    if isinstance(delegate, dict)
                    else {}
                )
                delegate_source = (
                    delegate_contract.get("observability", {}).get("source_contract")
                    or {}
                )
                valid_source = (
                    bool(delegate)
                    and str(delegate_contract.get("route_id") or "").startswith("qwork.playwright.")
                    and command == str(delegate_contract.get("launch", {}).get("command_or_tool") or "")
                    and argv[3] == delegate_source.get("spec")
                    and argv[5] == delegate.get("title")
                )
            else:
                valid_source = (
                    isinstance(direct_source, dict)
                    and argv[3] == direct_source.get("spec")
                    and argv[5] == direct_source.get("title")
                    and direct_source.get("execution_revision") == plan.get("implementation_revision")
                    and re.fullmatch(r"sha256:[0-9a-f]{64}", str(direct_source.get("body_sha256") or "")) is not None
                    and re.fullmatch(r"sha256:[0-9a-f]{64}", str(direct_source.get("spec_sha256") or "")) is not None
                )
            if not valid_source:
                raise ValueError(f"requirement Playwright contract mismatch: {case_id}")
            coordinates[item_id] = {
                "category": "deterministic-playwright",
                "command": command,
                "argv": argv,
                "case_id": case_id,
                **({"delegate_case_id": delegate_id} if delegate_id else {}),
            }
        else:
            raise ValueError(f"unclassified executable Case: {case_id}")
    return coordinates


def oracle_steps(repo: Path, run_root: Path, coordinate: dict[str, Any], dataset: Path) -> list[list[str]]:
    item_root = run_root / "items" / safe_name(str(coordinate["case_id"]))
    capture, compare = item_root / "capture", item_root / "compare"
    workbuddy = dataset / str(coordinate["workbuddy_reference"])
    return [
        ["node", str(dataset / "scripts/run_qwork_workbuddy_oracle.mjs"), str(repo), str(capture), str(coordinate["state"]), "--workbuddy", str(workbuddy)],
        [sys.executable, str(dataset / "scripts/compare_qwork_workbuddy_oracle.py"), "--capture", str(capture), "--workbuddy", str(workbuddy), "--output", str(compare), "--max-diff-ratio", str(coordinate["threshold"]), "--geometry-tolerance", str(coordinate["geometry_tolerance"]), "--fail-on-diff"],
    ]


def coordinate_steps(
    repo: Path,
    run_root: Path,
    coordinate: dict[str, Any],
    dataset: Path,
) -> tuple[list[list[str]], list[Path]]:
    if coordinate["category"] == "workbuddy-oracle":
        return oracle_steps(repo, run_root, coordinate, dataset), []
    if coordinate["category"] == "dataset-verifier":
        item_root = run_root / "items" / safe_name(str(coordinate["case_id"]))
        result_path = item_root / str(coordinate.get("artifact_name") or "storage-case-result.json")
        return [[*coordinate["argv"], "--output", str(result_path)]], [result_path]
    if coordinate.get("private_playwright"):
        private_root = (
            run_root
            / "PRIVATE-EVIDENCE"
            / private_run_namespace(run_root)
            / safe_name(str(coordinate["case_id"]))
        )
        return [[*coordinate["argv"], "--run-root", str(private_root)]], [
            private_root / "report.json",
            private_root / "build-manifest.json",
        ]
    return [coordinate["argv"]], []


def write_private_attestation(
    *, run_root: Path, coordinate: dict[str, Any], private_artifacts: list[Path]
) -> Path:
    report_path, build_manifest_path = private_artifacts
    report = load(report_path)
    build_manifest = load(build_manifest_path)
    case_id = str(coordinate["case_id"])
    if report.get("case_id") != case_id:
        raise ValueError(f"private report Case drift: {case_id}")
    if report.get("status") not in TERMINAL_COORDINATES:
        raise ValueError(f"private report has no terminal status: {case_id}")
    if report.get("zero_real_model_calls") is not True or report.get("isolated_qwork_home") is not True:
        raise ValueError(f"private report violated isolation or zero-model contract: {case_id}")
    cleanup = report.get("cleanup")
    if not isinstance(cleanup, dict) or not cleanup or not all(value is True for value in cleanup.values()):
        raise ValueError(f"private report cleanup is incomplete: {case_id}")
    evidence = report.get("evidence")
    if not isinstance(evidence, dict):
        raise ValueError(f"private report evidence is missing: {case_id}")
    if evidence.get("integrity") != "complete":
        raise ValueError(f"private report evidence integrity is incomplete: {case_id}")
    screenshots = evidence.get("screenshots")
    traces = evidence.get("traces")
    configured_states = coordinate.get("required_screenshot_states")
    required_states = (
        [str(value) for value in configured_states]
        if isinstance(configured_states, list)
        else ["entry", "transition", "final-state"]
    )
    if not isinstance(screenshots, list) or not isinstance(traces, list) or len(traces) != 1:
        raise ValueError(f"private report screenshot or trace contract failed: {case_id}")
    item_root = run_root / "items" / safe_name(case_id)
    attestation_path = item_root / "private-attestation.json"
    if attestation_path.exists():
        raise ValueError(f"private attestation already exists; audit before retry: {case_id}")
    visual_checkpoints = []
    for index, screenshot in enumerate(screenshots):
        name = Path(str(screenshot.get("path") or "")).name.lower()
        state = str(screenshot.get("state") or (
            "entry"
            if "entry" in name
            else "transition"
            if "transition" in name
            else "final-state"
            if "final" in name
            else f"checkpoint-{index + 1}"
        ))
        visual_checkpoints.append({
            "state": state,
            "sha256": str(screenshot.get("sha256") or ""),
            "caption": f"私有 Dataset 截图证明：{state}",
        })
    observed_states = {value["state"] for value in visual_checkpoints}
    if report["status"] == "pass":
        if any(state not in observed_states for state in required_states):
            raise ValueError(f"private report screenshot state contract failed: {case_id}")
    elif required_states and "assertion-failure" not in observed_states:
        raise ValueError(f"private failure evidence state contract failed: {case_id}")
    attestation = {
        "schema_version": 1,
        "case_id": case_id,
        "status": report["status"],
        "zero_real_model_calls": True,
        "isolated_qwork_home": True,
        "cleanup_complete": True,
        "source": report.get("source"),
        "implementation_revision": build_manifest.get("source_revision"),
        "private_evidence": {
            "report_sha256": sha256_file(report_path),
            "build_manifest_sha256": sha256_file(build_manifest_path),
            "screenshot_count": len(screenshots),
            "trace_count": len(traces),
            "visual_checkpoints": visual_checkpoints,
        },
    }
    atomic_json(attestation_path, attestation)
    return attestation_path


def infer_visual_state(name: str, *, failed: bool) -> str:
    lowered = name.lower()
    if "entry" in lowered:
        return "entry"
    if "transition" in lowered:
        return "transition"
    if "final" in lowered:
        return "final-state"
    if "before" in lowered:
        return "before-important-mutation"
    if "after" in lowered:
        return "after-important-mutation"
    if "test-finished" in lowered:
        return "checkpoint"
    if failed and ("fail" in lowered or "error" in lowered):
        return "assertion-failure"
    return "checkpoint"


def archive_public_playwright_evidence(
    *, repo: Path, run_root: Path, coordinate: dict[str, Any], failed: bool
) -> list[Path]:
    source_root = repo / "test-results"
    case_id = str(coordinate["case_id"])
    evidence_root = run_root / "items" / safe_name(case_id) / "evidence"
    if evidence_root.exists():
        raise ValueError(f"public Playwright evidence already exists; audit before retry: {case_id}")
    evidence_root.mkdir(parents=True)
    entries: list[dict[str, Any]] = []
    copied: list[Path] = []
    if source_root.is_dir():
        for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
            relative = source.relative_to(source_root)
            target = evidence_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(target)
            suffix = target.suffix.lower()
            kind = "screenshot" if suffix in {".png", ".jpg", ".jpeg", ".webp"} else "trace" if target.name == "trace.zip" else "artifact"
            entry: dict[str, Any] = {
                "path": str(target.relative_to(run_root)),
                "sha256": sha256_file(target),
                "kind": kind,
            }
            if kind == "screenshot":
                entry["state"] = infer_visual_state(target.name, failed=failed)
                entry["caption"] = f"{case_id} · {entry['state']}"
            entries.append(entry)
    manifest_path = evidence_root.parent / "evidence-manifest.json"
    atomic_json(manifest_path, {
        "schema_version": 1,
        "case_id": case_id,
        "status": "fail" if failed else "pass",
        "entries": entries,
    })
    return [manifest_path, *copied]


def execute_coordinate(repo: Path, run_root: Path, item_id: str, coordinate: dict[str, Any], dataset: Path) -> dict[str, Any]:
    log_root = run_root / "logs"
    log_root.mkdir(parents=True, exist_ok=True)
    stdout_path = log_root / f"{safe_name(item_id)}.stdout.log"
    stderr_path = log_root / f"{safe_name(item_id)}.stderr.log"
    if stdout_path.exists() or stderr_path.exists():
        raise ValueError(f"evidence already exists for pending coordinate {item_id}; audit before retry")
    steps, expected_artifacts = coordinate_steps(repo, run_root, coordinate, dataset)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    outputs: list[str] = []
    errors: list[str] = []
    exit_code = 0
    for argv in steps:
        environment = os.environ.copy()
        if coordinate.get("category") == "deterministic-playwright" and not coordinate.get("private_playwright"):
            environment["QWORK_RELEASE_GATE_EVIDENCE_DIR"] = str(
                repo / "test-results" / "release-gate-capture"
            )
            environment["UI_EVIDENCE_DIR"] = str(
                repo / "test-results" / "release-gate-capture" / "checkpoints"
            )
            server_dir = resolve_qwork_server_dir(repo)
            if server_dir:
                environment["QWORK_SERVER_DIR"] = str(server_dir)
        result = subprocess.run(
            argv,
            cwd=repo,
            text=True,
            capture_output=True,
            env=environment,
        )
        outputs.append(result.stdout)
        errors.append(result.stderr)
        exit_code = result.returncode
        if (
            not exit_code
            and coordinate.get("category") == "deterministic-playwright"
            and re.search(r"(?m)^\s*\d+\s+skipped\s*$", result.stdout)
        ):
            exit_code = 78
            errors.append("release gate forbids a selected Playwright test from reporting skipped\n")
        if exit_code:
            break
    missing_artifacts = [path for path in expected_artifacts if not path.is_file()]
    stdout_path.write_text("".join(outputs), encoding="utf-8")
    stderr_path.write_text("".join(errors), encoding="utf-8")
    if missing_artifacts:
        raise ValueError(
            "coordinate did not produce required evidence: "
            + ", ".join(str(path.relative_to(run_root)) for path in missing_artifacts)
        )
    if coordinate.get("private_playwright"):
        attestation_path = write_private_attestation(
            run_root=run_root,
            coordinate=coordinate,
            private_artifacts=expected_artifacts,
        )
        expected_artifacts = [attestation_path]
    elif coordinate.get("category") == "deterministic-playwright":
        expected_artifacts = archive_public_playwright_evidence(
            repo=repo,
            run_root=run_root,
            coordinate=coordinate,
            failed=exit_code != 0,
        )
    return {
        "status": "pass" if exit_code == 0 else "fail",
        "exit_code": exit_code,
        "started_at": started,
        "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stdout": str(stdout_path.relative_to(run_root)),
        "stdout_sha256": sha256_file(stdout_path),
        "stderr": str(stderr_path.relative_to(run_root)),
        "stderr_sha256": sha256_file(stderr_path),
        "artifacts": [
            {
                "path": str(path.relative_to(run_root)),
                "sha256": sha256_file(path),
            }
            for path in expected_artifacts
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--dataset-skill", type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--category", action="append", choices=sorted(LOCAL_CATEGORIES))
    parser.add_argument("--item-id", action="append")
    args = parser.parse_args()
    repo, plan_path = args.repo.resolve(), args.plan.resolve()
    dataset = (args.dataset_skill or repo / ".agents/skills/qwork-test-dataset").resolve()
    skill = Path(__file__).resolve().parent.parent
    run_root = validate_external_run_root(
        args.run_root,
        protected_roots=[repo, dataset, skill],
    )
    plan = load(plan_path)
    validate_authority(repo, plan, dataset, skill)
    cases = {path.stem: load(path) for path in sorted((dataset / "data/datasets/cases").glob("*.json"))}
    coordinates = classify(plan, cases)
    state_path = run_root / "runner-state.json"
    prior_state = load(state_path) if state_path.exists() else None
    state = prepare_state(
        prior=prior_state,
        plan_sha256=str(plan["plan_sha256"]),
        implementation_revision=str(plan["implementation_revision"]),
        classified_coordinates=coordinates,
    )
    summary: dict[str, int] = {}
    for coordinate in coordinates.values():
        category = str(coordinate["category"])
        summary[category] = summary.get(category, 0) + 1
    loopback = probe_loopback()
    server_dir = resolve_qwork_server_dir(repo)
    preflight = {"schema_version": 1, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "plan_sha256": plan["plan_sha256"], "implementation_revision": plan["implementation_revision"], "required_item_count": len(coordinates), "classification": dict(sorted(summary.items())), "environment_capabilities": {"loopback_bind": loopback, "qwork_dev_api": {"available": server_dir is not None, "path": str(server_dir) if server_dir else None}}, "live_execution_allowed": False, "shell_evaluation_allowed": False, "planned_local_execution_count": sum(summary.get(value, 0) for value in LOCAL_CATEGORIES), "executed_count": 0}
    atomic_json(run_root / "execution-preflight.json", preflight)
    if args.preflight_only or not args.category:
        print(json.dumps({"status": "ok", **preflight}, ensure_ascii=False))
        return 0
    requested, selected_ids = set(args.category), set(args.item_id or coordinates)
    selected = {
        item_id: coordinate
        for item_id, coordinate in coordinates.items()
        if item_id in selected_ids and coordinate["category"] in requested
    }
    if not loopback["available"]:
        blocked = [
            item_id
            for item_id, coordinate in selected.items()
            if coordinate_requires_loopback(item_id, coordinate)
        ]
        if blocked:
            raise RuntimeError(
                "loopback bind capability is required before execution; "
                f"zero coordinates executed; blocked: {', '.join(blocked[:20])}"
            )
    atomic_json(state_path, state)
    for item_id, coordinate in coordinates.items():
        if item_id not in selected_ids or coordinate["category"] not in requested:
            continue
        if item_id in state["coordinates"]:
            continue
        state["coordinates"][item_id] = {"category": coordinate["category"], "status": "running", "started_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        atomic_json(state_path, state)
        try:
            result = execute_coordinate(repo, run_root, item_id, coordinate, dataset)
        except BaseException as error:
            state["coordinates"][item_id].update({"status": "partial", "error": str(error)})
            atomic_json(state_path, state)
            raise
        state["coordinates"][item_id].update(result)
        atomic_json(state_path, state)
    failed = sum(value["status"] == "fail" for value in state["coordinates"].values())
    print(json.dumps({"status": "ok" if not failed else "fail", "executed": len(state["coordinates"]), "failed": failed, "state": str(state_path)}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
