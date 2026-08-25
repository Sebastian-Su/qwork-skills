---
name: qwork-test-dataset
description: 维护 QWork 全产品私有 E2E 数据、需求 Coverage Map、WorkBuddy 只读产品 Oracle、浅深主题/像素基线和 ~/.workbuddy 存储契约。用于新增或审计 QWork 功能、从 develop 文档/E2E/历史专家资料生成 Case、选择受影响或全量套件、检查来源闭合与执行就绪，以及更新 WorkBuddy UI/主题/存储快照。
---

# QWork Test Dataset

本 Skill 是 QWork 私有全量 E2E 数据的唯一真实源。它保存最小化的权威来源快照、逐原子需求、schema v3 Case、WorkBuddy 视觉基线和执行索引；项目 E2E Skill 负责规划、运行和判定，不复制本 Skill 的产品知识。

## 判定顺序

严格分开四层状态，不得用前一层替代后一层：

1. `source closure`：每个已接受来源都有稳定 revision/hash，且每个来源原子都进入需求或显式冲突/阻断。
2. `coverage closure`：每个 P0/P1 需求都绑定 Case 与类型匹配的 Oracle，且无孤儿 Case。
3. `execution readiness`：Case 有可解析 route、fixture、目标、证据和已通过的 reference run。
4. `product result`：当前 revision 的计划已执行、证据已 finalise、cleanup 与独立复测通过。

`covered` 只表示已有 Case，不表示 Case 已运行或产品已通过；`partial`、`pending`、`blocked` 不得计入通过。

## 权威入口

- 来源、需求与 Coverage Map：`data/datasets/source-acceptance.json`
- develop 文档/E2E 闭世界处置：`data/datasets/source-dispositions.json`
- Dataset 索引：`data/datasets/dataset.json`
- Case 实体：`data/datasets/cases/*.json`
- Case schema：`references/case-schema.yaml`
- Dataset schema：`references/dataset-schema.yaml`
- 路由与定位：`references/route-registry.yaml`、`references/locator-registry.yaml`
- 结构化 WorkBuddy Oracle → Case：`references/structured-oracle-coverage-map.yaml`
- 复合文档验收矩阵 → Case：`references/document-case-coverage-map.yaml`
- WorkBuddy 存储规则：`references/workbuddy-storage-rules.md`
- WorkBuddy 存储逐原子处置：`data/datasets/workbuddy-storage-dispositions.json`
- WorkBuddy 逐控件交互闭世界：`data/datasets/workbuddy-interaction-inventory.json`
- WorkBuddy 交互分类政策：`references/workbuddy-interaction-classification-policy.yaml`
- WorkBuddy 目标版本契约：`references/workbuddy-target-baseline.yaml`
- WorkBuddy 5.3.8 暗黑主题契约：`references/workbuddy-dark-theme-contract.yaml`
- 私有存储边界：`references/storage-contract.md`
- 私有 Electron Case：`data/e2e/functional-contracts.spec.ts`
- 私有 reference run 注册：`references/private-reference-runs.yaml`
- 确定性 reference run 注册：`references/deterministic-reference-runs.yaml`

引用一律使用 `skill://qwork-test-dataset/...`，不要把绝对路径写进 Case 或报告。

## 工作流

### 1. 冻结来源

来源进入 `data/sources/<source>/<revision-and-hash>/` 后才可派生。Git 来源必须记录 base/head 和 dirty 状态；飞书记录文档 revision 与正文 hash；`~/.workbuddy` 仅记录路径元数据、hash、计数和只读 SQLite schema；WorkBuddy UI 只允许导航、标签、菜单、展开/收起、截图和 DOM/几何检查。

该 Skill 的唯一实体源位于私人 `qwork-skills` 仓库；QWork 项目中的 `.agents/.codex/.claude` 都只能是未追踪的相对软链接。`data/` 始终是本机私有数据，不进入任何 Git 索引。

任何新来源都先按 `normative`、`evidence` 或 `context-only` 定权。当前 QWork 截图是 evidence，不能反向批准为视觉基线；用户指定的 WorkBuddy UI/数据是 normative Oracle。

