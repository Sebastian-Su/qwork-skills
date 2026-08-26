# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: summon-causality.spec.ts >> WB-EXPERT-001 + WB-EXPERT-002 | 专家详情与召唤保留草稿且不建会话
- Location: .agents/skills/qwork-test-dataset/data/e2e/summon-causality.spec.ts:36:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByTestId('composer-dock').getByRole('img', { name: '高级开发工程师头像', exact: true })
Expected: visible
Timeout: 8000ms
Error: element(s) not found

Call log:
  - Expect "soft toBeVisible" with timeout 8000ms
  - waiting for getByTestId('composer-dock').getByRole('img', { name: '高级开发工程师头像', exact: true })

```

```yaml
- banner:
  - button "收起侧栏":
    - img
  - button "搜索":
    - img
  - button "筛选":
    - img
- complementary:
  - text: QWork v0.1.0
  - navigation:
    - button "新建任务":
      - img
      - text: 新建任务
    - button "助理":
      - img
      - text: 助理
    - button "项目":
      - img
      - text: 项目
    - button "专家·技能·连接器":
      - img
      - text: 专家·技能·连接器
    - button "自动化":
      - img
      - text: 自动化
    - button "更多":
      - img
      - text: 更多 资料库·灵感
  - button "任务 (0)":
    - text: 任务 (0)
    - img
  - text: 暂无任务
  - button "空间 (0)":
    - text: 空间 (0)
    - img
  - button "新建空间":
    - img
  - text: 暂无空间
  - button "D Dev User"
  - button "消息中心":
    - img
  - button "连接 QWork":
    - img
- main:
  - toolbar "对话工具栏":
    - heading [level=1]
  - heading "WorkBuddy, 我帮你" [level=1]
  - tablist "任务场景":
    - tab "日常办公" [selected]:
      - img
      - text: 日常办公
    - tab "代码开发":
      - img
      - text: 代码开发
    - tab "设计创意":
      - img
      - text: 设计创意
  - button "文档处理":
    - img
    - text: 文档处理
  - button "金融服务":
    - img
    - text: 金融服务
  - button "数据分析及可视化":
    - img
    - text: 数据分析及可视化
  - button "个人工作台":
    - img
    - text: 个人工作台
  - button "深度研究":
    - img
    - text: 深度研究
  - button "视频":
    - img
    - text: 视频
  - button "更多快捷项":
    - img
  - text: 高 高级开发工程师
  - button "移除高级开发工程师":
    - img
  - textbox "今天帮你做些什么？ @ 引用对话文件，/ 调用技能与指令": 保留这段未发送的专家需求
  - button "更多操作":
    - img
  - button "Kimi-K3":
    - img
    - text: Kimi-K3
    - img
  - button "语音输入":
    - img
  - button "发送":
    - img
  - button "选择工作空间":
    - img
    - text: workspace
    - img
  - button "完全访问":
    - img
    - text: 完全访问
    - img
```

```
Error: expect(locator).toBeVisible() failed

Locator: getByText('召唤前附件.txt', { exact: true })
Expected: visible
Timeout: 8000ms
Error: element(s) not found

Call log:
  - Expect "soft toBeVisible" with timeout 8000ms
  - waiting for getByText('召唤前附件.txt', { exact: true })

```

```yaml
- banner:
  - button "收起侧栏":
    - img
  - button "搜索":
    - img
  - button "筛选":
    - img
- complementary:
  - text: QWork v0.1.0
  - navigation:
    - button "新建任务":
      - img
      - text: 新建任务
    - button "助理":
      - img
      - text: 助理
    - button "项目":
      - img
      - text: 项目
    - button "专家·技能·连接器":
      - img
      - text: 专家·技能·连接器
    - button "自动化":
      - img
      - text: 自动化
    - button "更多":
      - img
      - text: 更多 资料库·灵感
  - button "任务 (0)":
    - text: 任务 (0)
    - img
  - text: 暂无任务
  - button "空间 (0)":
    - text: 空间 (0)
    - img
  - button "新建空间":
    - img
  - text: 暂无空间
  - button "D Dev User"
  - button "消息中心":
    - img
  - button "连接 QWork":
    - img
