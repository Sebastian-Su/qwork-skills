# QWork 暗黑模式 UI 走查

## 结论先行

WorkBuddy 5.3.8 的暗黑能力是通用产品主题，不是只改页面背景。QWork 必须在真实主题入口、每个可见 surface 和冷启动上同时验证 resolved theme、控件背景、文字前景、交互状态与像素证据。

2026-08-25 的实机基线已经确认：

- 入口为 `用户菜单 -> 外观 -> 浅色|深色`；没有观察到“跟随系统”。
- 深色运行态为 `IDE Night`、`vscode-dark`、`color-scheme: dark`。
- body 背景为 `rgb(24, 24, 24)`，正文主色为 `rgba(228, 228, 228, 0.92)`。
- 深色选择跨真实进程终止与冷启动保持，调研结束后已恢复原浅色设置。
- 19/19 个 5.3.8 规范页面已采集深色截图，并逐 record 绑定 resolved-theme 元数据。
- 这些截图仍是 candidate reference：动态任务、草稿、活动气泡等尚未建立批准 mask，pixel Golden 与发布结论保持 `not_evaluated`。

权威字段和证据 URI 只读 `$qwork-test-dataset/references/workbuddy-dark-theme-contract.yaml`，本文件不复制其 hash。

## 已确认的 QWork 缺口

以下是用户运行态观察与当前源码的交叉确认，不是 WorkBuddy 缺陷：

| QWork surface | 当前证据 | 直接风险 | 当前结论 |
|---|---|---|---|
| 首页标题 | `src/renderer/src/layout/ThreadView.tsx` 的“QWork, 我帮你”使用 `text-black`，没有 dark override | 深色背景上标题仍为黑色，低对比或不可读 | confirmed-source-gap；需当前 revision Electron 复测 |
| 灵感页查询框与标题 | `src/renderer/src/pages/InspirationPage.tsx` 的页面、标题、卡片、搜索图标/placeholder 使用 white/black 固定色；输入框父容器 focused 时为白色 | 暗黑模式出现白色 query 输入区和黑色标题/正文 | confirmed-source-gap；需当前 revision Electron 复测 |
| 项目技能选择器查询框 | `src/renderer/src/components/project/ProjectSkillPicker.tsx` 的 dialog 与搜索框固定为 `#f2f2f2`、`#f7f7f7`、`#ebebeb`，没有 dark override | 深色弹窗中查询框仍沿用浅色背景 | confirmed-source-gap；需当前 revision Electron 复测 |

已有门禁没有覆盖全局主题正确性：`ui-layout-shell-home.spec.ts` 在深色只验证标题“可见”，不验证 computed color/contrast；`project-composer-dark-mode.spec.ts` 只保护 Composer；灵感页集成测试反而固定断言 light-only class。局部绿不能覆盖这些缺口。

## 必需执行矩阵

每个声明支持暗黑的 surface 至少执行：

1. 初始浅色，记录选择模式和 resolved theme。
2. 打开主题入口，保存入口截图和可选模式。
3. 切换深色，保存首个可观察帧、稳定帧和 resolved-theme 元数据。
4. 在深色执行 entry、主要转移和 final state。
5. 对 query/search/input 执行 empty、non-empty、focus、disabled；读取控件及首个非透明祖先的 effective background。
6. 对 heading、正文、placeholder、图标读取 computed foreground、effective background 和 contrast。
7. 覆盖 menu、popover、dialog、toast、tooltip、loading、empty、error、selected、hover、focus-visible。
8. 真实关闭并冷启动，验证持久化和首屏无 light flash。
9. 恢复用户原主题并保存恢复证据。
10. 按 `platform-oracle-matrix.json` 执行平台、viewport 和 DPI；缺坐标为 `not_evaluated`。

## 判定规则

- 主题身份不一致、截图缺主题元数据、query 输入区使用未批准的浅色 effective background、文字不可读、结构/溢出/可操作性错误：硬失败。
- 普通文本对比度至少 4.5:1；大字号文本至少 3:1。存在 WorkBuddy computed-style Oracle 时，还必须匹配精确颜色与批准容差，达到最低对比度不能代替复刻对齐。
- 白色控件不能按颜色一刀切：例如 WorkBuddy 某个深色状态明确批准的强调按钮可以保留；例外必须绑定 `state + element + Oracle`，不能靠组件名猜测。
- `bg-transparent` 的 input 仍要检查祖先背景；只读 input 自身会漏掉“白色 query 容器”。
- 静态 CSS、Tailwind class、DOM 可见或单张截图都不能单独成为 PASS。
- light/dark 截图内容漂移时先冻结 fixture 或审批 mask；禁止用空白差分图、整屏动态噪声或当前 QWork 自举 Golden。

## 报告要求

同一 HTML 第一屏显示：是否可提测、深色覆盖了哪些页面、哪些平台/viewport 未评估、已确认缺口和下一步。每个失败项按以下顺序展示：

`WorkBuddy reference -> QWork actual -> 可读差分 -> 元素 computed style/contrast -> 原始证据 hash`

差分图必须先检查非空、尺寸一致、像素分布有效；空白图或全透明图直接判报告失败。动态区域必须展示 mask，而不是把它藏在阈值里。