### 2. 原子化与编译

运行 `scripts/build_product_baseline.py` 将来源拆成稳定原子，并建立：

`source atom -> requirement -> oracle -> case -> suite/route -> evidence contract`

不得把整篇文档映射成一个泛化 Case。冲突必须保留双方 source atom、优先级和 resolution；无法自动提取精确 UI target 时标为 blocked，不得猜测坐标或把当前实现当设计稿。

飞书表格必须按完整数据行原子化，禁止把同一行的 token、值和用途拆成互不相干的 requirement。图片 `width/height` 取下载文件的物理像素；飞书排版框只保留为 `source_display_width/source_display_height`，不得当作截图 viewport。历史视觉图通过 `visual-frame-calibrations.yaml` 同时锁定 manifest hash、物理像素、CSS viewport 和 DPR。

视觉验收分两层：完整页面/状态使用冻结截图 `visual` Oracle；来源明确给出 token、组件样式或状态配色时使用 `computed-style` Oracle。后者只表示精确样式规则已进入 Case，不表示已执行或已通过；没有当前 reference run 时 readiness 必须保持 `partial`。

主题不能只写在 Case 标签里。存在浅深主题时，来源必须记录选择入口、可选模式、resolved theme、根/body 属性、computed `color-scheme`、持久化状态、平台/viewport/DPR 和逐截图主题绑定。静态 `IDE Night` CSS 只能证明产品含有暗黑能力，不能证明运行态、全部页面或 QWork 已对齐。详细采集与 fail-closed 规则读 `references/workbuddy-dark-theme-contract.yaml`。

当一条文档原子显式列出多个验收 ID（例如 `WB-UI-TASK-001~008`）时，只能通过 `document-case-coverage-map.yaml` 联合绑定多个当前 HEAD Case。Map 必须锁定来源/原子/spec hash，完整展开 ID，并保证每个 ID 由唯一目标认领；它只证明执行路由存在，不继承文档中的历史 green 结论。

文档元数据、章节引言、表头、历史结果快照、追溯链接和变更记录仍需保留在 source/requirement ledger，但只能通过 `document-atom-dispositions.yaml` 的来源 hash、原子 locator/hash 与 canonical 多来源闭包显式标记为 `not_applicable`。不得用标题关键字批量过滤，也不得把未实现的产品行为当作文档上下文移出 Case 闭世界。

### 3. 选择数据

- `requirement`：给定 requirement ID，选择所有保护它的 Case。
- `category`：按 business/negative/permission/state/data/UI/visual/geometry 等类别选择。
- `affected`：由项目 E2E planner 根据 source/code/route/capability 固定点展开。
- `full`：选择 manifest 的完整闭世界，禁止过滤失败、blocked 或难执行 Case。
- `cohort`：选择 manifest 中精确成员和 membership hash 冻结的横切集合，例如当前 WorkBuddy CDP、存储、专家、专家团或外部授权集合。

### 4. 验证

~~~bash
python3 .agents/skills/qwork-test-dataset/scripts/validate_private_storage.py \
  --repo . --skill qwork-test-dataset \
  --path .agents/skills/qwork-test-dataset/data/datasets/source-acceptance.json

node .agents/skills/qwork-test-dataset/scripts/validate_workbuddy_target_baseline.mjs

python3 .agents/skills/qwork-test-dataset/scripts/validate_source_acceptance.py \
  --repo . \
  --manifest skill://qwork-test-dataset/data/datasets/source-acceptance.json

python3 .agents/skills/qwork-test-dataset/scripts/validate_source_dispositions.py \
  --repo . \
  --manifest skill://qwork-test-dataset/data/datasets/source-dispositions.json

python3 .agents/skills/qwork-test-dataset/scripts/build_route_registry.py \
  --skill-root .agents/skills/qwork-test-dataset

python3 .agents/skills/qwork-test-dataset/scripts/test_external_skill_node_resolution.py \
  --repo .

