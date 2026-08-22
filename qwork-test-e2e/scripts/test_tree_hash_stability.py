#!/usr/bin/env python3
"""Keep frozen authority stable when only ephemeral run evidence changes."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    scripts = Path(__file__).resolve().parent
    builder = load_module(scripts / "build_release_gate_plan.py", "qwork_plan_builder")
    runner = load_module(scripts / "run_release_gate_plan.py", "qwork_plan_runner")
    evaluator = load_module(scripts / "evaluate_release_gate.py", "qwork_gate_evaluator")

    with tempfile.TemporaryDirectory(prefix="qwork-tree-hash-") as value:
        root = Path(value)
        (root / "references").mkdir()
        (root / "references/authority.yaml").write_text("version: 1\n", encoding="utf-8")

        initial_builder = builder.tree_hash(root)[0]
        initial_runner = runner.tree_hash(root)
        initial_evaluator = evaluator.tree_hash(root)
        if len({initial_builder, initial_runner, initial_evaluator}) != 1:
            raise RuntimeError("builder, runner and evaluator disagree before run output exists")

        (root / "data/runs/example").mkdir(parents=True)
        (root / "data/runs/example/plan.json").write_text("{}\n", encoding="utf-8")
        if builder.tree_hash(root)[0] != initial_builder:
            raise RuntimeError("builder authority changed after data/runs output")
        if runner.tree_hash(root) != initial_runner:
            raise RuntimeError("runner authority changed after data/runs output")
        if evaluator.tree_hash(root) != initial_evaluator:
            raise RuntimeError("evaluator authority changed after data/runs output")

        (root / "references/authority.yaml").write_text("version: 2\n", encoding="utf-8")
        if builder.tree_hash(root)[0] == initial_builder:
            raise RuntimeError("builder ignored an authoritative reference change")
        if runner.tree_hash(root) == initial_runner:
            raise RuntimeError("runner ignored an authoritative reference change")
        if evaluator.tree_hash(root) == initial_evaluator:
            raise RuntimeError("evaluator ignored an authoritative reference change")

    print("tree hash stability: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
