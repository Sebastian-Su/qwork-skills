#!/usr/bin/env python3
"""Build a fail-closed QWork E2E plan from an explicit base/head and private Dataset."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from external_artifact_storage import REPORT_JSON_NAME, validate_external_run_root


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(payload)


def tree_hash(root: Path, *, ignored_names: set[str] | None = None) -> tuple[str, list[dict[str, Any]]]:
    ignored_names = ignored_names or {"__pycache__", ".DS_Store"}
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if (
            not path.is_file()
            or any(part in ignored_names for part in relative.parts)
            or relative.parts[:2] == ("data", "runs")
        ):
            continue
        entries.append({"path": relative.as_posix(), "sha256": sha256_file(path), "size": path.stat().st_size})
    return canonical_hash({"files": entries}), entries


def status_entries(repo: Path) -> list[dict[str, Any]]:
    raw = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    parts = raw.split("\0")
    entries: list[dict[str, Any]] = []
    index = 0
    while index < len(parts):
        record = parts[index]
        index += 1
        if not record:
            continue
        status, path_value = record[:2], record[3:]
        original = None
        if status[0] in "RC" or status[1] in "RC":
            original = path_value
            if index < len(parts):
                path_value = parts[index]
                index += 1
        path = repo / path_value
        entries.append({
            "status": status,
            "path": path_value,
            "original_path": original,
            "sha256": sha256_file(path) if path.is_file() else "deleted-or-non-file",
        })
    return sorted(entries, key=lambda item: (item["path"], item["status"]))


def changed_files(repo: Path, base: str, head: str, dirty: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paths = set(git(repo, "diff", "--name-only", "--diff-filter=ACDMRTUXB", f"{base}...{head}").splitlines())
    paths.update(str(item["path"]) for item in dirty)
    result = []
    for value in sorted(path for path in paths if path):
        current = repo / value
        if current.is_file():
            digest = sha256_file(current)
        else:
            blob = git(repo, "show", f"{head}:{value}", check=False)
            digest = sha256_bytes(blob.encode()) if blob else "deleted"
        result.append({"path": value, "content_sha256": digest})
    return result


def source_path(source: dict[str, Any]) -> str | None:
    locator = str(source.get("locator") or "")
    if locator.startswith("git:"):
        parts = locator.split(":", 2)
        return parts[2] if len(parts) == 3 else None
    return None


def infer_surface(path: str, changed_content: str = "") -> str | None:
    lower_content = changed_content.lower()
    if any(
        marker in lower_content
        for marker in (
            "autocompactenabled",
            "max 模式",
            "max-mode",
            "qwork_e2e_model_menu_",
        )
    ):
        return "models"
    rules = {
        "auth": ("auth", "login", "account"),
        "assistant": ("assistant", "conversation", "session", "chat"),
        "task-lifecycle": ("task", "sidecar", "protocol", "stream"),
        "expert-market": ("expert", "plugin", "market"),
        "expert-team": ("team", "subagent"),
        "skills": ("skill",),
        "connectors": ("connector", "oauth", "mcp"),
        "projects": ("project", "workspace"),
        "automations": ("automation", "schedule"),
        "files": ("file", "artifact", "attachment"),
        "browser": ("browser",),
        "terminal": ("terminal", "pty"),
        "models": ("model", "llm", "provider", "auto", "max", "custom"),
        "media-generation": (
            "imagegen",
            "videogen",
            "media_progress",
            "built-in-media-generation",
            "qworkapicredentialbroker",
            "qwork_api_credentials",
            "product media",
        ),
        "permissions": ("permission", "security", "sandbox"),
        "settings": ("setting", "config"),
        "im": ("im/", "wecom", "message"),
        "window-runtime": ("window", "tray", "startup", "runtime"),
        "persistence": ("repository", "storage", "database", "persist"),
    }
    def score(value: str) -> str | None:
        lower = value.lower()
        matches = [
            (surface, sum(lower.count(token) for token in tokens))
            for surface, tokens in rules.items()
        ]
        surface, total = max(matches, key=lambda item: item[1])
        return surface if total else None

    # Generic integration files such as shared/api.ts and preload/index.ts do
    # not carry a useful domain in their path. Prefer the actual changed lines
    # so an affected plan selects the touched capability instead of silently
    # expanding to the entire product. New files fall back to their basename,
    # then their content and full path.
    return (
        score(changed_content)
        or score(Path(path).name)
        or score(path)
    )


def gate_only_item_ids(path: str, content: str) -> list[str]:
    if path.startswith("docs/team-collaboration/changes/") or path == "docs/team-collaboration/interface-ledger.md":
        return ["gate:source-dispositions"]
    if path == "vitest.config.ts":
        return ["gate:coverage"]
    if path == "playwright.config.ts":
        return ["gate:electron-build"] if "QWORK_RELEASE_GATE_EVIDENCE_DIR" in content else []
    if path == "e2e/fixtures/launch.ts":
        return ["gate:electron-build"] if (
            "QWORK_RELEASE_GATE_EVIDENCE_DIR" in content
            and "captureReleaseGateState" in content
        ) else []
    return []


SEMANTIC_ANCHOR = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"[a-z][a-z0-9]*(?:_[a-z0-9]+){2,}|"
    r"[a-z][A-Za-z0-9]{19,}|"
    r"[a-z][a-z0-9]*(?:-[a-z0-9]+){2,}"
    r")(?![A-Za-z0-9])"
)


def infer_unique_semantic_cases(
    case_files: dict[str, dict[str, Any]], changed_content: str
) -> tuple[list[str], list[str]]:
    """Bind a change to the Case that uniquely owns its high-signal contract atoms.

    Paths such as shared protocol or a provider live test are deliberately
    generic. Long protocol identifiers and explicit Oracle field names are a
    stronger causal coordinate than broad words such as session/model/expert.
    Only anchors occurring in exactly one Case are eligible, and only the
    highest-scoring Case(s) are retained so an adjacent helper name cannot
    broaden the affected closure.
    """
    changed_anchors = set(SEMANTIC_ANCHOR.findall(changed_content))
    if not changed_anchors:
        return [], []
    owners: dict[str, set[str]] = {}
    for case_id, case in case_files.items():
        serialized = json.dumps(case, ensure_ascii=False, sort_keys=True)
        for anchor in changed_anchors & set(SEMANTIC_ANCHOR.findall(serialized)):
            owners.setdefault(anchor, set()).add(case_id)
    unique = {
        anchor: next(iter(case_ids))
        for anchor, case_ids in owners.items()
        if len(case_ids) == 1
    }
    if not unique:
        return [], []
    scores: dict[str, int] = {}
    for case_id in unique.values():
        scores[case_id] = scores.get(case_id, 0) + 1
    best = max(scores.values())
    selected = sorted(case_id for case_id, score in scores.items() if score == best)
    anchors = sorted(anchor for anchor, case_id in unique.items() if case_id in selected)
    return selected, anchors


def qwork_server_available(repo: Path) -> bool:
    candidates: list[Path] = []
    override = os.environ.get("QWORK_SERVER_DIR", "").strip()
    if override:
        candidates.append(Path(override).expanduser())
    common_git = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    main_checkout = common_git.parent if common_git.name == ".git" else common_git
    candidates.append(main_checkout.parent / "qwork_server")
    return any((candidate.resolve() / "cmd/dev-api").is_dir() for candidate in candidates)


def case_requires_qwork_server(repo: Path, case: dict[str, Any]) -> bool:
    source = (
        case.get("execution_contract", {})
        .get("observability", {})
        .get("source_contract")
        or {}
    )
    spec = str(source.get("spec") or "")
    if not spec or spec.startswith("skill://"):
        return False
    path = repo / spec
    if not path.is_file():
        return False
    content = path.read_text(encoding="utf-8")
    return "canRunDevApi(" in content and "startDevApi(" in content


def case_requires_macos_native_fullscreen(case: dict[str, Any]) -> bool:
    source = (
        case.get("execution_contract", {})
        .get("observability", {})
        .get("source_contract")
        or {}
    )
    return (
        str(source.get("spec") or "") == "e2e/ui-layout-native-window.spec.ts"
        and "macOS 原生全屏" in str(case.get("title") or "")
    )


def infer_executable_capability_cases(
    case_files: dict[str, dict[str, Any]], surface: str
) -> tuple[list[str], list[str], list[str]]:
    """Keep broad capability inference causal by requiring an executable route.

    A source-exact match remains fail-closed even when its route is missing. A
    capability label alone is weaker evidence: importing every historical
    manual gap makes an unrelated implementation change appear to own it.
    """
    selected: list[str] = []
    excluded_manual_gaps: list[str] = []
    excluded_noncausal: list[str] = []
    for case_id, case in case_files.items():
        if case.get("coverage", {}).get("capability_id") != surface:
            continue
        strategy = (
            case.get("execution_contract", {}).get("launch", {}).get("strategy")
        )
        if strategy == "manual-blocked":
            excluded_manual_gaps.append(case_id)
        elif (
            (
                case.get("execution_contract", {})
                .get("observability", {})
                .get("source_contract")
                or {}
            )
            .get("action_count") == 0
            and not (case.get("ui_acceptance") or {}).get("required_screenshot_states")
        ) or (
            surface == "models"
            and (
                any(
                    marker in str(case.get("title") or "").lower()
                    for marker in (
                        "并发",
                        "concurrency",
                        "tpm",
                        "rate limit",
                        "限流",
                        "首事件超时",
                        "first event timeout",
                    )
                )
                or str(
                    (
                        case.get("execution_contract", {})
                        .get("observability", {})
                        .get("source_contract")
                        or {}
                    )
                    .get("spec") or ""
                ).endswith("/expert-model-concurrency-contract.spec.ts")
            )
        ):
            excluded_noncausal.append(case_id)
        else:
            selected.append(case_id)
    return (
        sorted(selected),
        sorted(excluded_manual_gaps),
        sorted(excluded_noncausal),
    )


def partition_exact_cases(
    case_files: dict[str, dict[str, Any]],
    exact_case_ids: list[str],
    *,
    head: str,
    path: str,
    current_content: str,
) -> tuple[list[str], list[str]]:
    """Drop only historical coordinates whose title no longer exists in HEAD."""
    retained: list[str] = []
    superseded: list[str] = []
    for case_id in exact_case_ids:
        case = case_files[case_id]
        source = (
            case.get("execution_contract", {})
            .get("observability", {})
            .get("source_contract", {})
        ) or {}
        historical_same_spec = (
            source.get("spec") == path
            and source.get("execution_revision")
            and source.get("execution_revision") != head
        )
        if historical_same_spec and str(case.get("title") or "") not in current_content:
            superseded.append(case_id)
        else:
            retained.append(case_id)
    return sorted(retained), sorted(superseded)


def changed_content(repo: Path, base: str, path: str) -> str:
    result = subprocess.run(
        ["git", "diff", "--unified=0", base, "--", path],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        return ""
    changed = "\n".join(
        line[1:]
        for line in result.stdout.splitlines()
        if line.startswith(("+", "-"))
        and not line.startswith(("+++", "---"))
    )
    if changed:
        return changed
    current = repo / path
    if current.is_file():
        try:
            return current.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ""
    return ""


def result_item(item_id: str, kind: str, command: str, layer: str, dimensions: list[str], **extra: Any) -> dict[str, Any]:
    return {"item_id": item_id, "kind": kind, "required": True, "command": command, "layer": layer, "dimensions": dimensions, **extra}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--scope", choices=("affected", "full"), default="affected")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-skill", type=Path)
    args = parser.parse_args()

    repo = args.repo.resolve()
    base = git(repo, "rev-parse", args.base).strip()
    head = git(repo, "rev-parse", args.head).strip()
    dataset_root = (args.dataset_skill or repo / ".agents/skills/qwork-test-dataset").resolve()
    project_skill = Path(__file__).resolve().parent.parent
    manifest_path = dataset_root / "data/datasets/source-acceptance.json"
    dataset_path = dataset_root / "data/datasets/dataset.json"
    disposition_path = dataset_root / "data/datasets/source-dispositions.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = {str(item["case_id"]): item for item in manifest["cases"]}
    case_files = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in sorted((dataset_root / "data/datasets/cases").glob("*.json"))}
    full_ids = [str(value) for value in manifest["suite_index"]["full_case_ids"]]
    if set(full_ids) != set(cases) or set(full_ids) != set(case_files):
        raise RuntimeError("Dataset closed-world mismatch: manifest, index and Case files differ")

    requirement_cases = {str(key): [str(value) for value in values] for key, values in manifest["suite_index"]["requirement_to_cases"].items()}
    source_by_id = {str(source["source_id"]): source for source in manifest["sources"]}
    path_cases: dict[str, set[str]] = {}
    for requirement in manifest["requirements"]:
        bound = set(requirement_cases.get(str(requirement["requirement_id"]), []))
        for atom in requirement.get("source_atoms", []):
            source = source_by_id.get(str(atom.get("source_id")))
            path = source_path(source or {})
            if path:
                path_cases.setdefault(path, set()).update(bound)

    dirty = status_entries(repo)
    changed = changed_files(repo, base, head, dirty)
    selected: set[str] = set()
    mappings: list[dict[str, Any]] = []
    inferred_manual_gaps: dict[str, set[str]] = {}
    inferred_noncausal: dict[str, set[str]] = {}
    superseded_exact_cases: dict[str, set[str]] = {}
    gate_only_changes: list[str] = []
    conservative_full = args.scope == "full"
    for change in changed:
        path = str(change["path"])
        content = changed_content(repo, base, path)
        gate_items = gate_only_item_ids(path, content)
        if gate_items:
            gate_only_changes.append(path)
            mappings.append({"changed_file": path, "strategy": "gate-only", "gate_item_ids": gate_items, "case_ids": []})
            continue
        exact = sorted(path_cases.get(path, set()))
        if exact:
            current_content = git(repo, "show", f"{head}:{path}", check=False)
            retained, superseded = partition_exact_cases(
                case_files,
                exact,
                head=head,
                path=path,
                current_content=current_content,
            )
            if not retained:
                retained = exact
                superseded = []
            selected.update(retained)
            if superseded:
                superseded_exact_cases.setdefault(path, set()).update(superseded)
            mappings.append({"changed_file": path, "strategy": "source-atom-exact", "case_ids": retained, "superseded_case_ids": superseded})
            continue
        semantic, anchors = infer_unique_semantic_cases(case_files, content)
        if semantic:
            selected.update(semantic)
            mappings.append({"changed_file": path, "strategy": "unique-semantic-anchor", "anchors": anchors, "case_ids": semantic})
            continue
        surface = infer_surface(path, content)
        inferred, manual_gaps, noncausal = (
            infer_executable_capability_cases(case_files, surface)
            if surface
            else ([], [], [])
        )
        if inferred:
            selected.update(inferred)
            if manual_gaps:
                inferred_manual_gaps.setdefault(str(surface), set()).update(manual_gaps)
            if noncausal:
                inferred_noncausal.setdefault(str(surface), set()).update(noncausal)
            mappings.append({"changed_file": path, "strategy": "implementation-surface-executable", "surface": surface, "case_ids": inferred, "excluded_manual_gap_case_ids": manual_gaps, "excluded_noncausal_case_ids": noncausal})
            continue
        conservative_full = True
        mappings.append({"changed_file": path, "strategy": "unknown-change-select-full", "case_ids": full_ids})

    if not conservative_full:
        selected.difference_update(
            case_id
            for case_ids in superseded_exact_cases.values()
            for case_id in case_ids
        )
    if conservative_full or not changed:
        selected = set(full_ids)
    selected_ids = sorted(selected)
    dataset_hash, dataset_files = tree_hash(dataset_root)
    skill_hash, skill_files = tree_hash(project_skill)
    route_hash = sha256_file(dataset_root / "references/route-registry.yaml")
    locator_hash = sha256_file(dataset_root / "references/locator-registry.yaml")

    required_items = [
        result_item("gate:source-acceptance", "source-atom", "python3 .agents/skills/qwork-test-e2e/scripts/validate_source_acceptance.py --repo . --manifest skill://qwork-test-dataset/data/datasets/source-acceptance.json", "static-architecture-type-lint", ["ui-structure-content-state", "ui-geometry-visual-responsive"]),
        result_item("gate:source-dispositions", "source-atom", "python3 .agents/skills/qwork-test-dataset/scripts/validate_source_dispositions.py --repo . --manifest skill://qwork-test-dataset/data/datasets/source-dispositions.json", "static-architecture-type-lint", ["historical-badcase-goodcase", "observability-correlation"]),
        result_item("gate:route-registry", "route", "python3 .agents/skills/qwork-test-dataset/scripts/validate_route_registry.py --repo . --skill-root .agents/skills/qwork-test-dataset", "real-user-path-e2e", ["ui-interaction-accessibility", "observability-correlation"]),
        result_item("gate:dataset-private-storage", "dataset-cohort", "python3 .agents/skills/qwork-test-dataset/scripts/validate_private_storage.py --repo . --skill qwork-test-dataset --path .agents/skills/qwork-test-dataset/data/datasets/source-acceptance.json", "dataset-benchmark-evaluation", ["cleanup-isolation", "permission-security"]),
        result_item("gate:dataset-schema", "dataset-cohort", "node .agents/skills/qwork-test-dataset/scripts/validate_cases_ajv.mjs", "dataset-benchmark-evaluation", ["happy-path", "negative", "boundary"]),
        result_item("gate:document-case-coverage", "source-atom", "python3 .agents/skills/qwork-test-dataset/scripts/test_document_case_coverage.py --skill-root .agents/skills/qwork-test-dataset", "dataset-benchmark-evaluation", ["ui-structure-content-state", "observability-correlation"]),
        result_item("gate:structured-oracle-coverage", "source-atom", "python3 .agents/skills/qwork-test-dataset/scripts/test_structured_oracle_coverage.py --skill-root .agents/skills/qwork-test-dataset", "dataset-benchmark-evaluation", ["ui-geometry-visual-responsive", "observability-correlation"]),
        result_item("gate:workbuddy-interaction-inventory", "source-atom", "python3 .agents/skills/qwork-test-dataset/scripts/validate_workbuddy_interaction_inventory.py --skill-root .agents/skills/qwork-test-dataset", "dataset-benchmark-evaluation", ["ui-interaction-accessibility", "observability-correlation"]),
        result_item("gate:live-case-authorization", "authorization", "python3 .agents/skills/qwork-test-dataset/scripts/test_live_case_authorization.py --skill-root .agents/skills/qwork-test-dataset", "permission-security", ["permission-security", "role-tenant-platform-environment-version"]),
        result_item("gate:typecheck", "layer", "npm run typecheck", "static-architecture-type-lint", ["role-tenant-platform-environment-version"]),
        result_item("gate:unit-integration", "layer", "npm test", "unit", ["happy-path", "negative", "boundary", "empty-loading-error"]),
        result_item("gate:coverage", "dimension", "npm run test:coverage -- --coverage.thresholds.autoUpdate=false", "regression", ["historical-badcase-goodcase"]),
        result_item("gate:electron-build", "execution-target", "npx electron-vite build", "contract-api-event-protocol", ["ui-api-event-persistence-seams"]),
    ]
    has_qwork_server = qwork_server_available(repo)
    current_platform = {"Darwin": "darwin", "Linux": "linux", "Windows_NT": "win32"}.get(os.uname().sysname, os.uname().sysname.lower())
    native_fullscreen_unavailable = os.environ.get(
        "QWORK_MACOS_NATIVE_FULLSCREEN_AVAILABLE", ""
    ).strip().lower() in {"0", "false", "no"}
    for case_id in selected_ids:
        case = case_files[case_id]
        execution = case["execution_contract"]
        source_contract = execution.get("observability", {}).get("source_contract") or {}
        execution_revision = source_contract.get("execution_revision")
        revision_drift = bool(execution_revision and execution_revision != head)
        command = (
            "manual-blocked"
            if revision_drift
            else str(execution["launch"].get("command_or_tool") or "manual-blocked")
        )
        target_platforms = list(execution.get("target", {}).get("platforms") or [])
        external_dependency = None
        if not revision_drift and target_platforms and current_platform not in target_platforms:
            external_dependency = f"platform runner: {','.join(target_platforms)}"
        elif (
            not revision_drift
            and current_platform == "darwin"
            and native_fullscreen_unavailable
            and case_requires_macos_native_fullscreen(case)
        ):
            external_dependency = "macOS native fullscreen GUI session"
        elif not revision_drift and not has_qwork_server and case_requires_qwork_server(repo, case):
            external_dependency = "qwork_server/cmd/dev-api checkout"
        external_dependency_required = external_dependency is not None
        required_items.append(result_item(
            f"case:{case_id}", "case", command,
            "real-user-path-e2e", list(case["selection"]["categories"]), case_id=case_id,
            route_id=execution["route_id"],
            execution_readiness=("partial" if revision_drift else execution["readiness"]),
            reference_run_status=execution["reference_run"]["status"],
            reference_run_id=execution["reference_run"].get("run_id"),
            authorization_required=bool(execution.get("authorization", {}).get("required")),
            external_dependency_required=external_dependency_required,
            external_dependency=external_dependency,
            target_platforms=target_platforms,
            required_screenshot_states=case.get("ui_acceptance", {}).get("required_screenshot_states", []),
            source_contract=source_contract or None,
            revision_drift=revision_drift,
            blockers=(
                [
                    f"Case executable belongs to {execution_revision}, not current implementation {head}",
                    "merge or check out the frozen executable revision before running this coordinate",
                ]
                if revision_drift
                else (
                    (
                        [
                            f"current platform {current_platform} is outside Case target platforms {target_platforms}",
                            "run this exact Case on a declared target platform",
                        ]
                        if external_dependency and external_dependency.startswith("platform runner:")
                        else (
                            [
                                "current macOS GUI session did not emit enter-full-screen after repeated isolated probes",
                                "rerun this exact Case in a fresh interactive macOS GUI session",
                            ]
                            if external_dependency == "macOS native fullscreen GUI session"
                            else [
                            "qwork_server/cmd/dev-api checkout is unavailable in this environment",
                            "provide QWORK_SERVER_DIR or restore the documented sibling checkout",
                            ]
                        )
                    )
                    if external_dependency_required
                    else list(execution.get("blockers") or [])
                )
            ),
        ))

    plan: dict[str, Any] = {
        "schema_version": 1,
        "project": "qwork",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "scope": args.scope,
        "closure_algorithm": "least-fixed-point",
        "base_revision": base,
        "implementation_revision": head,
        "current_checkout_revision": git(repo, "rev-parse", "HEAD").strip(),
        "dirty_entries": dirty,
        "changed_file_hashes": changed,
        "change_mappings": mappings,
        "conservative_full_expansion": conservative_full,
        "selected_case_ids": selected_ids,
        "required_items": required_items,
        "not_applicable": [
            {
                "kind": "capability-only-noncausal-case",
                "surface": surface,
                "case_ids": sorted(case_ids),
                "reason": "These Cases are assertion-only without UI evidence or belong to an adjacent concurrency/rate-limit domain. A broad capability label alone cannot establish impact; an exact changed source coordinate remains fail-closed.",
            }
            for surface, case_ids in sorted(inferred_noncausal.items())
        ] + [
            {
                "kind": "capability-only-manual-gap",
                "surface": surface,
                "case_ids": sorted(case_ids),
                "reason": "No changed source atom maps to these Cases and broad capability inference alone cannot establish ownership of a pre-existing manual route gap.",
            }
            for surface, case_ids in sorted(inferred_manual_gaps.items())
        ] + [
            {
                "kind": "superseded-source-coordinate",
                "path": path,
                "case_ids": sorted(case_ids),
                "reason": "The historical test title no longer exists in the current HEAD version of the same spec; the current HEAD source-exact Case is required instead.",
            }
            for path, case_ids in sorted(superseded_exact_cases.items())
        ] + [
            {
                "kind": "gate-only-change",
                "path": path,
                "gate_item_ids": gate_only_item_ids(path, changed_content(repo, base, path)),
                "reason": "This governance, coverage or execution-harness file is verified by its mandatory gate and does not independently broaden the product capability closure.",
            }
            for path in sorted(gate_only_changes)
        ],
        "asset_authority": {
            "source_acceptance_manifest": "skill://qwork-test-dataset/data/datasets/source-acceptance.json",
            "source_acceptance_sha256": sha256_file(manifest_path),
            "source_dispositions_sha256": sha256_file(disposition_path),
            "dataset_manifest_sha256": sha256_file(dataset_path),
            "dataset_tree_sha256": dataset_hash,
            "project_e2e_skill_tree_sha256": skill_hash,
            "route_registry_sha256": route_hash,
            "locator_registry_sha256": locator_hash,
            "dataset_file_count": len(dataset_files),
            "project_skill_file_count": len(skill_files),
        },
        "environment": {"platform": os.uname().sysname, "machine": os.uname().machine, "python": os.sys.version.split()[0]},
        "execution_contract": {
            "result_statuses": ["pass", "fail", "external-blocked"],
            "skip_and_known_gap_are_forbidden": True,
            "all_required_item_ids_must_be_unique": True,
            "cleanup_required": True,
            "independent_fresh_context_rerun_required": True,
            "report_json": f"<run-root>/{REPORT_JSON_NAME}",
        },
        "checkpoint": {
            "current_implementation_revision": head,
            "current_plan_hash": None,
            "first_trusted_failure": None,
            "repair_required_next_action": f"execute every required item and write current machine evidence into the canonical {REPORT_JSON_NAME}",
            "cleanup_status": "pending",
            "independent_rerun_status": "pending",
            "final_response_allowed": False,
        },
    }
    plan["plan_sha256"] = canonical_hash(plan)
    plan["checkpoint"]["current_plan_hash"] = plan["plan_sha256"]
    # Hash the final object with plan_sha256 and current_plan_hash intentionally excluded during verification.
    output_root = validate_external_run_root(
        args.output.parent,
        protected_roots=[repo, dataset_root, project_skill],
    )
    output_root.mkdir(parents=True, exist_ok=True)
    output = output_root / args.output.name
    output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "plan": str(output), "plan_sha256": plan["plan_sha256"], "selected_cases": len(selected_ids), "required_items": len(required_items), "conservative_full_expansion": conservative_full}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