python3 .agents/skills/qwork-test-dataset/scripts/test_private_reference_invalidation.py

python3 .agents/skills/qwork-test-dataset/scripts/test_storage_reference_authority.py

python3 .agents/skills/qwork-test-dataset/scripts/test_workbuddy_storage_batch.py

python3 .agents/skills/qwork-test-dataset/scripts/test_structured_source_reference_authority.py

python3 .agents/skills/qwork-test-dataset/scripts/test_structured_source_batch.py

python3 .agents/skills/qwork-test-dataset/scripts/test_validate_dataset_repo_binding.py

node .agents/skills/qwork-test-dataset/scripts/test_private_case_authority.mjs

python3 .agents/skills/qwork-test-dataset/scripts/test_private_electron_env_isolation.py

python3 .agents/skills/qwork-test-dataset/scripts/test_isolated_build_dependency_resolution.py

python3 .agents/skills/qwork-test-dataset/scripts/validate_route_registry.py \
  --repo . \
  --skill-root .agents/skills/qwork-test-dataset

node .agents/skills/qwork-test-dataset/scripts/validate_cases_ajv.mjs

python3 .agents/skills/qwork-test-dataset/scripts/test_document_case_causal_contract.py

python3 .agents/skills/qwork-test-dataset/scripts/test_document_case_coverage.py \
  --skill-root .agents/skills/qwork-test-dataset

python3 .agents/skills/qwork-test-dataset/scripts/test_document_atom_dispositions.py \
  --skill-root .agents/skills/qwork-test-dataset

python3 .agents/skills/qwork-test-dataset/scripts/test_structured_oracle_coverage.py \
  --skill-root .agents/skills/qwork-test-dataset

python3 .agents/skills/qwork-test-dataset/scripts/test_live_case_authorization.py \
  --skill-root .agents/skills/qwork-test-dataset

python3 .agents/skills/qwork-test-dataset/scripts/validate_workbuddy_interaction_inventory.py \
  --skill-root .agents/skills/qwork-test-dataset

python3 .agents/skills/qwork-test-dataset/scripts/validate_dataset.py \
  --repo . \
  --skill-root .agents/skills/qwork-test-dataset
~~~

上述命令必须全部退出 `0`。缺 Python `jsonschema` 时结构回退只用于快速反馈，AJV 校验仍是 schema v3 的权威本地校验。文档型 Case 还必须具备逐 Requirement 的 Given/When/Then、观测边界与反事实失败，且不得改变未实现 route 的 readiness。

存储 Case 另由 `scripts/validate_workbuddy_storage_case.py --case-id <exact-id>` 只读回放。它要求 Case 中每个 `WORKBUDDY-STORAGE:*` 原子在处置 manifest 中唯一存在；只有决策为 `resolved` 且实现为 `verified` 或 `not-required` 才通过。`pending` 必须输出原子级 `next_action`，不得转成 skip、known gap 或 UI PASS。

多个存储 Case 只能通过 `scripts/run_workbuddy_storage_batch.py` 的显式 `--case-id` 或 JSON `--case-file` 选择；runner 不提供隐式全选。输出必须位于本 Skill 的 Git ignored `data/runs/<run-id>/`，每个坐标调用前先写 `state.json` WAL，再逐 Case 保存原始 verifier 结果、stdout/stderr、SHA-256、统一 `report.json`、离线 `report.html` 与 `promotion-candidates.json`。Case 契约失败可以继续记录其他独立坐标；source、hash、state、evidence 或 verifier 协议错误必须立即停批。`--resume` 只复用 hash 完整的 `pass/fail` 坐标；任何 `running`、未知状态、pending-but-has-evidence、run/contract/Case 集漂移都要求人工证据审计，禁止重复执行。

~~~bash
python3 .agents/skills/qwork-test-dataset/scripts/run_workbuddy_storage_batch.py \
  --skill-root .agents/skills/qwork-test-dataset \
  --output .agents/skills/qwork-test-dataset/data/runs/<unique-run-id> \
  --case-id <exact-case-id> \
  --case-id <another-exact-case-id>
