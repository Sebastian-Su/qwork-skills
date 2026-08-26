#!/usr/bin/env python3
"""Run an explicit structured Oracle source Case batch with fail-closed evidence WAL."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from external_artifact_storage import validate_external_output_root


CASE_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
ROUTE_PREFIX = "qwork.dataset.structured-oracle-source."


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def canonical_source_inventory_sha256(manifest: dict[str, Any]) -> str:
    return f"sha256:{canonical_sha256(manifest.get('sources'))}"


def file_sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def ensure_within(path: Path, root: Path, label: str) -> None:
    if os.path.commonpath([str(path.resolve()), str(root.resolve())]) != str(root.resolve()):
        raise ValueError(f"{label} escapes the approved private Dataset root")


def evidence_path(output_root: Path, case_id: str) -> Path:
    return output_root / "cases" / case_id / "structured-source-result.json"


def validate_resume_state(state: dict[str, Any], contract_sha256: str, output_root: Path) -> None:
    if state.get("contract_sha256") != contract_sha256:
        raise ValueError("batch contract drifted; create a new run instead of resuming")
    if canonical_sha256(state.get("contract")) != contract_sha256:
        raise ValueError("stored batch contract integrity drifted")
    if state.get("run_id") != output_root.name:
        raise ValueError("batch run identity does not match its output directory")
    cases = state.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("batch state has no Case coordinates")
    state_case_ids = [str(item.get("case_id") or "") for item in cases]
    if state_case_ids != state["contract"].get("case_ids") or len(state_case_ids) != len(set(state_case_ids)):
        raise ValueError("batch state Case coordinates drifted")
    for item in cases:
        case_id = str(item.get("case_id") or "")
        status = str(item.get("status") or "")
        if status == "running" or status not in {"pending", "pass", "fail"}:
            raise ValueError(
                f"{case_id} requires manual evidence audit before any resume; status={status or 'missing'}"
            )
        report_path = evidence_path(output_root, case_id)
        if status == "pending" and report_path.exists():
            raise ValueError(f"pending Case already has evidence and requires manual audit: {case_id}")
        if status in {"pass", "fail"}:
            evidence = item.get("evidence") or {}
            if not report_path.is_file() or file_sha256(report_path) != evidence.get("sha256"):
                raise ValueError(f"completed Case evidence drifted: {case_id}")
            report = load_json(report_path)
            expected_report_status = "pass" if status == "pass" else "fail"
            if report.get("case_id") != case_id or report.get("status") != expected_report_status:
                raise ValueError(f"completed Case evidence authority drifted: {case_id}")


def render_report_html(report: dict[str, Any]) -> str:
    summary = report["plain_language_summary"]
    status_text = "可以提测" if report.get("gate_status") == "test-ready" else "暂时不能提测"

    def list_items(values: list[str]) -> str:
        return "".join(f"<li>{html.escape(str(value))}</li>" for value in values)

    rows = []
    labels = {"pass": "符合预期", "fail": "发现问题", "pending": "还没验证", "evidence-error": "证据异常"}
    for item in report.get("cases", []):
        evidence = "<br>".join(
            html.escape(str(value.get("path") or "")) for value in item.get("evidence", [])
        )
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item['id']))}</td>"
            f"<td>{html.escape(str(item['title']))}</td>"
            f"<td>{html.escape(labels.get(str(item['status']), '执行异常'))}</td>"
            f"<td>{html.escape(str(item['actual']))}</td>"
            f"<td><code>{evidence}</code></td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(str(report['title']))}</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f5f7fb;color:#172033}}
main{{max-width:1120px;margin:0 auto;padding:32px}} .hero,.card{{background:#fff;border:1px solid #e5e9f2;border-radius:16px;padding:24px;margin-bottom:18px}}
.status{{display:inline-block;background:#fff2e8;color:#ad4e00;border-radius:999px;padding:7px 12px;font-weight:700}}
h1{{margin:14px 0 8px}} h2{{font-size:18px}} .grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
table{{width:100%;border-collapse:collapse}} th,td{{text-align:left;vertical-align:top;border-bottom:1px solid #edf0f5;padding:10px}} code{{font-size:12px;word-break:break-all}}
details{{margin-top:12px}} @media(max-width:760px){{.grid{{grid-template-columns:1fr}}main{{padding:16px}}}}
</style></head><body><main>
<section class="hero"><span class="status">{status_text}</span><h1>{html.escape(str(report['title']))}</h1>
<p>{html.escape(str(summary['result_reason']))}</p><p><strong>聚焦结论：</strong>{html.escape(str(report['focused_conclusion']))}</p>
<p><strong>全量结论：</strong>{html.escape(str(report['full_suite_conclusion']))}</p></section>
<section class="grid"><div class="card"><h2>测了什么</h2><ul>{list_items(summary['what_was_tested'])}</ul></div>
<div class="card"><h2>没测什么</h2><ul>{list_items(summary['what_was_not_tested'])}</ul></div></section>
<section class="card"><h2>用户影响</h2><p>{html.escape(str(summary['user_impact']))}</p><h2>下一步</h2><p>{html.escape(str(summary['next_step']))}</p></section>
<section class="card"><h2>Case 结果</h2><table><thead><tr><th>ID</th><th>场景</th><th>状态</th><th>观察</th><th>证据</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<details><summary>技术明细</summary><pre>{html.escape(json.dumps(report, ensure_ascii=False, indent=2))}</pre></details></section>
</main></body></html>"""


