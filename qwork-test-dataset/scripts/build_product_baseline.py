#!/usr/bin/env python3
"""Compile QWork/WorkBuddy sources into a traceable full-product E2E baseline."""

from __future__ import annotations

import argparse
import atexit
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Any

import yaml


FACET_CATEGORIES = {
    "business-rule": ["business"],
    "acceptance-criterion": ["business"],
    "negative-rule": ["negative"],
    "role-permission": ["permission"],
    "state-transition": ["state", "recovery"],
    "data-side-effect": ["data"],
    "error-copy": ["error", "ui-content"],
    "non-functional": ["reliability"],
    "ui-structure": ["ui-structure"],
    "ui-geometry": ["ui-geometry"],
    "ui-visual": ["ui-visual"],
    "ui-content": ["ui-content"],
    "ui-state": ["ui-state"],
    "ui-interaction": ["ui-interaction"],
    "responsive": ["responsive"],
    "accessibility": ["accessibility"],
    "evidence-provenance": ["evidence-integrity"],
}
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
UI_ORACLE_TYPES = {
    "ui",
    "ui-structure",
    "ui-geometry",
    "ui-content",
    "ui-state",
    "ui-interaction",
    "responsive",
    "accessibility",
    "visual",
    "aria",
}

USER_VISIBLE_WORDS = (
    "用户",
    "页面",
    "界面",
    "显示",
    "可见",
    "按钮",
    "卡片",
    "弹窗",
    "菜单",
    "侧栏",
    "首页",
    "composer",
    "hover",
    "点击",
    "输入框",
    "截图",
    "viewport",
)

TECHNICAL_CONTRACT_WORDS = (
    "schema",
    "协议",
    "进程",
    "父子关系",
    "ipc",
    "api",
    "数据库",
    "sqlite",
    "落盘",
    "文件路径",
    "环境变量",
    "源码",
    "签名",
    "hash",
    "token 不",
    "renderer 不",
    "三平台",
    "darwin",
    "win32",
    "linux",
)

SURFACES = {
    "auth": ("auth", "登录", "账号", "身份", "cookie", "quc"),
    "shell-home": ("home", "首页", "侧栏", "shell", "sidebar", "titlebar", "新建任务"),
    "assistant": ("assistant", "助理", "会话", "conversation", "chat", "对话"),
    "task-lifecycle": ("task", "任务", "stream", "tool", "thinking", "执行"),
    "expert-market": ("expert", "专家", "召唤", "market"),
    "expert-team": ("team", "专家团", "lead", "member", "askuser", "成员"),
    "skills": ("skill", "技能"),
    "connectors": ("connector", "连接器", "mcp", "oauth"),
    "projects": ("project", "项目", "协作", "invite"),
    "automations": ("automation", "自动化", "定时", "schedule"),
    "files": ("file", "文件", "artifact", "附件", "upload", "workspace"),
    "browser": ("browser", "浏览器", "cdp"),
    "terminal": ("terminal", "终端", "shell"),
    "models": ("model", "模型", "llm", "provider", "dashscope"),
    "permissions": ("permission", "权限", "sandbox", "沙箱", "安全"),
    "settings": ("setting", "设置", "配置", "theme", "主题"),
    "im": ("im", "微信", "qq", "消息", "wecom"),
    "library": ("library", "更多", "邮箱", "知识库", "灵感", "inspiration"),
    "window-runtime": ("window", "窗口", "tray", "托盘", "startup", "启动", "runtime"),
    "persistence": ("storage", "存储", "persist", "数据库", "sqlite", "路径", "重启"),
}

DOC_SURFACE_DOMAINS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (r"^docs/qconnector/", ("connectors",)),
    (r"^docs/project-prd\.md$|^docs/project-cloud-contract\.md$", ("projects", "automations", "files", "connectors", "expert-market", "permissions")),
    (r"automation", ("automations", "assistant", "connectors", "permissions", "persistence")),
    (r"sidebar|shell-home", ("shell-home", "library", "files", "settings", "auth")),
    (r"expert|workbuddy", ("expert-market", "expert-team", "task-lifecycle", "permissions", "persistence", "shell-home")),
    (r"im-assistant", ("im", "assistant", "permissions", "persistence")),
    (r"packaging|testing-guide|commit-and-pr-guide", ("window-runtime", "permissions", "persistence")),
    (r"adr/0001-use-ziqdo", ("expert-team", "task-lifecycle")),
)

TEST_SURFACE_DOMAINS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (r"^e2e/auth", ("auth", "window-runtime")),
    (r"^e2e/assistant", ("im", "assistant", "settings")),
    (r"^e2e/automation", ("automations", "persistence", "im")),
    (r"^e2e/browser|^e2e/internal-browser", ("browser", "permissions")),
    (r"^e2e/connectors", ("connectors", "permissions", "settings")),
    (r"^e2e/expert-(?:ask-user|concurrency|team)", ("expert-team", "permissions", "persistence")),
    (r"^e2e/(?:bundled-experts|experts|real-expert-agent)", ("expert-market", "task-lifecycle", "permissions", "persistence")),
    (r"^e2e/(?:composer-file-attachment|explorer|my-files)", ("files", "shell-home", "permissions")),
    (r"^e2e/(?:im-loopback)", ("im", "assistant", "persistence")),
    (r"^e2e/(?:llm|model|conversation-errors)", ("models", "assistant", "task-lifecycle")),
    (r"^e2e/(?:permissions)", ("permissions",)),
    (r"^e2e/(?:plugins|skill)", ("skills", "expert-market", "permissions")),
    (r"^e2e/project", ("projects", "automations", "files", "permissions")),
    (r"^e2e/(?:config-home|config-isolation|settings)", ("settings", "persistence", "assistant")),
    (r"^e2e/(?:runtime|dev-startup|session-startup|startup-window|tray|window-content-safe|qwork-branding)", ("window-runtime", "persistence", "permissions")),
    (r"^e2e/(?:sessions|sidecar-crash|workflow)", ("task-lifecycle", "assistant", "persistence")),
    (r"^e2e/terminal", ("terminal", "permissions", "persistence")),
    (r"^e2e/workbuddy-collapsed-titlebar", ("shell-home", "window-runtime")),
    (r"^e2e/workbuddy-home-main|^e2e/workbuddy-layout|^e2e/workbuddy-ui-shell-home|^e2e/workbuddy-ui-responsive", ("shell-home", "files", "settings")),
    (r"^e2e/workbuddy-ui-sidebar-account", ("shell-home", "auth", "settings")),
    (r"^e2e/workbuddy-ui-expert-market", ("expert-market", "skills", "connectors")),
    (r"^e2e/workbuddy-ui-expert-team", ("expert-team", "permissions")),
    (r"^e2e/workbuddy-ui-task-lifecycle", ("task-lifecycle", "permissions", "terminal")),
    (r"^e2e/workbuddy-ui-secondary-surfaces", ("library", "projects", "automations", "skills", "connectors")),
)

DOC_DISPOSITIONS: tuple[tuple[str, str, str], ...] = (
    (r"^docs/commit-and-pr-guide\.md$|^docs/testing-guide\.md$", "release-governance", "Planner/runner policy, not a user-visible product requirement"),
    (r"^docs/audits/", "supporting-evidence", "Audit evidence does not define product behavior by itself"),
    (r"^docs/superpowers/plans/", "implementation-context", "Implementation plans support traceability but do not supersede approved specs"),
    (r"^docs/qconnector/(?:README|TODO|plan|retrospective|test-inventory|qqmusic-skill)\.md$", "implementation-context", "Connector planning/inventory context is not the product contract"),
)

NEGATIVE_WORDS = ("拒绝", "禁止", "不得", "不能", "失败", "错误", "invalid", "reject", "deny", "without")
PERMISSION_WORDS = ("权限", "沙箱", "授权", "认证", "登录", "permission", "auth", "credential", "token")
STATE_WORDS = ("状态", "恢复", "重启", "迁移", "中断", "完成", "等待", "running", "restart", "resume", "lifecycle")
DATA_WORDS = ("存储", "持久", "数据库", "文件", "路径", "sqlite", "db", "jsonl", "repository", "cache")
INTERACTION_WORDS = ("点击", "打开", "关闭", "选择", "输入", "拖拽", "hover", "click", "navigate", "切换", "弹窗")
VISUAL_WORDS = ("颜色", "字体", "圆角", "阴影", "渐变", "icon", "图标", "视觉", "截图", "color", "font", "radius")
RESPONSIVE_WORDS = ("响应式", "断点", "viewport", "dpr", "缩放", "window size", "resize")
ACCESSIBILITY_WORDS = ("aria", "无障碍", "键盘", "焦点", "role", "tab order")
ERROR_WORDS = ("错误文案", "报错", "提示", "error message", "失败提示")


def run_git(repo: pathlib.Path, *args: str, check: bool = True) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=check, capture_output=True, text=True).stdout


def run_git_blob(repo: pathlib.Path, revision: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def skill_ref(skill_root: pathlib.Path, path: pathlib.Path) -> str:
    return f"skill://qwork-test-dataset/{path.resolve().relative_to(skill_root.resolve()).as_posix()}"


def stable_slug(value: str, limit: int = 52) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:limit].strip("-") or "item"


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def classify(text: str, *, ui_hint: bool = False) -> str:
    lower = text.lower()
    if any(word in lower for word in ACCESSIBILITY_WORDS):
        return "accessibility"
    if any(word in lower for word in RESPONSIVE_WORDS):
        return "responsive"
    if re.search(r"\b\d+(?:\.\d+)?\s*px\b|\d+\s*[×x]\s*\d+", lower):
        return "ui-geometry"
    if any(word in lower for word in VISUAL_WORDS):
        return "ui-visual"
    if any(word in lower for word in ERROR_WORDS):
        return "error-copy"
    if any(word in lower for word in PERMISSION_WORDS):
        return "role-permission"
    if any(word in lower for word in NEGATIVE_WORDS):
        return "negative-rule"
    if any(word in lower for word in STATE_WORDS):
        return "state-transition"
    if any(word in lower for word in DATA_WORDS):
        return "data-side-effect"
    if any(word in lower for word in INTERACTION_WORDS):
        return "ui-interaction"
    return "ui-content" if ui_hint else "business-rule"


def atom_requires_ui(source: dict[str, Any], atom: dict[str, Any]) -> bool:
    facet = str(atom["facet"])
    if facet in {"data-side-effect", "evidence-provenance"}:
        return False
    if facet.startswith("ui-") or facet in {"responsive", "accessibility", "error-copy"}:
        return True
    if source["type"] in {
        "structured-workbuddy-oracle",
        "workbuddy-cdp",
        "workbuddy-visual",
    }:
        return True
    label = str(atom["label"]).lower()
    visible = any(word in label for word in USER_VISIBLE_WORDS)
    technical = any(word in label for word in TECHNICAL_CONTRACT_WORDS)
    return visible and not (technical and not any(word in label for word in ("页面", "界面", "显示", "可见")))


def semantic_oracle_type(source: dict[str, Any], atom: dict[str, Any]) -> str:
    facet = str(atom["facet"])
    if facet == "evidence-provenance":
        return "trace"
    if facet == "ui-visual":
        return "visual"
    if facet == "ui-geometry":
        return "ui-geometry"
    if facet in {"ui-structure", "ui-content", "ui-state", "ui-interaction", "responsive", "accessibility"}:
        return facet
    if facet == "error-copy":
        return "ui-content"
    if facet == "data-side-effect":
        return "database"
    if atom_requires_ui(source, atom):
        return "ui-state" if facet == "state-transition" else "ui"
    return {
        "state-transition": "event",
        "role-permission": "api",
        "non-functional": "trace",
        "negative-rule": "return",
        "acceptance-criterion": "return",
        "business-rule": "return",
    }.get(facet, "return")


def surface_for(text: str, path: str = "") -> str:
    haystack = f"{path} {text}".lower()
    scores = {
        surface: sum(1 for word in words if word.lower() in haystack)
        for surface, words in SURFACES.items()
    }
    winner, score = max(scores.items(), key=lambda item: (item[1], item[0]))
    return winner if score else "shell-home"


def document_surface(path: str, text: str) -> str:
    allowed: tuple[str, ...] | None = None
    for pattern, domains in DOC_SURFACE_DOMAINS:
        if re.search(pattern, path, re.I):
            allowed = domains
            break
    if not allowed:
        return surface_for(text, path)
    haystack = f"{path} {text}".lower()
    scores = {
        surface: sum(1 for word in SURFACES[surface] if word.lower() in haystack)
        for surface in allowed
    }
    winner, score = max(scores.items(), key=lambda item: (item[1], -allowed.index(item[0])))
    return winner if score else allowed[0]


def test_surface(path: str, title: str) -> str:
    allowed: tuple[str, ...] | None = None
    for pattern, domains in TEST_SURFACE_DOMAINS:
        if re.search(pattern, path, re.I):
            allowed = domains
            break
    if not allowed:
        return surface_for(title, path)
    haystack = title.lower()
    scores = {
        surface: sum(1 for word in SURFACES[surface] if word.lower() in haystack)
        for surface in allowed
    }
    winner, score = max(scores.items(), key=lambda item: (item[1], -allowed.index(item[0])))
    return winner if score else allowed[0]


def document_disposition(path: str) -> tuple[str, str]:
    for pattern, disposition, reason in DOC_DISPOSITIONS:
        if re.search(pattern, path, re.I):
            return disposition, reason
    return "product-normative", "Approved develop product specification or contract"


def discovered_source_disposition(path: str) -> tuple[str, str]:
    """Classify every non-Markdown/non-spec source in the frozen develop corpus."""
    if re.fullmatch(r"e2e/oracles/workbuddy-5\.3\.5-(?:automation|shell-home|sidebar-account)\.json", path):
        return "product-normative-structured-oracle", "Approved WorkBuddy CDP geometry, state, responsive and style Oracle"
    if path == "docs/expert-journey-phase2-coverage.yaml":
        return "release-governance", "Coverage and historical execution bookkeeping bind planning but do not supersede the referenced PRD"
    if path == "docs/audits/workbuddy-skills-audit.json":
        return "supporting-evidence", "Machine-readable audit evidence does not define product behavior by itself"
    if path.startswith("e2e/fixtures/"):
        return "execution-fixture", "Runner fixture required to reproduce an existing E2E route"
    if path.startswith("e2e/oracles/red/") or path.endswith("-red-evidence.json"):
        return "historical-red-evidence", "Red-stage evidence proves test causality but is not a product Oracle"
    if ".spec.ts-snapshots/" in path:
        return "implementation-screenshot-evidence", "QWork-generated screenshot verifies an implementation run and cannot approve itself as design"
    if path.startswith("docs/qconnector/") and pathlib.PurePosixPath(path).suffix in {".mjs", ".py", ".html", ".json"}:
        return "implementation-context", "Connector research, capture tooling or generated presentation context is not an approved product contract"
    if path == "docs/settings.json":
        return "implementation-context", "Repository-local settings are implementation context, not user-visible product behavior"
    return "supporting-evidence", "Discovered source is retained in the closed-world ledger but is not independently normative"


GEOMETRY_SUFFIXES = (
    "width",
    "height",
    "size",
    "gap",
    "inset",
    "offset",
    "radius",
    "padding",
    "margin",
    "top",
    "left",
    "right",
    "bottom",
    "fontsize",
    "lineheight",
)


def is_geometry_key(key: str) -> bool:
    lower = key.lower()
    return lower in {"x", "y"} or lower.endswith(GEOMETRY_SUFFIXES)