~~~

批次成功只证明显式选择的确定性 Case；报告必须保持 `full_suite_conclusion=未运行` 与 `final_response_allowed=false`。`promotion-candidates.json` 的 `storage_runs` 和 `failed_storage_runs` 都只是待审核注册片段，不能自动修改 tracked `references/deterministic-reference-runs.yaml`。审核每个 Case 的原子集合、report/verifier/disposition hash、实现 revision 与时间后，才可登记并重建 Dataset；同类 Case 不继承通过结论。通过证据只能生成 `ready/pass`；失败证据只能生成 `partial/fail` 和非空原子级 blocker，不能晋升 ready，也不能退回 `pending` 掩盖已执行事实。

结构化 WorkBuddy Oracle 来源 Case 使用 `scripts/run_structured_oracle_source_batch.py`，同样只接受显式 Case ID，并额外要求所有坐标绑定同一可读取的冻结 Git revision。它只核对 accepted source inventory、Git blob、JSON Pointer 与 canonical scalar hash，不启动 Electron。批次 manifest 必须连同自身 SHA-256 和 contract SHA-256 人工登记到 `deterministic-reference-runs.yaml`；编译器再展开逐 Case report/runner/source inventory authority。任一 manifest、source inventory、Case 原子、report、runner 或 revision 漂移都必须退回 `partial`。

~~~bash
python3 .agents/skills/qwork-test-dataset/scripts/run_structured_oracle_source_batch.py \
  --repo . \
  --skill-root .agents/skills/qwork-test-dataset \
  --output .agents/skills/qwork-test-dataset/data/runs/<unique-run-id> \
  --case-file <explicit-case-id-array.json>
~~~

### 5. 私有 Electron Case 与 reference run

共享仓库已有 E2E 不足以直接证明规范原子时，把完整用户路径写入 `data/e2e/functional-contracts.spec.ts`。测试必须使用无障碍角色/名称定位，显式覆盖入口、转移、终态、禁止结果和 cleanup；不得用标题中的验收 ID 代替测试体证据。

执行统一走 `scripts/run_private_playwright_case.mjs`。Runner 会在 `data/runs/<run-id>/` 内重新构建隔离 Electron app，分配临时 QWork home，强制使用仓库 fake sidecar，并保存 `report.json`、build manifest、Playwright JSON、三态截图和 trace；运行结束必须删除含外向依赖软链接的临时 `app/` 装配，只保留闭合证据。禁止复用仓库 `out/`、真实 `~/.qwork`、账号或模型 Provider。

~~~bash
node .agents/skills/qwork-test-dataset/scripts/run_private_playwright_case.mjs \
  --repo . \
  --case-id <stable-case-id> \
  --case-title '<exact-test-title>' \
  --run-root .agents/skills/qwork-test-dataset/data/runs/<unique-run-id>
~~~

Reference run 通过后，把唯一 Case ID、report 的 `skill://` URI、SHA-256 和所需截图状态写入 `references/private-reference-runs.yaml` 的 `runs`，再重建 Dataset。编译器只有在报告身份、source/spec hash、实现 revision、唯一测试结果、截图、trace、隔离/零真实模型声明及全部 artifact hash 同时通过时才将 Case 标为 `ready`；任一变更自动使旧证据失效。

已稳定复现的产品缺口写入同文件的 `failed_runs`，同时记录 failure classification、完整摘要和失败状态截图。编译器对失败报告执行同等严格的身份、authority、artifact、trace、隔离与哈希检查，但只允许生成 `last_outcome=fail`、`reference_run=failed`、`readiness=partial` 和非空 repair blocker；失败证据不得进入 ready 或任何通过率。

## WorkBuddy Oracle

当前唯一批准的复刻与发布验收目标是 WorkBuddy `5.3.8`。CDP UI、动效和安装包 manifest 必须同时绑定 `references/workbuddy-target-baseline.yaml` 中的版本、bundle ID、`app.asar` SHA-256 和 Electron integrity SHA-256；任何 `5.3.14` 快照仅保留为历史实验/evidence，禁止进入 normative baseline、Case PASS 或发布结论。