- main:
  - toolbar "对话工具栏":
    - heading [level=1]
  - heading "WorkBuddy, 我帮你" [level=1]
  - tablist "任务场景":
    - tab "日常办公" [selected]:
      - img
      - text: 日常办公
    - tab "代码开发":
      - img
      - text: 代码开发
    - tab "设计创意":
      - img
      - text: 设计创意
  - button "文档处理":
    - img
    - text: 文档处理
  - button "金融服务":
    - img
    - text: 金融服务
  - button "数据分析及可视化":
    - img
    - text: 数据分析及可视化
  - button "个人工作台":
    - img
    - text: 个人工作台
  - button "深度研究":
    - img
    - text: 深度研究
  - button "视频":
    - img
    - text: 视频
  - button "更多快捷项":
    - img
  - text: 高 高级开发工程师
  - button "移除高级开发工程师":
    - img
  - textbox "今天帮你做些什么？ @ 引用对话文件，/ 调用技能与指令": 保留这段未发送的专家需求
  - button "更多操作":
    - img
  - button "Kimi-K3":
    - img
    - text: Kimi-K3
    - img
  - button "语音输入":
    - img
  - button "发送":
    - img
  - button "选择工作空间":
    - img
    - text: workspace
    - img
  - button "完全访问":
    - img
    - text: 完全访问
    - img