def structured_oracle_atoms(
    source_id: str,
    value: Any,
    *,
    surface: str,
    viewport: dict[str, int | float],
    pointer: str = "",
) -> list[dict[str, Any]]:
    """Flatten an approved structured WorkBuddy Oracle without losing exact scalar values."""
    atoms: list[dict[str, Any]] = []

    def evidence_only(segments: list[str]) -> bool:
        """Separate frozen-source provenance from observable product truth."""
        path = "/" + "/".join(segments)
        return (
            path == "/schemaVersion"
            or (path.startswith("/source/") and not path.endswith("/brandPolicy"))
            or path.startswith("/coverage/captured/")
            or path.startswith("/pixelBaseline/")
            or path.startswith("/editor/references/")
            or path in {
                "/templates/referenceImage",
                "/templates/referenceSha256",
                "/templates/referenceDimensions/width",
                "/templates/referenceDimensions/height",
            }
        )

    def visit(node: Any, segments: list[str]) -> None:
        if isinstance(node, dict):
            for key in sorted(node):
                visit(node[key], [*segments, str(key)])
            return
        if isinstance(node, list):
            for index, item in enumerate(node):
                visit(item, [*segments, str(index)])
            return
        json_pointer = "/" + "/".join(
            segment.replace("~", "~0").replace("/", "~1") for segment in segments
        )
        canonical = json.dumps(node, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        key = segments[-1] if segments else "root"
        atom_id = f"{source_id}:PTR:{sha256_text(json_pointer)[:14].upper()}"
        label = f"WorkBuddy structured Oracle {json_pointer} equals {canonical}"
        atom: dict[str, Any] = {
            "atom_id": atom_id,
            "facet": "ui-state",
            "locator": f"json-pointer:{json_pointer}",
            "label": label,
            "extracted_value_hash": f"sha256:{sha256_text(canonical)}",
            "surface": surface,
            "viewport": viewport,
        }
        if evidence_only(segments):
            atom.update(
                {
                    "facet": "evidence-provenance",
                    "evidence_only": True,
                }
            )
        elif isinstance(node, (int, float)) and not isinstance(node, bool) and is_geometry_key(key):
            atom.update(
                {
                    "facet": "ui-geometry",
                    "measurement_kind": "spacing",
                    "expected_css_px": node,
                    "target": "/" + "/".join(segments[:-1]) or "/",
                    "relation": f"property:{key}",
                }
            )
        atoms.append(atom)

    visit(value, [segment for segment in pointer.split("/") if segment])
    return atoms


STORAGE_DURABLE_ROOTS = {
    "artifact-index",
    "audit-log",
    "connectors",
    "local_storage",
    "memory",
    "plans",
    "project-resources",
    "projects",
    "sessions",
    "skills",
    "tasks",
    "teams",
    "workspace",
}
STORAGE_PACKAGE_ROOTS = {
    "binaries",
    "connectors-marketplace",
    "plugin-marketplace-state-new",
    "plugins",
}
STORAGE_REGENERATED_ROOTS = {"app", "logs", "shell-snapshots", "traces"}
STORAGE_DURABLE_FILES = {
    ".mcp.json",
    "BOOTSTRAP.md",
    "IDENTITY.md",
    "SOUL.md",
    "USER.md",
    "device-id",
    "mcp-approvals.json",
    "models.json",
    "settings.json",
    "user-state.json",
    "workbuddy.db",
    "workspace-state.json",
}

QWORK_STORAGE_TARGETS = {
    "plugins": "~/.qwork/plugins",
    "skills": "~/.qwork/skills",
    "sessions": "~/.qwork/sessions",
    "projects": "~/.qwork/work-gui/projects",
    "automations": "~/.qwork/work-gui/automations",
    "connectors": "~/.qwork/work-gui/connectors",
    "artifact-index": "~/.qwork/work-gui/files",
    "project-resources": "~/.qwork/work-gui/projects",
    "settings.json": "~/.qwork/settings.json",
}


def storage_entry_policy(entry: dict[str, Any]) -> tuple[str, str, str]:
    """Return migration treatment, priority and acceptance statement for one inventory entry."""
    path = str(entry["path"])
    root = path.split("/", 1)[0]
    if root in STORAGE_DURABLE_ROOTS or root in STORAGE_DURABLE_FILES or path.startswith("workbuddy.db"):
        return (
            "preserve-or-explicitly-transform",
            "P1",
            "preserve durable semantics and stable identity, or record an explicit versioned transform with restart/rollback proof",
        )
    if root in STORAGE_PACKAGE_ROOTS:
        return (
            "reinstall-by-canonical-identity",
            "P2",
            "resolve the package by one canonical identity/path and never persist marketplace aliases or version folders as logical identity",
        )
    if root in STORAGE_REGENERATED_ROOTS or root in {".DS_Store", "install-timing-reported", "last-launch.json"}:
        return (
            "regenerate-or-exclude",
            "P2",
            "regenerate or exclude runtime/cache material without treating it as durable user state",
        )
    return (
        "explicit-adjudication-required",
        "P2",
        "declare preserve, transform, reinstall, regenerate or exclude behavior before migration; silent dropping is forbidden",
    )


def storage_entry_disposition(entry: dict[str, Any]) -> dict[str, Any]:
    """Separate a source classification from a final product decision and implementation proof."""
    path = str(entry["path"])
    root = path.split("/", 1)[0]
    treatment, _priority, _acceptance = storage_entry_policy(entry)
    qwork_target = QWORK_STORAGE_TARGETS.get(root)
    if treatment == "regenerate-or-exclude":
        final_action = "exclude" if root == ".DS_Store" else "regenerate"
        return {
            "treatment": treatment,
            "final_action": final_action,
            "decision_status": "resolved",
            "implementation_status": "not-required",
            "qwork_target": None,
            "evidence": "runtime/cache data is not migrated as durable user state",
            "next_action": None,
        }
    if treatment == "reinstall-by-canonical-identity":
        return {
            "treatment": treatment,
            "final_action": "reinstall",
            "decision_status": "resolved",
            "implementation_status": "pending",
            "qwork_target": qwork_target,
            "evidence": "source classification is resolved; full-family QWork reinstall proof is not yet bound",
            "next_action": "bind a QWork canonical package identity, loader result and restart/rollback evidence for this family",
        }
    if treatment == "preserve-or-explicitly-transform":
        return {
            "treatment": treatment,
            "final_action": None,
            "decision_status": "pending",
            "implementation_status": "pending",
            "qwork_target": qwork_target,
            "evidence": "durable source state is inventoried, but preserve versus transform has not been adjudicated",
            "next_action": "choose preserve or versioned transform, then bind QWork target plus restart and rollback proof",
        }
    return {
        "treatment": treatment,
        "final_action": None,
        "decision_status": "pending",
        "implementation_status": "pending",
        "qwork_target": qwork_target,
        "evidence": "source entry is inventoried but has no approved migration treatment",
        "next_action": "adjudicate preserve, transform, reinstall, regenerate or exclude and bind implementation evidence",
    }


def markdown_atoms(source_id: str, content: str) -> list[dict[str, Any]]:
    atoms: list[dict[str, Any]] = []
    heading = "document"
    paragraph: list[tuple[int, str]] = []
    in_code = False

    def flush() -> None:
        nonlocal paragraph
        if not paragraph:
            return
        start = paragraph[0][0]
        text = normalized(" ".join(line for _, line in paragraph))
        paragraph = []
        if len(text) < 8:
            return
        add_atom(start, text)

    def add_atom(line: int, text: str) -> None:
        facet = classify(text, ui_hint=any(word in heading.lower() for word in ("ui", "界面", "页面", "布局", "视觉")))
        atom_id = f"{source_id}:L{line}:{sha256_text(text)[:10]}"
        atom: dict[str, Any] = {
            "atom_id": atom_id,
            "facet": facet,
            "locator": f"line:{line};heading:{heading}",
            "label": text[:240],
            "extracted_value_hash": f"sha256:{sha256_text(text)}",
        }
        measurement = geometry_measurement(text)
        if facet == "ui-geometry" and measurement:
            atom.update(measurement)
        elif facet == "ui-geometry":
            atom["measurement_kind"] = "spacing"
            atom["expected_css_px"] = first_number(text) or 1
        atoms.append(atom)

    for line_no, raw in enumerate(content.splitlines(), start=1):
        line = raw.strip()
        if line.startswith("```") or line.startswith("~~~"):
            flush()
            in_code = not in_code
            continue
        if in_code or not line:
            flush()
            continue
        match = re.match(r"^#{1,6}\s+(.+)$", line)
        if match:
            flush()
            heading = normalized(match.group(1))
            continue
        if re.match(r"^(?:[-*+] |\d+[.)] |\|)", line):
            flush()
            clean = re.sub(r"^(?:[-*+] |\d+[.)] )", "", line)
            if len(normalized(clean)) >= 8 and not re.fullmatch(r"\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)+\|?", line):
                add_atom(line_no, normalized(clean))
            continue
        paragraph.append((line_no, line))
    flush()
    return atoms


def lark_atoms(source_id: str, xml: str) -> list[dict[str, Any]]:
    root = ET.fromstring(f"<document>{xml}</document>")
    atoms: list[dict[str, Any]] = []
    heading = "document"
    accepted = {"p", "li", "tr", "blockquote", "whiteboard"}
    for element in root.iter():
        if element.tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            heading = normalized("".join(element.itertext())) or heading
            continue
        if element.tag not in accepted:
            continue
        # Only leaf-ish blocks; parent tables/lists would duplicate descendants.
        if element.tag in {"blockquote", "tr"} and any(child.tag in accepted for child in element.iter() if child is not element):
            continue
        text = normalized(" ".join(element.itertext()))
        if len(text) < 8:
            continue
        block_id = element.attrib.get("id") or f"anon-{len(atoms) + 1}"
        facet = classify(text, ui_hint=True)
        atom: dict[str, Any] = {
            "atom_id": f"{source_id}:{block_id}:{facet}",
            "facet": facet,
            "locator": f"block:{block_id};heading:{heading}",
            "label": text[:240],
            "extracted_value_hash": f"sha256:{sha256_text(text)}",
        }
        measurement = geometry_measurement(text)
        if facet == "ui-geometry" and measurement:
            atom.update(measurement)
        elif facet == "ui-geometry":
            atom["measurement_kind"] = "spacing"
            atom["expected_css_px"] = first_number(text) or 1
        atoms.append(atom)
    return atoms


def geometry_measurement(text: str) -> dict[str, Any] | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:px)?\s*[×x]\s*(\d+(?:\.\d+)?)\s*(?:px)?", text, re.I)
    if match:
        return {"measurement_kind": "size", "expected_width": float(match.group(1)), "expected_height": float(match.group(2))}
    match = re.search(r"(\d+(?:\.\d+)?)\s*px", text, re.I)
    if match:
        return {"measurement_kind": "spacing", "expected_css_px": float(match.group(1))}
    return None


def first_number(text: str) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


def cdp_surface(state: str) -> str:
    explicit = {
        "surface-新建任务": "shell-home",
        "surface-助理": "assistant",
        "surface-项目": "projects",
        "surface-专家-技能-连接器": "expert-market",
        "surface-market-专家": "expert-market",
        "surface-market-专家-list": "expert-market",
        "surface-market-专家团-list": "expert-team",
        "surface-market-技能": "skills",
        "surface-market-连接器": "connectors",
        "surface-自动化": "automations",
        "surface-automation-定时任务": "automations",
        "surface-automation-运行记录": "automations",
        "surface-资料库": "library",
        "surface-更多-应用-灵感": "library",
        "surface-library-我的邮箱": "library",
        "surface-library-腾讯文档": "library",
        "surface-library-ima知识库": "library",
        "surface-library-乐享知识库": "library",
        "surface-library-灵感": "library",
    }
    if state not in explicit:
        raise ValueError(f"unmapped WorkBuddy CDP state: {state}")
    return explicit[state]


def control_target(control: dict[str, Any], index: int) -> str:
    role = str(control.get("role") or "")
    aria = normalized(str(control.get("ariaLabel") or ""))
    title = normalized(str(control.get("title") or ""))
    text = normalized(str(control.get("text") or ""))[:100]
    return f"control[{index}] tag={control.get('tag') or 'unknown'} role={role or '-'} aria={aria or '-'} title={title or '-'} text={text or '-'}"


