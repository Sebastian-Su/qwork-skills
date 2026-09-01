# QWork 完整 E2E 门禁契约

## 唯一真相与三态

产品需求、Case 与 Suite 的唯一来源是 `source_acceptance_manifest: skill://qwork-test-dataset/data/datasets/source-acceptance.json`。项目 Skill 不复制 Oracle。

Evaluator 只允许三种终态：

- `test-ready`：当前 revision 的闭包、全部必需结果、证据、cleanup 和独立重跑都通过；
- `repair-required`：任何本地产品、测试、Case、Dataset、fixture、runner、locator、Skill、环境配方或证据缺口；这是继续信号，不允许结束；
- `external-blocked`：仅限新增权限/凭据、不可用外部账号/设备/服务、付费或不可逆授权，以及尚未裁决的产品/Figma/API 语义。

本地缺口优先于外部 blocker。报告是证据，不是终态。

## Planner

~~~bash
python3 .agents/skills/qwork-test-e2e/scripts/build_release_gate_plan.py \
  --repo . --base <base-sha> --head <head-sha> \
  --scope affected \
  --output /absolute/path/QWORK-E2E-TEMPORARY-DATA-DO-NOT-COMMIT/<run-id>/plan.json
~~~

Planner 使用 `least-fixed-point`（最小不动点）闭包，从显式 base/head、dirty tracked/untracked 和 `changed_file_hashes` 出发，映射：

`change/source atom -> requirement/category -> capability/risk -> case/dataset/suite -> route/target -> layer/dimension`

精确来源映射优先；能判定产品 surface 的实现文件保守选择该 surface 全部 Case；未知变更执行 `fail_on_unmapped_change` 的保守语义，选择 full 闭世界而不是漏测。`token_budget_may_reduce_scope: false`，Token、时间、成本或 Case 数都不能缩减必需闭包。

Planner 固定实现、source、Case/Dataset、route、locator、runner 与 Skill hash。任何这些资产变化后必须重新生成 plan，并 `rerun_all_required_items_after_every_change`。没有轮数预算：`maximum_iterations: null`。

## 执行结果

执行前必须由 `scripts/run_release_gate_plan.py --preflight-only` 证明 plan 的每个 required item 被唯一分类为 `gate`、`dataset-verifier`、`deterministic-playwright`、`workbuddy-oracle`、`live-authorization` 或 `runner-gap`。分类总数必须等于 required item 总数。`dataset-verifier` 只能读取冻结的私有 Dataset，并按精确 Case ID 产出原子级处置结果；它不证明 Electron UI，也不证明尚未实现的真实迁移链。禁止 shell 求值；外部授权 Case 不能经本地执行路径发起。

正式执行使用逐 item WAL。每个坐标在子进程前原子写入 `running`，证据与终态落盘后才变成 `pass/fail`。恢复时只要发现 `running/partial` 或待执行坐标已有证据路径，就零执行停机并要求人工审计，防止重复调用或证据覆盖。已有 `pass/fail` 坐标必须绑定同一 `plan_sha256`、`implementation_revision` 与分类，后续分类执行必须原样保留并跳过；未知坐标、revision/category 漂移一律在子进程前拒绝。

preflight 必须保存运行所需环境能力。`gate:unit-integration`、`gate:coverage` 与 deterministic Playwright 依赖本机 `127.0.0.1` loopback bind；执行器须在任何坐标启动前用 ephemeral port 探测。能力不足时零执行拒绝并记为本地环境配方缺口，禁止把 `listen EPERM` 连锁失败归因于产品。

每个 `required_items[]` 在唯一 `<run-root>/QWORK-E2E-REPORT.json` 的 `results[]` 有同 ID 结果。PASS 至少保存：

- 当前 `implementation_revision`、`plan_sha256`；
- runner/command、开始结束时间、exit code 或结构化 outcome；
- 相对 run root 的 artifact 路径和 SHA-256；
- `cleanup_status=pass` 与 failure classification。

UI Case 还要在 `cases[]` 和 `case_results[]` 同时存在，状态一致，并按 `required_screenshot_states` 保存当前 run 的入口、关键转移、重要 mutation 前后、失败和终态关键截图。`ui_pass_requires_oracle_screenshot: true`；API/日志截图不能代判 UI，UI 截图不能代判数据库或持久化结果。

任何 required item 的 skip、known gap、pending 或 `not_applicable` 都是 `repair-required`。执行计划中的 `not-applicable` 只能在运行前携带直接证据分类，不能用于逃避已选项目。

## Evaluator 与自动报告

~~~bash
python3 .agents/skills/qwork-test-e2e/scripts/evaluate_release_gate.py \
  --repo . \
  --plan /absolute/path/QWORK-E2E-TEMPORARY-DATA-DO-NOT-COMMIT/<run-id>/plan.json \
  --run-root /absolute/path/QWORK-E2E-TEMPORARY-DATA-DO-NOT-COMMIT/<run-id>
~~~

Evaluator 先运行 `validate_source_acceptance`，再调用 `finalize_e2e_report`。`auto_generate_after_every_e2e_attempt: true`；`single_canonical_report_json: true`；报告生成失败、孤儿截图、hash 漂移或 HTML 未嵌入全部截图一律 fail closed。`plain_language_summary` 用口语回答测了什么、没测什么、为什么、用户影响和下一步；原始机器字段进入折叠技术明细。

Evaluator 复核 plan/hash、当前 revision、来源新鲜度、所有必需结果、证据、cleanup 和 `require_independent_fresh_context_rerun`。只有能直接观察 grader 的 route/runner 证据才有效；多路由证据必须绑定同一 implementation/plan/runner revision 和 artifact hash。

## Continuation checkpoint 与终态锁

每次 attempt 保存 `require_continuation_checkpoint: true`：

- `current_implementation_revision`
- `current_plan_hash`
- `first_trusted_failure`
- 非空 `repair_required_next_action`
- `cleanup_status`
- `independent_rerun_status`
- `final_response_allowed`

`repair-required` 时 `final_response_allowed=false`，必须自动执行下一动作、补回归、重新计算影响闭包并重跑全部必需项。进程 yield 或上下文压缩后 `auto_resume_after_yield_or_compaction`，不得等待用户再次要求继续。只有当前 revision 的 `test-ready` 或经过排除检查的严格 `external-blocked` 才允许结束。

## QWork 执行边界

- deterministic Electron：独立临时 `ZIQDO_CONFIG_HOME` + `e2e/fixtures/fake-sidecar.mjs`；证明契约和 UI，不证明真实模型质量。
- real sidecar/model/account：必须独立授权、限制权限/调用/副作用、保留真实协议证据；未授权时只能按精确 external blocker 处理。
- WorkBuddy CDP：只读导航/标签/菜单/展开/截图/DOM/几何；禁止 create/install/connect/authorize/delete/send/run。
- WorkBuddy 官方文档：`Quickstart` 展开导航与 desktop sitemap 集合必须闭合，正文原子全映射到 `workbuddy-official-docs` cohort；品牌名和品牌素材可替换，但功能语义与交互不可豁免；缺 viewport/DPR 校准的文档图片不得成为像素或几何 PASS。
- 完整平台发布：macOS/Windows/Linux 均需当前 runner 结果；缺平台为未验证，不得用本机代替。

## 反向门禁

必须持续验证：未映射 change/source atom、缺 Case/route/result、过期 revision/hash、UI PASS 缺截图、cleanup 失败、独立重跑缺失、报告失败都会得到 `repair-required`；Skill/runner/Case 修改后旧 plan 失效；本地配置或 runner 缺陷永远不能伪装成 `external-blocked`。
