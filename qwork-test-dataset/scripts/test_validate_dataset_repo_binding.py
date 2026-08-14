#!/usr/bin/env python3
"""Regression test: the aggregate validator must use the explicit QWork repo."""

from __future__ import annotations

import pathlib

from validate_dataset import playwright_identity_command


def main() -> int:
    skill_root = pathlib.Path("/private/qwork-skills/qwork-test-dataset")
    qwork_repo = pathlib.Path("/workspace/qwork")
    command = playwright_identity_command(skill_root, qwork_repo)
    repo_index = command.index("--repo") + 1
    skill_index = command.index("--skill-root") + 1
    assert command[repo_index] == str(qwork_repo)
    assert command[skill_index] == str(skill_root)
    assert command[repo_index] != str(skill_root.parent.parent.parent)
    print("aggregate Dataset repo binding test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
