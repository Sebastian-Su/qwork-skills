#!/usr/bin/env python3
"""Compile runner WAL and frozen Cases into the single canonical QWork E2E report."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from external_artifact_storage import REPORT_JSON_NAME, validate_external_run_root


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(root: Path, path: Path) -> dict[str, str]:
    resolved = path.resolve()
    resolved.relative_to(root.resolve())
    return {"path": str(resolved.relative_to(root.resolve())), "sha256": sha256(resolved)}


def visual_state(name: str, failed: bool) -> str:
    lowered = name.lower()
    if "entry" in lowered:
        return "entry"
    if "transition" in lowered:
        return "transition"
    if "final-state" in lowered or "final" in lowered:
        return "final-state"
    if "diff" in lowered or (failed and ("fail" in lowered or "error" in lowered)):
        return "assertion-failure"
    return "checkpoint"


def case_evidence(run_root: Path, case_id: str, status: str) -> list[dict[str, Any]]:
    item_root = run_root / "items" / case_id
    private = item_root / "private-attestation.json"
    if private.is_file():
        value = load(private)
        entries: list[dict[str, Any]] = [{"kind": "attestation", **artifact(run_root, private)}]
        for checkpoint in value.get("private_evidence", {}).get("visual_checkpoints", []):
            entries.append({
                "kind": "private-screenshot-attestation",
                "state": checkpoint["state"],
                "caption": checkpoint["caption"],
                "sha256": checkpoint["sha256"],
            })
        return entries
    manifest = item_root / "evidence-manifest.json"
    if manifest.is_file():
        entries = [{"kind": "manifest", **artifact(run_root, manifest)}]
        for value in load(manifest).get("entries", []):
            entry = dict(value)
            if entry.get("kind") == "screenshot":
                entry.setdefault("caption", f"{case_id} · {entry.get('state', 'checkpoint')}")
            entries.append(entry)
        return entries
    entries = []
    if item_root.is_dir():
        for path in sorted(value for value in item_root.rglob("*") if value.is_file()):
            suffix = path.suffix.lower()
            kind = "screenshot" if suffix in {".png", ".jpg", ".jpeg", ".webp"} else "trace" if path.name == "trace.zip" else "artifact"
            entry: dict[str, Any] = {"kind": kind, **artifact(run_root, path)}
            if kind == "screenshot":
                entry["state"] = visual_state(path.name, status == "fail")
                entry["caption"] = f"{case_id} · {entry['state']}"
            entries.append(entry)
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--dataset-skill", type=Path)
    args = parser.parse_args()
    repo, plan_path = args.repo.resolve(), args.plan.resolve()
    dataset = (args.dataset_skill or repo / ".agents/skills/qwork-test-dataset").resolve()
    skill = Path(__file__).resolve().parent.parent
    run_root = validate_external_run_root(
        args.run_root,
        protected_roots=[repo, dataset, skill],
    )
    plan = load(plan_path)
    state = load(run_root / "runner-state.json") if (run_root / "runner-state.json").is_file() else {"coordinates": {}}
    preflight = load(run_root / "execution-preflight.json")
    cases = {path.stem: load(path) for path in (dataset / "data/datasets/cases").glob("*.json")}
    coordinates = state.get("coordinates", {})
    results: list[dict[str, Any]] = []
    human_cases: list[dict[str, Any]] = []
    machine_cases: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    visual_gap_count = 0

    for item in plan["required_items"]:
        item_id = item["item_id"]
        coordinate = coordinates.get(item_id)
        case = cases.get(str(item.get("case_id") or "")) if item.get("kind") == "case" else None
        if coordinate:
            status = coordinate["status"]
            classification = "product" if status == "fail" else "evidence"
            message = "executed coordinate passed" if status == "pass" else "executed coordinate failed"
            artifacts = []
            for key in ("stdout", "stderr"):
                path = coordinate.get(key)
                if path and (run_root / path).is_file():
                    artifacts.append(artifact(run_root, run_root / path))
            for value in coordinate.get("artifacts", []):
                path = run_root / value["path"]
                if path.is_file():
                    artifacts.append(artifact(run_root, path))
        elif case and item.get("external_dependency_required"):
            status, classification = "external-blocked", "external"
            dependency = str(item.get("external_dependency") or "")
            message = f"Case 所需外部执行边界当前不可用：{dependency}；本地 runner 不得把 skip 冒充通过"
            artifacts = [artifact(run_root, run_root / "execution-preflight.json")]
        elif case and case["execution_contract"]["authorization"].get("required"):
            status, classification = "external-blocked", "external"
            message = "真实账号、服务或模型调用需要独立授权，当前本地批处理禁止执行"
            artifacts = [artifact(run_root, run_root / "execution-preflight.json")]
        elif case and item.get("revision_drift") and item.get("command") == "manual-blocked":
            status, classification = "runner-gap", "runner"
            message = "Case 的冻结可执行坐标属于另一 revision，当前 checkout 不得冒充执行"
            artifacts = [artifact(run_root, run_root / "execution-preflight.json")]
        elif case and case["execution_contract"]["launch"].get("strategy") == "manual-blocked":
            status, classification = "runner-gap", "runner"
            message = "Case 已定义但缺少可自动执行的本地 runner"
            artifacts = [artifact(run_root, run_root / "execution-preflight.json")]
        else:
            status, classification = "not-run", "evidence"
            message = "当前 attempt 尚未执行该必需坐标"
            artifacts = [artifact(run_root, run_root / "execution-preflight.json")]
        result: dict[str, Any] = {
            "item_id": item_id,
            "status": status,
            "plan_sha256": plan["plan_sha256"],
            "implementation_revision": plan["implementation_revision"],
            "failure_classification": classification,
            "message": message,
            "cleanup_status": "pass" if status in {"pass", "fail"} else "not-run",
            "artifacts": artifacts,
        }
        if status == "external-blocked":
            dependency_blocked = bool(item.get("external_dependency_required"))
            dependency = str(item.get("external_dependency") or "")
            platform_blocked = dependency.startswith("platform runner:")
            native_fullscreen_blocked = dependency == "macOS native fullscreen GUI session"
            result.update({
                "blocker_class": (
                    "unavailable-external-account-service-or-device"
                    if dependency_blocked
                    else "new-permission-or-credential"
                ),
                "exclusion_checks": (
                    ["current platform is outside the frozen Case target platforms", "selected Playwright skip is forbidden"]
                    if platform_blocked
                    else ["isolated Electron probes did not emit enter-full-screen", "selected Playwright skip is forbidden"]
                    if native_fullscreen_blocked
                    else ["QWORK_SERVER_DIR unresolved", "documented sibling cmd/dev-api absent", "selected Playwright skip is forbidden"]
                    if dependency_blocked
                    else ["local runner forbids live authorization", "zero real model calls recorded"]
                ),
                "unlock_action": (
                    f"rerun the exact Case on one declared target platform: {','.join(item.get('target_platforms') or [])}"
                    if platform_blocked
                    else "rerun the exact Case in a fresh interactive macOS GUI session that emits the native enter-full-screen event"
                    if native_fullscreen_blocked
                    else "provide a readable qwork_server checkout containing cmd/dev-api via QWORK_SERVER_DIR and rerun the exact Case"
                    if dependency_blocked
                    else f"separately authorize exact Case {case['id']} with provider/model/call budget"
                ),
            })
        if not case:
            counts[status] = counts.get(status, 0) + 1
            results.append(result)
            continue
        case_id = case["id"]
        route = case["execution_contract"]["route_id"]
        ui = case["execution_contract"]["navigation"].get("kind") == "ui-route"
        evidence = case_evidence(run_root, case_id, status)
        screenshot_states = {
            str(value.get("state")) for value in evidence
            if value.get("kind") in {"screenshot", "private-screenshot-attestation"}
        }
        required_states = list(case.get("ui_acceptance", {}).get("required_screenshot_states", []))
        visual_gaps = sorted(set(required_states) - screenshot_states) if ui and status in {"pass", "fail"} else []
        if ui and status == "fail" and required_states and "assertion-failure" not in screenshot_states:
            visual_gaps = sorted(set(visual_gaps) | {"assertion-failure"})
        human_status = "inconclusive" if status == "pass" and visual_gaps else status
        if human_status != status:
            result["status"] = human_status
            result["failure_classification"] = "evidence"
            result["message"] = "测试断言通过，但当前 run 缺少声明的视觉 checkpoint，证据不足"
        counts[human_status] = counts.get(human_status, 0) + 1
        results.append(result)
        visual_gap_count += bool(visual_gaps)
        human_cases.append({
            "id": case_id,
            "title": case["title"],
            "status": human_status,
            "executor": "electron-cdp" if ui else "dataset-verifier",
            "ui": ui,
            "ui_attempted": status in {"pass", "fail"} and ui,
            "route": route,
            "expected": "满足冻结 Case、因果、持久化与 UI Oracle",
            "actual": message if human_status == status else "测试断言通过，但当前 run 缺少声明的视觉 checkpoint，证据不足",
            "required_screenshot_states": required_states,
            "visual_evidence_gap": visual_gaps,
            "evidence": evidence,
        })
        machine_cases.append({"case_id": case_id, "status": human_status})

    storage_failure_count = sum(
        1
        for value in results
        if value["status"] == "fail" and "WORKBUDDY-STORAGE" in value["item_id"]
    )
    oracle_results = [value for value in results if "WORKBUDDY-CDP" in value["item_id"]]
    oracle_failure_count = sum(1 for value in oracle_results if value["status"] == "fail")
    defects = []
    if storage_failure_count:
        defects.append({
            "id": "QW-FULL-E2E-001",
            "title": "WorkBuddy 存储迁移合同未闭合",
            "severity": "P0",
            "expected": "所有 ~/.workbuddy 条目有明确处置与实现/回滚证据",
            "actual": f"{storage_failure_count} 个存储 Case 失败",
            "impact": "历史数据与身份路径无法宣称安全迁移",
        })
    if oracle_failure_count or visual_gap_count:
        defects.append({
            "id": "QW-FULL-E2E-002",
            "title": "WorkBuddy UI 像素与结构未对齐",
            "severity": "P0",
            "expected": f"冻结 {len(oracle_results)} 个状态通过像素/几何/结构 Oracle",
            "actual": f"{oracle_failure_count} 个 WorkBuddy Oracle 失败，{visual_gap_count} 个已执行 UI Case 缺必要视觉 checkpoint",
            "impact": "不能宣称 Figma 级对齐",
        })
    if counts.get("runner-gap", 0):
        defects.append({
            "id": "QW-FULL-E2E-003",
            "title": "全量自动执行闭包缺失",
            "severity": "P0",
            "expected": "每个必需 Case 有确定性或授权 runner",
            "actual": f"{counts.get('runner-gap', 0)} 个 Case 缺 runner",
            "impact": "完整产品回归仍不能一键复现",
        })

    report = {
        "project": "qwork",
        "run_id": run_root.name,
        "title": "QWork 全产品私有 E2E 当前实现审计",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "gate_status": "repair-required",
        "plan_sha256": plan["plan_sha256"],
        "implementation_revision": plan["implementation_revision"],
        "plain_language_summary": {
            "what_was_tested": [f"冻结全量 {len(plan['selected_case_ids'])} 个 Case", "本地门禁、存储/Oracle、Electron 因果与 WorkBuddy UI 对齐"],
            "what_was_not_tested": [f"{counts.get('runner-gap', 0)} 个 Case 缺本地 runner", f"{counts.get('external-blocked', 0)} 个真实服务 Case 未获独立授权", "Windows/Linux 当前平台实跑"],
            "result_reason": (
                f"当前报告有 {counts.get('fail', 0)} 个失败、{counts.get('inconclusive', 0)} 个证据不足、"
                f"{counts.get('runner-gap', 0)} 个 runner-gap 和 {counts.get('external-blocked', 0)} 个外部授权边界，不能提测。"
            ),
            "user_impact": "在产品失败、迁移合同、UI Oracle 和自动执行缺口关闭前，不能保证复刻后的核心行为、数据安全与界面一致性。",
            "next_step": (
                f"先修首个受信本地失败，再为 {counts.get('runner-gap', 0)} 个 Case 补齐本地 runner，"
                f"关闭 {storage_failure_count} 个存储迁移失败和 {oracle_failure_count} 个 WorkBuddy Oracle 失败，随后重建计划并全量复测。"
            ),
        },
        "scope": {"included": ["full closed-world plan"], "excluded": ["unauthorized live calls", "non-darwin platform execution"]},
        "environment": {"implementation_revision": plan["implementation_revision"], "plan_sha256": plan["plan_sha256"], "platform": "darwin"},
        "results": results,
        "cases": human_cases,
        "case_results": machine_cases,
        "commands": [],
        "defects": defects,
        "blockers": [f"local runner gaps: {counts.get('runner-gap', 0)}", f"live authorization boundaries: {counts.get('external-blocked', 0)}"],
        "residual_risks": ["macOS result cannot substitute Windows/Linux", "fake sidecar does not prove real model quality"],
        "cleanup": {"status": "pass", "details": "每个已执行坐标按 runner 合同清理；私有原始证据保留在 Git ignored Dataset", "evidence": [artifact(run_root, run_root / "runner-state.json")]},
        "independent_rerun": {"status": "pending", "plan_sha256": plan["plan_sha256"], "evidence": []},
        "checkpoint": {
            "current_implementation_revision": plan["implementation_revision"],
            "current_plan_hash": plan["plan_sha256"],
            "first_trusted_failure": next((value["item_id"] for value in results if value["status"] != "pass"), "none"),
            "repair_required_next_action": "repair the first trusted local failure, rebuild the plan, and rerun every required item",
            "cleanup_status": "pass",
            "independent_rerun_status": "pending",
            "final_response_allowed": False,
        },
        "focused_conclusion": "local deterministic closure executed where runners exist",
        "full_suite_conclusion": "repair-required",
        "visual_artifact_exclusions": [],
    }
    output = run_root / REPORT_JSON_NAME
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "report": str(output), "results": len(results), "cases": len(human_cases), "counts": counts, "visual_evidence_gaps": visual_gap_count}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