def build_report(state: dict[str, Any], case_authority: dict[str, dict[str, Any]]) -> dict[str, Any]:
    results = state["cases"]
    passed = sum(item["status"] == "pass" for item in results)
    failed = sum(item["status"] == "fail" for item in results)
    pending = sum(item["status"] == "pending" for item in results)
    infrastructure_failed = sum(item["status"] not in {"pass", "fail", "pending"} for item in results)
    first_failure = next((item for item in results if item["status"] != "pass"), None)
    if infrastructure_failed:
        reason = f"批次遇到 {infrastructure_failed} 个证据或执行基础设施错误，已停止剩余坐标。"
        next_step = str(first_failure.get("first_error") or "审计首个异常坐标及证据后创建新 run。")
    elif failed:
        reason = f"选中的 {len(results)} 个 Case 中有 {failed} 个不再匹配冻结结构化来源。"
        next_step = str(first_failure.get("first_error") or "修复首个来源或编译漂移后重跑同一坐标。")
    elif pending:
        reason = f"本批次仍有 {pending} 个 Case 未执行，不能形成完整结论。"
        next_step = "先审计未完成坐标及证据，再从新 run 继续。"
    else:
        reason = "本次选中的结构化来源完整性 Case 均通过，但完整产品全量 E2E 和发布门禁未运行。"
        next_step = "审核 promotion-candidates.json 后登记当前证据，再选择下一批。"
    cases = []
    for result in results:
        authority = case_authority[result["case_id"]]
        evidence = [{"kind": "json", **result["evidence"]}] if result.get("evidence") else []
        cases.append({
            "id": result["case_id"],
            "title": authority["title"],
            "status": result["status"],
            "route": authority["execution_contract"]["route_id"],
            "executor": "deterministic-runner",
            "ui": False,
            "expected": authority["execution_contract"]["launch"]["success_oracle"],
            "actual": (
                f"{result.get('passed_atom_count', 0)}/{result.get('required_atom_count', 0)} 原子通过"
                if result["status"] == "pass"
                else str(result.get("first_error") or result["status"])
            ),
            "evidence": evidence,
        })
    return {
        "schema_version": 1,
        "project": "qwork",
        "title": "QWork WorkBuddy 结构化 Oracle 来源聚焦验证",
        "run_id": state["run_id"],
        "generated_at": now_utc(),
        "gate_status": "repair-required",
        "plain_language_summary": {
            "what_was_tested": [f"{len(results)} 个显式选择的 WorkBuddy 结构化 Oracle 来源完整性 Case"],
            "what_was_not_tested": ["完整产品全量 E2E", "Electron UI", "真实模型调用", "非结构化来源 Case"],
            "result_reason": reason,
            "user_impact": "验证只读取冻结 Git blob 与私有 Dataset，不打开或修改 live ~/.workbuddy 与 ~/.qwork。",
            "next_step": next_step,
        },
        "focused_conclusion": f"选中 {len(results)} 个，{passed} 通过、{failed} Case 失败、{infrastructure_failed} 基础设施失败、{pending} 未执行",
        "full_suite_conclusion": "未运行，不能据此宣称完整产品可提测",
        "environment": state["contract"],
        "scope": {"included_case_ids": state["contract"]["case_ids"], "selection": "explicit"},
        "cases": cases,
        "commands": ["validate_structured_oracle_source_case.py --case-id <exact-case-id>"],
        "defects": [
            {"case_id": item["case_id"], "summary": item.get("first_error") or item["status"]}
            for item in results if item["status"] == "fail"
        ],
        "blockers": [next_step] if first_failure else [],
        "residual_risks": ["full product release gate was not executed"],
        "cleanup": {"status": "passed", "details": "runner only wrote inside the approved ignored run root"},
        "checkpoint": {
            "current_implementation_revision": state["contract"]["implementation_revision"],
            "current_plan_hash": state["contract_sha256"],
            "first_trusted_failure": first_failure["case_id"] if first_failure else None,
            "repair_required_next_action": next_step,
            "cleanup_status": "passed",
            "independent_rerun_status": "not_run",
            "final_response_allowed": False,
        },
    }


