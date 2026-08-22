#!/usr/bin/env python3
"""Derive a closed, privacy-minimized WorkBuddy control interaction ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
from collections import Counter
from typing import Any


ACTIONABLE_TAGS = {"a", "button", "input", "select", "textarea"}
ACTIONABLE_ROLES = {
    "button", "checkbox", "combobox", "link", "menuitem", "menuitemcheckbox",
    "menuitemradio", "option", "radio", "slider", "spinbutton", "switch", "tab", "textbox",
}

CASES = {
    "sidebar_oracle": "QW-E2E-PRIVATE-FUNCTIONAL-CONTRACTS-SPEC-762BA0DA",
    "sidebar_collapse": "QW-E2E-UI-LAYOUT-SHELL-HOME-SPEC-48230AF7",
    "sidebar_search_filter": "QW-E2E-UI-JOURNEY-SIDEBAR-ACCOUNT-SPEC-6BFC6BBC",
    "sidebar_history": "QW-E2E-UI-JOURNEY-SIDEBAR-ACCOUNT-SPEC-10B2C20A",
    "sidebar_footer": "QW-E2E-UI-JOURNEY-SIDEBAR-ACCOUNT-SPEC-D902F746",
    "account": "QW-E2E-UI-JOURNEY-SIDEBAR-ACCOUNT-SPEC-C43AD151",
    "home": "QW-E2E-UI-LAYOUT-SHELL-HOME-SPEC-AFF15030",
    "composer": "QW-E2E-UI-LAYOUT-SHELL-HOME-SPEC-01670D4E",
    "permission": "QW-E2E-UI-LAYOUT-SHELL-HOME-SPEC-C528DC9E",
    "task_waiting": "QW-E2E-UI-JOURNEY-TASK-LIFECYCLE-SPEC-2CDE4AA8",
    "task_done": "QW-E2E-UI-JOURNEY-TASK-LIFECYCLE-SPEC-C8015AE3",
    "task_artifact": "QW-E2E-UI-JOURNEY-TASK-LIFECYCLE-SPEC-77EA17F5",
    "project": "QW-E2E-UI-JOURNEY-SECONDARY-SURFACES-SPEC-61A2B17F",
    "market_top": "QW-E2E-UI-JOURNEY-EXPERT-MARKET-SPEC-F6F1C4ED",
    "market_scene": "QW-E2E-UI-JOURNEY-EXPERT-MARKET-SPEC-B0863473",
    "market_filter": "QW-E2E-UI-JOURNEY-EXPERT-MARKET-SPEC-2F29967C",
    "market_card": "QW-E2E-UI-JOURNEY-EXPERT-MARKET-SPEC-191F76C8",
    "market_detail": "QW-E2E-UI-JOURNEY-EXPERT-MARKET-SPEC-2A9F86FC",
    "expert_summon": "QW-E2E-PRIVATE-FUNCTIONAL-CONTRACTS-SPEC-DDF919C7",
    "team_summon": "QW-E2E-PRIVATE-FUNCTIONAL-CONTRACTS-SPEC-16EA4BFF",
    "team_detail": "QW-E2E-UI-JOURNEY-EXPERT-MARKET-SPEC-62FC83D2",
    "skill_market": "QW-E2E-UI-JOURNEY-SECONDARY-SURFACES-SPEC-0D6AE10E",
    "connector_market": "QW-E2E-UI-JOURNEY-SECONDARY-SURFACES-SPEC-FBF49ACD",
    "automation": "QW-E2E-UI-JOURNEY-SECONDARY-SURFACES-SPEC-61E7AB5B",
    "automation_oracle": "QW-E2E-PRIVATE-FUNCTIONAL-CONTRACTS-SPEC-784ABD65",
    "library": "QW-E2E-UI-JOURNEY-SECONDARY-SURFACES-SPEC-B163B51E",
}

GLOBAL_NAV = {"新建任务", "助理", "项目", "专家·技能·连接器", "自动化", "资料库", "更多 应用·灵感"}
MARKET_NAV = {"专家", "技能", "连接器", "专家团"}
AUTOMATION_NAV = {"定时任务", "运行记录"}
LIBRARY_NAV = {"我的邮箱", "腾讯文档", "ima知识库", "乐享知识库", "灵感"}
EXTERNAL_RE = re.compile(r"连接|授权|扫码|分享")
MUTATION_RE = re.compile(r"新建|添加|创建|发送|运行|执行|保存|删除|移除|退出|重新生成|点赞|点踩|Add to favorites|收藏")
def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(payload)


def normalized(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def source_label(control: dict[str, Any]) -> str:
    return normalized(control.get("ariaLabel") or control.get("title") or control.get("text"))


def actionable(control: dict[str, Any]) -> bool:
    return str(control.get("tag") or "") in ACTIONABLE_TAGS or str(control.get("role") or "") in ACTIONABLE_ROLES


def sidebar_history(control: dict[str, Any], label: str) -> bool:
    box = control.get("box") or {}
    return (
        control.get("role") == "button"
        and float(box.get("x") or 0) <= 12.1
        and 239 <= float(box.get("width") or 0) <= 241
        and float(box.get("y") or 0) >= 330
        and label not in GLOBAL_NAV
    )


def account_identity(control: dict[str, Any], label: str) -> bool:
    box = control.get("box") or {}
    return (
        control.get("tag") == "button"
        and float(box.get("x") or 0) <= 12.1
        and float(box.get("width") or 0) >= 150
        and float(box.get("y") or 0) >= 900
        and bool(label)
    )


def private_label(control: dict[str, Any], label: str) -> bool:
    return sidebar_history(control, label) or account_identity(control, label)


def pending(family: str, case_ids: list[str], next_action: str) -> tuple[str, str, str, list[str], str]:
    return "source-case-reference-pending", "pending", family, case_ids, next_action


def gap(family: str, next_action: str, unlabeled: bool = False) -> tuple[str, str, str, list[str], str]:
    classification = "unlabeled-interaction-gap" if unlabeled else "unobserved-local-interaction-gap"
    return classification, "gap", family, [], next_action


def inferred_unlabeled(
    state: str,
    index: int,
    control: dict[str, Any],
) -> tuple[str, list[str]] | None:
    box = control.get("box") or {}
    x = float(box.get("x") or 0)
    y = float(box.get("y") or 0)
    width = float(box.get("width") or 0)
    role = str(control.get("role") or "")
    tag = str(control.get("tag") or "")
    if tag == "input":
        if state == "surface-项目":
            return "project-search", [CASES["project"]]
        if state.startswith("surface-market") or state == "surface-专家-技能-连接器":
            key = "skill_market" if state == "surface-market-技能" else "connector_market" if state == "surface-market-连接器" else "market_top"
            return "market-search", [CASES[key]]
        if state == "surface-library-灵感":
            return "inspiration-search", ["QW-E2E-PRIVATE-FUNCTIONAL-CONTRACTS-SPEC-58E577BB"]
    if state == "surface-library-我的邮箱" and x == 288 and y == 12:
        return "library-back", [CASES["library"]]
    if state == "surface-专家-技能-连接器" and x == 248.5 and width == 144:
        return "market-more-menu-item", [CASES["market_top"]]
    if state == "surface-market-技能" and 134 <= y <= 136 and 25 <= width <= 27:
        return "skill-market-card", [CASES["skill_market"]]
    if state == "surface-新建任务":
        if x == 1232 and y == 433:
            return "home-quick-scene-carousel", [CASES["home"]]
        if x == 614 and y == 567:
            return "composer-product-entry", [CASES["composer"]]
        if role == "button" and 1043 <= x <= 1045 and y == 567:
            return "composer-control", [CASES["composer"]]
        if role == "button" and x == 1326 and y == 567:
            return "composer-send", [CASES["composer"]]
    if state == "surface-助理":
        if y == 123.5 and x in {202, 226}:
            return "assistant-inline-action", [CASES["task_done"]]
        if y == 11.5 and x in {1600, 1636}:
            return "assistant-header-action", [CASES["task_done"]]
        if y < 0 and x in {1352.1953125, 1384.1953125}:
            return "offscreen-message-control", [CASES["task_done"]]
        if y == 1002 and (
            692 <= x <= 695 or x in {1079.984375, 1362.1953125}
        ):
            return "assistant-composer-control", [CASES["composer"]]
    return None


def classify(
    state: str,
    index: int,
    control: dict[str, Any],
    label: str,
    action_targets: dict[str, str],
    case_by_state: dict[str, str],
) -> tuple[str, str, str, list[str], str | None]:
    if not actionable(control):
        return "non-actionable-semantic-node", "covered", "semantic-source-node", [], None
    if control.get("disabled"):
        return "disabled-control", "covered", "disabled-state", [case_by_state[state]], None
    if not label:
        inferred = inferred_unlabeled(state, index, control)
        if inferred:
            family, case_ids = inferred
            return pending(
                family,
                case_ids,
                "Add a stable accessible name to the QWork counterpart, then run and register the exact interaction Case; the source identity is inferred only from frozen geometry and screenshot context.",
            )
        return gap("unlabeled-control", "Capture DOM ancestry and an accessible name, then add an exact isolated QWork interaction Case.", True)

    if label in action_targets:
        target = action_targets[label]
        return "observed-read-only-transition", "covered", "read-only-navigation", [case_by_state[target]], None

    if label == "收起侧边栏":
        return pending("global-sidebar-toggle", [CASES["sidebar_collapse"], CASES["sidebar_oracle"]], "Run and register the exact sidebar collapse/restore Case on the current revision.")
    if label in {"搜索", "筛选"}:
        return pending("global-sidebar-query", [CASES["sidebar_search_filter"], CASES["sidebar_oracle"]], "Repair the WorkBuddy style mismatch and register the current search/filter reference run.")
    if sidebar_history(control, label):
        return pending("conversation-history-item", [CASES["sidebar_history"]], "Run the source-bound history selection, search, filter and count Case with minimized fixtures.")
    if label in {"消息中心", "产物", "概览", "进入全屏", "收起右栏", "关闭"}:
        key = "task_artifact" if label in {"产物", "收起右栏"} else "sidebar_footer" if label == "消息中心" else "task_done"
        return pending("global-shell-action", [CASES[key]], "Execute and register the exact shell transition for this control family.")
    if re.fullmatch(r"WorkBuddy v\d+(?:\.\d+)+", label):
        return pending("product-version-link", [CASES["home"]], "Verify the QWork product identity/version affordance and its non-destructive destination in an isolated shell Case.")
    if account_identity(control, label):
        return pending("account-profile", [CASES["account"]], "Run the account menu Case against the current revision after repairing its Oracle mismatch.")
    if (state.startswith("surface-market") or state == "surface-专家-技能-连接器") and (
        label.startswith("召唤") or (control.get("tag") == "article" and "召唤" in label)
    ):
        team = state == "surface-market-专家团-list"
        return "representative-causality-covered", "covered", "team-summon" if team else "expert-summon", [CASES["team_summon"] if team else CASES["expert_summon"]], None
    if EXTERNAL_RE.search(label):
        return "external-capability-blocked", "blocked", "external-capability", [], "Use a disposable authorized account and an isolated external-service fixture under separate explicit authorization."

    if state == "surface-新建任务":
        if control.get("role") == "tab" or label in {"日常办公", "代码开发"}:
            return pending("home-mode", [CASES["home"]], "Run and register the complete Home mode and quick-scene interaction matrix.")
        if label in {"文档处理", "金融服务", "数据分析及可视化", "个人工作台", "幻灯片", "深度研究", "视频生成", "产品管理"}:
            return pending("home-quick-scene", [CASES["home"]], "Run every quick-scene prefill through the Home Case without sending a model request.")
        if control.get("role") in {"textbox", "combobox"} or label in {"选择工作空间"}:
            key = "permission" if "权限" in label else "composer"
            return pending("composer-control", [CASES[key]], "Run the complete composer, model, permission and workspace selection matrix without sending.")

    if state == "surface-助理":
        if label == "对话内搜索（⌘F / Ctrl+F）":
            return pending("assistant-in-thread-search", [CASES["task_done"]], "Run query, no-result, next/previous, shortcut and focus-return states with a deterministic assistant transcript.")
        if label.startswith("已完成"):
            return pending("assistant-completion-header", [CASES["task_done"]], "Run completion-header expand/collapse, metadata and keyboard states with deterministic timing.")
        if label in {"复制", "朗读", "更多操作"}:
            return pending("assistant-result-action", [CASES["task_done"]], "Run and register copy/read/more result actions with deterministic assistant fixtures.")
        if "权限" in label or label == "默认权限":
            return pending("assistant-permission", [CASES["permission"]], "Run the default and full-access permission selector matrix.")
        if control.get("role") in {"textbox", "combobox"}:
            return pending("assistant-composer", [CASES["composer"]], "Run the assistant composer/model selector matrix without a real provider.")

    if state == "surface-项目":
        if label == "新建项目":
            return "side-effect-not-exercised", "blocked", "project-create", [CASES["project"]], "Exercise create/cancel/save only in an isolated disposable WorkBuddy profile or the QWork fake backend."
        return pending("project-template", [CASES["project"]], "Run each project template as an equivalence member and verify its deterministic prefill and cancel path.")

    if state.startswith("surface-market") or state == "surface-专家-技能-连接器":
        if label.startswith("召唤") or (control.get("tag") == "article" and "召唤" in label):
            team = state == "surface-market-专家团-list"
            return "representative-causality-covered", "covered", "team-summon" if team else "expert-summon", [CASES["team_summon"] if team else CASES["expert_summon"]], None
        if label in {"综合", "最热", "最新"} or control.get("role") == "tab":
            return pending("market-filter-sort", [CASES["market_filter"]], "Run and register every expert/team category and sort permutation with stable catalog fixtures.")
        if label == "我的专家":
            return pending("my-experts", [CASES["market_top"]], "Run My Experts navigation and empty/populated state Cases.")
        if label == "向右滚动":
            return pending("featured-scene-carousel", [CASES["market_scene"]], "Run carousel boundaries, focus order and responsive geometry Cases.")
        if label == "连接":
            return "external-capability-blocked", "blocked", "connector-auth", [CASES["connector_market"]], "Use a disposable connector tenant and separately authorized credentials."
        if state == "surface-market-技能":
            return pending("skill-market-card", [CASES["skill_market"]], "Run the documented current skill-market capability boundary Case.")
        if state == "surface-market-连接器":
            return pending("connector-market-card", [CASES["connector_market"]], "Run connector card geometry/detail Cases without initiating authorization.")
        return pending("expert-market-card", [CASES["market_card"], CASES["market_detail"]], "Run card/detail geometry and content Cases over the exact expert and team cohorts.")

    if state.startswith("surface-automation") or state == "surface-自动化":
        if MUTATION_RE.search(label):
            return "side-effect-not-exercised", "blocked", "automation-mutation", [CASES["automation"]], "Exercise add/edit/save/run/delete with isolated schedule storage and a fake sidecar only."
        return pending("automation-template-or-control", [CASES["automation"], CASES["automation_oracle"]], "Run and register the automation template/editor/list/history interaction matrix.")

    if state == "surface-资料库" or state.startswith("surface-library") or state == "surface-更多-应用-灵感":
        if label == "Add to favorites" or label == "我的收藏":
            return "side-effect-not-exercised", "blocked", "inspiration-favorite", [], "Exercise favorite/unfavorite persistence in an isolated disposable WorkBuddy profile and add the QWork parity Case."
        if state == "surface-library-灵感":
            if control.get("role") == "tab" or control.get("tag") == "input":
                return "source-case-reference-pending", "pending", "inspiration-filter-search", ["QW-E2E-PRIVATE-FUNCTIONAL-CONTRACTS-SPEC-58E577BB"], "Repair the registered inspiration product gap, then rerun search/category empty, filtered and responsive states."
            return "source-case-reference-pending", "pending", "inspiration-card", ["QW-E2E-PRIVATE-FUNCTIONAL-CONTRACTS-SPEC-58E577BB"], "Repair the registered closed-world card/favorite product gap, then rerun the exact Case."
        return pending("library-source", [CASES["library"]], "Run local library navigation, empty, configured and unavailable state Cases without authorizing external sources.")

    if MUTATION_RE.search(label):
        return "side-effect-not-exercised", "blocked", "unclassified-mutation", [], "Exercise this mutation only in an isolated disposable profile after defining cleanup and forbidden outcomes."
    return gap("unmapped-local-control", "Inspect the exact transition and add a source-bound isolated QWork Case; do not infer it from the entry screenshot.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill-root", type=pathlib.Path, required=True)
    parser.add_argument("--snapshot", default="data/evidence/workbuddy-cdp/5.3.14-surfaces-v2")
    parser.add_argument("--output", default="data/datasets/workbuddy-interaction-inventory.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.skill_root.resolve()
    snapshot = root / args.snapshot
    manifest_path = snapshot / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    product_version = str(manifest.get("version") or "")
    if not product_version:
        raise ValueError("WorkBuddy CDP manifest is missing version")
    title_prefix = f"WorkBuddy {product_version} 当前 UI · "
    snapshot_uri = f"skill://qwork-test-dataset/{args.snapshot.strip('/')}"
    policy_path = root / "references/workbuddy-interaction-classification-policy.yaml"

    case_by_state: dict[str, str] = {}
    for path in (root / "data/datasets/cases").glob("*.json"):
        case = json.loads(path.read_text(encoding="utf-8"))
        title = str(case.get("title") or "")
        if title.startswith(title_prefix):
            case_by_state[title.removeprefix(title_prefix)] = str(case["id"])
    states = [str(record["state"]) for record in manifest.get("records", [])]
    if set(states) != set(case_by_state):
        raise ValueError("every frozen CDP state must have one exact source Case before interaction derivation")
    available_cases = {path.stem for path in (root / "data/datasets/cases").glob("*.json")}
    missing_constants = sorted(set(CASES.values()) - available_cases)
    if missing_constants:
        raise ValueError(f"classification policy references missing Cases: {missing_constants}")

    action_targets: dict[str, str] = {}
    for record in manifest.get("records", []):
        action = record.get("action") or {}
        label = normalized(action.get("label"))
        if label:
            action_targets[label] = str(record["state"])

    controls: list[dict[str, Any]] = []
    for record in manifest.get("records", []):
        state = str(record["state"])
        payload = json.loads((snapshot / f"{state}.json").read_text(encoding="utf-8"))
        for index, control in enumerate(payload.get("controls", [])):
            raw_label = source_label(control)
            redacted = private_label(control, raw_label)
            label = None if redacted or not raw_label else raw_label[:160]
            classification, status, family, case_ids, next_action = classify(
                state, index, control, raw_label, action_targets, case_by_state,
            )
            fingerprint = canonical_hash({"state": state, "index": index, "control": control})
            entry = {
                "control_id": f"WBC-{fingerprint[:16].upper()}",
                "state": state,
                "index": index,
                "source_locator": f"{snapshot_uri}/{state}.json#/controls/{index}",
                "control_sha256": f"sha256:{canonical_hash(control)}",
                "tag": control.get("tag"),
                "role": control.get("role"),
                "label": label,
                "label_redacted": redacted,
                "disabled": bool(control.get("disabled")),
                "actionable": actionable(control),
                "classification": classification,
                "status": status,
                "family": family,
                "case_ids": sorted(set(case_ids)),
                "next_action": next_action,
            }
            controls.append(entry)

    status_counts = Counter(entry["status"] for entry in controls)
    class_counts = Counter(entry["classification"] for entry in controls)
    family_counts = Counter(entry["family"] for entry in controls)
    actionable_count = sum(bool(entry["actionable"]) for entry in controls)
    result = {
        "schema_version": 1,
        "authority": {
            "source": f"{snapshot_uri}/manifest.json",
            "manifest_sha256": f"sha256:{sha256_bytes(manifest_bytes)}",
            "product": manifest.get("product"),
            "version": manifest.get("version"),
            "captured_at": manifest.get("captured_at"),
            "mutation_policy": manifest.get("mutation_policy"),
        },
        "classification_policy": "skill://qwork-test-dataset/references/workbuddy-interaction-classification-policy.yaml",
        "classification_policy_sha256": f"sha256:{sha256_bytes(policy_path.read_bytes())}",
        "privacy": {
            "raw_user_authored_labels_copied": False,
            "redacted_control_count": sum(bool(entry["label_redacted"]) for entry in controls),
        },
        "summary": {
            "state_count": len(states),
            "control_count": len(controls),
            "actionable_count": actionable_count,
            "non_actionable_count": len(controls) - actionable_count,
            "status_counts": dict(sorted(status_counts.items())),
            "classification_counts": dict(sorted(class_counts.items())),
            "family_counts": dict(sorted(family_counts.items())),
            "unclassified_count": 0,
        },
        "controls": controls,
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "output": str(output), **result["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
