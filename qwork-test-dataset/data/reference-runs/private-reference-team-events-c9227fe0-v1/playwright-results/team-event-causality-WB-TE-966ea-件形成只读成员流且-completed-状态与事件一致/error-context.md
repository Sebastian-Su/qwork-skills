# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: team-event-causality.spec.ts >> WB-TEAM-004/005/006 | 真实成员事件形成只读成员流且 completed 状态与事件一致
- Location: .agents/skills/qwork-test-dataset/data/e2e/team-event-causality.spec.ts:16:1

# Error details

```
Error: expect(locator).toHaveCount(expected) failed

Locator:  getByRole('textbox')
Expected: 0
Received: 1
Timeout:  8000ms

Call log:
  - Expect "toHaveCount" with timeout 8000ms
  - waiting for getByRole('textbox')
    20 × locator resolved to 1 element
       - unexpected value "1"

```

# Test source

```ts
  1   | import { expect, test, type ElectronApplication } from "@playwright/test";
  2   | import {
  3   |   attachUiState,
  4   |   setContentSize,
  5   |   summonGameStudio,
  6   | } from "../../../../../e2e/fixtures/workbuddy-ui";
  7   | import {
  8   |   cleanup,
  9   |   createTestHome,
  10  |   createWorkspace,
  11  |   openApp,
  12  | } from "./fixtures/launch-isolated";
  13  | 
  14  | type ObservedEvent = { kind?: string; thread_id?: string; text?: string; status?: string };
  15  | 
  16  | test("WB-TEAM-004/005/006 | 真实成员事件形成只读成员流且 completed 状态与事件一致", async ({}, testInfo) => {
  17  |   const home = await createTestHome("team-event-causality");
  18  |   await createWorkspace(home);
  19  |   let app: ElectronApplication | undefined;
  20  |   try {
  21  |     const opened = await openApp(home);
  22  |     app = opened.app;
  23  |     const page = opened.page;
  24  |     await setContentSize(app, page);
  25  |     const composer = await summonGameStudio(page);
  26  |     await expect(page.getByRole("navigation", { name: "专家团成员" })).toHaveCount(0);
  27  | 
  28  |     await page.evaluate(() => {
  29  |       const target = window as typeof window & { __privateTeamEvents?: unknown[] };
  30  |       target.__privateTeamEvents = [];
  31  |       window.workGui.events.onSessionEvent((event) => target.__privateTeamEvents?.push(event));
  32  |     });
  33  |     await attachUiState(page, testInfo, "entry-lead-registered-without-running-members");
  34  |     await composer.fill("请制定 Sprint 规划并完成质量门禁检查");
  35  |     await composer.press("Enter");
  36  | 
  37  |     const release = page.getByRole("button", { name: /发布运营.*已完成/ });
  38  |     const quality = page.getByRole("button", { name: /质量保障.*已完成/ });
  39  |     await expect(release).toBeVisible();
  40  |     await expect(quality).toBeVisible();
  41  |     await expect(
  42  |       page.getByText("团队总结：Sprint 规划与质量门禁均已完成。", { exact: true }),
  43  |     ).toBeVisible();
  44  |     await attachUiState(page, testInfo, "transition-members-completed-before-lead-summary");
  45  | 
  46  |     const events = await page.evaluate(() => {
  47  |       const target = window as typeof window & { __privateTeamEvents?: unknown[] };
  48  |       return (target.__privateTeamEvents ?? []) as ObservedEvent[];
  49  |     });
  50  |     await testInfo.attach("team-session-events.json", {
  51  |       body: Buffer.from(`${JSON.stringify(events, null, 2)}\n`),
  52  |       contentType: "application/json",
  53  |     });
  54  |     await attachUiState(page, testInfo, "evidence-raw-event-order-before-assertion");
  55  |     const index = (kind: string, threadId?: string) => events.findIndex(
  56  |       (event) => event.kind === kind && (!threadId || event.thread_id === threadId),
  57  |     );
  58  |     for (const threadId of ["team-release", "team-quality"]) {
  59  |       expect(index("subagent_thread_started", threadId), JSON.stringify(events)).toBeGreaterThanOrEqual(0);
  60  |       expect(index("subagent_text_delta", threadId), JSON.stringify(events)).toBeGreaterThan(index("subagent_thread_started", threadId));
  61  |       expect(index("subagent_thread_completed", threadId), JSON.stringify(events)).toBeGreaterThan(index("subagent_text_delta", threadId));
  62  |     }
  63  |     expect(events.filter((event) => event.kind === "subagent_thread_started")).toHaveLength(2);
  64  |     expect(events.filter((event) => event.kind === "subagent_thread_completed")).toHaveLength(2);
  65  | 
  66  |     await release.click();
  67  |     await expect(page.getByRole("heading", { name: "发布运营" })).toBeVisible();
  68  |     await expect(page.getByText("团队：游戏开发工作室", { exact: true })).toBeVisible();
  69  |     await expect(page.getByText(/更新时间：\d{2}:\d{2}/)).toBeVisible();
  70  |     await expect(page.getByText("工具调用：未上报（ZiqDo）", { exact: false })).toBeVisible();
  71  |     await expect(page.getByText("模型：e2e-balanced · in 120 · out 40", { exact: true })).toBeVisible();
  72  |     await expect(page.getByText("Sprint 规划已完成", { exact: true })).toBeVisible();
> 73  |     await expect(page.getByRole("textbox")).toHaveCount(0);
      |                                             ^ Error: expect(locator).toHaveCount(expected) failed
  74  |     await expect(page.getByRole("button", { name: "重试此成员任务" })).toHaveCount(0);
  75  |     await attachUiState(page, testInfo, "final-member-independent-readonly-transcript");
  76  | 
  77  |     await page.getByRole("button", { name: /游戏开发工作室.*负责人/ }).click();
  78  |     await expect(page.getByRole("textbox")).toBeEnabled();
  79  |     await expect(
  80  |       page.getByText("团队总结：Sprint 规划与质量门禁均已完成。", { exact: true }),
  81  |     ).toBeVisible();
  82  |   } finally {
  83  |     await cleanup(app, home);
  84  |   }
  85  | });
  86  | 
  87  | test("WB-TEAM-008 | Lead 总结必须晚于所需成员完成事件", async ({}, testInfo) => {
  88  |   const home = await createTestHome("team-lead-summary-order");
  89  |   await createWorkspace(home);
  90  |   let app: ElectronApplication | undefined;
  91  |   try {
  92  |     const opened = await openApp(home);
  93  |     app = opened.app;
  94  |     const page = opened.page;
  95  |     await setContentSize(app, page);
  96  |     const composer = await summonGameStudio(page);
  97  |     await page.evaluate(() => {
  98  |       const target = window as typeof window & { __privateTeamEvents?: unknown[] };
  99  |       target.__privateTeamEvents = [];
  100 |       window.workGui.events.onSessionEvent((event) => target.__privateTeamEvents?.push(event));
  101 |     });
  102 |     await attachUiState(page, testInfo, "entry-lead-before-member-delegation");
  103 |     await composer.fill("请制定 Sprint 规划并完成质量门禁检查");
  104 |     await composer.press("Enter");
  105 |     await expect(page.getByRole("button", { name: /发布运营.*已完成/ })).toBeVisible();
  106 |     await expect(page.getByRole("button", { name: /质量保障.*已完成/ })).toBeVisible();
  107 |     await attachUiState(page, testInfo, "transition-member-results-returned");
  108 | 
  109 |     const events = await page.evaluate(() => {
  110 |       const target = window as typeof window & { __privateTeamEvents?: unknown[] };
  111 |       return (target.__privateTeamEvents ?? []) as ObservedEvent[];
  112 |     });
  113 |     await testInfo.attach("team-summary-order-events.json", {
  114 |       body: Buffer.from(`${JSON.stringify(events, null, 2)}\n`),
  115 |       contentType: "application/json",
  116 |     });
  117 |     await attachUiState(page, testInfo, "failure-lead-summary-overtook-member-events");
  118 |     const summaryIndex = events.findIndex(
  119 |       (event) => event.kind === "text_delta" && event.text === "团队总结：Sprint 规划与质量门禁均已完成。",
  120 |     );
  121 |     expect(summaryIndex).toBeGreaterThanOrEqual(0);
  122 |     for (const threadId of ["team-release", "team-quality"]) {
  123 |       const completedIndex = events.findIndex(
  124 |         (event) => event.kind === "subagent_thread_completed" && event.thread_id === threadId,
  125 |       );
  126 |       expect(completedIndex).toBeGreaterThanOrEqual(0);
  127 |       expect(summaryIndex, JSON.stringify(events)).toBeGreaterThan(completedIndex);
  128 |     }
  129 |   } finally {
  130 |     await cleanup(app, home);
  131 |   }
  132 | });
  133 | 
```