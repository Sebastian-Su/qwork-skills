#!/usr/bin/env python3
"""Render a normalized E2E report JSON as a self-contained Chinese HTML report."""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any

UI_EXECUTORS = {"ego-browser", "computer-use", "electron-cdp", "desktop-ui", "browser-ui"}
PASS = {"pass", "passed"}
FAIL = {"fail", "failed", "known_gap", "repair-required"}
BLOCKED = {"blocked", "external-blocked", "environment_blocked"}

STATUS_LABELS = {
    "pass": "符合预期",
    "passed": "符合预期",
    "fail": "发现问题",
    "failed": "发现问题",
    "known_gap": "已知问题，仍未通过",
    "repair-required": "需要修复",
    "blocked": "被外部条件卡住",
    "external-blocked": "被外部条件卡住",
    "environment_blocked": "受环境影响，没验证完",
    "inconclusive": "证据不足，无法确认",
    "skipped": "本次未执行",
    "pending": "还没验证",
    "not_applicable": "本次不需要检查",
    "not-run": "本次尚未执行",
    "runner-gap": "缺少本地自动执行器",
}

SCREENSHOT_STATE_LABELS = {
    "entry": "进入页面时",
    "major-state-transition": "关键操作完成后",
    "before-important-mutation": "重要操作前",
    "after-important-mutation": "重要操作后",
    "before-and-after-important-mutation": "重要操作前后",
    "assertion-failure": "出现问题时",
    "final-state": "最终结果",
}

ENVIRONMENT_LABELS = {
    "revision": "代码版本",
    "implementation_revision": "代码版本",
    "platform": "运行平台",
    "environment": "测试环境",
    "base": "对比起点",
    "head": "本次版本",
    "plan_sha256": "测试计划校验值",
}


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def items(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def status_class(value: Any) -> str:
    status = str(value or "pending").lower()
    if status in PASS:
        return "pass"
    if status in FAIL:
        return "fail"
    if status == "runner-gap":
        return "fail"
    if status in BLOCKED:
        return "blocked"
    return "pending"


def status_label(value: Any) -> str:
    status = str(value or "pending").lower()
    return STATUS_LABELS.get(status, "结果待确认")


def gate_label(value: Any) -> str:
    gate = str(value or "repair-required").lower()
    if gate == "test-ready":
        return "可以提测"
    if gate == "repair-required":
        return "暂时不能提测"
    if gate in BLOCKED:
        return "暂时无法完成验证"
    return "结果待确认"


def readable_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("message", "reason", "description", "title", "id"):
            if value.get(key):
                return str(value[key])
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def validate_plain_language_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = mapping(report.get("plain_language_summary"))
    required_lists = ("what_was_tested", "what_was_not_tested")
    required_text = ("result_reason", "user_impact", "next_step")
    for key in required_lists:
        value = summary.get(key)
        if not isinstance(value, list) or (key == "what_was_tested" and not value):
            raise ValueError(f"plain_language_summary.{key} must be a list and tested scope cannot be empty")
    for key in required_text:
        if not isinstance(summary.get(key), str) or not summary[key].strip():
            raise ValueError(f"plain_language_summary.{key} must be non-empty plain language")
    return summary


def resolve_artifact(path_value: str, root: Path) -> Path:
    candidate = Path(path_value)
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"artifact escapes run root: {path_value}") from exc
    if not resolved.is_file():
        raise FileNotFoundError(f"evidence artifact not found: {path_value}")
    return resolved


def image_uri(path: Path) -> tuple[str, str]:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if not mime.startswith("image/"):
        raise ValueError(f"screenshot evidence is not an image: {path}")
    raw = path.read_bytes()
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}", hashlib.sha256(raw).hexdigest()


