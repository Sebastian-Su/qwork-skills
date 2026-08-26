#!/usr/bin/env python3
"""Focused regression tests for source atom semantic extraction."""

from __future__ import annotations

import importlib.util
import json
import struct
import tempfile
from pathlib import Path


def load_builder():
    path = Path(__file__).with_name("build_product_baseline.py")
    spec = importlib.util.spec_from_file_location("qwork_dataset_builder", path)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load build_product_baseline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_module(name: str):
    path = Path(__file__).with_name(name)
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    builder = load_builder()

    for title in (
        "登录用户用自然语言生图后只看到保存到工作区的本地产物",
        "生视频逐次授权并展示阶段，停止只终止本地等待",
    ):
        actual = builder.test_surface("e2e/built-in-media-generation.spec.ts", title)
        if actual != "media-generation":
            raise AssertionError(f"media generation E2E was classified as {actual!r}")

    examples = {
        "关键截图、report.json 和 SHA-256 必须归档": "evidence-provenance",
        "纯图标按钮必须具有稳定的中文 accessible name": "accessibility",
        "所有纯图标按钮均有可访问名称": "accessibility",
        "动画尊重 prefers-reduced-motion，状态不得仅以颜色区分": "accessibility",
        "点击搜索图标后，标题栏原位展开搜索输入区": "ui-interaction",
        "加载 icon.svg 并把 data URI 持久化到 DTO 的 icon 字段": "data-side-effect",
        "完成使用绿色图标；失败使用明确失败图标": "state-transition",
        "最大化单张截图像素差异率不超过 1.5%": "non-functional",
        "三张专家团真机执行截图作为 WorkBuddy Oracle 来源": "evidence-provenance",
        "为对齐截图而写死不可运行的假数据": "negative-rule",
        "图标位恒存在，没有图标时也保留占位": "ui-structure",
        "卡片圆角、阴影和背景颜色必须与批准设计一致": "ui-visual",
    }
    for text, expected in examples.items():
        actual = builder.classify(text, ui_hint=True)
        if actual != expected:
            raise AssertionError(f"classify({text!r})={actual!r}, expected {expected!r}")

    registry_atom = {
        "facet": "business-rule",
        "label": "<package>@<marketplace> 按 scope 区分安装记录数组，读取用户级 scope: user 记录",
    }
    if builder.atom_requires_ui({"type": "git-document"}, registry_atom):
        raise AssertionError("registry scope contract was misclassified as a user-visible UI requirement")

    xml = """
    <h2 id="tokens">Design tokens</h2>
    <table id="token-table">
      <thead><tr><th><p id="h1">Token</p></th><th><p id="h2">Value</p></th></tr></thead>
      <tbody><tr id="row-1"><td><p id="c1">--cb-green-color</p></td><td><p id="c2">#00b96b</p></td></tr></tbody>
    </table>
    """
    atoms = builder.lark_atoms("SRC", xml)
    if len(atoms) != 1:
        raise AssertionError(f"table extraction produced {len(atoms)} atoms instead of one data row")
    atom = atoms[0]
    if atom["locator"] != "block:row-1;heading:Design tokens":
        raise AssertionError(f"table row locator is not stable: {atom['locator']}")
    if atom["label"] != "--cb-green-color | #00b96b":
        raise AssertionError(f"table row cells were not preserved together: {atom['label']}")
    if atom["facet"] != "ui-visual":
        raise AssertionError(f"design token row has wrong facet: {atom['facet']}")

    media = load_module("capture_lark_media.py")
    with tempfile.TemporaryDirectory(prefix="qwork-png-dimensions-") as root:
        image = Path(root) / "frame.png"
        image.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13)
            + b"IHDR"
            + struct.pack(">II", 3360, 2168)
            + b"\x08\x06\x00\x00\x00"
        )
        if media.image_dimensions(image) != (3360, 2168):
            raise AssertionError("media capture did not read physical PNG dimensions")

    skill_root = Path(__file__).resolve().parents[1]
    visual_path = (
        skill_root
        / "data/benchmarks/ui-visual/workbuddy-feishu-revision-95/manifest.json"
    )
    visual_manifest = json.loads(visual_path.read_text(encoding="utf-8"))
    calibrations = builder.load_visual_calibrations(
        skill_root, visual_path, visual_manifest
    )
    if len(calibrations) != 26:
        raise AssertionError(f"visual calibration closed world is {len(calibrations)}, expected 26")
    expert = calibrations["workbuddy-expert-market.png"]
    if expert["viewport"] != {"width": 1680, "height": 1084, "dpr": 2}:
        raise AssertionError(f"expert frame calibration drifted: {expert['viewport']}")

    print("source atom semantic extraction: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