def load_case_ids(args: argparse.Namespace) -> list[str]:
    values = list(args.case_id or [])
    if args.case_file:
        file_values = load_json(args.case_file)
        if not isinstance(file_values, list):
            raise ValueError("case file must be a JSON array of exact Case IDs")
        values.extend(str(value) for value in file_values)
    if not values:
        raise ValueError("at least one explicit --case-id or --case-file is required")
    if len(values) != len(set(values)):
        raise ValueError("duplicate Case coordinate in batch request")
    if not all(CASE_ID_RE.fullmatch(value) for value in values):
        raise ValueError("Case IDs may contain only letters, numbers, dot, underscore and hyphen")
    return values


def require_git_revision(repo: Path, revision: str) -> None:
    completed = subprocess.run(
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    if completed.returncode:
        raise ValueError(f"Case implementation revision is unavailable: {revision}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--skill-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--case-file", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    repo = args.repo.resolve()
    skill_root = args.skill_root.resolve()
    output_root = validate_external_output_root(
        args.output,
        protected_roots=[repo, skill_root],
    )
    if not CASE_ID_RE.fullmatch(output_root.name):
        raise ValueError("batch output must end in one stable run identifier")
    case_ids = load_case_ids(args)

    verifier = skill_root / "scripts/validate_structured_oracle_source_case.py"
    runner = Path(__file__).resolve()
    manifest = load_json(skill_root / "data/datasets/source-acceptance.json")
    source_inventory_sha256 = canonical_source_inventory_sha256(manifest)
    case_authority: dict[str, dict[str, Any]] = {}
    revisions: set[str] = set()
    for case_id in case_ids:
        case = load_json(skill_root / "data/datasets/cases" / f"{case_id}.json")
        if case.get("id") != case_id:
            raise ValueError(f"Case identity drifted: {case_id}")
        route = str(case.get("execution_contract", {}).get("route_id") or "")
        if not route.startswith(ROUTE_PREFIX):
            raise ValueError(f"Case is not a structured Oracle source route: {case_id}")
        revisions.add(str(case.get("verification", {}).get("implementation_revision") or ""))
        case_authority[case_id] = case
    if len(revisions) != 1 or not next(iter(revisions)):
        raise ValueError("selected Cases do not bind one implementation revision")
    implementation_revision = next(iter(revisions))
    require_git_revision(repo, implementation_revision)
    contract = {
        "schema_version": 1,
        "case_ids": case_ids,
        "implementation_revision": implementation_revision,
        "source_inventory_canonical_sha256": source_inventory_sha256,
        "verifier_sha256": file_sha256(verifier),
        "runner_sha256": file_sha256(runner),
    }
    contract_sha256 = canonical_sha256(contract)
    state_path = output_root / "state.json"
    if args.resume:
        if not state_path.is_file():
            raise ValueError("resume requested but state.json is missing")
        state = load_json(state_path)
        validate_resume_state(state, contract_sha256, output_root)
    else:
        if output_root.exists() and any(output_root.iterdir()):
            raise ValueError("new batch output must be absent or empty")
        output_root.mkdir(parents=True, exist_ok=True)
        state = {
            "schema_version": 1,
            "run_id": output_root.name,
            "started_at": now_utc(),
            "updated_at": now_utc(),
            "contract": contract,
            "contract_sha256": contract_sha256,
            "cases": [{"case_id": case_id, "status": "pending", "attempt": 0} for case_id in case_ids],
        }
        atomic_write_json(state_path, state)

    batch_fatal = False
    for item in state["cases"]:
        if item["status"] != "pending":
            continue
        case_id = item["case_id"]
        case_dir = output_root / "cases" / case_id
        ensure_within(case_dir, output_root, "Case evidence directory")
        case_dir.mkdir(parents=True, exist_ok=True)
        result_path = evidence_path(output_root, case_id)
        item.update({"status": "running", "attempt": 1, "started_at": now_utc()})
        state["updated_at"] = now_utc()
        atomic_write_json(state_path, state)

        command = [
            sys.executable, str(verifier), "--repo", str(repo), "--skill-root", str(skill_root),
            "--case-id", case_id, "--output", str(result_path),
        ]
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        atomic_write_text(case_dir / "stdout.log", completed.stdout)
        atomic_write_text(case_dir / "stderr.log", completed.stderr)
        item["exit_code"] = completed.returncode
        item["finished_at"] = now_utc()
        if not result_path.is_file():
            item.update({"status": "evidence-error", "first_error": "verifier did not create evidence"})
            batch_fatal = True
        else:
            result = load_json(result_path)
            item.update({
                "evidence": {"path": result_path.relative_to(output_root).as_posix(), "sha256": file_sha256(result_path)},
                "required_atom_count": result.get("required_atom_count"),
                "passed_atom_count": result.get("passed_atom_count"),
                "failed_atom_count": result.get("failed_atom_count"),
                "first_error": next(iter(result.get("errors") or []), None),
            })
            if completed.returncode == 0 and result.get("status") == "pass":
                item["status"] = "pass"
            elif completed.returncode == 1 and result.get("status") == "fail":
                item["status"] = "fail"
            else:
                item.update({"status": "evidence-error", "first_error": "verifier exit/result contract mismatch"})
                batch_fatal = True
        state["updated_at"] = now_utc()
        atomic_write_json(state_path, state)
        if batch_fatal:
            break

    report = build_report(state, case_authority)
    atomic_write_json(output_root / "QWORK-E2E-REPORT.json", report)
    atomic_write_text(output_root / "QWORK-E2E-REPORT.html", render_report_html(report))
    passing: dict[str, Any] = {}
    failed: dict[str, Any] = {}
    for item in state["cases"]:
        if item["status"] not in {"pass", "fail"}:
            continue
        candidate = {
            "run_id": f"{state['run_id']}/{item['case_id']}",
            "report": f"skill://qwork-test-dataset/{output_root.relative_to(skill_root).as_posix()}/{item['evidence']['path']}",
            "report_sha256": item["evidence"]["sha256"],
            "runner_sha256": contract["verifier_sha256"],
            "source_inventory_canonical_sha256": contract["source_inventory_canonical_sha256"],
            "implementation_revision": contract["implementation_revision"],
            "verified_at": item["finished_at"],
        }
        if item["status"] == "pass":
            passing[item["case_id"]] = candidate
        else:
            failed[item["case_id"]] = {**candidate, "failure_summary": item["first_error"]}
    atomic_write_json(output_root / "promotion-candidates.json", {
        "schema_version": 1,
        "run_id": state["run_id"],
        "contract_sha256": contract_sha256,
        "structured_source_runs": passing,
        "failed_structured_source_runs": failed,
    })
    if batch_fatal:
        return 2
    return 0 if all(item["status"] == "pass" for item in state["cases"]) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
        print(f"structured source batch unavailable: {error}", file=sys.stderr)
        raise SystemExit(2)