```

# Test source

```ts
  1   | import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
  2   | import fs from "node:fs/promises";
  3   | import path from "node:path";
  4   | import {
  5   |   attachUiState,
  6   |   setContentSize,
  7   | } from "../../../../../e2e/fixtures/workbuddy-ui";
  8   | import {
  9   |   cleanup,
  10  |   createTestHome,
  11  |   createWorkspace,
  12  |   openApp,
  13  | } from "./fixtures/launch-isolated";
  14  | 
  15  | async function openFixture(prefix: string) {
  16  |   const home = await createTestHome(prefix);
  17  |   const workspace = await createWorkspace(home);
  18  |   const sidecarLog = path.join(home, "sidecar-control.jsonl");
  19  |   const opened = await openApp(home, { E2E_SIDECAR_CONTROL_LOG: sidecarLog });
  20  |   await setContentSize(opened.app, opened.page);
  21  |   return { ...opened, home, sidecarLog, workspace };
  22  | }
  23  | 
  24  | async function controlTypes(sidecarLog: string): Promise<string[]> {
  25  |   return (await fs.readFile(sidecarLog, "utf8").catch(() => ""))
  26  |     .split("\n")
  27  |     .filter(Boolean)
  28  |     .map((line) => JSON.parse(line) as { type?: string })
  29  |     .map((message) => message.type ?? "unknown");
  30  | }
  31  | 
  32  | async function taskCount(page: Page): Promise<string> {
  33  |   return (await page.getByText(/^任务 \(\d+\)$/).first().textContent()) ?? "";
  34  | }
  35  | 
  36  | test("WB-EXPERT-001 + WB-EXPERT-002 | 专家详情与召唤保留草稿且不建会话", async ({}, testInfo) => {
  37  |   const fixture = await openFixture("expert-draft-causality");
  38  |   let app: ElectronApplication | undefined = fixture.app;
  39  |   try {
  40  |     const { page, sidecarLog, workspace } = fixture;
  41  |     const composer = page.getByRole("textbox");
  42  |     const draft = "保留这段未发送的专家需求";
  43  |     const attachment = path.join(workspace, "召唤前附件.txt");
  44  |     await fs.writeFile(attachment, "召唤前已存在的附件内容", "utf8");
  45  |     await fixture.app.evaluate(({ ipcMain }, selected) => {
  46  |       ipcMain.removeHandler("dialog:openFiles");
  47  |       ipcMain.handle("dialog:openFiles", () => [selected.attachment]);
  48  |       ipcMain.removeHandler("dialog:openDirectory");
  49  |       ipcMain.handle("dialog:openDirectory", () => selected.workspace);
  50  |     }, { attachment, workspace });
  51  |     await page.getByRole("button", { name: "更多操作", exact: true }).click();
  52  |     await page.getByRole("menuitem", { name: "添加文件", exact: true }).click();
  53  |     await expect(page.getByText("召唤前附件.txt", { exact: true })).toBeVisible();
  54  | 
  55  |     await composer.fill(draft);
  56  |     await page.getByRole("button", { name: "默认权限", exact: true }).click();
  57  |     await page.getByRole("switch", { name: "允许完全访问", exact: true }).click();
  58  |     await expect(page.getByRole("button", { name: "完全访问", exact: true })).toBeVisible();
  59  |     await page.keyboard.press("Escape");
  60  | 
  61  |     await page.getByRole("button", { name: "Qwen3.7-Plus", exact: true }).click();
  62  |     await page.getByRole("menuitemradio", { name: "Kimi-K3", exact: true }).click();
  63  | 
  64  |     const workspaceName = path.basename(workspace);
  65  |     const modelName = "Kimi-K3";
  66  |     await page.getByRole("button", { name: "选择工作空间", exact: true }).click();
  67  |     await page.getByRole("button", { name: "选择其他文件夹…", exact: true }).click();
  68  |     const workspaceButton = page.getByRole("button", { name: "选择工作空间", exact: true });
  69  |     await expect(workspaceButton).toContainText(workspaceName);
  70  |     await expect(page.getByRole("button", { name: modelName, exact: true })).toBeVisible();
  71  |     const before = {
  72  |       tasks: await taskCount(page),
  73  |       url: page.url(),
  74  |       userBubbles: await page.locator(".message-copy").count(),
  75  |       thinkingBlocks: await page.getByText("深度思考", { exact: true }).count(),
  76  |       toolCards: await page.locator('[data-testid="tool-call-details"]').count(),
  77  |       memberBars: await page.getByRole("navigation", { name: "专家团成员" }).count(),
  78  |     };
  79  |     await page.getByRole("button", { name: "专家·技能·连接器", exact: true }).click();
  80  |     await page.getByRole("button", { name: /高级开发工程师.*从证据出发/ }).click();
  81  |     const detail = page.getByRole("dialog", { name: "高级开发工程师" });
  82  |     await expect(detail).toContainText("能力介绍");
  83  |     await expect(detail.getByRole("button", { name: /^“/ })).toHaveCount(3);
  84  |     await attachUiState(page, testInfo, "entry-expert-detail-with-draft");
  85  | 
  86  |     await detail.getByRole("button", { name: "召唤 高级开发工程师" }).click();
  87  |     await expect(page.getByRole("dialog", { name: "高级开发工程师" })).toHaveCount(0);
  88  |     const dock = page.getByTestId("composer-dock");
  89  |     await attachUiState(page, testInfo, "transition-expert-selected-before-oracles");
  90  |     await expect.soft(page.getByRole("heading", { name: "WorkBuddy, 我帮你", exact: true })).toBeVisible();
  91  |     await expect.soft(composer).toHaveValue(draft);
  92  |     await expect.soft(dock).toContainText("高级开发工程师");
  93  |     await expect.soft(dock.getByRole("img", { name: "高级开发工程师头像", exact: true })).toBeVisible();
> 94  |     await expect.soft(page.getByText("召唤前附件.txt", { exact: true })).toBeVisible();
      |                                                                     ^ Error: expect(locator).toBeVisible() failed
  95  |     await expect.soft(workspaceButton).toContainText(workspaceName);
  96  |     await expect.soft(page.getByRole("button", { name: modelName, exact: true })).toBeVisible();
  97  |     await expect.soft(page.getByRole("button", { name: "完全访问", exact: true })).toBeVisible();
  98  | 
  99  |     await expect.soft(page.getByText(/^任务 \(\d+\)$/).first()).toHaveText(before.tasks);
  100 |     expect.soft(page.url()).toBe(before.url);
  101 |     expect.soft(page.url()).not.toMatch(/\/task\/[^/?#]+/);
  102 |     expect.soft(await page.locator(".message-copy").count()).toBe(before.userBubbles);
  103 |     expect.soft(await page.getByText("深度思考", { exact: true }).count()).toBe(before.thinkingBlocks);
  104 |     expect.soft(await page.locator('[data-testid="tool-call-details"]').count()).toBe(before.toolCards);
  105 |     expect.soft(await page.getByRole("navigation", { name: "专家团成员" }).count()).toBe(before.memberBars);
  106 |     await expect.soft(
  107 |       page.getByTestId("thread-message-list").getByText(draft, { exact: true }),
  108 |     ).toHaveCount(0);
  109 |     const inputValue = await composer.inputValue();
  110 |     expect.soft(inputValue).toBe(draft);
  111 |     expect.soft(inputValue).not.toContain("qwork_expert_identity");
  112 |     expect.soft(inputValue).not.toContain("ziqdo-plugin.json");
  113 |     expect.soft(inputValue).not.toContain("principal");
  114 |     expect.soft(inputValue).not.toContain("roster");
  115 |     const types = await controlTypes(sidecarLog);
  116 |     expect.soft(types).not.toContain("create_session");
  117 |     expect.soft(types).not.toContain("user_message");
  118 |     await attachUiState(page, testInfo, "final-expert-no-session-no-user-message");
  119 |   } finally {
  120 |     await cleanup(app, fixture.home);
  121 |   }
  122 | });
  123 | 
  124 | test("WB-TEAM-001B | 专家团卡片右上召唤只选择团队且不启动成员", async ({}, testInfo) => {
  125 |   const fixture = await openFixture("team-direct-summon-causality");
  126 |   let app: ElectronApplication | undefined = fixture.app;
  127 |   try {
  128 |     const { page, sidecarLog } = fixture;
  129 |     const before = await taskCount(page);
  130 |     await page.getByRole("button", { name: "专家·技能·连接器", exact: true }).click();
  131 |     await page.getByRole("tab", { name: "专家团", exact: true }).click();
  132 |     const card = page.getByRole("button", { name: /游戏开发工作室.*由负责人统筹/ });
  133 |     await attachUiState(page, testInfo, "entry-team-card");
  134 |     await card.getByRole("button", { name: "召唤游戏开发工作室" }).click();
  135 | 
  136 |     await expect(page.getByRole("dialog", { name: "游戏开发工作室" })).toHaveCount(0);
  137 |     await expect(page.getByTestId("composer-dock")).toContainText("游戏开发工作室");
  138 |     await expect(page.getByRole("textbox")).toBeEmpty();
  139 |     await attachUiState(page, testInfo, "transition-team-selected-without-run");
  140 | 
  141 |     await expect(page.getByText(/^任务 \(\d+\)$/).first()).toHaveText(before);
  142 |     const types = await controlTypes(sidecarLog);
  143 |     expect(types).not.toContain("create_session");
  144 |     expect(types).not.toContain("user_message");
  145 |     expect(types).not.toContain("subscribe_subagent_streams");
  146 |     await attachUiState(page, testInfo, "final-team-no-session-no-member-stream");
  147 |   } finally {
  148 |     await cleanup(app, fixture.home);
  149 |   }
  150 | });
  151 | 
  152 | test("WB-TEAM-002 | 专家团详情召唤保留草稿且无会话成员栏", async ({}, testInfo) => {
  153 |   const fixture = await openFixture("team-draft-causality");
  154 |   let app: ElectronApplication | undefined = fixture.app;
  155 |   try {
  156 |     const { page, sidecarLog } = fixture;
  157 |     const composer = page.getByRole("textbox");
  158 |     await composer.fill("保留这段未发送的团队需求");
  159 |     const before = await taskCount(page);
  160 |     await page.getByRole("button", { name: "专家·技能·连接器", exact: true }).click();
  161 |     await page.getByRole("tab", { name: "专家团", exact: true }).click();
  162 |     await page.getByRole("button", { name: /游戏开发工作室.*由负责人统筹/ }).click();
  163 |     const detail = page.getByRole("dialog", { name: "游戏开发工作室" });
  164 |     await expect(detail).toContainText("团队成员");
  165 |     await attachUiState(page, testInfo, "entry-team-detail-with-draft");
  166 | 
  167 |     await detail.getByRole("button", { name: "召唤 游戏开发工作室" }).click();
  168 |     await expect(composer).toHaveValue("保留这段未发送的团队需求");
  169 |     await expect(page.getByTestId("composer-dock")).toContainText("游戏开发工作室");
  170 |     await attachUiState(page, testInfo, "transition-team-selected-draft-preserved");
  171 | 
  172 |     await expect(page.getByText(/^任务 \(\d+\)$/).first()).toHaveText(before);
  173 |     await expect(
  174 |       page.getByTestId("thread-message-list").getByText("保留这段未发送的团队需求", { exact: true }),
  175 |     ).toHaveCount(0);
  176 |     const types = await controlTypes(sidecarLog);
  177 |     expect(types).not.toContain("create_session");
  178 |     expect(types).not.toContain("user_message");
  179 |     expect(types).not.toContain("subscribe_subagent_streams");
  180 |     await attachUiState(page, testInfo, "final-team-no-session-no-member-workspace");
  181 |   } finally {
  182 |     await cleanup(app, fixture.home);
  183 |   }
  184 | });
  185 | 
```