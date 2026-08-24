---
name: qwork-test-e2e
description: QWork Electron 客户端的完整项目 E2E 编排与发布门禁。用于功能回归、全量测试、WorkBuddy UI/存储对齐、专家/专家团真实旅程、Figma/截图像素验收、变更影响闭包、发布前检查和图文报告；绑定私有 qwork-test-dataset，生成不可静默缩减的 plan，只依据当前机器证据输出 test-ready、repair-required 或 external-blocked。
---

# QWork Test E2E

先读仓库根 `AGENTS.md` 和 `docs/testing-guide.md`。产品 Oracle 与 Case 的唯一真实源是 `$qwork-test-dataset`；本 Skill 只规划、执行、取证、判定和报告。

## 终态与继续规则

- `test-ready`：当前 revision 的完整影响闭包、全部必需项、证据、cleanup 和独立重跑通过。
- `repair-required`：本地产品/测试/Case/Dataset/fixture/runner/locator/环境/证据缺口；这是继续信号，读取 checkpoint 的 `repair_required_next_action` 自动修复、重建 plan、重跑全部必需项，不得结束。
- `external-blocked`：只允许新权限/凭据、不可用外部账号/服务/设备、付费或不可逆授权、未裁决产品/Figma/API 语义；必须有排除性检查和唯一解锁动作。

任何本地缺口优先于外部 blocker。`final_response_allowed` 默认 false，只有当前 revision 的 `test-ready` 或严格 `external-blocked` 才能为 true。

## 权威绑定

~~~yaml
source_acceptance_manifest: skill://qwork-test-dataset/data/datasets/source-acceptance.json
dataset_manifest: skill://qwork-test-dataset/data/datasets/dataset.json
workbuddy_target_baseline: skill://qwork-test-dataset/references/workbuddy-target-baseline.yaml
selection_modes: [requirement, category, affected, full]
release_gate_policy: references/release-gate-policy.yaml
release_gate_contract: references/release-gate-contract.md
report_policy: references/report-policy.yaml
artifact_root: test-artifacts/e2e/<run-id>
screenshot_checkpoints: [entry, major-state-transition, before-and-after-important-mutation, assertion-failure, final-state]
~~~

执行前必须运行 `scripts/validate_source_acceptance.py`，并通过 Dataset Skill 的 `validate_source_dispositions.py` 与 `validate_route_registry.py`。任何 unmapped source atom、未覆盖 P0/P1 requirement、develop 文档/E2E 处置缺口、Case/route 不闭合、Playwright test body hash 漂移、错误 suite index 或用户可见需求没有真实 UI route 均为 `repair-required`。详细几何要求使用 `ui-geometry` Oracle：固定 viewport/DPR/坐标空间/target/容差；默认几何容差 `±2 CSS px`，像素阈值与 mask 必须来自批准基线。

Full plan 还必须把 Dataset 的复合文档 Case 映射、结构化 WorkBuddy Oracle 映射、WorkBuddy 控件闭世界清单和真实 provider Case 授权边界列为独立 required gate。控件清单必须逐一绑定冻结 UI 状态与 DOM 坐标，并明确标记 covered、pending 或 blocked；仅有 Dataset tree hash 不足以向报告解释这些治理约束是否通过。

## 1. 构建影响闭包

~~~bash
python3 .agents/skills/qwork-test-e2e/scripts/build_release_gate_plan.py \
  --repo . --base <base-sha> --head <head-sha> \
  --scope affected \
  --output test-artifacts/e2e/<run-id>/plan.json
~~~

Planner 从显式 base/head、所有 changed/dirty 文件和内容 hash 开始，按 `least-fixed-point` 展开到 requirement/category、capability/risk、Case/Dataset/Suite、route/target、layer/dimension。未知变更保守选择 full 闭世界；Token、时间、成本或 Case 数不能缩减必需范围。任何代码、Case、Dataset、runner、locator、source 或 Skill 变更都会使旧 plan 失效。

## 2. 执行

按 plan 的 `required_items[]` 原样执行并写入同一 `report.json`。不得以命令退出码代替用户可见结果，也不得把 skip/known gap/pending 计入通过。

执行批次结束后必须运行 `scripts/compile_release_gate_report.py`，从冻结 plan、逐坐标 WAL、公开证据清单和私有 attestation确定性生成唯一 `report.json`；禁止手工拼接或把缺 runner、未授权、未执行、截图缺失压成通过。

先运行零执行预检；它会校验 revision、plan、Skill、Dataset 与 Route hash，将每项严格分类，并默认拒绝所有 live Case 与 shell 字符串求值：