def validate_cases(report: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    cases = [mapping(case) for case in items(report.get("cases"))]
    allowed = {
        "pass",
        "passed",
        "fail",
        "failed",
        "blocked",
        "external-blocked",
        "environment_blocked",
        "inconclusive",
        "skipped",
        "known_gap",
        "pending",
        "not_applicable",
        "not-run",
        "runner-gap",
    }
    for case in cases:
        case_id = str(case.get("id") or "unknown")
        status = str(case.get("status") or "pending").lower()
        if status not in allowed:
            raise ValueError(f"case {case_id} has unsupported status: {status}")
        evidence = [mapping(entry) for entry in items(case.get("evidence"))]
        screenshots = [entry for entry in evidence if str(entry.get("kind", "")).lower() == "screenshot"]
        private_screenshot_attestations = [
            entry for entry in evidence
            if str(entry.get("kind", "")).lower() == "private-screenshot-attestation"
        ]
        is_ui = bool(case.get("ui")) or str(case.get("executor", "")).lower() in UI_EXECUTORS
        ui_attempted = bool(case.get("ui_attempted")) or bool(screenshots)
        screenshot_states: set[str] = set()
        for entry in private_screenshot_attestations:
            state = str(entry.get("state") or "").strip()
            digest = str(entry.get("sha256") or "").removeprefix("sha256:").lower()
            if not state or not entry.get("caption") or len(digest) != 64 or any(
                value not in "0123456789abcdef" for value in digest
            ):
                raise ValueError(
                    f"private screenshot attestation for case {case_id} requires state, caption, and sha256"
                )
            if entry.get("path"):
                raise ValueError(f"private screenshot attestation for case {case_id} must not expose a raw path")
            screenshot_states.add(state)
        for entry in evidence:
            path_value = entry.get("path")
            if path_value:
                path = resolve_artifact(str(path_value), root)
                if str(entry.get("kind", "")).lower() == "screenshot":
                    state = str(entry.get("state") or "").strip()
                    expected_hash = str(entry.get("sha256") or "").strip().lower()
                    if not state or not entry.get("caption") or not expected_hash:
                        raise ValueError(f"screenshot for case {case_id} requires state, caption, and sha256")
                    _, actual_hash = image_uri(path)
                    if actual_hash != expected_hash:
                        raise ValueError(f"screenshot hash mismatch for case {case_id}: {path_value}")
                    screenshot_states.add(state)
        required_value = case.get("required_screenshot_states")
        if is_ui and ui_attempted and not isinstance(required_value, list):
            raise ValueError(f"attempted UI case {case_id} must declare required_screenshot_states")
        required_states = {
            str(value).strip() for value in items(required_value) if str(value).strip()
        }
        declared_gaps = {
            str(value).strip() for value in items(case.get("visual_evidence_gap")) if str(value).strip()
        }
        allow_declared_repair_gap = report.get("gate_status") == "repair-required"
        if is_ui and ui_attempted and required_states:
            if "entry" not in required_states:
                raise ValueError(f"attempted UI case {case_id} required_screenshot_states must include entry")
            missing_states = required_states - screenshot_states
            if missing_states and not (
                allow_declared_repair_gap and missing_states <= declared_gaps
            ):
                raise ValueError(
                    f"attempted UI case {case_id} is missing screenshots for: " + ", ".join(sorted(missing_states))
                )
        if is_ui and status in PASS and required_states:
            universal_states = {"entry", "final-state"}
            if not universal_states.issubset(required_states):
                raise ValueError(f"UI case {case_id} required_screenshot_states must include entry and final-state")
            missing_states = required_states - screenshot_states
            if missing_states:
                raise ValueError(
                    f"UI case {case_id} cannot PASS without screenshots for: " + ", ".join(sorted(missing_states))
                )
        if (
            is_ui
            and status in FAIL
            and required_states
            and "assertion-failure" not in screenshot_states
            and not (allow_declared_repair_gap and "assertion-failure" in declared_gaps)
        ):
            raise ValueError(f"failed UI case {case_id} requires assertion-failure screenshot")
    return cases


def list_html(values: Any, empty: str = "无") -> str:
    rows = items(values)
    if not rows:
        return f'<p class="muted">{esc(empty)}</p>'
    return "<ul>" + "".join(f"<li>{esc(readable_text(row))}</li>" for row in rows) + "</ul>"


def environment_html(value: Any) -> str:
    env = mapping(value)
    if not env:
        return '<p class="muted">未提供环境信息</p>'
    return (
        '<dl class="meta">'
        + "".join(
            f"<div><dt>{esc(ENVIRONMENT_LABELS.get(str(key), key))}</dt><dd>{esc(val)}</dd></div>"
            for key, val in env.items()
        )
        + "</dl>"
    )


def case_rows(cases: list[dict[str, Any]]) -> str:
    rows: list[str] = []
    for case in cases:
        evidence_links = []
        for entry in items(case.get("evidence")):
            record = mapping(entry)
            if record.get("path"):
                evidence_links.append(esc(record["path"]))
        rows.append(
            "<tr>"
            f"<td><strong>{esc(case.get('title', '未命名检查项'))}</strong>"
            f'<details class="row-tech"><summary>查看技术编号</summary><code>{esc(case.get("id", ""))}</code>'
            f"<small>{esc(case.get('route', ''))} · {esc(case.get('executor', ''))}</small>"
            f"<small>机器状态：{esc(case.get('status', 'pending'))}</small></details></td>"
            f'<td><span class="status {status_class(case.get("status"))}">{esc(status_label(case.get("status")))}</span></td>'
            f"<td>{esc(case.get('expected', ''))}</td>"
            f"<td>{esc(case.get('actual', ''))}</td>"
            f'<td>{len(evidence_links)} 份<details class="row-tech"><summary>查看证据文件</summary><code>{esc(", ".join(evidence_links) or "—")}</code></details></td>'
            "</tr>"
        )
    return "".join(rows) or '<tr><td colspan="5" class="muted">本次没有可执行检查项</td></tr>'


def gallery_html(cases: list[dict[str, Any]], root: Path) -> str:
    figures: list[str] = []
    for case in cases:
        for entry in items(case.get("evidence")):
            record = mapping(entry)
            if str(record.get("kind", "")).lower() != "screenshot" or not record.get("path"):
                continue
            path = resolve_artifact(str(record["path"]), root)
            uri, digest = image_uri(path)
            figures.append(
                '<figure class="shot">'
                f'<img src="{uri}" alt="{esc(record.get("caption") or case.get("title") or path.name)}">'
                "<figcaption>"
                f"<strong>{esc(case.get('title') or case.get('id', ''))} · {esc(SCREENSHOT_STATE_LABELS.get(str(record.get('state')), record.get('state', '检查节点')))}</strong>"
                f"<p>{esc(record.get('caption', ''))}</p>"
                f'<details class="row-tech"><summary>查看证据文件</summary><code>{esc(record.get("path"))}</code><code>sha256:{digest}</code></details>'
                "</figcaption></figure>"
            )
    return "".join(figures) or '<p class="muted">本次没有需要展示的页面截图。</p>'


def defects_html(value: Any) -> str:
    cards: list[str] = []
    for defect in items(value):
        item = mapping(defect)
        cards.append(
            '<article class="defect">'
            f"<h3>{esc(item.get('id', 'DEFECT'))} · {esc(item.get('title', '未命名缺陷'))}</h3>"
            f"<p><b>问题级别：</b>{esc(item.get('severity', '尚未分级'))}</p>"
            f"<p><b>本来应该：</b>{esc(item.get('expected', ''))}</p>"
            f"<p><b>实际看到：</b>{esc(item.get('actual', ''))}</p>"
            f"<p><b>为什么会这样 / 有什么影响：</b>{esc(item.get('root_cause') or item.get('impact') or '还在确认')}</p>"
            f"<p><b>怎么复现：</b>{esc(item.get('reproduction', ''))}</p>"
            "</article>"
        )
    return "".join(cards) or '<p class="muted">本次没有登记新问题。</p>'


def commands_html(value: Any) -> str:
    rows: list[str] = []
    for command in items(value):
        item = mapping(command)
        if not item:
            rows.append(f"<li><code>{esc(command)}</code></li>")
            continue
        rows.append(
            "<li><code>" + esc(item.get("command", "")) + "</code>"
            f' <span class="status {"pass" if item.get("exit_code") == 0 else "fail"}">exit {esc(item.get("exit_code", "?"))}</span></li>'
        )
    return "<ul>" + "".join(rows) + "</ul>" if rows else '<p class="muted">未记录命令。</p>'


def render(report: dict[str, Any], root: Path) -> str:
    cases = validate_cases(report, root)
    plain = validate_plain_language_summary(report)
    totals = {"pass": 0, "fail": 0, "blocked": 0, "pending": 0}
    for case in cases:
        totals[status_class(case.get("status"))] += 1
    scope = mapping(report.get("scope"))
    cleanup = mapping(report.get("cleanup"))
    title = report.get("title") or f"{report.get('project', '项目')} 测试结果报告"
    generated = report.get("generated_at") or datetime.now().astimezone().isoformat(timespec="seconds")
    gate = report.get("gate_status") or "repair-required"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><style>
:root{{--ink:#142033;--muted:#667085;--paper:#f4f6f8;--card:#fff;--line:#dce2ea;--navy:#101f38;--blue:#356cff;--green:#158466;--red:#c53f4b;--amber:#b66b11;--shadow:0 18px 55px rgba(18,32,54,.11)}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;line-height:1.6}}header{{background:var(--navy);color:#fff;padding:56px max(28px,calc((100vw - 1180px)/2))}}header p{{color:#b9c6d9}}main{{max-width:1180px;margin:-24px auto 64px;padding:0 24px}}section{{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:26px;margin:18px 0;box-shadow:var(--shadow)}}h1{{margin:0;font-size:38px}}h2{{margin:0 0 18px}}h3{{margin:8px 0}}.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}}.metric,.answer{{padding:18px;border-radius:14px;background:#f7f9fc}}.metric b{{display:block;font-size:28px}}.verdict{{border-left:6px solid var(--blue);padding:18px 22px;margin-bottom:18px;background:#f3f7ff;border-radius:12px}}.verdict h3{{font-size:28px;margin:2px 0}}.status{{display:inline-flex;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:700}}.status.pass{{background:#daf4ea;color:var(--green)}}.status.fail{{background:#fee4e7;color:var(--red)}}.status.blocked{{background:#fff0d8;color:var(--amber)}}.status.pending{{background:#e9edf3;color:#526077}}.muted,small{{color:var(--muted)}}table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{padding:12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}td small{{display:block}}.mono,code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;overflow-wrap:anywhere}}.gallery{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}.shot{{margin:0;border:1px solid var(--line);border-radius:14px;overflow:hidden;background:#fff}}.shot img{{display:block;width:100%;height:auto;background:#edf1f5}}figcaption{{padding:14px}}figcaption code{{display:block;color:var(--muted)}}.defect{{border-left:4px solid var(--red);padding:4px 18px;margin:16px 0;background:#fff8f8}}.meta{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}.meta div{{padding:12px;background:#f7f9fc;border-radius:10px}}dt{{font-size:12px;color:var(--muted)}}dd{{margin:3px 0 0;font-weight:600}}details.technical{{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:20px 26px;margin:18px 0}}details.technical>summary{{font-weight:700;cursor:pointer}}.row-tech{{margin-top:5px;color:var(--muted)}}.row-tech summary{{cursor:pointer;font-size:12px}}@media(max-width:780px){{.grid,.gallery,.meta{{grid-template-columns:1fr}}table{{display:block;overflow:auto}}}}
</style></head><body>
<header><p>{esc(report.get("project", ""))}</p><h1>{esc(title)}</h1><p>生成时间 {esc(generated)} · 测试结论：{esc(gate_label(gate))}</p></header>
<main>
<section><h2>先看结论</h2><div class="verdict"><small>这次能不能提测？</small><h3>{esc(gate_label(gate))}</h3><p>{esc(plain["result_reason"])}</p></div><div class="grid"><div class="answer"><h3>这次检查了什么</h3>{list_html(plain["what_was_tested"])}</div><div class="answer"><h3>这次没检查什么</h3>{list_html(plain["what_was_not_tested"], "没有额外未检查的范围")}</div><div class="answer"><h3>对用户有什么影响</h3><p>{esc(plain["user_impact"])}</p></div><div class="answer"><h3>接下来怎么做</h3><p>{esc(plain["next_step"])}</p></div></div></section>
<section><h2>逐项检查结果</h2><div class="grid"><div class="metric"><small>一共检查</small><b>{len(cases)} 项</b></div><div class="metric"><small>结果分布</small><p>{totals["pass"]} 项符合预期 · {totals["fail"]} 项发现问题 · {totals["blocked"]} 项被卡住 · {totals["pending"]} 项未完成</p></div></div><table><thead><tr><th>检查内容</th><th>结果</th><th>本来应该</th><th>实际看到</th><th>证据</th></tr></thead><tbody>{case_rows(cases)}</tbody></table></section>
<section><h2>关键截图：这些画面证明了什么</h2><div class="gallery">{gallery_html(cases, root)}</div></section>
<section><h2>本次发现的问题</h2>{defects_html(report.get("defects"))}</section>
<section><h2>还没解决的事情</h2><h3>当前被什么卡住</h3>{list_html(report.get("blockers"), "没有外部阻塞")}<h3>还需要留意什么</h3>{list_html(report.get("residual_risks"), "没有额外风险")}</section>
<section><h2>测试收尾</h2><p><b>测试数据和临时进程：</b><span class="status {status_class(cleanup.get("status"))}">{esc(status_label(cleanup.get("status")))}</span> {esc(cleanup.get("details", ""))}</p><p><b>下一步：</b>{esc(plain["next_step"])}</p></section>
<details class="technical"><summary>技术明细（开发和测试人员需要时展开）</summary><h3>机器判定</h3><p>运行编号：<code>{esc(report.get("run_id", ""))}</code></p><p>门禁状态：<code>{esc(gate)}</code></p><p>聚焦场景：{esc(report.get("focused_conclusion", "未单独声明"))}</p><p>完整范围：{esc(report.get("full_suite_conclusion", "未单独声明"))}</p><h3>范围与环境</h3><h4>纳入范围</h4>{list_html(scope.get("included"))}<h4>排除或未授权</h4>{list_html(scope.get("excluded"))}{environment_html(report.get("environment"))}<h3>执行命令</h3>{commands_html(report.get("commands"))}</details>
</main></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Normalized report.json")
    parser.add_argument("--output", type=Path, help="Output report.html; defaults beside input")
    parser.add_argument("--artifact-root", type=Path, help="Allowed root for all evidence paths")
    args = parser.parse_args()

    input_path = args.input.resolve()
    root = (args.artifact_root or input_path.parent).resolve()
    output_path = (args.output or input_path.with_suffix(".html")).resolve()
    try:
        output_path.relative_to(root)
    except ValueError as exc:
        raise SystemExit(f"output escapes artifact root: {output_path}") from exc

    report = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise SystemExit("report input must be a JSON object")
    rendered = render(report, root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
