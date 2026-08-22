#!/usr/bin/env python3
"""Fail closed when a real-provider QWork Case lacks explicit authorization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REAL_PROVIDER_SPEC = "e2e/real-expert-agent.spec.ts"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", type=Path, required=True)
    args = parser.parse_args()
    case_dir = args.skill_root.resolve() / "data/datasets/cases"
    cases = [
        case
        for path in case_dir.glob("*.json")
        for case in [json.loads(path.read_text(encoding="utf-8"))]
        if (
            ((case.get("execution_contract") or {}).get("observability") or {})
            .get("source_contract")
            or {}
        )
        .get("spec")
            == REAL_PROVIDER_SPEC
    ]
    if len(cases) != 2:
        raise AssertionError(
            f"expected exactly 2 real-provider Cases from {REAL_PROVIDER_SPEC}, found {len(cases)}"
        )
    for case in sorted(cases, key=lambda item: item["id"]):
        case_id = case["id"]
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
    print(f"real-provider authorization gate: {len(cases)} Cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