~~~bash
python3 .agents/skills/qwork-test-e2e/scripts/run_release_gate_plan.py \
  --repo . --plan test-artifacts/e2e/<run-id>/plan.json \
  --run-root test-artifacts/e2e/<run-id> --preflight-only
~~~

正式本地执行只能显式选择 `gate`、`dataset-verifier`、`deterministic-playwright` 或 `workbuddy-oracle`。`dataset-verifier` 仅对冻结私有 Dataset 执行非 UI 的只读确定性判定；当前用于逐 Case 验证 `~/.workbuddy` 原子处置、QWork 目标和实现证据，不能代替 Electron UI 或真实持久化迁移 E2E。私有 Electron Case 的原始截图、trace、Playwright JSON 和构建清单必须留在 Dataset Skill 的 `data/runs/`；项目 run 只接收哈希绑定的脱敏 attestation，不得复制私有原始证据。执行器逐坐标先写 WAL；发现旧 `running/partial`、已有证据冲突、未知命令或 authority drift 时，在下一个子进程前停止。已有 `pass/fail` 坐标必须属于同一 plan/revision/category，并在执行后原样保留，禁止分类别运行覆盖旧终态。`npm test`、coverage 和 deterministic Electron 执行前必须零执行探测 `127.0.0.1` loopback bind；能力不足属于本地执行环境缺口，不得写成产品失败。`live-authorization` 永远不由该命令执行，必须建立独立授权 runner；`runner-gap` 是本地修复项，不得 skip。

| 层级 | QWork 入口 |
|---|---|
| static/type | `npm run typecheck` |
| unit/integration/contract | `npm test` |
| coverage/regression | `npm run test:coverage` |
| 私有 Dataset 确定性判定 | plan 中的 `validate_workbuddy_storage_case.py --case-id <exact-id>` |
| Electron build | `npx electron-vite build` |
| Electron UI | plan 中的 `npx playwright test <spec> -g <title>` |
| 完整 E2E | `npm run test:e2e`，仅当 full plan 或项目门禁要求 |
| packaged runtime | `npm run smoke:packaged-node/python/sidecar`，仅相关时 |

Deterministic Electron 使用隔离临时目录和 `e2e/fixtures/fake-sidecar.mjs`，不得写成真实模型/线上服务通过。真实 sidecar、真实账号、外部服务、生产数据或付费模型需要独立授权与受限调用契约。

## 3. 自动报告与证据

每次 E2E attempt 在 cleanup 后自动从唯一 `report.json` 生成 `report.html`，无需用户提醒：

~~~bash
python3 .agents/skills/qwork-test-e2e/scripts/finalize_e2e_report.py \
  --input test-artifacts/e2e/<run-id>/report.json \
  --output test-artifacts/e2e/<run-id>/report.html \
  --artifact-root test-artifacts/e2e/<run-id> \
  --plan test-artifacts/e2e/<run-id>/plan.json
~~~

`plain_language_summary` 第一屏用口语回答测了什么、没测什么、能否提测、原因、用户影响和下一步；Case ID、route、executor、revision/hash、命令和路径放入折叠“技术明细”。报告不是终态。

UI Case 按状态机保存关键截图。UI PASS 无当前 run 的入口/终态和全部声明 checkpoint 时必须是 `INCONCLUSIVE`；失败 UI Case 必须有 assertion-failure 截图。截图不能替代 IPC、事件、DB、文件或持久化证据。Finalizer 拒绝孤儿截图、越界路径、错误 hash、缺选中 Case 或 HTML 未嵌入全部图片；报告失败为 `repair-required`。

## 4. 机器判定

~~~bash
python3 .agents/skills/qwork-test-e2e/scripts/evaluate_release_gate.py \
  --repo . \
  --plan test-artifacts/e2e/<run-id>/plan.json \
  --run-root test-artifacts/e2e/<run-id>
~~~

Evaluator 先验证 source acceptance，再调用 `finalize_e2e_report`，然后核对 plan/revision/hash、逐项结果、artifact、cleanup 和独立新上下文重跑。只有它输出 `test-ready` 才能说达到提测标准。

## 5. Continuation checkpoint

每个 attempt 保存：`current_implementation_revision`、`current_plan_hash`、`first_trusted_failure`、非空 `repair_required_next_action`、`cleanup_status`、`independent_rerun_status`、`final_response_allowed`。进程 yield 或上下文压缩后按 checkpoint 自动继续；`repair-required` 必须补修复前证据、最小根因改动、回归保护、重新生成 plan 并重跑所有必需项。

完整结果先写口语结论和用户影响，再附唯一 HTML、关键截图与逐项结果。任何未执行、证据不足、环境阻塞或已知问题都不得计入通过。
