# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: team-event-causality.spec.ts >> WB-TEAM-008 | Lead 总结必须晚于所需成员完成事件
- Location: .agents/skills/qwork-test-dataset/data/e2e/team-event-causality.spec.ts:87:1

# Error details

```
Error: [{"type":"session_event","kind":"status","session_id":"wg-msse36xr-vebnw6","status":"streaming"},{"type":"session_event","kind":"text_delta","session_id":"wg-msse36xr-vebnw6","text":"团队总结：Sprint 规划与质量门禁均已完成。"},{"type":"session_event","kind":"status","session_id":"wg-msse36xr-vebnw6","status":"idle"},{"type":"session_event","kind":"subagent_thread_started","session_id":"wg-msse36xr-vebnw6","thread_id":"team-release","agent_id":"release-ops-lead","name":"发布运营","model":"e2e-balanced"},{"type":"session_event","kind":"subagent_thread_started","session_id":"wg-msse36xr-vebnw6","thread_id":"team-quality","agent_id":"quality-lead","name":"质量保障","model":"e2e-reasoning"},{"type":"session_event","kind":"subagent_text_delta","session_id":"wg-msse36xr-vebnw6","thread_id":"team-release","delta":"Sprint 规划已完成"},{"type":"session_event","kind":"subagent_text_delta","session_id":"wg-msse36xr-vebnw6","thread_id":"team-quality","delta":"质量门禁检查通过"},{"type":"session_event","kind":"subagent_thread_completed","session_id":"wg-msse36xr-vebnw6","thread_id":"team-release","status":"completed","input_tokens":120,"output_tokens":40},{"type":"session_event","kind":"subagent_thread_completed","session_id":"wg-msse36xr-vebnw6","thread_id":"team-quality","status":"completed","input_tokens":150,"output_tokens":35}]

expect(received).toBeGreaterThan(expected)

Expected: > 7
Received:   1
```

# Test source

```ts
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
  73  |     await expect(page.getByRole("textbox")).toHaveCount(0);
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
> 127 |       expect(summaryIndex, JSON.stringify(events)).toBeGreaterThan(completedIndex);
      |                                                    ^ Error: [{"type":"session_event","kind":"status","session_id":"wg-msse36xr-vebnw6","status":"streaming"},{"type":"session_event","kind":"text_delta","session_id":"wg-msse36xr-vebnw6","text":"团队总结：Sprint 规划与质量门禁均已完成。"},{"type":"session_event","kind":"status","session_id":"wg-msse36xr-vebnw6","status":"idle"},{"type":"session_event","kind":"subagent_thread_started","session_id":"wg-msse36xr-vebnw6","thread_id":"team-release","agent_id":"release-ops-lead","name":"发布运营","model":"e2e-balanced"},{"type":"session_event","kind":"subagent_thread_started","session_id":"wg-msse36xr-vebnw6","thread_id":"team-quality","agent_id":"quality-lead","name":"质量保障","model":"e2e-reasoning"},{"type":"session_event","kind":"subagent_text_delta","session_id":"wg-msse36xr-vebnw6","thread_id":"team-release","delta":"Sprint 规划已完成"},{"type":"session_event","kind":"subagent_text_delta","session_id":"wg-msse36xr-vebnw6","thread_id":"team-quality","delta":"质量门禁检查通过"},{"type":"session_event","kind":"subagent_thread_completed","session_id":"wg-msse36xr-vebnw6","thread_id":"team-release","status":"completed","input_tokens":120,"output_tokens":40},{"type":"session_event","kind":"subagent_thread_completed","session_id":"wg-msse36xr-vebnw6","thread_id":"team-quality","status":"completed","input_tokens":150,"output_tokens":35}]
  128 |     }
  129 |   } finally {
  130 |     await cleanup(app, home);
  131 |   }
  132 | });
  133 | 
```