通过 Electron CDP 采集时先读 `references/locator-registry.yaml` 与 `references/route-registry.yaml`。普通网页仍必须使用 Ego Lite；这里仅因目标是本地 Electron 且需要 renderer DOM/几何，才使用 `connectOverCDP`。禁止创建、安装、连接、授权、删除、发送、运行或修改账号；真实 `~/.workbuddy` 全程只读。

视觉 Case 固定 viewport、DPR、字体与平台，保存入口、转移、终态和失败截图。结构/可访问性错误硬失败；几何默认容差 `±2 CSS px`；像素差采用经批准阈值并显式记录 mask，缺少平台 Golden 为 `not_evaluated`，不是 PASS。

### 5.3.8 暗黑模式基线

暗黑调研必须从真实 `用户菜单 -> 外观 -> 深色` 进入；5.3.8 实机只观察到 `浅色`、`深色`，没有“跟随系统”控件，禁止替它补造第三种模式。采集前后分别运行 `scripts/capture_workbuddy_theme_contract.mjs`，冷启动后用 `scripts/capture_workbuddy_theme_state.mjs` 绑定持久化证据；19 个页面用 `capture_workbuddy_surfaces.mjs` 并设置 `WORKBUDDY_EXPECTED_THEME=dark`，使每个 record 自带 resolved-theme 元数据。

当前 darwin `1680×1084 @2` 已取得 19/19 深色运行态和冷启动证据；语义主题契约已绑定 5.3.8 runtime，但截图含动态任务、草稿和活动气泡，尚未批准 mask，因此 pixel Golden 与发布结论仍为 `not_evaluated`。不得把“截图已采集”写成“像素对齐通过”。

暗黑 UI Case 至少逐项覆盖 query/search/input 的空、非空、focused、disabled，标题/正文/placeholder，菜单/弹窗/toast/内嵌预览，以及切换前、切换后、冷启动和恢复原主题。查询框沿用浅色背景或标题沿用黑色前景时，必须输出元素坐标与 computed style；只有 WorkBuddy 对应状态明确批准白色控件时才可例外。

当前 WorkBuddy CDP Case 使用 `scripts/run_qwork_workbuddy_oracle.mjs` 启动隔离 QWork Electron，再由 `scripts/compare_qwork_workbuddy_oracle.py --fail-on-diff` 判定。报告生成成功不等于 Case 通过；任一导航、像素或语义几何失败都必须以非零退出码阻断。参考运行结果及 runner/report SHA 必须由 baseline 编译器写入 Case，不得手工改成绿色。

冻结 CDP 快照还必须用 `scripts/build_workbuddy_interaction_inventory.py` 派生逐控件清单，并由 `scripts/validate_workbuddy_interaction_inventory.py` 复算。清单要求每个 `state + control index` 坐标唯一归类为源转移、代表性因果覆盖、待执行 Case、本地交互缺口、外部能力阻断、数据副作用阻断或非交互节点；页面截图覆盖不得冒充交互覆盖。用户对话标题与账户名只记脱敏坐标，不复制原文。

## 维护约束

- Dataset 派生数据、快照、基线、证据与运行产物永远私有且 Git ignored；仅 `data/e2e/` 的脱敏测试源码可由私人 qwork-skills 仓库追踪。禁止提交用户内容、凭据、Cookie、Token 或未脱敏标识。
- Case ID 与稳定路径不可随标题或版本目录漂移；版本放字段，不放逻辑身份路径。
- 更新来源、Case、schema、route、runner 或 Oracle 后，旧计划和旧结果全部失效，必须重建并独立复测。
- 新增 Case 必须同时更新 manifest、dataset index、suite index 和对应来源映射；验证器不允许孤儿或重复 ID。
- 真实账号、外部服务或付费模型必须由项目 E2E Skill 建立独立授权边界，Dataset 本身不发起调用。
