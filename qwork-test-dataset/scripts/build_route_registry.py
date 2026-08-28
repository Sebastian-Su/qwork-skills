#!/usr/bin/env python3
"""Build the exact Case -> execution route registry from the private Dataset."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import yaml


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.skill_root.resolve()
    output = (args.output or root / "references/route-registry.yaml").resolve()
    case_dir = root / "data/datasets/cases"
    cases = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(case_dir.glob("*.json"))]
    routes: dict[str, dict] = {}
    for case in cases:
        contract = case["execution_contract"]
        route_id = str(contract["route_id"])
        if route_id in routes:
            raise ValueError(f"duplicate route_id: {route_id}")
        source_contract = contract["observability"].get("source_contract")
        route = {
            "case_id": case["id"],
            "capability_id": case["coverage"]["capability_id"],
            "readiness": contract["readiness"],
            "target": contract["target"],
            "authorization": contract["authorization"],
            "launch": contract["launch"],
            "navigation": contract["navigation"],
            "fixtures": contract["fixtures"],
            "evidence": contract["observability"]["artifacts"],
            "source_contract": source_contract,
            "oracle_contract": contract["observability"].get("oracle_contract"),
        }
        routes[route_id] = route
    payload = {
        "schema_version": 2,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "policy": {
            "case_to_route": "one-to-one",
            "playwright_contract": "test body SHA, line range, action and assertion count are mandatory",
            "source_requirement_routes": "manual-blocked until a dedicated runner exists; delegated command routes must name one source-bound Playwright Case and reuse its exact command; executable Oracle routes retain failing reference truth",
            "workbuddy_oracle": "read-only Electron CDP only; never mutate account or product data",
        },
        "route_count": len(routes),
        "routes": routes,
    }
    output.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=True), encoding="utf-8")
    print(json.dumps({"status": "ok", "routes": len(routes), "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
