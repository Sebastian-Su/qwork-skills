#!/usr/bin/env python3
"""Fail closed when a real-provider QWork Case lacks explicit authorization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REAL_PROVIDER_CASE_IDS = {
    "QW-E2E-REAL-EXPERT-AGENT-SPEC-11602AAB",
    "QW-E2E-REAL-EXPERT-AGENT-SPEC-A481C263",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", type=Path, required=True)
    args = parser.parse_args()
    case_dir = args.skill_root.resolve() / "data/datasets/cases"
    cases = {
        case["id"]: case
        for path in case_dir.glob("*.json")
        for case in [json.loads(path.read_text(encoding="utf-8"))]
    }
    for case_id in sorted(REAL_PROVIDER_CASE_IDS):
        case = cases[case_id]
        contract = case["execution_contract"]
        authorization = contract["authorization"]
        if authorization.get("required") is not True:
            raise AssertionError(f"real-provider Case is not authorization-gated: {case_id}")
        if "real external account/service/model route named by the source test" not in authorization.get("scopes", []):
            raise AssertionError(f"real-provider Case lacks an explicit scope: {case_id}")
        if "independent authorization for real external route pending" not in contract["blockers"]:
            raise AssertionError(f"real-provider Case lacks the authorization blocker: {case_id}")
        setup = str(contract["fixtures"].get("setup") or "")
        if "separately authorized real external fixture" not in setup:
            raise AssertionError(f"real-provider Case fixture is not fail-closed: {case_id}")
    print(f"real-provider authorization gate: {len(REAL_PROVIDER_CASE_IDS)} Cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