def cdp_atoms(source_id: str, snapshot_dir: pathlib.Path, manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    atoms: list[dict[str, Any]] = []
    metadata: dict[str, dict[str, Any]] = {}
    for record in manifest.get("records", []):
        state = str(record["state"])
        state_file = snapshot_dir / f"{state}.json"
        full = json.loads(state_file.read_text(encoding="utf-8"))
        surface = cdp_surface(state)
        state_key = f"{stable_slug(state).upper()}-{sha256_text(state)[:10].upper()}"
        screenshot_id = f"{source_id}:{state_key}:visual"
        transition_id = f"{source_id}:{state_key}:transition"
        viewport = full["viewport"]
        atoms.extend([
            {
                "atom_id": screenshot_id,
                "facet": "ui-visual",
                "locator": f"cdp-state:{state};screenshot:{full['screenshot']}",
                "label": f"WorkBuddy 5.3.12 state {state} is the current visual Oracle at {viewport['width']}x{viewport['height']} CSS px and DPR {viewport['dpr']}",
                "extracted_value_hash": f"sha256:{full['screenshot_sha256']}",
                "surface": surface,
            },
            {
                "atom_id": transition_id,
                "facet": "ui-interaction",
                "locator": f"cdp-state:{state};action:{json.dumps(full.get('action'), ensure_ascii=False, sort_keys=True)}",
                "label": f"The read-only action {json.dumps(full.get('action'), ensure_ascii=False, sort_keys=True)} reaches WorkBuddy state {state}",
                "extracted_value_hash": f"sha256:{sha256_text(json.dumps(full.get('action'), ensure_ascii=False, sort_keys=True))}",
                "surface": surface,
            },
        ])
        metadata[screenshot_id] = {"kind": "visual", "state": state, "record": full, "snapshot_dir": snapshot_dir}
        metadata[transition_id] = {"kind": "transition", "state": state, "record": full, "snapshot_dir": snapshot_dir}
        for index, control in enumerate(full.get("controls", [])):
            box = control.get("box") or {}
            target = control_target(control, index)
            geometry_id = f"{source_id}:{state_key}:CONTROL:{index}:geometry"
            content_id = f"{source_id}:{state_key}:CONTROL:{index}:content"
            style_hash = sha256_text(json.dumps(control.get("style") or {}, ensure_ascii=False, sort_keys=True))
            atoms.extend([
                {
                    "atom_id": geometry_id,
                    "facet": "ui-geometry",
                    "locator": f"cdp-state:{state};{target}",
                    "label": f"In WorkBuddy state {state}, {target} has CSS box x={box.get('x')} y={box.get('y')} width={box.get('width')} height={box.get('height')}",
                    "extracted_value_hash": f"sha256:{sha256_text(json.dumps(box, sort_keys=True))}",
                    "measurement_kind": "absolute-box",
                    "expected_box": box,
                    "surface": surface,
                },
                {
                    "atom_id": content_id,
                    "facet": "ui-state" if control.get("selected") or control.get("disabled") else "ui-structure",
                    "locator": f"cdp-state:{state};{target}",
                    "label": f"In WorkBuddy state {state}, {target} is visible with selected={bool(control.get('selected'))} disabled={bool(control.get('disabled'))} and computed-style sha256:{style_hash}",
                    "extracted_value_hash": f"sha256:{sha256_text(json.dumps(control, ensure_ascii=False, sort_keys=True))}",
                    "surface": surface,
                },
            ])
            metadata[geometry_id] = {"kind": "geometry", "state": state, "target": target, "control": control, "record": full}
            metadata[content_id] = {"kind": "content", "state": state, "target": target, "control": control, "record": full}
    return atoms, metadata


TEST_PATTERN = re.compile(
    r"(?m)^\s*(?:test|it)(?:\.(?:skip|only|fixme))?\s*\(\s*([\"'`])(.{3,240}?)\1",
)


def extract_playwright_contracts(path: str, content: str) -> dict[str, dict[str, Any]]:
    script = pathlib.Path(__file__).with_name("extract_playwright_contracts.mjs")
    result = subprocess.run(
        ["node", str(script), path],
        input=content,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    contracts: dict[str, dict[str, Any]] = {}
    for contract in payload.get("tests", []):
        title = normalized(str(contract["title"]))
        if title in contracts:
            raise ValueError(f"duplicate test title cannot form a stable route in {path}: {title}")
        contracts[title] = contract
    return contracts


def test_atoms(source_id: str, path: str, content: str) -> list[dict[str, Any]]:
    atoms: list[dict[str, Any]] = []
    contracts = extract_playwright_contracts(path, content)
    for match in TEST_PATTERN.finditer(content):
        title = normalized(match.group(2))
        line = content.count("\n", 0, match.start()) + 1
        facet = "negative-rule" if any(word in title.lower() for word in NEGATIVE_WORDS) else "acceptance-criterion"
        atom = {
                "atom_id": f"{source_id}:L{line}:{sha256_text(title)[:10]}",
                "facet": facet,
                "locator": f"line:{line};test:{title}",
                "label": title,
                "extracted_value_hash": f"sha256:{sha256_text(title)}",
            }
        contract = contracts.get(title)
        if not contract:
            raise ValueError(f"TypeScript AST could not bind test title in {path}: {title}")
        atom["test_contract"] = contract
        atoms.append(atom)
    unmatched = sorted(set(contracts) - {str(atom["label"]) for atom in atoms})
    if unmatched:
        raise ValueError(f"regex/AST test inventory mismatch in {path}: {unmatched[:20]}")
    return atoms


def make_source(
    source_id: str,
    source_type: str,
    authority: str,
    domain: str,
    locator: str,
    revision: str,
    content_hash: str,
    atoms: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "type": source_type,
        "authority_kind": authority,
        "authority_domain": domain,
        "approval_status": "approved" if authority == "normative" else "not-applicable",
        "locator": locator,
        "revision": revision,
        "content_hash": f"sha256:{content_hash}",
        "content_facets": sorted({str(atom["facet"]) for atom in atoms}),
        "inventory": {
            "extraction_status": "complete",
            "atom_count": len(atoms),
            "atoms": atoms,
        },
    }


def resolve_develop_e2e_execution(
    *,
    title: str,
    develop_atom: dict[str, Any],
    develop_revision: str,
    develop_content_sha256: str,
    head_entry: dict[str, Any] | None,
    head_revision: str,
) -> tuple[dict[str, Any], str, str, list[str]]:
    """Bind a develop E2E Case without assuming the feature HEAD contains it.

    The Dataset source universe intentionally combines the latest accepted
    develop docs/E2E with an independent expert feature/history HEAD.  A newer
    develop test is still valid executable evidence even before it is merged
    into the feature branch, but its current-worktree route is not runnable.
    Preserve the develop contract and expose that drift as a readiness blocker
    instead of rejecting the entire source closure.
    """

    current = next(
        (
            item
            for item in (head_entry or {}).get("atoms", [])
            if str(item["label"]) == title
        ),
        None,
    )
    if current is not None:
        return (
            current,
            head_revision,
            str((head_entry or {})["content_sha256"]),
            [],
        )
    return (
        develop_atom,
        develop_revision,
        develop_content_sha256,
        [
            "accepted develop E2E coordinate is not present in the current feature HEAD; merge or check out the frozen develop revision before execution"
        ],
    )


def default_case(
    case_id: str,
    title: str,
    surface: str,
    route_id: str,
    spec: str | None,
    categories: list[str],
    test_contract: dict[str, Any] | None = None,
    execution_revision: str | None = None,
    spec_sha256: str | None = None,
) -> dict[str, Any]:
    private_spec = bool(spec and spec.startswith("skill://qwork-test-dataset/"))
    private_runner = (
        "run_private_team_terminal_case.mjs"
        if spec and spec.endswith("/team-terminal-matrix.spec.ts")
        else "run_private_tool_failure_case.mjs"
        if spec and spec.endswith("/tool-failure-causality.spec.ts")
        else "run_private_sidebar_oracle_case.mjs"
        if spec and spec.endswith("/sidebar-account-oracle-completeness.spec.ts")
        else "run_private_shell_oracle_case.mjs"
        if spec and spec.endswith("/shell-home-oracle-completeness.spec.ts")
        else "run_private_automation_oracle_case.mjs"
        if spec and spec.endswith("/automation-oracle-gap-completeness.spec.ts")
        else "run_private_playwright_case.mjs"
    )
    command = (
        f"node .agents/skills/qwork-test-dataset/scripts/{private_runner} "
        f"--repo . --case-id {case_id} --case-title {json.dumps(title, ensure_ascii=False)}"
        if private_spec
        else f'npx playwright test {spec} -g {json.dumps(title, ensure_ascii=False)}'
        if spec
        else None
    )
    readiness = "partial"
    is_live = bool(
        spec
        and (
            ".live.spec.ts" in spec
            or "-live.spec.ts" in spec
            or "auth-real-login" in spec
            or spec == "e2e/real-expert-agent.spec.ts"
            or "@live" in title.lower()
        )
    )
    blockers = (
        ["independent authorization for real external route pending", "reference run pending"]
        if is_live
        else ["reference run pending", "case-level screenshot checkpoint audit pending"]
        if spec
        else ["dedicated QWork UI Oracle runner is not implemented", "reference run pending"]
    )
    actions = [str(item["expression"]) for item in (test_contract or {}).get("actions", [])]
    assertions = [str(item["expression"]) for item in (test_contract or {}).get("assertions", [])]
    helpers = [str(item["expression"]) for item in (test_contract or {}).get("helpers", [])]
    semantic_steps = actions or helpers[:12] or [title]
    semantic_outcomes = assertions or ["the specified user-visible state and durable outcome match the governing requirement"]
    return {
        "schema_version": 3,
        "id": case_id,
        "title": title,
        "kind": "negative" if "negative" in categories else "golden",
        "priority": "P0" if surface in {"auth", "assistant", "task-lifecycle", "expert-market", "expert-team", "permissions"} else "P1",
        "lifecycle_status": "active",
        "execution_type": "desktop",
        "execution_mode": "real-process",
        "coverage": {"capability_id": surface, "journey": surface, "states_covered": ["entry", "transition", "final-state"], "risk_ids": []},
        "sources": [],
        "derived_requirements": [],
        "verification": {"last_outcome": "pending", "environment_scope": "isolated Electron fixture", "implementation_revision": None, "last_verified_at": None, "status_reason": "generated baseline has not completed its reference run"},
        "preconditions": {"repository": "qwork", "isolated_config_home": True},
        "steps": [{"action": "launch isolated QWork Electron"}, *[{"action": value} for value in semantic_steps]],
        "expected_outcomes": semantic_outcomes,
        "forbidden_outcomes": ["silent failure", "false success", "state leakage outside the isolated fixture"],
        "oracles": [],
        "cleanup": {"action": "close Electron and remove the case-owned temporary state"},
        "evidence": ["entry screenshot", "transition screenshot", "final-state screenshot", "trace or durable-state evidence"],
        "ui_acceptance": {"viewport_profiles": [{"id": "darwin-default", "width": 1200, "height": 800, "dpr": 1}], "required_screenshot_states": ["entry", "transition", "final-state"]},
        "execution_contract": {
            "contract_version": 1,
            "readiness": readiness,
            "route_id": route_id,
            "target": {"kind": "installed-app", "platforms": ["darwin", "win32", "linux"], "artifact": ("skill://qwork-test-dataset/data/runs/<run-id>/app + Electron" if private_spec else "repo://out/main/index.js + Electron")},
            "authorization": {"required": is_live, "scopes": (["real external account/service/model route named by the source test"] if is_live else [])},
            "preflight": [
                {"action": "resolve repo revision and dependency lock", "oracle": "revision and lock hashes are recorded"},
                {"action": "allocate isolated QWork home", "oracle": "fixture path is unique and outside ~/.qwork"},
            ],
            "launch": {"strategy": "command" if command else "manual-blocked", "command_or_tool": command, "success_oracle": "Electron window and target surface are visible", "failure_action": "repair route or launcher; do not skip"},
            "navigation": {"kind": "ui-route", "entrypoint": surface, "steps": [{"action": value} for value in semantic_steps], "locator_strategy": "accessible role/name first; project locator registry fallback", "success_oracle": "all source-bound assertions pass", "failure_action": "capture screenshot and DOM/IPC evidence, then repair locator"},
            "fixtures": {"setup": ("case-owned temp home plus separately authorized real external fixture" if is_live else "case-owned temp home and deterministic fake sidecar unless live authority is explicit"), "isolation": "no reuse of ~/.qwork, real account, or production data without explicit Case authority", "cleanup": "close app and remove temp home"},
            "observability": {"artifacts": ["report.json", "entry.png", "transition.png", "final-state.png"], "correlation": "case_id + run_id + revision", "failure_classification": "product|fixture|route|environment|external", "source_contract": ({"spec": spec, "line_start": test_contract["line_start"], "line_end": test_contract["line_end"], "body_sha256": f"sha256:{test_contract['body_sha256']}", "assertion_count": len(assertions), "action_count": len(actions), "execution_revision": execution_revision, "spec_sha256": f"sha256:{spec_sha256}"} if test_contract else None)},
            "reference_run": {"status": "pending", "run_id": None, "verified_at": None, "environment": "not yet independently replayed"},
            "cleanup": {"actions": ["close Electron application", "remove case-owned temporary directory"], "success_oracle": "no case-owned process or temporary state remains"},
            "blockers": blockers,
        },
        "selection": {"requirement_ids": [], "categories": categories, "suite_ids": []},
    }


def compile_source_bound_causal_contract(case: dict[str, Any]) -> None:
    """Compile exact source Oracles into an auditable causal Case contract.

    Document requirements are not executable evidence by themselves. This
    function therefore makes their Given/When/Then and counterfactual failure
    explicit without changing route readiness or pretending that a runner
    exists. The runner must later replace the source-defined trigger with exact
    locators/commands while preserving this one-to-one Requirement closure.
    """

    requirements = {
        str(item["requirement_id"]): item
        for item in case.get("derived_requirements", [])
    }
    probes: list[dict[str, Any]] = []
    for oracle in case.get("oracles", []):
        requirement_id = str(oracle["requirement_id"])
        requirement = requirements.get(requirement_id)
        if requirement is None:
            raise ValueError(
                f"{case['id']} Oracle has no derived requirement: {requirement_id}"
            )
        assertion = str(oracle["assertion"])
        if not assertion.strip():
            raise ValueError(f"{case['id']} has an empty Oracle: {requirement_id}")
        oracle_type = str(oracle["type"])
        probes.append(
            {
                "requirement_id": requirement_id,
                "oracle_type": oracle_type,
                "given": (
                    "the isolated fixture is at the source-defined entry state and "
                    "the relevant pre-trigger UI, protocol and durable-state baseline is captured"
                ),
                "when": (
                    f"perform the source-defined scenario trigger for {case['title']} exactly once "
                    "and retain its correlation identity"
                ),
                "then": assertion,
                "observation_boundary": {
                    "ui": "renderer UI and navigation state",
                    "ui-structure": "renderer DOM and accessibility tree",
                    "ui-geometry": "renderer CSS-pixel geometry at the declared viewport and DPR",
                    "ui-content": "renderer visible content",
                    "ui-state": "renderer interaction state",
                    "ui-interaction": "renderer input/output interaction boundary",
                    "responsive": "renderer layout at every declared breakpoint",
                    "accessibility": "accessibility tree and keyboard interaction",
                    "visual": "pixel comparison at the declared viewport and DPR",
                    "aria": "accessibility tree",
                    "event": "session/sidecar event stream",
                    "api": "typed IPC or service API boundary",
                    "database": "case-owned durable database state",
                    "file": "case-owned filesystem state",
                    "network": "case-owned request ledger",
                    "return": "typed return value and side-effect ledger",
                    "console": "redacted case-owned console stream",
                    "log": "redacted case-owned structured log",
                    "trace": "case-owned execution trace",
                    "llm-judge": "frozen rubric and independently preserved response evidence",
                }.get(oracle_type, f"source-defined {oracle_type} boundary"),
                "failure_if": (
                    "the exact assertion is contradicted, omitted, only observed before the trigger, "
                    "or cannot be causally attributed to this one trigger"
                ),
            }
        )

    if not probes:
        raise ValueError(f"{case['id']} has no source-bound causal probes")

    original_first_step = dict(case["steps"][0])
    case["steps"] = [
        original_first_step,
        {
            "action": (
                "capture the pre-trigger baseline for "
                f"{case['coverage']['capability_id']} at every source-bound observation boundary"
            )
        },
        {
            "action": (
                "perform the source-defined scenario trigger for "
                f"{case['title']} exactly once; record the action, route and correlation identity"
            )
        },
        *[
            {
                "action": (
                    f"observe {probe['observation_boundary']} after the trigger and assert "
                    f"[{probe['requirement_id']}] exactly: {probe['then']}"
                )
            }
            for probe in probes
        ],
        {
            "action": (
                "compare the pre-trigger and post-trigger evidence, reject unrelated prior state, "
                "and preserve the per-Requirement causal verdict"
            )
        },
    ]
    case["expected_outcomes"] = list(
        dict.fromkeys(str(probe["then"]) for probe in probes)
    )
    case["forbidden_outcomes"] = [
        *[
            (
                f"FAIL [{probe['requirement_id']}]: evidence contradicts, omits, or cannot "
                f"causally attribute the exact Oracle: {probe['then']}"
            )
            for probe in probes
        ],
        "false success from pre-existing state, an unrelated event, or evidence captured before the trigger",
        "state leakage outside the isolated fixture",
    ]
    case["causal_probe_plan"] = probes
    case["execution_contract"]["navigation"]["steps"] = case["steps"][1:]
    case["execution_contract"]["navigation"]["success_oracle"] = (
        "every causal probe has one post-trigger observation, exact Requirement verdict and "
        "counterfactual failure check"
    )


def mark_private_reference_stale(
    case: dict[str, Any],
    reference: dict[str, Any],
    report: dict[str, Any],
    reason: str,
) -> None:
    """Retain historical evidence without treating it as current authority."""

    contract = case["execution_contract"]
    run_id = str(reference["run_id"])
    contract["reference_run"] = {
        "status": "pending",
        "run_id": run_id,
        "verified_at": str(report["finished_at"]),
        "environment": (
            "historical isolated Electron evidence retained; current runner/source authority "
            "requires a new zero-live-call reference run"
        ),
    }
    contract["readiness"] = "partial"
    contract["blockers"] = [reason]
    case["verification"] = {
        "last_outcome": "pending",
        "environment_scope": contract["reference_run"]["environment"],
        "implementation_revision": str(report["source"]["implementation_revision"]),
        "last_verified_at": str(report["finished_at"]),
        "status_reason": f"stale private reference {run_id}: {reason}",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--develop", default="develop")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--lark-snapshot", required=True)
    parser.add_argument("--storage-snapshot", required=True)
    parser.add_argument("--visual-manifest", required=True)
    parser.add_argument("--cdp-snapshot", required=True)
    parser.add_argument("--develop-snapshot", required=True)
    parser.add_argument(
        "--qwork-oracle-report",
        help="optional current-revision QWork-to-WorkBuddy Oracle report used to bind reference-run truth",
    )
    args = parser.parse_args()

    repo = pathlib.Path(args.repo).resolve()
    final_output = pathlib.Path(args.output_root).resolve()
    final_output.parent.mkdir(parents=True, exist_ok=True)
    output = pathlib.Path(
        tempfile.mkdtemp(prefix=f".{final_output.name}.staging-", dir=final_output.parent)
    )
    atexit.register(lambda: shutil.rmtree(output, ignore_errors=True))
    cases_dir = output / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    develop = run_git(repo, "rev-parse", args.develop).strip()
    head = run_git(repo, "rev-parse", args.head).strip()
    created_at = dt.datetime.now(dt.timezone.utc).isoformat()
    skill_root = output.parent.parent
    structured_coverage_map = yaml.safe_load(
        (skill_root / "references/structured-oracle-coverage-map.yaml").read_text(
            encoding="utf-8"
        )
    )
    document_coverage_map = yaml.safe_load(
        (skill_root / "references/document-case-coverage-map.yaml").read_text(
            encoding="utf-8"
        )
    )
    document_atom_dispositions = yaml.safe_load(
        (skill_root / "references/document-atom-dispositions.yaml").read_text(
            encoding="utf-8"
        )
    )
    private_reference_runs = yaml.safe_load(
        (skill_root / "references/private-reference-runs.yaml").read_text(
            encoding="utf-8"
        )
    )

    sources: list[dict[str, Any]] = []
    requirements: list[dict[str, Any]] = []
    cases: dict[str, dict[str, Any]] = {}
    source_atom_to_case: dict[str, str] = {}
    source_dispositions: list[dict[str, Any]] = []
    storage_dispositions: list[dict[str, Any]] = []
    e2e_case_by_coordinate: dict[tuple[str, str], str] = {}

    head_e2e: dict[str, dict[str, Any]] = {}
    for path in sorted(
        value
        for value in run_git(repo, "ls-tree", "-r", "--name-only", head, "e2e").splitlines()
        if value.endswith(".spec.ts")
    ):
        content = run_git(repo, "show", f"{head}:{path}")
        head_e2e[path] = {
            "content": content,
            "content_sha256": sha256_text(content),
            "atoms": test_atoms(f"QHEAD-E2E-{stable_slug(path)}", path, content),
        }

    private_e2e_root = skill_root / "data/e2e"
    private_e2e_specs: list[dict[str, Any]] = []
    for private_path in sorted(private_e2e_root.glob("*.spec.ts")):
        relative = private_path.relative_to(private_e2e_root).as_posix()
        locator = f"skill://qwork-test-dataset/data/e2e/{relative}"
        content = private_path.read_text(encoding="utf-8")
        source_id = f"QPRIVATE-E2E-{stable_slug(relative)}"
        private_e2e_specs.append({
            "path": private_path,
            "locator": locator,
            "content": content,
            "content_sha256": sha256_text(content),
            "source_id": source_id,
            "atoms": test_atoms(source_id, locator, content),
        })
    if not private_e2e_specs:
        raise ValueError("private functional E2E source set is empty")

    develop_snapshot = pathlib.Path(args.develop_snapshot).resolve()
    develop_snapshot_manifest = json.loads(
        (develop_snapshot / "manifest.json").read_text(encoding="utf-8")
    )
    if str(develop_snapshot_manifest.get("revision")) != develop:
        raise ValueError(
            "develop snapshot revision does not match the requested develop revision"
        )
    develop_inventory = json.loads(
        (develop_snapshot / "inventory.json").read_text(encoding="utf-8")
    )
    develop_closed_world = {
        str(item["path"]): item
        for item in develop_inventory
        if str(item.get("path", "")).startswith(("docs/", "e2e/"))
    }

    def register_case(case: dict[str, Any]) -> str:
        existing = cases.get(case["id"])
        if existing is None:
            cases[case["id"]] = case
        return str(case["id"])

    def case_for_surface(surface: str) -> str:
        matching = [case_id for case_id, case in cases.items() if case["coverage"]["capability_id"] == surface and case["execution_contract"]["launch"]["strategy"] != "manual-blocked"]
        if matching:
            return sorted(matching)[0]
        case_id = f"QW-E2E-GAP-{surface.upper()}"
        register_case(default_case(case_id, f"补齐 {surface} 全链路产品验收", surface, f"qwork.gap.{surface}", None, ["business", "ui-interaction", "ui-state"]))
        return case_id

    def case_for_source_group(
        source_id: str,
        group: str,
        surface: str,
        title: str,
        categories: list[str],
    ) -> str:
        identity = f"{source_id}\0{group}\0{surface}"
        case_id = (
            f"QW-REQ-{stable_slug(source_id, 34).upper()}-"
            f"{stable_slug(group, 34).upper()}-{sha256_text(identity)[:8].upper()}"
        )
        route_id = (
            f"qwork.requirement.{stable_slug(source_id, 36)}."
            f"{stable_slug(group, 28)}-{sha256_text(identity)[:10]}"
        )
        register_case(default_case(case_id, title, surface, route_id, None, categories))
        return case_id

    def heading_group(atom: dict[str, Any]) -> str:
        locator = str(atom.get("locator") or "")
        match = re.search(r"(?:^|;)heading:([^;]+)", locator)
        return normalized(match.group(1)) if match else "document"

    # Develop E2E is executable evidence and provides the initial route registry.
    develop_paths = run_git(repo, "ls-tree", "-r", "--name-only", develop, "e2e").splitlines()
    for path in sorted(path for path in develop_paths if path.endswith(".spec.ts")):
        content = run_git(repo, "show", f"{develop}:{path}")
        develop_content_sha256 = sha256_text(content)
        source_id = f"QDEV-E2E-{stable_slug(path)}"
        atoms = test_atoms(source_id, path, content)
        if not atoms:
            continue
        sources.append(make_source(source_id, "git-e2e", "evidence", "execution", f"git:{develop}:{path}", develop, sha256_text(content), atoms))
        source_dispositions.append({"locator": f"git:{develop}:{path}", "path": path, "disposition": "executable-evidence", "reason": "Existing Electron E2E supplies an execution route and supporting evidence; its assertions do not supersede product Oracle", "content_sha256": sha256_text(content)})
        for atom in atoms:
            title = str(atom["label"])
            execution_atom, execution_revision, execution_spec_sha256, drift_blockers = (
                resolve_develop_e2e_execution(
                    title=title,
                    develop_atom=atom,
                    develop_revision=develop,
                    develop_content_sha256=develop_content_sha256,
                    head_entry=head_e2e.get(path),
                    head_revision=head,
                )
            )
            surface = test_surface(path, title)
            case_id = f"QW-E2E-{stable_slug(pathlib.Path(path).stem).upper()}-{sha256_text(title)[:8].upper()}"
            facet = str(atom["facet"])
            categories = sorted(set(FACET_CATEGORIES[facet] + ["ui-interaction", "ui-state"]))
            route_id = f"qwork.playwright.{stable_slug(path)}.{sha256_text(title)[:10]}"
            case = default_case(
                case_id,
                title,
                surface,
                route_id,
                path,
                categories,
                execution_atom.get("test_contract"),
                execution_revision,
                execution_spec_sha256,
            )
            if drift_blockers:
                case["execution_contract"]["blockers"] = [
                    *drift_blockers,
                    *case["execution_contract"]["blockers"],
                ]
                case["verification"]["status_reason"] = drift_blockers[0]
            register_case(case)
            source_atom_to_case[str(atom["atom_id"])] = case_id
            e2e_case_by_coordinate[(path, title)] = case_id

    # Private Dataset E2E is the canonical implementation home for product
    # acceptance routes that must not be committed to the shared repository.
    # The complete Skill source and each test body are hash-bound; execution
    # always builds into a case-owned private directory and uses fake-sidecar.
    private_supporting = [
        ("skill://qwork-test-dataset/data/e2e/fixtures/capture-electron-runtime.ts", skill_root / "data/e2e/fixtures/capture-electron-runtime.ts"),
        ("skill://qwork-test-dataset/data/e2e/fixtures/launch-isolated.ts", skill_root / "data/e2e/fixtures/launch-isolated.ts"),
        ("skill://qwork-test-dataset/scripts/private-case-authority.mjs", skill_root / "scripts/private-case-authority.mjs"),
        ("skill://qwork-test-dataset/scripts/run_private_playwright_case.mjs", skill_root / "scripts/run_private_playwright_case.mjs"),
        ("skill://qwork-test-dataset/scripts/build_isolated_electron.mjs", skill_root / "scripts/build_isolated_electron.mjs"),
        ("skill://qwork-test-dataset/scripts/electron-isolated-build.config.ts", skill_root / "scripts/electron-isolated-build.config.ts"),
        ("skill://qwork-test-dataset/scripts/playwright-private.config.ts", skill_root / "scripts/playwright-private.config.ts"),
        ("skill://qwork-test-dataset/package.json", skill_root / "package.json"),
        ("repo://e2e/fixtures/fake-sidecar.mjs", repo / "e2e/fixtures/fake-sidecar.mjs"),
        ("repo://e2e/fixtures/workbuddy-ui.ts", repo / "e2e/fixtures/workbuddy-ui.ts"),
    ]
    team_terminal_supporting = [
        ("skill://qwork-test-dataset/data/e2e/fixtures/capture-electron-runtime.ts", skill_root / "data/e2e/fixtures/capture-electron-runtime.ts"),
        ("skill://qwork-test-dataset/data/e2e/fixtures/launch-team-terminal-isolated.ts", skill_root / "data/e2e/fixtures/launch-team-terminal-isolated.ts"),
        ("skill://qwork-test-dataset/data/e2e/fixtures/team-terminal-sidecar.mjs", skill_root / "data/e2e/fixtures/team-terminal-sidecar.mjs"),
        ("skill://qwork-test-dataset/scripts/run_private_team_terminal_case.mjs", skill_root / "scripts/run_private_team_terminal_case.mjs"),
        ("skill://qwork-test-dataset/scripts/private-case-authority.mjs", skill_root / "scripts/private-case-authority.mjs"),
        ("skill://qwork-test-dataset/scripts/run_private_playwright_case.mjs", skill_root / "scripts/run_private_playwright_case.mjs"),
        ("skill://qwork-test-dataset/scripts/build_isolated_electron.mjs", skill_root / "scripts/build_isolated_electron.mjs"),
        ("skill://qwork-test-dataset/scripts/electron-isolated-build.config.ts", skill_root / "scripts/electron-isolated-build.config.ts"),
        ("skill://qwork-test-dataset/scripts/playwright-private.config.ts", skill_root / "scripts/playwright-private.config.ts"),
        ("skill://qwork-test-dataset/package.json", skill_root / "package.json"),
        ("repo://e2e/fixtures/workbuddy-ui.ts", repo / "e2e/fixtures/workbuddy-ui.ts"),
    ]
    tool_failure_supporting = [
        ("skill://qwork-test-dataset/data/e2e/fixtures/capture-electron-runtime.ts", skill_root / "data/e2e/fixtures/capture-electron-runtime.ts"),
        ("skill://qwork-test-dataset/data/e2e/fixtures/launch-tool-failure-isolated.ts", skill_root / "data/e2e/fixtures/launch-tool-failure-isolated.ts"),
        ("skill://qwork-test-dataset/data/e2e/fixtures/tool-failure-sidecar.mjs", skill_root / "data/e2e/fixtures/tool-failure-sidecar.mjs"),
        ("skill://qwork-test-dataset/scripts/run_private_tool_failure_case.mjs", skill_root / "scripts/run_private_tool_failure_case.mjs"),
        ("skill://qwork-test-dataset/scripts/private-case-authority.mjs", skill_root / "scripts/private-case-authority.mjs"),
        ("skill://qwork-test-dataset/scripts/run_private_playwright_case.mjs", skill_root / "scripts/run_private_playwright_case.mjs"),
        ("skill://qwork-test-dataset/scripts/build_isolated_electron.mjs", skill_root / "scripts/build_isolated_electron.mjs"),
        ("skill://qwork-test-dataset/scripts/electron-isolated-build.config.ts", skill_root / "scripts/electron-isolated-build.config.ts"),
        ("skill://qwork-test-dataset/scripts/playwright-private.config.ts", skill_root / "scripts/playwright-private.config.ts"),
        ("skill://qwork-test-dataset/package.json", skill_root / "package.json"),
        ("repo://e2e/fixtures/workbuddy-ui.ts", repo / "e2e/fixtures/workbuddy-ui.ts"),
    ]
    sidebar_oracle_supporting = [
        ("skill://qwork-test-dataset/data/e2e/fixtures/capture-electron-runtime.ts", skill_root / "data/e2e/fixtures/capture-electron-runtime.ts"),
        ("skill://qwork-test-dataset/data/e2e/fixtures/launch-isolated.ts", skill_root / "data/e2e/fixtures/launch-isolated.ts"),
        ("skill://qwork-test-dataset/scripts/run_private_sidebar_oracle_case.mjs", skill_root / "scripts/run_private_sidebar_oracle_case.mjs"),
        ("skill://qwork-test-dataset/scripts/private-case-authority.mjs", skill_root / "scripts/private-case-authority.mjs"),
        ("skill://qwork-test-dataset/scripts/run_private_playwright_case.mjs", skill_root / "scripts/run_private_playwright_case.mjs"),
        ("skill://qwork-test-dataset/scripts/build_isolated_electron.mjs", skill_root / "scripts/build_isolated_electron.mjs"),
        ("skill://qwork-test-dataset/scripts/electron-isolated-build.config.ts", skill_root / "scripts/electron-isolated-build.config.ts"),
        ("skill://qwork-test-dataset/scripts/playwright-private.config.ts", skill_root / "scripts/playwright-private.config.ts"),
        ("skill://qwork-test-dataset/package.json", skill_root / "package.json"),
        ("repo://e2e/fixtures/fake-sidecar.mjs", repo / "e2e/fixtures/fake-sidecar.mjs"),
        ("repo://e2e/fixtures/workbuddy-ui.ts", repo / "e2e/fixtures/workbuddy-ui.ts"),
    ]
    shell_oracle_supporting = [
        ("skill://qwork-test-dataset/data/e2e/fixtures/capture-electron-runtime.ts", skill_root / "data/e2e/fixtures/capture-electron-runtime.ts"),
        ("skill://qwork-test-dataset/data/e2e/fixtures/launch-isolated.ts", skill_root / "data/e2e/fixtures/launch-isolated.ts"),
        ("skill://qwork-test-dataset/scripts/run_private_shell_oracle_case.mjs", skill_root / "scripts/run_private_shell_oracle_case.mjs"),
        ("skill://qwork-test-dataset/scripts/private-case-authority.mjs", skill_root / "scripts/private-case-authority.mjs"),
        ("skill://qwork-test-dataset/scripts/run_private_playwright_case.mjs", skill_root / "scripts/run_private_playwright_case.mjs"),
        ("skill://qwork-test-dataset/scripts/build_isolated_electron.mjs", skill_root / "scripts/build_isolated_electron.mjs"),
        ("skill://qwork-test-dataset/scripts/electron-isolated-build.config.ts", skill_root / "scripts/electron-isolated-build.config.ts"),
        ("skill://qwork-test-dataset/scripts/playwright-private.config.ts", skill_root / "scripts/playwright-private.config.ts"),
        ("skill://qwork-test-dataset/package.json", skill_root / "package.json"),
        ("repo://e2e/fixtures/fake-sidecar.mjs", repo / "e2e/fixtures/fake-sidecar.mjs"),
        ("repo://e2e/fixtures/workbuddy-ui.ts", repo / "e2e/fixtures/workbuddy-ui.ts"),
    ]
    automation_oracle_supporting = [
        ("skill://qwork-test-dataset/data/e2e/fixtures/capture-electron-runtime.ts", skill_root / "data/e2e/fixtures/capture-electron-runtime.ts"),
        ("skill://qwork-test-dataset/data/e2e/fixtures/launch-isolated.ts", skill_root / "data/e2e/fixtures/launch-isolated.ts"),
        ("skill://qwork-test-dataset/scripts/run_private_automation_oracle_case.mjs", skill_root / "scripts/run_private_automation_oracle_case.mjs"),
        ("skill://qwork-test-dataset/scripts/private-case-authority.mjs", skill_root / "scripts/private-case-authority.mjs"),
        ("skill://qwork-test-dataset/scripts/run_private_playwright_case.mjs", skill_root / "scripts/run_private_playwright_case.mjs"),
        ("skill://qwork-test-dataset/scripts/build_isolated_electron.mjs", skill_root / "scripts/build_isolated_electron.mjs"),
        ("skill://qwork-test-dataset/scripts/electron-isolated-build.config.ts", skill_root / "scripts/electron-isolated-build.config.ts"),
        ("skill://qwork-test-dataset/scripts/playwright-private.config.ts", skill_root / "scripts/playwright-private.config.ts"),
        ("skill://qwork-test-dataset/package.json", skill_root / "package.json"),
        ("repo://e2e/fixtures/fake-sidecar.mjs", repo / "e2e/fixtures/fake-sidecar.mjs"),
        ("repo://e2e/fixtures/workbuddy-ui.ts", repo / "e2e/fixtures/workbuddy-ui.ts"),
    ]
    for private_spec in private_e2e_specs:
        sources.append(
            make_source(
                private_spec["source_id"],
                "private-dataset-e2e",
                "evidence",
                "execution",
                private_spec["locator"],
                head,
                private_spec["content_sha256"],
                private_spec["atoms"],
            )
        )
        for atom in private_spec["atoms"]:
            title = str(atom["label"])
            surface = test_surface(private_spec["locator"], title)
            case_id = (
                "QW-E2E-PRIVATE-FUNCTIONAL-CONTRACTS-SPEC-"
                f"{sha256_text(title)[:8].upper()}"
            )
            categories = sorted(
                set(FACET_CATEGORIES[str(atom["facet"])] + ["ui-interaction", "ui-state", "recovery"])
            )
            route_id = f"qwork.private-playwright.{stable_slug(private_spec['path'].stem)}.{sha256_text(title)[:10]}"
            case = default_case(
                case_id,
                title,
                surface,
                route_id,
                private_spec["locator"],
                categories,
                atom.get("test_contract"),
                head,
                private_spec["content_sha256"],
            )
            supporting_contracts = (
                team_terminal_supporting
                if private_spec["path"].name == "team-terminal-matrix.spec.ts"
                else tool_failure_supporting
                if private_spec["path"].name == "tool-failure-causality.spec.ts"
                else sidebar_oracle_supporting
                if private_spec["path"].name == "sidebar-account-oracle-completeness.spec.ts"
                else shell_oracle_supporting
                if private_spec["path"].name == "shell-home-oracle-completeness.spec.ts"
                else automation_oracle_supporting
                if private_spec["path"].name == "automation-oracle-gap-completeness.spec.ts"
                else private_supporting
            )
            case["execution_contract"]["observability"]["source_contract"]["supporting_contracts"] = [
                {
                    "path": locator,
                    "revision": head,
                    "sha256": f"sha256:{sha256_bytes(path.read_bytes())}",
                    "purpose": "private Electron launcher, runner, build configuration or deterministic repository fixture",
                }
                for locator, path in supporting_contracts
            ]
            register_case(case)
            source_atom_to_case[str(atom["atom_id"])] = case_id
            e2e_case_by_coordinate[(private_spec["locator"], title)] = case_id

    # Normative develop docs.
    develop_docs = run_git(repo, "ls-tree", "-r", "--name-only", develop, "docs").splitlines()
    for path in sorted(path for path in develop_docs if path.endswith(".md")):
        content = run_git(repo, "show", f"{develop}:{path}")
        disposition, disposition_reason = document_disposition(path)
        source_dispositions.append({"locator": f"git:{develop}:{path}", "path": path, "disposition": disposition, "reason": disposition_reason, "content_sha256": sha256_text(content)})
        if disposition != "product-normative":
            continue
        source_id = f"QDEV-DOC-{stable_slug(path)}"
        atoms = markdown_atoms(source_id, content)
        if not atoms:
            continue
        sources.append(make_source(source_id, "git-document", "normative", "product", f"git:{develop}:{path}", develop, sha256_text(content), atoms))
        for atom in atoms:
            surface = document_surface(path, str(atom["label"]))
            group = heading_group(atom)
            source_atom_to_case[str(atom["atom_id"])] = case_for_source_group(
                source_id,
                group,
                surface,
                f"{path} · {group} 产品契约",
                FACET_CATEGORIES[str(atom["facet"])],
            )

    # Every remaining frozen develop source receives an explicit, hash-bound disposition.
    # Approved structured WorkBuddy JSON Oracles are compiled into exact scalar requirements;
    # fixtures, red evidence, implementation snapshots and research artifacts remain traceable
    # without being promoted into product truth.
    disposed_develop_paths = {
        str(item["path"])
        for item in source_dispositions
        if str(item["locator"]).startswith(f"git:{develop}:")
    }
    structured_surfaces = {
        "e2e/oracles/workbuddy-5.3.5-automation.json": "automations",
        "e2e/oracles/workbuddy-5.3.5-shell-home.json": "shell-home",
        "e2e/oracles/workbuddy-5.3.5-sidebar-account.json": "shell-home",
    }
    for path in sorted(set(develop_closed_world) - disposed_develop_paths):
        blob = run_git_blob(repo, develop, path)
        content_sha256 = sha256_bytes(blob)
        disposition, disposition_reason = discovered_source_disposition(path)
        source_dispositions.append(
            {
                "locator": f"git:{develop}:{path}",
                "path": path,
                "disposition": disposition,
                "reason": disposition_reason,
                "content_sha256": content_sha256,
                "blob_sha1": str(develop_closed_world[path].get("blob_sha1") or ""),
                "size": int(develop_closed_world[path].get("size") or len(blob)),
            }
        )
        if disposition != "product-normative-structured-oracle":
            continue
        structured = json.loads(blob.decode("utf-8"))
        surface = structured_surfaces[path]
        source_id = f"WORKBUDDY-ORACLE-5-3-5-{stable_slug(pathlib.PurePosixPath(path).stem).upper()}"
        source_viewport = {"width": 1681, "height": 1084, "dpr": 1}
        atoms = structured_oracle_atoms(
            source_id,
            structured,
            surface=surface,
            viewport=source_viewport,
        )
        sources.append(
            make_source(
                source_id,
                "structured-workbuddy-oracle",
                "normative",
                "ui-geometry-state-responsive-style",
                f"git:{develop}:{path}",
                develop,
                content_sha256,
                atoms,
            )
        )
        for atom in atoms:
            pointer = str(atom["locator"]).removeprefix("json-pointer:")
            pointer_parts = [part for part in pointer.split("/") if part]
            group = next(iter(pointer_parts), "root")
            if atom.get("evidence_only"):
                # Evidence metadata nested under a product group (for example
                # editor/references) must not inherit that group's Electron
                # route or make its PASS appear to prove product behavior.
                group = "evidence-" + "-".join(pointer_parts[:2] or ["root"])
            source_atom_to_case[str(atom["atom_id"])] = case_for_source_group(
                source_id,
                group,
                surface,
                f"WorkBuddy 5.3.5 {surface} · {group} 结构化 Oracle",
                FACET_CATEGORIES[str(atom["facet"])],
            )

    closed_world_paths = set(develop_closed_world)
    ledger_paths = {
        str(item["path"])
        for item in source_dispositions
        if str(item["locator"]).startswith(f"git:{develop}:")
    }
    if ledger_paths != closed_world_paths:
        missing = sorted(closed_world_paths - ledger_paths)
        extra = sorted(ledger_paths - closed_world_paths)
        raise ValueError(
            f"develop docs/e2e ledger is not closed: missing={missing[:20]} extra={extra[:20]}"
        )

    # Current expert/team documents plus every changed/new current E2E source.
    # Tests retain their stable coordinate Case while develop and HEAD remain
    # separate source lineage records. The executable contract always binds HEAD.
    head_paths = run_git(repo, "ls-tree", "-r", "--name-only", head, "docs", "e2e").splitlines()
    for path in sorted(
        path for path in head_paths
        if path.endswith((".md", ".spec.ts"))
        and (path.endswith(".spec.ts") or re.search(r"expert|workbuddy", path, re.I))
    ):
        content = run_git(repo, "show", f"{head}:{path}")
        develop_content = run_git(repo, "show", f"{develop}:{path}", check=False)
        if develop_content and sha256_text(develop_content) == sha256_text(content):
            source_dispositions.append({"locator": f"git:{head}:{path}", "path": path, "disposition": "deduplicated-identical-to-develop", "reason": "Current expert/history file is byte-identical to the accepted develop source", "content_sha256": sha256_text(content)})
            continue
        is_spec = path.endswith(".spec.ts")
        if not is_spec:
            disposition, disposition_reason = document_disposition(path)
            source_dispositions.append({"locator": f"git:{head}:{path}", "path": path, "disposition": disposition, "reason": disposition_reason, "content_sha256": sha256_text(content)})
            if disposition != "product-normative":
                continue
        else:
            source_dispositions.append({"locator": f"git:{head}:{path}", "path": path, "disposition": "executable-evidence", "reason": "Changed/new expert E2E evidence in current head", "content_sha256": sha256_text(content)})
        source_id = f"QHEAD-{'E2E' if is_spec else 'DOC'}-{stable_slug(path)}"
        atoms = (
            test_atoms(source_id, path, content)
            if is_spec
            else markdown_atoms(source_id, content)
        )
        if not atoms:
            continue
        sources.append(make_source(source_id, "git-e2e" if is_spec else "git-document", "evidence" if is_spec else "normative", "execution" if is_spec else "product", f"git:{head}:{path}", head, sha256_text(content), atoms))
        for atom in atoms:
            if is_spec:
                title = str(atom["label"])
                surface = test_surface(path, title)
                coordinate = (path, title)
                existing_case_id = e2e_case_by_coordinate.get(coordinate)
                if existing_case_id:
                    source_atom_to_case[str(atom["atom_id"])] = existing_case_id
                    continue
                case_id = f"QW-E2E-{stable_slug(pathlib.Path(path).stem).upper()}-{sha256_text(title)[:8].upper()}"
                categories = sorted(set(FACET_CATEGORIES[str(atom["facet"])] + ["ui-interaction", "ui-state"]))
                route_id = f"qwork.playwright.{stable_slug(path)}.{sha256_text(title)[:10]}"
                register_case(
                    default_case(
                        case_id,
                        title,
                        surface,
                        route_id,
                        path,
                        categories,
                        atom.get("test_contract"),
                        head,
                        sha256_text(content),
                    )
                )
                e2e_case_by_coordinate[coordinate] = case_id
                source_atom_to_case[str(atom["atom_id"])] = case_id
            else:
                surface = document_surface(path, str(atom["label"]))
                group = heading_group(atom)
                source_atom_to_case[str(atom["atom_id"])] = case_for_source_group(
                    source_id,
                    group,
                    surface,
                    f"{path} · {group} 产品契约",
                    FACET_CATEGORIES[str(atom["facet"])],
                )

    # User-approved WorkBuddy reverse-engineering document.
    lark_dir = pathlib.Path(args.lark_snapshot).resolve()
    lark_xml = (lark_dir / "document.xml").read_text(encoding="utf-8")
    lark_manifest = json.loads((lark_dir / "manifest.json").read_text(encoding="utf-8"))
    lark_source_id = "WORKBUDDY-FEISHU-B4QJ-REV95"
    atoms = lark_atoms(lark_source_id, lark_xml)
    sources.append(make_source(lark_source_id, "lark-document", "normative", "product-ui-storage", str(lark_manifest["source_locator"]), str(lark_manifest["revision_id"]), str(lark_manifest["content_sha256"]), atoms))
    for atom in atoms:
        surface = surface_for(str(atom["label"]))
        group = heading_group(atom)
        source_atom_to_case[str(atom["atom_id"])] = case_for_source_group(
            lark_source_id,
            group,
            surface,
            f"WorkBuddy 飞书需求 · {group}",
            FACET_CATEGORIES[str(atom["facet"])],
        )

    # Frozen WorkBuddy images: visual requirements are covered; CSS geometry remains blocked until CDP measures viewport/DPR.
    visual_path = pathlib.Path(args.visual_manifest).resolve()
    visual_manifest = json.loads(visual_path.read_text(encoding="utf-8"))
    fallback_visual = visual_manifest["images"][0]
    visual_atoms: list[dict[str, Any]] = []
    visual_meta: dict[str, dict[str, Any]] = {}
    cdp_meta: dict[str, dict[str, Any]] = {}
    for image in visual_manifest["images"]:
        image_id = stable_slug(str(image["original_name"])).upper()
        visual_atom_id = f"WORKBUDDY-VISUAL:{image_id}:visual"
        geometry_atom_id = f"WORKBUDDY-VISUAL:{image_id}:geometry"
        image_size_hash = sha256_text(f"{image['width']}x{image['height']}")
        visual_atoms.extend([
            {"atom_id": visual_atom_id, "facet": "ui-visual", "locator": f"block:{image['block_id']};image:{image['original_name']}", "label": f"WorkBuddy visual state {image['original_name']}", "extracted_value_hash": f"sha256:{image['sha256']}"},
            {"atom_id": geometry_atom_id, "facet": "ui-geometry", "locator": f"block:{image['block_id']};image:{image['original_name']}", "label": f"WorkBuddy source image pixel size {image['width']}x{image['height']} for {image['original_name']}", "extracted_value_hash": f"sha256:{image_size_hash}", "measurement_kind": "size", "expected_width": image["width"], "expected_height": image["height"]},
        ])
        visual_meta[visual_atom_id] = image
        visual_meta[geometry_atom_id] = image
        image_surface = surface_for(str(image["original_name"]))
        case_id = case_for_source_group(
            "WORKBUDDY-VISUAL-REV95",
            str(image["original_name"]),
            image_surface,
            f"WorkBuddy 历史视觉基线 · {image['original_name']}",
            ["ui-visual", "ui-geometry"],
        )
        source_atom_to_case[visual_atom_id] = case_id
        source_atom_to_case[geometry_atom_id] = case_id
    sources.append(make_source("WORKBUDDY-VISUAL-REV95", "frozen-visual-baseline", "normative", "ui", f"skill://qwork-test-dataset/{visual_path.relative_to(output.parent.parent).as_posix()}", "95", sha256_bytes(visual_path.read_bytes()), visual_atoms))

    # Current WorkBuddy Electron UI is a user-approved Figma-equivalent source. Compile every state,
    # visible control, CSS box and screenshot without mutating the product.
    cdp_dir = pathlib.Path(args.cdp_snapshot).resolve()
    cdp_manifest_path = cdp_dir / "manifest.json"
    cdp_manifest = json.loads(cdp_manifest_path.read_text(encoding="utf-8"))
    cdp_atoms_list, cdp_meta = cdp_atoms("WORKBUDDY-CDP-5-3-12-V4", cdp_dir, cdp_manifest)
    for atom in cdp_atoms_list:
        meta = cdp_meta[str(atom["atom_id"])]
        state = str(meta["state"])
        source_atom_to_case[str(atom["atom_id"])] = case_for_source_group(
            "WORKBUDDY-CDP-5-3-12-V4",
            state,
            str(atom["surface"]),
            f"WorkBuddy 5.3.12 当前 UI · {state}",
            FACET_CATEGORIES[str(atom["facet"])],
        )
    sources.append(make_source(
        "WORKBUDDY-CDP-5-3-12-V4",
        "electron-cdp-ui-snapshot",
        "normative",
        "current-product-ui",
        f"skill://qwork-test-dataset/{cdp_manifest_path.relative_to(output.parent.parent).as_posix()}",
        str(cdp_manifest["captured_at"]),
        sha256_bytes(cdp_manifest_path.read_bytes()),
        cdp_atoms_list,
    ))

    # A captured Oracle run changes execution truth, not source authority. Bind it
    # only after all CDP source groups have stable Case identities. A failing
    # reference run proves a product mismatch while still proving the route is
    # executable; it must never be collapsed back to "manual-blocked".
    qwork_oracle_report_path = (
        pathlib.Path(args.qwork_oracle_report).resolve()
        if args.qwork_oracle_report
        else None
    )
    qwork_oracle_report: dict[str, Any] | None = None
    qwork_oracle_results: dict[str, dict[str, Any]] = {}
    qwork_oracle_capture: dict[str, Any] | None = None
    if qwork_oracle_report_path:
        qwork_oracle_report = json.loads(
            qwork_oracle_report_path.read_text(encoding="utf-8")
        )
        qwork_oracle_results = {
            str(item["state"]): item
            for item in qwork_oracle_report.get("results", [])
        }
        expected_states = {str(item["state"]) for item in cdp_manifest["records"]}
        if set(qwork_oracle_results) != expected_states:
            raise ValueError(
                "QWork Oracle report state set does not exactly match the frozen WorkBuddy CDP manifest"
            )
        capture_path = qwork_oracle_report_path.parent.parent / "capture" / "capture-manifest.json"
        qwork_oracle_capture = json.loads(capture_path.read_text(encoding="utf-8"))
        if int(qwork_oracle_capture.get("state_count", -1)) != len(expected_states):
            raise ValueError("QWork Oracle capture does not cover the full frozen state set")

    # WorkBuddy storage is a user-declared normative source. Compile every minimized
    # inventory record, not only top-level domains, so no package, durable record,
    # symlink-like object or cache family can silently disappear from migration design.
    storage_dir = pathlib.Path(args.storage_snapshot).resolve()
    storage_manifest = json.loads((storage_dir / "manifest.json").read_text(encoding="utf-8"))
    storage_inventory = json.loads((storage_dir / "inventory.json").read_text(encoding="utf-8"))
    domain_counts: dict[str, int] = defaultdict(int)
    storage_atoms: list[dict[str, Any]] = []
    for entry in storage_inventory:
        domain_counts[str(entry["path"]).split("/", 1)[0]] += 1
    for domain, count in sorted(domain_counts.items()):
        label = f"~/.workbuddy/{domain} is a stable WorkBuddy storage domain with {count} inventoried files"
        atom_id = f"WORKBUDDY-STORAGE:DOMAIN:{stable_slug(domain).upper()}"
        storage_atoms.append({"atom_id": atom_id, "facet": "data-side-effect", "locator": f"inventory-domain:{domain}", "label": label, "extracted_value_hash": f"sha256:{sha256_text(label)}", "priority": "P1"})
        case_id = case_for_source_group(
            "WORKBUDDY-STORAGE-LOCAL",
            f"domain-{domain}",
            "persistence",
            f"~/.workbuddy/{domain} 顶级存储域契约",
            ["data"],
        )
        source_atom_to_case[atom_id] = case_id
        storage_dispositions.append({
            "atom_id": atom_id,
            "case_id": case_id,
            "record_kind": "domain",
            "source_locator": f"inventory-domain:{domain}",
            "source_hash": f"sha256:{sha256_text(label)}",
            "source_entry_count": count,
            "treatment": "inventory-domain",
            "final_action": "inventory",
            "decision_status": "resolved",
            "implementation_status": "verified",
            "qwork_target": QWORK_STORAGE_TARGETS.get(domain),
            "evidence": "the frozen inventory exactly proves domain presence and entry count",
            "next_action": None,
        })
    for entry_index, entry in enumerate(storage_inventory):
        path = str(entry["path"])
        treatment, priority, acceptance = storage_entry_policy(entry)
        canonical_record = {
            "path": path,
            "path_pseudonymized": bool(entry.get("path_pseudonymized")),
            "kind": str(entry.get("kind") or "unknown"),
            "size": entry.get("size"),
            "extension": str(entry.get("extension") or ""),
            "sensitive_name": bool(entry.get("sensitive_name")),
            "content_copied": bool(entry.get("content_copied")),
            "sha256": entry.get("sha256"),
            "treatment": treatment,
        }
        canonical = json.dumps(canonical_record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        atom_id = f"WORKBUDDY-STORAGE:ENTRY:{sha256_text(path)[:20].upper()}"
        label = (
            f"~/.workbuddy/{path} inventory entry ({entry.get('kind')}, {entry.get('size')} bytes) must {acceptance}"
        )
        storage_atoms.append(
            {
                "atom_id": atom_id,
                "facet": "data-side-effect",
                "locator": f"inventory-entry:{entry_index};path:{path}",
                "label": label,
                "extracted_value_hash": f"sha256:{sha256_text(canonical)}",
                "priority": priority,
                "storage_treatment": treatment,
                "path_pseudonymized": bool(entry.get("path_pseudonymized")),
            }
        )
        root = path.split("/", 1)[0]
        case_id = case_for_source_group(
            "WORKBUDDY-STORAGE-LOCAL",
            f"{root}-{treatment}",
            "persistence",
            f"~/.workbuddy/{root} · {treatment} 迁移契约",
            ["data", "recovery"],
        )
        source_atom_to_case[atom_id] = case_id
        disposition = storage_entry_disposition(entry)
        storage_dispositions.append({
            "atom_id": atom_id,
            "case_id": case_id,
            "record_kind": "entry",
            "source_locator": f"inventory-entry:{entry_index};path:{path}",
            "source_hash": f"sha256:{sha256_text(canonical)}",
            "source_path": path,
            "path_pseudonymized": bool(entry.get("path_pseudonymized")),
            "sensitive_name": bool(entry.get("sensitive_name")),
            "content_copied": bool(entry.get("content_copied")),
            **disposition,
        })
    for entry in storage_inventory:
        schema = entry.get("sqlite_schema")
        if not schema:
            continue
        for obj in schema.get("objects", []):
            if obj.get("type") != "table":
                continue
            table = str(obj["name"])
            shape = json.dumps(obj.get("columns", []), ensure_ascii=False, sort_keys=True)
            atom_id = f"WORKBUDDY-STORAGE:TABLE:{stable_slug(table).upper()}"
            storage_atoms.append({"atom_id": atom_id, "facet": "data-side-effect", "locator": f"sqlite:{entry['path']};table:{table}", "label": f"WorkBuddy database table {table} preserves its declared column contract", "extracted_value_hash": f"sha256:{sha256_text(shape)}", "priority": "P1"})
            db_root = str(entry["path"]).split("/", 1)[0]
            case_id = case_for_source_group(
                "WORKBUDDY-STORAGE-LOCAL",
                f"sqlite-{db_root}-{table}",
                "persistence",
                f"~/.workbuddy/{entry['path']} · SQLite {table} schema 契约",
                ["data", "recovery"],
            )
            source_atom_to_case[atom_id] = case_id
            storage_dispositions.append({
                "atom_id": atom_id,
                "case_id": case_id,
                "record_kind": "sqlite-table",
                "source_locator": f"sqlite:{entry['path']};table:{table}",
                "source_hash": f"sha256:{sha256_text(shape)}",
                "source_path": str(entry["path"]),
                "table": table,
                "treatment": "preserve-schema-semantics-or-versioned-transform",
                "final_action": None,
                "decision_status": "pending",
                "implementation_status": "pending",
                "qwork_target": QWORK_STORAGE_TARGETS.get(db_root),
                "evidence": "the frozen SQLite schema is known; no QWork table mapping and rollback proof is bound",
                "next_action": "map each source column invariant to a QWork repository/schema or approve a versioned transform with restart/rollback proof",
            })
    sources.append(make_source("WORKBUDDY-STORAGE-LOCAL", "local-storage-inventory", "normative", "storage", "~/.workbuddy/", str(storage_manifest["captured_at"]), str(storage_manifest["inventory_sha256"]), storage_atoms))

    storage_atom_ids = {str(atom["atom_id"]) for atom in storage_atoms}
    disposition_atom_ids = [str(item["atom_id"]) for item in storage_dispositions]
    if storage_atom_ids != set(disposition_atom_ids) or len(disposition_atom_ids) != len(set(disposition_atom_ids)):
        raise ValueError("WorkBuddy storage dispositions are not an exact one-to-one atom map")

    source_ids = [str(source["source_id"]) for source in sources]
    atom_ids = [str(atom["atom_id"]) for source in sources for atom in source["inventory"]["atoms"]]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("compiled sources contain duplicate source_id values")
    if len(atom_ids) != len(set(atom_ids)):
        duplicates = sorted({value for value in atom_ids if atom_ids.count(value) > 1})
        raise ValueError(f"compiled sources contain duplicate atom_id values: {duplicates[:20]}")

    # The current branch may contain a revised copy of an accepted develop
    # document. Identical atoms across those two revisions are lineage for one
    # product rule, not two independent requirements. Include an occurrence
    # ordinal so intentionally repeated text inside one document stays distinct.
    atom_lineage_keys: dict[str, tuple[str, str, str, int]] = {}
    for source in sources:
        source_id = str(source["source_id"])
        if not source_id.startswith(("QDEV-DOC-", "QHEAD-DOC-", "QDEV-E2E-", "QHEAD-E2E-")):
            continue
        document_id = re.sub(r"^Q(?:DEV|HEAD)-(?:DOC|E2E)-", "", source_id)
        occurrences: dict[tuple[str, str], int] = defaultdict(int)
        for atom in source["inventory"]["atoms"]:
            contract = atom.get("test_contract")
            content_identity = (
                str(contract["body_sha256"])
                if isinstance(contract, dict)
                else str(atom["extracted_value_hash"])
            )
            signature = (str(atom["facet"]), content_identity)
            ordinal = occurrences[signature]
            occurrences[signature] += 1
            atom_lineage_keys[str(atom["atom_id"])] = (
                document_id,
                signature[0],
                signature[1],
                ordinal,
            )
    canonical_requirements: dict[tuple[str, str, str, int], dict[str, Any]] = {}

    # Compile every atom into one requirement and attach category-specific oracles.
    for source in sources:
        for atom in source["inventory"]["atoms"]:
            atom_id = str(atom["atom_id"])
            facet = str(atom["facet"])
            case_id = source_atom_to_case[atom_id]
            case = cases[case_id]
            surface = str(case["coverage"]["capability_id"])
            lineage_key = atom_lineage_keys.get(atom_id)
            canonical = canonical_requirements.get(lineage_key) if lineage_key else None
            if canonical is not None:
                source_ref = {
                    "source_id": source["source_id"],
                    "atom_id": atom_id,
                    "locator": atom["locator"],
                }
                canonical["requirement"]["source_atoms"].append(source_ref)
                for oracle in canonical["requirement"]["oracles"]:
                    oracle["source_atom_ids"].append(atom_id)
                canonical_case = canonical["case"]
                derived = next(
                    item
                    for item in canonical_case["derived_requirements"]
                    if item["requirement_id"] == canonical["requirement"]["requirement_id"]
                )
                derived["source_atom_ids"].append(atom_id)
                if source["source_id"] not in derived["supporting_sources"]:
                    derived["supporting_sources"].append(source["source_id"])
                canonical_case["sources"].append({
                    "source_id": source["source_id"],
                    "type": source["type"],
                    "authority_kind": source["authority_kind"],
                    "authority_domain": source["authority_domain"],
                    "stable_source_id": source["locator"],
                    "locator": atom["locator"],
                    "revision": source["revision"],
                    "version": None,
                    "approval_status": source["approval_status"],
                    "retrieved_at": created_at,
                    "content_hash": atom["extracted_value_hash"],
                    "redaction_status": "minimized",
                    "supports": [canonical["governing_source_id"]],
                })
                continue
            requirement_id = f"REQ-{sha256_text(atom_id)[:14].upper()}"
            categories = FACET_CATEGORIES[facet]
            oracle: dict[str, Any] = {
                "type": semantic_oracle_type(source, atom),
                "source_atom_ids": [atom_id],
                "assertion": str(atom["label"]),
            }
            coverage_status = "covered"
            priority = str(atom.get("priority") or ("P0" if surface in {"auth", "assistant", "task-lifecycle", "expert-market", "expert-team", "permissions"} else "P1"))
            status_reason = None
            if facet == "ui-visual":
                image = visual_meta.get(atom_id)
                cdp = cdp_meta.get(atom_id)
                if cdp and cdp["kind"] == "visual":
                    record = cdp["record"]
                    baseline = cdp["snapshot_dir"] / str(record["screenshot"])
                    oracle = {"type": "visual", "source_atom_ids": [atom_id], "baseline": {"locator": f"skill://qwork-test-dataset/{baseline.relative_to(output.parent.parent).as_posix()}", "sha256": f"sha256:{record['screenshot_sha256']}"}, "viewport": record["viewport"], "comparison": {"max_diff_ratio": 0.01, "mask_regions": []}, "assertion": f"QWork state matches current WorkBuddy 5.3.12 CDP state {cdp['state']} at the frozen viewport and DPR"}
                elif image:
                    baseline = visual_path.parent / str(image["path"])
                    oracle = {"type": "visual", "source_atom_ids": [atom_id], "baseline": {"locator": f"skill://qwork-test-dataset/{baseline.relative_to(output.parent.parent).as_posix()}", "sha256": f"sha256:{image['sha256']}"}, "viewport": {"width": image["width"], "height": image["height"], "dpr": 1}, "comparison": {"max_diff_ratio": 0.01, "mask_regions": []}, "assertion": f"QWork surface matches frozen WorkBuddy baseline {image['original_name']} within approved 1% pixel threshold"}
                else:
                    # Style text without a page-specific frozen export remains traceable but not falsely green.
                    coverage_status = "blocked"
                    priority = "P2"
                    status_reason = "source style atom is not bound to one unambiguous visual frame"
                    fallback_baseline = visual_path.parent / str(fallback_visual["path"])
                    oracle = {"type": "visual", "source_atom_ids": [atom_id], "baseline": {"locator": f"skill://qwork-test-dataset/{fallback_baseline.relative_to(output.parent.parent).as_posix()}", "sha256": f"sha256:{fallback_visual['sha256']}"}, "viewport": {"width": fallback_visual["width"], "height": fallback_visual["height"], "dpr": 1}, "comparison": {"max_diff_ratio": 0.01, "mask_regions": []}, "assertion": f"CDP must bind this style requirement to its exact WorkBuddy frame before visual comparison; the home frame is only a frozen source anchor"}
            elif facet == "ui-geometry":
                image = visual_meta.get(atom_id)
                cdp = cdp_meta.get(atom_id)
                if cdp and cdp["kind"] == "geometry":
                    box = cdp["control"]["box"]
                    oracle = {"type": "ui-geometry", "source_atom_ids": [atom_id], "target": cdp["target"], "coordinate_space": "renderer CSS px", "viewport": cdp["record"]["viewport"], "tolerance_css_px": 2, "expected": {"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"]}, "relative": {}, "assertion": str(atom["label"])}
                elif image:
                    coverage_status = "blocked"
                    priority = "P2"
                    status_reason = "source image pixels are frozen, but CSS viewport/DPR and target node require current WorkBuddy CDP measurement"
                    oracle = {"type": "ui-geometry", "source_atom_ids": [atom_id], "target": f"CDP target for {image['original_name']}", "coordinate_space": "source image pixels pending renderer CSS-px calibration", "viewport": {"width": image["width"], "height": image["height"], "dpr": 1}, "tolerance_css_px": 2, "expected": {"width": image["width"], "height": image["height"]}, "relative": {}, "assertion": f"CDP must calibrate the frozen {image['original_name']} image size to renderer CSS px before this geometry gate can become covered"}
                else:
                    expected: dict[str, Any] = {}
                    relative: dict[str, Any] = {}
                    if atom.get("measurement_kind") == "size":
                        expected = {"width": atom.get("expected_width", 1), "height": atom.get("expected_height", 1)}
                    else:
                        relative = {
                            "anchor_target": str(atom.get("target") or "source-defined parent"),
                            "relation": str(atom.get("relation") or "spacing"),
                            "expected_css_px": atom.get("expected_css_px", 1),
                        }
                    oracle = {
                        "type": "ui-geometry",
                        "source_atom_ids": [atom_id],
                        "target": str(atom.get("target") or "source-defined semantic target"),
                        "coordinate_space": "renderer CSS px",
                        "viewport": atom.get("viewport") or {"width": 1200, "height": 800, "dpr": 1},
                        "tolerance_css_px": 2,
                        "expected": expected,
                        "relative": relative,
                        "assertion": str(atom["label"]),
                    }
            requirement = {
                "requirement_id": requirement_id,
                "priority": priority,
                "surface": "ui" if atom_requires_ui(source, atom) else surface,
                "rule": str(atom["label"]),
                "categories": categories,
                "source_atoms": [{"source_id": source["source_id"], "atom_id": atom_id, "locator": atom["locator"]}],
                "oracles": [oracle],
                "case_ids": [case_id] if coverage_status == "covered" else [],
                "coverage_status": coverage_status,
                "status_reason": status_reason,
            }
            requirements.append(requirement)
            if coverage_status == "covered":
                case["selection"]["requirement_ids"].append(requirement_id)
                case["derived_requirements"].append({"requirement_id": requirement_id, "source_atom_ids": [atom_id], "content_facets": [facet], "acceptance_categories": categories, "surface": surface, "priority": priority, "rule": str(atom["label"]), "authority_domain": str(source["authority_domain"]), "governing_sources": [str(source["source_id"])], "supporting_sources": [], "conflicts": [], "resolution": {"status": "resolved", "reason": "compiled from the user-approved source hierarchy"}, "oracle": str(oracle["assertion"])})
                case["oracles"].append({"requirement_id": requirement_id, "type": oracle["type"], "assertion": str(oracle["assertion"])})
                case["sources"].append({"source_id": source["source_id"], "type": source["type"], "authority_kind": source["authority_kind"], "authority_domain": source["authority_domain"], "stable_source_id": source["locator"], "locator": atom["locator"], "revision": source["revision"], "version": None, "approval_status": source["approval_status"], "retrieved_at": created_at, "content_hash": atom["extracted_value_hash"], "redaction_status": "minimized"})
                if lineage_key:
                    canonical_requirements[lineage_key] = {
                        "requirement": requirement,
                        "case": case,
                        "governing_source_id": str(source["source_id"]),
                    }

    requirement_ids = [str(requirement["requirement_id"]) for requirement in requirements]
    if len(requirement_ids) != len(set(requirement_ids)):
        duplicates = sorted({value for value in requirement_ids if requirement_ids.count(value) > 1})
        raise ValueError(f"compiled requirements contain duplicate requirement_id values: {duplicates[:20]}")

    # Some evidence sources name the executable acceptance Case that governs
    # one precise rule. Reuse it only through an exact, unambiguous Case-ID
    # token. Normative documents included in the reviewed Coverage Map are
    # deliberately excluded: matching identifiers are locator hints, not
    # proof that a test body covers the document's complete Given/When/Then and
    # forbidden outcome. Those atoms may bind only in the hash-locked mapping
    # pass below.
    acceptance_id = re.compile(r"\b(?:WB|QW)-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d{3}\b")
    executable_by_acceptance_id: dict[str, set[str]] = defaultdict(set)
    for executable_id, executable_case in cases.items():
        if not str(executable_case["execution_contract"]["route_id"]).startswith(
            ("qwork.playwright.", "qwork.private-playwright.")
        ):
            continue
        for token in acceptance_id.findall(str(executable_case["title"])):
            executable_by_acceptance_id[token].add(executable_id)
    requirement_by_id = {str(item["requirement_id"]): item for item in requirements}
    for source_case_id, source_case in list(cases.items()):
        if source_case["execution_contract"]["launch"]["strategy"] != "manual-blocked":
            continue
        retained: list[dict[str, Any]] = []
        for derived in source_case["derived_requirements"]:
            rule = str(derived["rule"])
            token_matches = list(acceptance_id.finditer(rule))
            # A compact range such as `WB-UI-TASK-002/003` or
            # `WB-UI-EXPERT-001~007` names several acceptance contracts. One
            # executable Case cannot prove the whole row merely because its
            # first ID is an exact substring. Keep those rows source-bound
            # until every member is expanded and mapped independently.
            compact_range = any(
                match.end() < len(rule) and rule[match.end()] in {"/", "~", "-"}
                for match in token_matches
            )
            tokens = {match.group(0) for match in token_matches}
            if len(tokens) != 1 or compact_range:
                retained.append(derived)
                continue
            targets = {
                target
                for token in tokens
                for target in executable_by_acceptance_id.get(token, set())
            }
            if len(targets) != 1:
                retained.append(derived)
                continue
            target_id = next(iter(targets))
            target = cases[target_id]
            requirement_id = str(derived["requirement_id"])
            requirement = requirement_by_id[requirement_id]
            if any(
                str(source_atom["source_id"]) in document_coverage_map["sources"]
                for source_atom in requirement["source_atoms"]
            ):
                retained.append(derived)
                continue
            requirement["case_ids"] = [target_id]
            target["derived_requirements"].append(derived)
            target["selection"]["requirement_ids"].append(requirement_id)
            target["oracles"].extend(
                oracle
                for oracle in source_case["oracles"]
                if oracle["requirement_id"] == requirement_id
            )
            requirement_sources = {
                (str(item["source_id"]), str(item["locator"]))
                for item in requirement["source_atoms"]
            }
            target["sources"].extend(
                item
                for item in source_case["sources"]
                if (str(item["source_id"]), str(item["locator"]))
                in requirement_sources
            )
        source_case["derived_requirements"] = retained
        retained_ids = {str(item["requirement_id"]) for item in retained}
        source_case["selection"]["requirement_ids"] = sorted(retained_ids)
        source_case["oracles"] = [
            item
            for item in source_case["oracles"]
            if str(item["requirement_id"]) in retained_ids
        ]

    # Reviewed document matrix rows may require several executable Cases to
    # jointly prove one product requirement. Bind those rows only through the
    # explicit, hash-locked Coverage Map. Every acceptance ID in the row must
    # be claimed exactly once; the source requirement remains one semantic
    # rule with multiple executable routes rather than being silently split or
    # treated as covered by the first matching title.
    source_by_id = {str(item["source_id"]): item for item in sources}
    requirement_by_id = {str(item["requirement_id"]): item for item in requirements}
    spec_registry = document_coverage_map["spec_registry"]
    target_registry = document_coverage_map["target_registry"]
    mapped_document_requirements: set[str] = set()
    for document_source_id, source_coverage in document_coverage_map["sources"].items():
        accepted_source = source_by_id.get(str(document_source_id))
        if accepted_source is None:
            raise ValueError(f"document Coverage Map source is missing: {document_source_id}")
        if (
            str(accepted_source["locator"]) != str(source_coverage["source_locator"])
            or str(accepted_source["content_hash"]) != str(source_coverage["source_sha256"])
        ):
            raise ValueError(f"document Coverage Map source drifted: {document_source_id}")
        atoms_by_locator = {
            str(atom["locator"]): atom
            for atom in accepted_source["inventory"]["atoms"]
        }
        for mapping in source_coverage["mappings"]:
            locator = str(mapping["atom_locator"])
            atom = atoms_by_locator.get(locator)
            if atom is None or str(atom["extracted_value_hash"]) != str(mapping["atom_sha256"]):
                raise ValueError(
                    f"document Coverage Map atom drifted: {document_source_id} {locator}"
                )
            matching_requirements = [
                requirement
                for requirement in requirements
                if any(
                    str(source_atom["source_id"]) == str(document_source_id)
                    and str(source_atom["locator"]) == locator
                    for source_atom in requirement["source_atoms"]
                )
            ]
            if len(matching_requirements) != 1:
                raise ValueError(
                    f"document atom must resolve to one requirement: {document_source_id} {locator}"
                )
            requirement = matching_requirements[0]
            requirement_id = str(requirement["requirement_id"])
            if requirement_id in mapped_document_requirements:
                raise ValueError(f"canonical document requirement mapped twice: {requirement_id}")
            mapped_document_requirements.add(requirement_id)

            target_configs: list[dict[str, Any]] = []
            observed_acceptance_ids: set[str] = set()
            for target_ref in map(str, mapping["target_ids"]):
                registry_target = dict(target_registry[target_ref])
                spec_ref = str(registry_target.pop("spec_ref"))
                target_config = {**spec_registry[spec_ref], **registry_target}
                target_id = str(target_config["case_id"])
                target = cases.get(target_id)
                if target is None:
                    raise ValueError(f"document Coverage Map target is missing: {target_id}")
                source_contract = target["execution_contract"]["observability"]["source_contract"]
                if (
                    str(source_contract["execution_revision"]) != str(target_config["execution_revision"])
                    or str(source_contract["spec"]) != str(target_config["spec"])
                    or str(source_contract["spec_sha256"]) != str(target_config["spec_sha256"])
                    or str(target["title"]) != str(target_config["title"])
                ):
                    raise ValueError(f"document Coverage Map target drifted: {target_id}")
                target_acceptance_ids = set(map(str, target_config["acceptance_ids"]))
                if observed_acceptance_ids & target_acceptance_ids:
                    raise ValueError(
                        f"document acceptance ID is claimed by multiple targets: {target_id}"
                    )
                observed_acceptance_ids.update(target_acceptance_ids)
                target_configs.append(target_config)
            expected_acceptance_ids = set(map(str, mapping["acceptance_ids"]))
            if observed_acceptance_ids != expected_acceptance_ids:
                raise ValueError(
                    f"document acceptance expansion is not closed: {document_source_id} {locator}"
                )

            holders = [
                case
                for case in cases.values()
                if any(
                    str(derived["requirement_id"]) == requirement_id
                    for derived in case["derived_requirements"]
                )
            ]
            if len(holders) != 1:
                raise ValueError(
                    f"document requirement must have one pre-map holder: {requirement_id}"
                )
            source_case = holders[0]
            derived = next(
                item
                for item in source_case["derived_requirements"]
                if str(item["requirement_id"]) == requirement_id
            )
            requirement_sources = {
                (str(item["source_id"]), str(item["locator"]))
                for item in requirement["source_atoms"]
            }
            bound_sources = [
                item
                for item in source_case["sources"]
                if (str(item["source_id"]), str(item["locator"]))
                in requirement_sources
            ]
            bound_oracles = [
                item
                for item in source_case["oracles"]
                if str(item["requirement_id"]) == requirement_id
            ]
            target_ids: list[str] = []
            for target_config in target_configs:
                target_id = str(target_config["case_id"])
                target_ids.append(target_id)
                target = cases[target_id]
                if target is source_case:
                    # A single-ID row may already have been bound by the exact
                    # acceptance-token pass above. The reviewed multi-Case map
                    # still audits it, but must not duplicate and then remove
                    # its own requirement ledger.
                    continue
                target["derived_requirements"].append(dict(derived))
                target["selection"]["requirement_ids"].append(requirement_id)
                target["oracles"].extend(dict(item) for item in bound_oracles)
                target["sources"].extend(dict(item) for item in bound_sources)
            requirement["case_ids"] = sorted(target_ids)
            if str(source_case["id"]) not in set(target_ids):
                source_case["derived_requirements"] = [
                    item
                    for item in source_case["derived_requirements"]
                    if str(item["requirement_id"]) != requirement_id
                ]
                source_case["selection"]["requirement_ids"] = [
                    item
                    for item in source_case["selection"]["requirement_ids"]
                    if str(item) != requirement_id
                ]
                source_case["oracles"] = [
                    item
                    for item in source_case["oracles"]
                    if str(item["requirement_id"]) != requirement_id
                ]

    # A document also contains provenance that must remain attributable but is
    # not a product behavior: metadata, section introductions, table headers,
    # historical result snapshots, trace links and change logs. Remove those
    # atoms from the executable Case closed world only through an exact,
    # hash-locked disposition. Canonical requirements that merge develop and
    # HEAD copies must be disposed in full; a partial match is a build error.
    disposition_by_atom: dict[tuple[str, str], dict[str, Any]] = {}
    for disposition_source_id, source_policy in document_atom_dispositions["sources"].items():
        disposition_source = source_by_id.get(str(disposition_source_id))
        if disposition_source is None:
            raise ValueError(
                f"document disposition source is missing: {disposition_source_id}"
            )
        if (
            str(disposition_source["locator"]) != str(source_policy["source_locator"])
            or str(disposition_source["content_hash"]) != str(source_policy["source_sha256"])
        ):
            raise ValueError(
                f"document disposition source drifted: {disposition_source_id}"
            )
        atoms_by_locator = {
            str(atom["locator"]): atom
            for atom in disposition_source["inventory"]["atoms"]
        }
        for entry in source_policy["atoms"]:
            locator = str(entry["atom_locator"])
            key = (str(disposition_source_id), locator)
            if key in disposition_by_atom:
                raise ValueError(f"document atom disposition duplicated: {key}")
            atom = atoms_by_locator.get(locator)
            if atom is None or str(atom["extracted_value_hash"]) != str(entry["atom_sha256"]):
                raise ValueError(f"document atom disposition drifted: {key}")
            disposition_by_atom[key] = entry

    disposed_requirement_ids: set[str] = set()
    for requirement in requirements:
        requirement_id = str(requirement["requirement_id"])
        atom_keys = {
            (str(item["source_id"]), str(item["locator"]))
            for item in requirement["source_atoms"]
        }
        configured_keys = atom_keys & disposition_by_atom.keys()
        if not configured_keys:
            continue
        if configured_keys != atom_keys:
            raise ValueError(
                f"canonical requirement is only partly disposed: {requirement_id}"
            )
        if requirement_id in mapped_document_requirements:
            raise ValueError(
                f"document requirement is both executable and disposed: {requirement_id}"
            )
        reasons = {
            str(disposition_by_atom[key]["status_reason"])
            for key in configured_keys
        }
        if len(reasons) != 1:
            raise ValueError(
                f"canonical document disposition reasons differ: {requirement_id}"
            )
        requirement["coverage_status"] = "not_applicable"
        requirement["status_reason"] = next(iter(reasons))
        requirement["case_ids"] = []
        requirement["oracles"] = []
        disposed_requirement_ids.add(requirement_id)

        for case in cases.values():
            if requirement_id not in set(map(str, case["selection"]["requirement_ids"])):
                continue
            case["selection"]["requirement_ids"] = [
                value
                for value in case["selection"]["requirement_ids"]
                if str(value) != requirement_id
            ]
            case["derived_requirements"] = [
                item
                for item in case["derived_requirements"]
                if str(item["requirement_id"]) != requirement_id
            ]
            case["oracles"] = [
                item
                for item in case["oracles"]
                if str(item["requirement_id"]) != requirement_id
            ]
            case["sources"] = [
                item
                for item in case["sources"]
                if (str(item["source_id"]), str(item["locator"])) not in atom_keys
            ]

    for empty_case_id in [
        case_id
        for case_id, case in cases.items()
        if not case["derived_requirements"]
        and case["execution_contract"]["launch"]["strategy"] == "manual-blocked"
    ]:
        del cases[empty_case_id]

    # A structured Oracle pointer can reuse an executable Case only through the
    # reviewed closed-world Coverage Map. The map binds each exact JSON Pointer
    # to one fail-closed Playwright test and hashes the full spec, the Oracle
    # input and the helper that performs aggregate comparison. Unlisted/gap
    # pointers deliberately remain source-bound runner gaps.
    requirements_by_id = {str(item["requirement_id"]): item for item in requirements}
    source_by_id = {str(item["source_id"]): item for item in sources}
    for structured_source_id, coverage in structured_coverage_map["sources"].items():
        mappings = list(coverage["mappings"])
        pointer_to_target: dict[str, str] = {}
        targets: dict[str, dict[str, Any]] = {}
        for mapping in mappings:
            target_config = mapping["target"]
            target_id = str(target_config["case_id"])
            target = cases.get(target_id)
            if target is None:
                raise ValueError(f"structured Oracle target Case is missing: {target_id}")
            source_contract = target["execution_contract"]["observability"]["source_contract"]
            if (
                str(source_contract["execution_revision"]) != str(target_config["execution_revision"])
                or str(source_contract["spec"]) != str(target_config["spec"])
                or str(source_contract["spec_sha256"]) != str(target_config["spec_sha256"])
                or str(target["title"]) != str(target_config["title"])
            ):
                raise ValueError(f"structured Oracle target contract drifted: {target_id}")
            targets[target_id] = target
            for pointer in map(str, mapping["covered_pointers"]):
                if pointer in pointer_to_target:
                    raise ValueError(
                        f"structured Oracle pointer maps to multiple Cases: {pointer}"
                    )
                pointer_to_target[pointer] = target_id
        accepted_source = source_by_id.get(str(structured_source_id))
        if accepted_source is None:
            raise ValueError(f"structured Oracle source is missing: {structured_source_id}")
        covered_pointers = set(pointer_to_target)
        gap_pointers = set(map(str, coverage["gap_pointers"]))
        product_pointers = {
            str(atom["locator"]).removeprefix("json-pointer:")
            for atom in accepted_source["inventory"]["atoms"]
            if not atom.get("evidence_only")
        }
        if covered_pointers & gap_pointers or covered_pointers | gap_pointers != product_pointers:
            raise ValueError(
                f"structured Oracle Coverage Map is not closed: {structured_source_id}"
            )
        moved_requirement_ids: set[str] = set()
        for source_case in cases.values():
            if any(source_case is target for target in targets.values()):
                continue
            retained: list[dict[str, Any]] = []
            for derived in source_case["derived_requirements"]:
                requirement_id = str(derived["requirement_id"])
                requirement = requirements_by_id[requirement_id]
                pointers = {
                    str(item["locator"]).removeprefix("json-pointer:")
                    for item in requirement["source_atoms"]
                    if str(item["source_id"]) == str(structured_source_id)
                }
                if not pointers or not pointers <= covered_pointers:
                    retained.append(derived)
                    continue
                if len(pointers) != 1:
                    raise ValueError(
                        f"structured Oracle requirement must bind one exact pointer: {requirement_id}"
                    )
                pointer = next(iter(pointers))
                target_id = pointer_to_target[pointer]
                target = targets[target_id]
                requirement["case_ids"] = [target_id]
                target["derived_requirements"].append(derived)
                target["selection"]["requirement_ids"].append(requirement_id)
                target["oracles"].extend(
                    oracle
                    for oracle in source_case["oracles"]
                    if str(oracle["requirement_id"]) == requirement_id
                )
                target["sources"].extend(
                    item
                    for item in source_case["sources"]
                    if str(item["source_id"]) == str(structured_source_id)
                    and str(item["locator"]).removeprefix("json-pointer:") in pointers
                )
                moved_requirement_ids.add(requirement_id)
            source_case["derived_requirements"] = retained
            retained_ids = {str(item["requirement_id"]) for item in retained}
            source_case["selection"]["requirement_ids"] = [
                value
                for value in source_case["selection"]["requirement_ids"]
                if str(value) in retained_ids
            ]
            source_case["oracles"] = [
                item
                for item in source_case["oracles"]
                if str(item["requirement_id"]) in retained_ids
            ]
            retained_source_keys = {
                (str(item["source_id"]), str(item["locator"]))
                for requirement_id in retained_ids
                for item in requirements_by_id[requirement_id]["source_atoms"]
            }
            source_case["sources"] = [
                item
                for item in source_case["sources"]
                if (str(item["source_id"]), str(item["locator"]))
                in retained_source_keys
            ]
        if len(moved_requirement_ids) != len(covered_pointers):
            raise ValueError(
                f"structured Oracle pointer transfer mismatch for {structured_source_id}: "
                f"{len(moved_requirement_ids)} requirements for {len(covered_pointers)} pointers"
            )
        source_revision = str(accepted_source["revision"])
        source_path = str(accepted_source["locator"]).split(":", 2)[2]
        for mapping in mappings:
            target_config = mapping["target"]
            target_id = str(target_config["case_id"])
            supporting = [
                {
                    "path": source_path,
                    "revision": source_revision,
                    "sha256": str(target_config["oracle_sha256"]),
                    "purpose": "frozen structured WorkBuddy product Oracle governing the mapped pointers",
                },
            ]
            if target_config.get("helper"):
                supporting.append(
                    {
                        "path": str(target_config["helper"]),
                        "revision": str(target_config["execution_revision"]),
                        "sha256": str(target_config["helper_sha256"]),
                        "purpose": "geometry/style comparison and required-check aggregation helper",
                    }
                )
            for item in supporting:
                actual = f"sha256:{sha256_bytes(run_git_blob(repo, item['revision'], item['path']))}"
                if actual != item["sha256"]:
                    raise ValueError(f"structured Oracle supporting contract drifted: {item['path']}")
            source_contract = targets[target_id]["execution_contract"]["observability"]["source_contract"]
            existing_supporting = source_contract.setdefault("supporting_contracts", [])
            existing_supporting.extend(
                item for item in supporting if item not in existing_supporting
            )

    # Remove cases that were superseded by exact head variants only if they have no requirements.
    cases = {case_id: case for case_id, case in cases.items() if case["selection"]["requirement_ids"]}
    for case in cases.values():
        case["selection"]["requirement_ids"] = sorted(set(case["selection"]["requirement_ids"]))
        case["selection"]["categories"] = sorted({category for req in case["derived_requirements"] for category in req["acceptance_categories"]})
        case["selection"]["suite_ids"] = sorted(["full", *[f"requirement:{value}" for value in case["selection"]["requirement_ids"]], *[f"category:{value}" for value in case["selection"]["categories"]]])
        case["sources"] = list({(item["source_id"], item["locator"]): item for item in case["sources"]}.values())
        source_ids = {str(item["source_id"]) for item in case["sources"]}
        if str(case["execution_contract"]["route_id"]).startswith("qwork.requirement."):
            compile_source_bound_causal_contract(case)
        has_ui_oracle = any(str(item.get("type")) in UI_ORACLE_TYPES for item in case["oracles"])
        if not has_ui_oracle and not str(case["execution_contract"]["route_id"]).startswith(
            ("qwork.playwright.", "qwork.private-playwright.")
        ):
            case["execution_type"] = "integration"
            case["execution_mode"] = "real-process"
            case.pop("ui_acceptance", None)
            case["preconditions"] = {
                "repository": "qwork",
                "isolated_config_home": True,
            }
            case["steps"] = [
                {"action": "start the isolated process, protocol or persistence fixture"},
                *case["steps"][1:],
            ]
            case["evidence"] = [
                "protocol, process, return-value or durable-state evidence",
                "machine-readable assertion result",
            ]
            contract = case["execution_contract"]
            contract["target"] = {
                "kind": "process",
                "platforms": ["darwin", "win32", "linux"],
                "artifact": "repo://QWork process/protocol/persistence boundary named by the source",
            }
            contract["launch"] = {
                "strategy": "manual-blocked",
                "command_or_tool": None,
                "success_oracle": "the source-bound non-UI contract is directly observed at its process, protocol or persistence boundary",
                "failure_action": "implement a source-bound integration runner; do not substitute a screenshot or static text scan",
            }
            contract["navigation"] = {
                "kind": "process-protocol",
                "entrypoint": str(case["coverage"]["capability_id"]),
                "steps": case["steps"],
                "locator_strategy": "source-bound process/protocol/persistence identifier",
                "success_oracle": "every declared non-UI oracle is directly observed",
                "failure_action": "capture structured boundary evidence and repair the integration runner",
            }
            contract["observability"] = {
                "artifacts": ["integration-result.json"],
                "correlation": "case_id + run_id + revision",
                "failure_classification": "product|fixture|route|environment",
                "source_contract": None,
            }
            contract["blockers"] = [
                "dedicated source-bound non-UI integration runner is not implemented",
                "reference run pending",
            ]
        structured_evidence_atoms = {
            str(atom_id)
            for requirement in case["derived_requirements"]
            for atom_id in requirement["source_atom_ids"]
            if ":PTR:" in str(atom_id)
            and any(
                str(source.get("source_id", "")).startswith("WORKBUDDY-ORACLE-5-3-5-")
                for source in case["sources"]
            )
            and all(
                category == "evidence-integrity"
                for category in requirement["acceptance_categories"]
            )
        }
        if structured_evidence_atoms:
            if len(structured_evidence_atoms) != sum(
                len(requirement["source_atom_ids"])
                for requirement in case["derived_requirements"]
            ):
                raise ValueError(
                    f"{case['id']} mixes structured provenance with product behavior"
                )
            case_id = str(case["id"])
            command = (
                "python3 .agents/skills/qwork-test-dataset/scripts/"
                "validate_structured_oracle_source_case.py "
                f"--repo . --skill-root .agents/skills/qwork-test-dataset --case-id {case_id}"
            )
            contract = case["execution_contract"]
            case["execution_type"] = "integration"
            case["execution_mode"] = "deterministic-replay"
            case.pop("ui_acceptance", None)
            case["preconditions"] = {
                "repository": "qwork",
                "frozen_git_revision": develop,
            }
            case["steps"] = [
                {"action": "load the exact frozen Git blob named by the structured Oracle source"},
                {"action": "resolve every Case-bound JSON Pointer without opening QWork or WorkBuddy"},
                {"action": "recompute canonical scalar hashes and compare them with the source atom ledger"},
            ]
            case["expected_outcomes"] = [
                "the frozen source blob hash matches its accepted source record",
                "every Case-bound JSON Pointer resolves exactly once",
                "every canonical scalar value hash matches the atom ledger",
            ]
            case["evidence"] = ["machine-readable structured source integrity result"]
            case["cleanup"] = {"action": "none; verifier is read-only over Git and private Dataset manifests"}
            contract.update({
                "readiness": "partial",
                "route_id": f"qwork.dataset.structured-oracle-source.{stable_slug(case_id, 80)}",
                "target": {"kind": "deterministic-runner", "platforms": ["darwin", "win32", "linux"], "artifact": "skill://qwork-test-dataset/scripts/validate_structured_oracle_source_case.py"},
                "authorization": {"required": False, "scopes": []},
                "preflight": [
                    {"action": "resolve the exact accepted Git source and revision", "oracle": "the source blob hash matches the frozen source ledger"},
                    {"action": "resolve the exact Case atom set", "oracle": "all atoms are evidence-provenance JSON Pointer atoms from one accepted structured source"},
                ],
                "launch": {"strategy": "command", "command_or_tool": command, "success_oracle": "every bound pointer and scalar hash matches the accepted structured source", "failure_action": "preserve pointer-level failures and rebuild the Dataset from the approved source; never reinterpret source metadata as UI behavior"},
                "navigation": {"kind": "cli-command", "entrypoint": "structured-oracle-source-integrity", "steps": [{"action": "run the exact Case ID through the read-only source verifier"}], "locator_strategy": "accepted source ID plus JSON Pointer", "success_oracle": "the verifier returns zero with no source, pointer or scalar drift", "failure_action": "repair source capture or Dataset compilation"},
                "fixtures": {"setup": "accepted Git blob and generated source atom ledger", "isolation": "does not launch Electron or read live user state", "cleanup": "none; all inputs are read-only"},
                "observability": {"artifacts": ["structured-source-result.json"], "correlation": "case_id + source_id + revision + source sha256", "failure_classification": "source-drift|pointer-missing|scalar-drift|dataset-drift", "source_contract": None},
                "reference_run": {"status": "pending", "run_id": None, "verified_at": None, "environment": "read-only frozen Git source; reference replay pending"},
                "cleanup": {"actions": ["assert no Electron process or live user state was opened"], "success_oracle": "only the requested report artifact was created"},
                "blockers": ["reference source-integrity replay pending"],
            })
            case["verification"] = {
                "last_outcome": "pending",
                "environment_scope": "read-only frozen Git and private Dataset",
                "implementation_revision": head,
                "last_verified_at": None,
                "status_reason": "dedicated source-integrity verifier implemented; reference run pending",
            }
        if "WORKBUDDY-STORAGE-LOCAL" in source_ids:
            case_id = str(case["id"])
            command = (
                "python3 .agents/skills/qwork-test-dataset/scripts/validate_workbuddy_storage_case.py "
                f"--skill-root .agents/skills/qwork-test-dataset --case-id {case_id}"
            )
            contract = case["execution_contract"]
            case["execution_type"] = "integration"
            case["execution_mode"] = "deterministic-replay"
            case.pop("ui_acceptance", None)
            case["preconditions"] = {
                "repository": "qwork",
                "isolated_config_home": False,
                "frozen_workbuddy_inventory": str(storage_manifest["inventory_sha256"]),
            }
            case["steps"] = [
                {"action": "load the frozen privacy-minimized WorkBuddy storage inventory"},
                {"action": "select only the source atoms bound to this Case"},
                {"action": "verify exact disposition, QWork target and implementation evidence for every atom"},
            ]
            case["expected_outcomes"] = [
                "every bound storage atom has exactly one explicit disposition",
                "resolved migration decisions have a canonical QWork target or a justified no-copy action",
                "implementation-required atoms include restart and rollback evidence before PASS",
            ]
            case["evidence"] = ["machine-readable per-atom storage disposition result"]
            case["cleanup"] = {"action": "none; verifier is read-only over frozen private Dataset assets"}
            contract.update({
                "readiness": "partial",
                "route_id": f"qwork.dataset.workbuddy-storage.{stable_slug(case_id, 80)}",
                "target": {"kind": "deterministic-runner", "platforms": ["darwin", "win32", "linux"], "artifact": "skill://qwork-test-dataset/scripts/validate_workbuddy_storage_case.py"},
                "authorization": {"required": False, "scopes": []},
                "preflight": [
                    {"action": "verify source inventory and disposition manifest hashes", "oracle": "frozen inventory and one-to-one atom map are unchanged"},
                    {"action": "resolve exact Case atom set", "oracle": "all atoms belong to WORKBUDDY-STORAGE-LOCAL and exist once"},
                ],
                "launch": {"strategy": "command", "command_or_tool": command, "success_oracle": "all Case-bound storage atoms have resolved decisions and verified or not-required implementation state", "failure_action": "preserve per-atom failures and execute each unique next_action; never skip or silently drop data"},
                "navigation": {"kind": "cli-command", "entrypoint": "workbuddy-storage-disposition-verifier", "steps": [{"action": "run the exact Case ID through the read-only verifier"}], "locator_strategy": "source atom ID and frozen inventory locator", "success_oracle": "the verifier returns zero and reports no pending decision or implementation", "failure_action": "repair product decision, migration implementation or evidence binding"},
                "fixtures": {"setup": "frozen metadata/hash/schema-only inventory and generated disposition manifest", "isolation": "never reads or writes live ~/.workbuddy or ~/.qwork during Case replay", "cleanup": "none; all inputs are immutable Dataset assets"},
                "observability": {"artifacts": ["storage-case-result.json"], "correlation": "case_id + source inventory sha256 + disposition manifest sha256", "failure_classification": "source-drift|decision-pending|implementation-pending|evidence-drift", "source_contract": None},
                "reference_run": {"status": "pending", "run_id": None, "verified_at": None, "environment": "read-only frozen private Dataset; reference replay pending"},
                "cleanup": {"actions": ["assert no live WorkBuddy or QWork state was opened or modified"], "success_oracle": "verifier created no state outside the requested report path"},
                "blockers": ["reference run pending; unresolved per-atom product decisions or implementation evidence remain machine-verifiable failures"],
            })
            case["verification"] = {
                "last_outcome": "pending",
                "environment_scope": "read-only frozen private Dataset",
                "implementation_revision": head,
                "last_verified_at": None,
                "status_reason": "dedicated verifier implemented; reference run pending",
            }
        if "WORKBUDDY-CDP-5-3-12-V4" in source_ids and qwork_oracle_report:
            state_locators = {
                match.group(1)
                for item in case["sources"]
                if (match := re.search(r"(?:^|;)cdp-state:([^;]+)", str(item["locator"])))
            }
            if len(state_locators) != 1:
                raise ValueError(f"{case['id']} does not bind exactly one WorkBuddy CDP state")
            state = next(iter(state_locators))
            result = qwork_oracle_results[state]
            report_ref = skill_ref(skill_root, qwork_oracle_report_path)
            capture_ref = skill_ref(
                skill_root,
                qwork_oracle_report_path.parent.parent / "capture" / "capture-manifest.json",
            )
            runner = skill_root / "scripts/run_qwork_workbuddy_oracle.mjs"
            comparator = skill_root / "scripts/compare_qwork_workbuddy_oracle.py"
            run_root = f"<run-root>/qwork-workbuddy/{stable_slug(state)}"
            command = (
                f"node .agents/skills/qwork-test-dataset/scripts/run_qwork_workbuddy_oracle.mjs . "
                f"{run_root}/capture {json.dumps(state, ensure_ascii=False)} && "
                f"python3 .agents/skills/qwork-test-dataset/scripts/compare_qwork_workbuddy_oracle.py "
                f"--capture {run_root}/capture "
                f"--workbuddy .agents/skills/qwork-test-dataset/data/evidence/workbuddy-cdp/5.3.12-surfaces-v4 "
                f"--output {run_root}/compare --max-diff-ratio 0.01 "
                f"--geometry-tolerance 2 --fail-on-diff"
            )
            contract = case["execution_contract"]
            contract["target"] = {
                "kind": "installed-app",
                "platforms": ["darwin"],
                "artifact": "repo://out/main/index.js + Electron",
            }
            contract["launch"] = {
                "strategy": "command",
                "command_or_tool": command,
                "success_oracle": "the selected state is captured and both pixel and semantic-geometry Oracles pass",
                "failure_action": "preserve report, screenshots and diff image; classify as product, route, fixture, or environment failure",
            }
            contract["observability"]["artifacts"] = [
                "capture-manifest.json",
                "oracle-report.json",
                "entry.png",
                "transition.png",
                "final-state.png",
                "diff.png",
            ]
            contract["observability"]["oracle_contract"] = {
                "state": state,
                "runner_sha256": f"sha256:{sha256_bytes(runner.read_bytes())}",
                "comparator_sha256": f"sha256:{sha256_bytes(comparator.read_bytes())}",
                "reference_report": report_ref,
                "reference_report_sha256": f"sha256:{sha256_bytes(qwork_oracle_report_path.read_bytes())}",
                "capture_manifest": capture_ref,
                "capture_manifest_sha256": f"sha256:{sha256_bytes((qwork_oracle_report_path.parent.parent / 'capture' / 'capture-manifest.json').read_bytes())}",
                "max_diff_ratio": float(qwork_oracle_report["policy"]["max_diff_ratio"]),
                "geometry_tolerance_css_px": float(qwork_oracle_report["policy"]["geometry_tolerance_css_px"]),
            }
            status = str(result["status"])
            contract["reference_run"] = {
                "status": "passed" if status == "pass" else "failed",
                "run_id": "qwork-workbuddy-oracle-full-20260813",
                "verified_at": str(qwork_oracle_report["generated_at"]),
                "environment": str(qwork_oracle_capture["isolation"]),
            }
            failure_summary = "; ".join(str(value) for value in result.get("failures", []))
            contract["readiness"] = "ready" if status == "pass" else "partial"
            contract["blockers"] = [] if status == "pass" else [
                f"current revision {qwork_oracle_capture['repo_revision']} fails {state}: {failure_summary}",
            ]
            case["verification"] = {
                "last_outcome": "pass" if status == "pass" else "fail",
                "environment_scope": str(qwork_oracle_capture["isolation"]),
                "implementation_revision": str(qwork_oracle_capture["repo_revision"]),
                "last_verified_at": str(qwork_oracle_report["generated_at"]),
                "status_reason": "reference Oracle passed" if status == "pass" else failure_summary,
            }
            case["ui_acceptance"] = {
                "viewport_profiles": [{"id": "workbuddy-darwin-1680x1084-dpr2", "width": 1680, "height": 1084, "dpr": 2}],
                "required_screenshot_states": ["entry", "transition", "final-state"],
            }
        private_reference = private_reference_runs.get("runs", {}).get(str(case["id"]))
        failed_private_reference = private_reference_runs.get("failed_runs", {}).get(str(case["id"]))
        if private_reference and failed_private_reference:
            raise ValueError(f"private Case cannot register both passing and failed authority: {case['id']}")
        if private_reference:
            contract = case["execution_contract"]
            if not str(contract["route_id"]).startswith("qwork.private-playwright."):
                raise ValueError(f"private reference targets a non-private route: {case['id']}")
            report_ref = str(private_reference["report"])
            report_path = skill_root / report_ref.removeprefix("skill://qwork-test-dataset/")
            if not report_path.is_file():
                raise ValueError(f"private reference report is missing: {report_ref}")
            report_hash = f"sha256:{sha256_bytes(report_path.read_bytes())}"
            if report_hash != str(private_reference["report_sha256"]):
                raise ValueError(f"private reference report hash drifted: {case['id']}")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            source_contract = contract["observability"]["source_contract"]
            if (
                report.get("status") != "pass"
                or report.get("exit_code") != 0
                or report.get("case_id") != case["id"]
                or report.get("case_title") != case["title"]
                or report.get("zero_real_model_calls") is not True
                or report.get("isolated_qwork_home") is not True
                or report.get("evidence", {}).get("integrity") != "complete"
                or report.get("cleanup", {}).get("app_assembly_removed") is not True
                or report.get("source", {}).get("spec") != source_contract["spec"]
                or report.get("source", {}).get("spec_sha256") != source_contract["spec_sha256"]
                or report.get("source", {}).get("implementation_revision") != head
            ):
                raise ValueError(f"private reference authority mismatch: {case['id']}")
            if (report_path.parent / "app").exists():
                raise ValueError(f"private reference retained transient app assembly: {case['id']}")
            expected_authority = [
                {"locator": item["path"], "sha256": item["sha256"]}
                for item in source_contract.get("supporting_contracts", [])
            ]
            supporting_authority_drifted = report.get("authority", {}).get("files") != expected_authority
            selected = report.get("selected_tests", [])
            if len(selected) != 1 or selected[0].get("title") != case["title"] or selected[0].get("status") != "expected":
                raise ValueError(f"private reference did not select one passing Case: {case['id']}")
            screenshots = report.get("evidence", {}).get("screenshots", [])
            for state in private_reference["required_screenshot_states"]:
                if not any(state in str(item.get("path") or "") for item in screenshots):
                    raise ValueError(f"private reference screenshot is missing: {case['id']} {state}")
            traces = report.get("evidence", {}).get("traces", [])
            if len(traces) != 1:
                raise ValueError(f"private reference must contain one trace: {case['id']}")
            for artifact in [
                report["evidence"]["build_manifest"],
                report["evidence"]["playwright_report"],
                report["evidence"]["stderr"],
                report["evidence"]["electron_runtime"],
                *screenshots,
                *traces,
            ]:
                artifact_path = report_path.parent / str(artifact["path"])
                actual = f"sha256:{sha256_bytes(artifact_path.read_bytes())}"
                if actual != str(artifact["sha256"]):
                    raise ValueError(f"private reference artifact hash drifted: {case['id']} {artifact['path']}")
            contract["reference_run"] = {
                "status": "passed",
                "run_id": str(private_reference["run_id"]),
                "verified_at": str(report["finished_at"]),
                "environment": "isolated Electron build, case-owned QWork home, deterministic fake sidecar, zero real model calls",
            }
            contract["readiness"] = "ready"
            contract["blockers"] = []
            contract["observability"]["artifacts"] = [
                "report.json",
                "build-manifest.json",
                "playwright-report.json",
                "entry screenshot",
                "transition screenshot",
                "final-state screenshot",
                "trace.zip",
            ]
            case["verification"] = {
                "last_outcome": "pass",
                "environment_scope": contract["reference_run"]["environment"],
                "implementation_revision": head,
                "last_verified_at": str(report["finished_at"]),
                "status_reason": f"hash-verified private reference run {private_reference['run_id']} passed",
            }
            if supporting_authority_drifted:
                mark_private_reference_stale(
                    case,
                    private_reference,
                    report,
                    "private reference supporting authority drifted; rerun this exact Case with the current private runner",
                )
        elif failed_private_reference:
            contract = case["execution_contract"]
            if not str(contract["route_id"]).startswith("qwork.private-playwright."):
                raise ValueError(f"failed private reference targets a non-private route: {case['id']}")
            report_ref = str(failed_private_reference["report"])
            report_path = skill_root / report_ref.removeprefix("skill://qwork-test-dataset/")
            if not report_path.is_file():
                raise ValueError(f"failed private reference report is missing: {report_ref}")
            report_hash = f"sha256:{sha256_bytes(report_path.read_bytes())}"
            if report_hash != str(failed_private_reference["report_sha256"]):
                raise ValueError(f"failed private reference report hash drifted: {case['id']}")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            source_contract = contract["observability"]["source_contract"]
            if (
                report.get("status") != "fail"
                or report.get("exit_code") == 0
                or report.get("case_id") != case["id"]
                or report.get("case_title") != case["title"]
                or report.get("zero_real_model_calls") is not True
                or report.get("isolated_qwork_home") is not True
                or report.get("evidence", {}).get("integrity") != "complete"
                or report.get("cleanup", {}).get("app_assembly_removed") is not True
                or report.get("source", {}).get("spec") != source_contract["spec"]
                or report.get("source", {}).get("spec_sha256") != source_contract["spec_sha256"]
                or report.get("source", {}).get("implementation_revision") != head
            ):
                raise ValueError(f"failed private reference authority mismatch: {case['id']}")
            if (report_path.parent / "app").exists():
                raise ValueError(f"failed private reference retained transient app assembly: {case['id']}")
            expected_authority = [
                {"locator": item["path"], "sha256": item["sha256"]}
                for item in source_contract.get("supporting_contracts", [])
            ]
            supporting_authority_drifted = report.get("authority", {}).get("files") != expected_authority
            selected = report.get("selected_tests", [])
            if len(selected) != 1 or selected[0].get("title") != case["title"] or selected[0].get("status") != "unexpected":
                raise ValueError(f"failed private reference did not select one failing Case: {case['id']}")
            screenshots = report.get("evidence", {}).get("screenshots", [])
            for state in failed_private_reference["required_screenshot_states"]:
                if not any(state in str(item.get("path") or "") for item in screenshots):
                    raise ValueError(f"failed private reference screenshot is missing: {case['id']} {state}")
            traces = report.get("evidence", {}).get("traces", [])
            if len(traces) != 1:
                raise ValueError(f"failed private reference must contain one trace: {case['id']}")
            for artifact in [
                report["evidence"]["build_manifest"],
                report["evidence"]["playwright_report"],
                report["evidence"]["stderr"],
                report["evidence"]["electron_runtime"],
                *screenshots,
                *traces,
            ]:
                artifact_path = report_path.parent / str(artifact["path"])
                actual = f"sha256:{sha256_bytes(artifact_path.read_bytes())}"
                if actual != str(artifact["sha256"]):
                    raise ValueError(f"failed private reference artifact hash drifted: {case['id']} {artifact['path']}")
            failure_summary = str(failed_private_reference["failure_summary"])
            contract["reference_run"] = {
                "status": "failed",
                "run_id": str(failed_private_reference["run_id"]),
                "verified_at": str(report["finished_at"]),
                "environment": "isolated Electron build, case-owned QWork home, deterministic fake sidecar, zero real model calls",
            }
            contract["readiness"] = "partial"
            contract["blockers"] = [failure_summary]
            contract["observability"]["artifacts"] = [
                "report.json",
                "build-manifest.json",
                "playwright-report.json",
                "entry screenshot",
                "transition screenshot",
                "failure screenshot",
                "trace.zip",
            ]
            case["verification"] = {
                "last_outcome": "fail",
                "environment_scope": contract["reference_run"]["environment"],
                "implementation_revision": head,
                "last_verified_at": str(report["finished_at"]),
                "status_reason": f"hash-verified product gap from {failed_private_reference['run_id']}: {failure_summary}",
            }
            if supporting_authority_drifted:
                mark_private_reference_stale(
                    case,
                    failed_private_reference,
                    report,
                    "failed private reference supporting authority drifted; rerun this exact Case before accepting the product-gap evidence",
                )
        path = cases_dir / f"{case['id']}.json"
        path.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    requirement_to_cases = {req["requirement_id"]: req["case_ids"] for req in requirements if req["coverage_status"] == "covered"}
    category_to_cases: dict[str, set[str]] = defaultdict(set)
    for case_id, case in cases.items():
        for category in case["selection"]["categories"]:
            category_to_cases[category].add(case_id)
    cohort_members: dict[str, set[str]] = {
        "all-active": set(cases),
        "playwright-source-bound": set(),
        "deterministic-no-live-authorization": set(),
        "dataset-verifier": set(),
        "live-external-authorization": set(),
        "source-oracle-runner-gap": set(),
        "ui": set(),
        "visual": set(),
        "geometry": set(),
        "workbuddy-current-cdp": set(),
        "workbuddy-historical-visual": set(),
        "workbuddy-storage": set(),
        "expert-individual": set(),
        "expert-team": set(),
        "projects": set(),
        "automations": set(),
        "connectors": set(),
        "auth": set(),
    }
    for case_id, case in cases.items():
        route = str(case["execution_contract"]["route_id"])
        required_authority = bool(case["execution_contract"]["authorization"]["required"])
        source_ids = {str(item["source_id"]) for item in case["sources"]}
        categories = set(case["selection"]["categories"])
        capability = str(case["coverage"]["capability_id"])
        if route.startswith(("qwork.playwright.", "qwork.private-playwright.")):
            cohort_members["playwright-source-bound"].add(case_id)
            cohort_members["live-external-authorization" if required_authority else "deterministic-no-live-authorization"].add(case_id)
        elif route.startswith(("qwork.dataset.workbuddy-storage.", "qwork.dataset.structured-oracle-source.")):
            cohort_members["dataset-verifier"].add(case_id)
            cohort_members["deterministic-no-live-authorization"].add(case_id)
        elif case["execution_contract"]["launch"]["strategy"] == "manual-blocked":
            cohort_members["source-oracle-runner-gap"].add(case_id)
        if categories & UI_CATEGORIES:
            cohort_members["ui"].add(case_id)
        if "ui-visual" in categories:
            cohort_members["visual"].add(case_id)
        if "ui-geometry" in categories:
            cohort_members["geometry"].add(case_id)
        if "WORKBUDDY-CDP-5-3-12-V4" in source_ids:
            cohort_members["workbuddy-current-cdp"].add(case_id)
        if "WORKBUDDY-VISUAL-REV95" in source_ids:
            cohort_members["workbuddy-historical-visual"].add(case_id)
        if "WORKBUDDY-STORAGE-LOCAL" in source_ids:
            cohort_members["workbuddy-storage"].add(case_id)
        if capability == "expert-market":
            cohort_members["expert-individual"].add(case_id)
        if capability == "expert-team":
            cohort_members["expert-team"].add(case_id)
        if capability in {"projects", "automations", "connectors", "auth"}:
            cohort_members[capability].add(case_id)
    cohort_index = {
        cohort_id: {
            "case_ids": sorted(members),
            "case_count": len(members),
            "membership_sha256": f"sha256:{sha256_text(json.dumps(sorted(members), separators=(',', ':')))}",
        }
        for cohort_id, members in sorted(cohort_members.items())
    }
    conflicts = [
        {
            "conflict_id": "SRC-CONFLICT-WORKBUDDY-T04-T05-DUPLICATE",
            "status": "open-requires-cdp-refresh",
            "reason": "t04-streaming.png and t05-done.png have identical SHA-256 although they claim distinct lifecycle states",
            "sources": ["WORKBUDDY-VISUAL-REV95"],
        },
        {
            "conflict_id": "SRC-FRESHNESS-DEVELOP-REMOTE-UNVERIFIED",
            "status": "environment-blocked",
            "reason": "origin/develop could not be fetched through the current SSH proxy; local develop was captured but is not proven remote-current",
            "sources": [source["source_id"] for source in sources if source["source_id"].startswith("QDEV-")],
        },
        {
            "conflict_id": "SRC-VERSION-WORKBUDDY-5-3-8-VS-5-3-12",
            "status": "scoped-resolution",
            "reason": "Frozen 5.3.8 images remain normative for historical expert/team acceptance; current 5.3.12 CDP is normative for the captured current shell, market, automation and library states. Overlapping visual changes require explicit per-Case adjudication rather than automatic baseline replacement.",
            "sources": ["WORKBUDDY-VISUAL-REV95", "WORKBUDDY-CDP-5-3-12-V4"],
        },
        {
            "conflict_id": "SRC-CONFLICT-COMPOSER-ORACLE-VS-HEAD-E2E",
            "status": "open-product-alignment",
            "reason": "The normative WorkBuddy 5.3.5 Shell/Home Oracle requires a 960x180 Composer container, while the current HEAD E2E hard-asserts an 800x178 surface. The placeholder remains independently covered, but neither implementation evidence nor a passing test may silently supersede the product dimensions.",
            "sources": [
                "WORKBUDDY-ORACLE-5-3-5-WORKBUDDY-5-3-5-SHELL-HOME",
                "QHEAD-E2E-e2e-workbuddy-ui-shell-home-spec-ts",
            ],
            "oracle_locators": [
                "json-pointer:/shared/composer/targetContainerWidth",
                "json-pointer:/shared/composer/targetContainerHeight",
            ],
            "observed_contract": {
                "locator": "git:19f210518dbad3768eb14a09baa5eea226016c7b:e2e/workbuddy-ui-shell-home.spec.ts#WB-UI-HOME-002",
                "surface_width": 800,
                "surface_height": 178,
            },
            "required_decision": "Align QWork implementation and its E2E expectation to the WorkBuddy Oracle, or explicitly approve a superseding product source before changing the baseline.",
        },
    ]
    manifest = {
        "schema_version": 1,
        "project": "qwork",
        "scope": "full local private product E2E baseline across QWork develop, expert/team history, WorkBuddy requirement/UI/storage sources",
        "generated_at": created_at,
        "implementation_revisions": {"develop": develop, "head": head},
        "develop_closed_world": {
            "source_id": str(develop_snapshot_manifest["source_id"]),
            "inventory_locator": f"skill://qwork-test-dataset/{(develop_snapshot / 'inventory.json').relative_to(output.parent.parent).as_posix()}",
            "inventory_sha256": f"sha256:{develop_snapshot_manifest['inventory_sha256']}",
            "docs_e2e_entry_count": len(develop_closed_world),
            "disposed_entry_count": len(
                {
                    str(item["path"])
                    for item in source_dispositions
                    if str(item["locator"]).startswith(f"git:{develop}:")
                }
            ),
        },
        "geometry_policy": {"tolerance_css_px": 2, "source": "QWork project AGENTS.md"},
        "visual_policy": {"max_diff_ratio": 0.01, "dynamic_masks": "explicit-only"},
        "sources": sources,
        "requirements": requirements,
        "cases": [
            {"case_id": case_id, "title": case["title"], "requirement_ids": case["selection"]["requirement_ids"], "categories": case["selection"]["categories"], "execution_type": case["execution_type"], "route_id": case["execution_contract"]["route_id"], "required_screenshot_states": case.get("ui_acceptance", {}).get("required_screenshot_states", []), "case_locator": f"skill://qwork-test-dataset/data/datasets/cases/{case_id}.json"}
            for case_id, case in sorted(cases.items())
        ],
        "suite_index": {"selection_modes": ["requirement", "category", "cohort", "affected", "full"], "requirement_to_cases": requirement_to_cases, "category_to_cases": {key: sorted(value) for key, value in sorted(category_to_cases.items())}, "cohort_to_cases": {key: value["case_ids"] for key, value in cohort_index.items()}, "full_case_ids": sorted(cases)},
        "cohort_index": cohort_index,
        "coverage_summary": {
            "source_count": len(sources),
            "source_atoms": sum(source["inventory"]["atom_count"] for source in sources),
            "requirements": len(requirements),
            "covered_requirement_count": sum(req["coverage_status"] == "covered" for req in requirements),
            "blocked_requirement_count": sum(req["coverage_status"] == "blocked" for req in requirements),
            "cases": len(cases),
            "unmapped_source_atoms": 0,
            "uncovered_p0_p1": sum(req["priority"] in {"P0", "P1"} and req["coverage_status"] not in {"covered", "not_applicable"} for req in requirements),
            "orphan_cases": 0,
            "execution_ready_cases": sum(case["execution_contract"]["readiness"] == "ready" for case in cases.values()),
            "execution_partial_cases": sum(case["execution_contract"]["readiness"] == "partial" for case in cases.values()),
        },
        "source_conflicts": conflicts,
    }
    (output / "source-acceptance.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    disposition_manifest = {
        "schema_version": 1,
        "project": "qwork",
        "develop_revision": develop,
        "head_revision": head,
        "generated_at": created_at,
        "policy": "Every discovered develop doc/E2E and expert/history head source receives an explicit disposition. Only product-normative sources generate product requirements; governance and context still bind the release gate or evidence registry.",
        "closed_world": {
            "inventory_locator": f"skill://qwork-test-dataset/{(develop_snapshot / 'inventory.json').relative_to(output.parent.parent).as_posix()}",
            "inventory_sha256": f"sha256:{develop_snapshot_manifest['inventory_sha256']}",
            "expected_develop_docs_e2e_paths": len(develop_closed_world),
            "disposed_develop_docs_e2e_paths": len(
                {
                    str(item["path"])
                    for item in source_dispositions
                    if str(item["locator"]).startswith(f"git:{develop}:")
                }
            ),
            "status": "closed",
        },
        "dispositions": sorted(source_dispositions, key=lambda item: (item["path"], item["locator"])),
        "counts": dict(sorted({value: sum(item["disposition"] == value for item in source_dispositions) for value in {item["disposition"] for item in source_dispositions}}.items())),
    }
    (output / "source-dispositions.json").write_text(json.dumps(disposition_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dataset = {
        "schema_version": 1,
        "dataset": {"name": "qwork/full-product-private-e2e", "version": created_at[:10] + ".1", "owner": "qwork", "visibility": "private", "storage": {"kind": "project-skill", "skill": "qwork-test-dataset", "path": "data/datasets/cases"}, "created_at": created_at, "source_policy": "provenance-required", "redaction_policy": "private-minimized", "source_acceptance_manifest": "data/datasets/source-acceptance.json", "selection_modes": ["requirement", "category", "cohort", "affected", "full"], "cohort_index": "data/datasets/cohorts.json"},
        "items": [{"case_id": case_id, "case_version": 1, "kind": case["kind"], "lifecycle_status": case["lifecycle_status"], "execution_mode": case["execution_mode"], "source_requirement_ids": case["selection"]["requirement_ids"], "categories": case["selection"]["categories"], "suite_ids": case["selection"]["suite_ids"], "route_id": case["execution_contract"]["route_id"], "verification": case["verification"], "case_locator": f"data/datasets/cases/{case_id}.json", "redaction": {"status": "complete", "reviewed_at": created_at}} for case_id, case in sorted(cases.items())],
    }
    (output / "dataset.json").write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cohorts = {
        "schema_version": 1,
        "dataset_name": dataset["dataset"]["name"],
        "dataset_version": dataset["dataset"]["version"],
        "generated_at": created_at,
        "cohorts": [
            {"cohort_id": cohort_id, **value}
            for cohort_id, value in cohort_index.items()
        ],
    }
    (output / "cohorts.json").write_text(json.dumps(cohorts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    storage_disposition_manifest = {
        "schema_version": 1,
        "policy_version": "qwork-workbuddy-storage-disposition/v1",
        "generated_at": created_at,
        "source_snapshot": f"skill://qwork-test-dataset/{storage_dir.relative_to(skill_root).as_posix()}",
        "source_inventory_sha256": str(storage_manifest["inventory_sha256"]),
        "source_canonical_sha256": sha256_text(json.dumps(storage_inventory, ensure_ascii=False, sort_keys=True, separators=(",", ":"))),
        "source_entry_count": len(storage_inventory),
        "source_atom_count": len(storage_atoms),
        "record_count": len(storage_dispositions),
        "rules": {
            "one_atom_one_disposition": True,
            "silent_drop_forbidden": True,
            "source_alias_in_identity_forbidden": True,
            "live_roots_read_or_written": False,
        },
        "counts": {
            "decision_status": dict(sorted({value: sum(item["decision_status"] == value for item in storage_dispositions) for value in {item["decision_status"] for item in storage_dispositions}}.items())),
            "implementation_status": dict(sorted({value: sum(item["implementation_status"] == value for item in storage_dispositions) for value in {item["implementation_status"] for item in storage_dispositions}}.items())),
            "treatment": dict(sorted({value: sum(item["treatment"] == value for item in storage_dispositions) for value in {item["treatment"] for item in storage_dispositions}}.items())),
        },
        "records": sorted(storage_dispositions, key=lambda item: item["atom_id"]),
    }
    (output / "workbuddy-storage-dispositions.json").write_text(
        json.dumps(storage_disposition_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    interaction_inventory = skill_root / "data/datasets/workbuddy-interaction-inventory.json"
    if interaction_inventory.is_file():
        shutil.copy2(interaction_inventory, output / interaction_inventory.name)
    backup = final_output.parent / f".{final_output.name}.previous-{os.getpid()}"
    if backup.exists():
        raise ValueError(f"dataset transaction backup already exists: {backup}")
    had_previous = final_output.exists()
    if had_previous:
        os.replace(final_output, backup)
    try:
        os.replace(output, final_output)
    except BaseException:
        if had_previous and backup.exists() and not final_output.exists():
            os.replace(backup, final_output)
        raise
    if backup.exists():
        shutil.rmtree(backup)
    print(json.dumps({"status": "ok", **manifest["coverage_summary"], "manifest": str(final_output / "source-acceptance.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
