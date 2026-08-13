---
name: qwork-test-e2e
description: QWork Work GUI Electron 客户端的项目 E2E 执行与口语化图文报告适配器。用于按变更范围选择现有 Playwright Electron、Vitest、集成和打包 smoke 路径，保存关键状态截图，并从唯一 report.json 生成产品和业务人员可直接理解的 report.html。用户要求 QWork 功能回归、Electron UI 验收、Figma/截图对齐、发布前检查或 E2E 报告时使用。当前已有专家旅程 Coverage Map v1、执行入口与报告交付，Dataset 绑定和发布门禁 planner/evaluator 尚未补齐，因此不得据此单独宣称 test-ready。
---

# QWork Test E2E

先读仓库根 AGENTS.md 和 docs/testing-guide.md。现有测试与夹具的事实源是仓库内 src/**/*.test.*、e2e/*.spec.ts、e2e/fixtures/、playwright.config.ts 和 package.json；本 Skill 只负责选择路径、整理证据和生成报告，不复制测试实现。

## 当前能力边界

- 默认只检查用户明确功能及其受影响闭包；只有用户明确说“全量测试”才执行仓库规定的全量门禁。
- Playwright Electron 默认使用隔离临时目录和 fake-sidecar.mjs，不得把假 sidecar 结果写成真实模型或线上服务通过。
- 真实 sidecar、真实账号、外部服务、生产数据或付费模型必须单独取得授权。
- 当前 report_delivery=ready，专家旅程 Coverage Map v1 已落盘；项目 Dataset、release-gate planner/evaluator 仍为 missing，所以整体 readiness 是 partial。报告生成成功不等于达到提测标准。

## 执行入口

| 目标 | 入口 | 说明 |
|---|---|---|
| 单元、组件、集成或契约 | npx vitest run TARGET | 只执行受影响目标 |
| Electron UI 流程 | npm run typecheck、npx electron-vite build、npx playwright test SPEC | 使用现有 Electron fixture |
| 仓库完整门禁 | npm run typecheck、npm test、npm run test:coverage、npm run test:e2e | 仅在用户明确要求全量测试或项目发布流程强制时 |
| 打包产物 smoke | npm run smoke:packaged-node/python/sidecar | 只在打包范围受影响时 |

不要用命令退出码代替用户可见结果。UI 用例必须验证可见状态；IPC、文件、sidecar、持久化和安全结果必须由对应结构化证据证明。

## 自动测试报告与关键截图

~~~yaml
report_contract:
  policy: references/report-policy.yaml
  auto_generate_after_every_e2e_attempt: true
  user_request_required: false
  artifact_root: test-artifacts/e2e/<run-id>
  machine_result: <artifact_root>/report.json
  human_report: <artifact_root>/report.html
  renderer: scripts/render_e2e_report.py
  finalizer: scripts/finalize_e2e_report.py
~~~

1. 每次 attempt 使用唯一 report.json；机器结果和人类 cases 不得拆成两份会漂移的 JSON。
2. report.json 必须填写 plain_language_summary：what_was_tested、what_was_not_tested、result_reason、user_impact、next_step。
3. HTML 第一屏必须用口语回答“测了什么、没测什么、能不能提测、为什么、影响谁、下一步做什么”。把状态显示为“符合预期、发现问题、还没验证、暂时不能提测”；Case ID、route、executor、revision、hash、命令和证据路径放入默认折叠的“技术明细”。
4. Electron/UI Case 按状态机保留入口、关键操作前后、失败和终态截图。UI PASS 无证据或缺关键截图时必须标记 INCONCLUSIVE，并向读者显示“证据不足，无法确认”；截图不能代替 IPC、文件或持久化证据。
5. cleanup 后运行 finalizer。它拒绝孤儿截图、错误 hash、越出 run root 的路径和漏嵌截图；报告失败属于需要修复，不能只在聊天中口头说明。
6. 报告不是终态。出现 repair-required 时必须继续修复报告或测试资产；只有项目未来补齐 evaluator 后，才能由机器门禁决定最终提测状态。

~~~bash
python3 .agents/skills/qwork-test-e2e/scripts/finalize_e2e_report.py \
  --input "test-artifacts/e2e/<run-id>/report.json" \
  --output "test-artifacts/e2e/<run-id>/report.html" \
  --artifact-root "test-artifacts/e2e/<run-id>"
~~~

## 汇报

先写口语结论、用户影响和下一步，再附报告路径、关键截图和逐项结果。技术状态保留在报告折叠区。任何未执行、证据不足、环境阻塞或已知问题都不得计入通过。

本 Skill 尚不是完整发布评估器。没有当前 revision 的完整影响闭包、全层结果、cleanup 和独立复测时，只能准确汇报已验证范围，不能说“达到提测标准”。
