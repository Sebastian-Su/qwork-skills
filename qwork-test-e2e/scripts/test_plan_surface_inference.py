#!/usr/bin/env python3
"""Regression checks for affected-plan capability inference."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def load_builder():
    path = Path(__file__).resolve().parent / "build_release_gate_plan.py"
    spec = importlib.util.spec_from_file_location("qwork_plan_builder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    builder = load_builder()
    assert builder.infer_surface(
        "src/shared/api.ts",
        "+ models: { listCustom, setMaxMode }",
    ) == "models"
    assert builder.infer_surface(
        "src/main/sidecar/SidecarSupervisor.ts",
        "+ async reloadRuntimeSettings(): Promise<void>",
    ) == "settings"
    assert builder.infer_surface(
        "src/main/sidecar/supervisorRuntimeSettings.test.ts",
    ) == "settings"
    assert builder.infer_surface(
        "src/main/runtimeSettings.ts",
        "+ autoCompactEnabled: enabled\n+ Max 模式",
    ) == "models"
    assert builder.infer_surface(
        "src/main/e2eStartupPolicy.ts",
        "+ QWORK_E2E_MODEL_MENU_BUNDLED_SKILLS_ROOT",
    ) == "models"
    assert builder.infer_surface(
        "src/renderer/src/components/ToolCallCard.tsx",
        "+ if (event.type === 'media_progress') renderMediaProgress(event)",
    ) == "media-generation"
    assert builder.infer_surface(
        "src/main/sidecar/QWorkApiCredentialBroker.ts",
        "+ export class QWorkApiCredentialBroker {}",
    ) == "media-generation"
    assert builder.infer_surface(
        "src/shared/protocol.ts",
        "+ qwork_api_credentials: true",
    ) == "media-generation"
    assert builder.gate_only_item_ids("vitest.config.ts", "") == ["gate:coverage"]
    assert builder.gate_only_item_ids(
        "e2e/fixtures/launch.ts",
        "+ const evidenceDir = process.env.QWORK_RELEASE_GATE_EVIDENCE_DIR\n+ captureReleaseGateState(app, 'entry')",
    ) == ["gate:electron-build"]
    assert builder.gate_only_item_ids(
        "e2e/fixtures/launch.ts",
        "+ export async function launchApp() {}",
    ) == []
    assert builder.gate_only_item_ids(
        "docs/team-collaboration/interface-ledger.md",
        "+ protocol evidence",
    ) == ["gate:source-dispositions"]
    semantic, anchors = builder.infer_unique_semantic_cases(
        {
            "EXPERT-CONTEXT": {
                "title": "SessionStart hidden context",
                "expected": "session_start_additional_context controlHasExpertIdentity",
            },
            "ADJACENT-HELPER": {
                "title": "helper",
                "expected": "verifyTrustedExpertActivation",
            },
        },
        "+ session_start_additional_context\n+ controlHasExpertIdentity\n+ verifyTrustedExpertActivation",
    )
    assert semantic == ["EXPERT-CONTEXT"]
    assert anchors == ["controlHasExpertIdentity", "session_start_additional_context"]
    media_selected, media_excluded, media_noncausal = builder.infer_executable_capability_cases(
        {
            "IMAGEGEN": {
                "coverage": {"capability_id": "media-generation"},
                "execution_contract": {
                    "launch": {"strategy": "command"},
                    "observability": {"source_contract": {"action_count": 6}},
                },
            },
            "VIDEOGEN": {
                "coverage": {"capability_id": "media-generation"},
                "execution_contract": {
                    "launch": {"strategy": "command"},
                    "observability": {"source_contract": {"action_count": 22}},
                },
            },
            "UNRELATED-AUTH": {
                "coverage": {"capability_id": "auth"},
                "execution_contract": {
                    "launch": {"strategy": "command"},
                    "observability": {"source_contract": {"action_count": 3}},
                },
            },
        },
        "media-generation",
    )
    assert media_selected == ["IMAGEGEN", "VIDEOGEN"]
    assert media_excluded == []
    assert media_noncausal == []
    assert builder.case_requires_macos_native_fullscreen({
        "title": "macOS 原生全屏移除交通灯偏移",
        "execution_contract": {"observability": {"source_contract": {
            "spec": "e2e/ui-layout-native-window.spec.ts",
        }}},
    }) is True
    assert builder.case_requires_macos_native_fullscreen({
        "title": "ordinary window state",
        "execution_contract": {"observability": {"source_contract": {
            "spec": "e2e/window.spec.ts",
        }}},
    }) is False
    selected, excluded, noncausal = builder.infer_executable_capability_cases(
        {
            "MODEL-UI": {
                "coverage": {"capability_id": "models"},
                "execution_contract": {"launch": {"strategy": "command"}},
            },
            "MODEL-SOURCE-REQ": {
                "coverage": {"capability_id": "models"},
                "execution_contract": {
                    "launch": {"strategy": "command"},
                    "observability": {"source_contract": None},
                },
            },
            "MODEL-DOC-GAP": {
                "coverage": {"capability_id": "models"},
                "execution_contract": {"launch": {"strategy": "manual-blocked"}},
            },
            "MODEL-ASSERTION-ONLY": {
                "coverage": {"capability_id": "models"},
                "execution_contract": {
                    "launch": {"strategy": "command"},
                    "observability": {"source_contract": {"action_count": 0}},
                },
            },
            "MODEL-CONCURRENCY": {
                "title": "Provider Model 并发与 TPM 限流",
                "coverage": {"capability_id": "models"},
                "execution_contract": {
                    "launch": {"strategy": "command"},
                    "observability": {"source_contract": {"action_count": 1}},
                },
                "ui_acceptance": {"required_screenshot_states": ["entry", "final-state"]},
            },
            "MODEL-TEAM-POLICY": {
                "title": "成员模型覆盖与主会话回退",
                "coverage": {"capability_id": "models"},
                "execution_contract": {
                    "launch": {"strategy": "command"},
                    "observability": {"source_contract": {
                        "action_count": 2,
                        "spec": "skill://qwork-test-dataset/data/e2e/expert-model-concurrency-contract.spec.ts",
                    }},
                },
                "ui_acceptance": {"required_screenshot_states": ["entry", "final-state"]},
            },
            "MODEL-FIRST-EVENT-TIMEOUT": {
                "title": "模型首事件超时必须结束等待并提供可重试终态",
                "coverage": {"capability_id": "models"},
                "execution_contract": {
                    "launch": {"strategy": "command"},
                    "observability": {"source_contract": {
                        "action_count": 5,
                        "spec": "skill://qwork-test-dataset/data/e2e/model-first-event-timeout.spec.ts",
                    }},
                },
                "ui_acceptance": {"required_screenshot_states": ["entry", "transition", "final-state"]},
            },
            "SETTINGS-UI": {
                "coverage": {"capability_id": "settings"},
                "execution_contract": {"launch": {"strategy": "command"}},
            },
        },
        "models",
    )
    assert selected == ["MODEL-SOURCE-REQ", "MODEL-UI"]
    assert excluded == ["MODEL-DOC-GAP"]
    assert noncausal == [
        "MODEL-ASSERTION-ONLY",
        "MODEL-CONCURRENCY",
        "MODEL-FIRST-EVENT-TIMEOUT",
        "MODEL-TEAM-POLICY",
    ]
    retained, superseded = builder.partition_exact_cases(
        {
            "OLD": {
                "title": "old model priority",
                "execution_contract": {
                    "observability": {
                        "source_contract": {
                            "spec": "e2e/model.spec.ts",
                            "execution_revision": "base",
                        }
                    }
                },
            },
            "CURRENT": {
                "title": "new Auto priority",
                "execution_contract": {
                    "observability": {
                        "source_contract": {
                            "spec": "e2e/model.spec.ts",
                            "execution_revision": "head",
                        }
                    }
                },
            },
        },
        ["CURRENT", "OLD"],
        head="head",
        path="e2e/model.spec.ts",
        current_content='test("new Auto priority", () => {})',
    )
    assert retained == ["CURRENT"]
    assert superseded == ["OLD"]
    print("plan surface inference: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
