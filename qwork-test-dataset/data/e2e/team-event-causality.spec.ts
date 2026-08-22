import { expect, test, type ElectronApplication } from "@playwright/test";
import {
  attachUiState,
  setContentSize,
  summonGameStudio,
} from "../../../../../e2e/fixtures/ui-contract";
import {
  cleanup,
  createTestHome,
  createWorkspace,
  openApp,
} from "./fixtures/launch-isolated";

type ObservedEvent = { kind?: string; thread_id?: string; text?: string; status?: string };

test("WB-TEAM-004/005/006 | 真实成员事件形成只读成员流且 completed 状态与事件一致", async ({}, testInfo) => {
  const home = await createTestHome("team-event-causality");
  await createWorkspace(home);
  let app: ElectronApplication | undefined;
  try {
    const opened = await openApp(home);
    app = opened.app;
    const page = opened.page;
    await setContentSize(app, page);
    const composer = await summonGameStudio(page);
    await expect(page.getByRole("navigation", { name: "专家团成员" })).toHaveCount(0);

    await page.evaluate(() => {
      const target = window as typeof window & { __privateTeamEvents?: unknown[] };
      target.__privateTeamEvents = [];
      window.workGui.events.onSessionEvent((event) => target.__privateTeamEvents?.push(event));
    });
    await attachUiState(page, testInfo, "entry-lead-registered-without-running-members");
    await composer.fill("请制定 Sprint 规划并完成质量门禁检查");
    await composer.press("Enter");

    const release = page.getByRole("button", { name: /发布运营.*已完成/ });
    const quality = page.getByRole("button", { name: /质量保障.*已完成/ });
    await expect(release).toBeVisible();
    await expect(quality).toBeVisible();
    await expect(
      page.getByText("团队总结：Sprint 规划与质量门禁均已完成。", { exact: true }),
    ).toBeVisible();
    await attachUiState(page, testInfo, "transition-members-completed-before-lead-summary");

    const events = await page.evaluate(() => {
      const target = window as typeof window & { __privateTeamEvents?: unknown[] };
      return (target.__privateTeamEvents ?? []) as ObservedEvent[];
    });
    await testInfo.attach("team-session-events.json", {
      body: Buffer.from(`${JSON.stringify(events, null, 2)}\n`),
      contentType: "application/json",
    });
    await attachUiState(page, testInfo, "evidence-raw-event-order-before-assertion");
    const index = (kind: string, threadId?: string) => events.findIndex(
      (event) => event.kind === kind && (!threadId || event.thread_id === threadId),
    );
    for (const threadId of ["team-release", "team-quality"]) {
      expect(index("subagent_thread_started", threadId), JSON.stringify(events)).toBeGreaterThanOrEqual(0);
      expect(index("subagent_text_delta", threadId), JSON.stringify(events)).toBeGreaterThan(index("subagent_thread_started", threadId));
      expect(index("subagent_thread_completed", threadId), JSON.stringify(events)).toBeGreaterThan(index("subagent_text_delta", threadId));
    }
    expect(events.filter((event) => event.kind === "subagent_thread_started")).toHaveLength(2);
    expect(events.filter((event) => event.kind === "subagent_thread_completed")).toHaveLength(2);

    await release.click();
    await expect(page.getByRole("heading", { name: "发布运营" })).toBeVisible();
    await expect(page.getByText("团队：游戏开发工作室", { exact: true })).toBeVisible();
    await expect(page.getByText(/更新时间：\d{2}:\d{2}/)).toBeVisible();
    await expect(page.getByText("工具调用：未上报（ZiqDo）", { exact: false })).toBeVisible();
    await expect(page.getByText("模型：e2e-balanced · in 120 · out 40", { exact: true })).toBeVisible();
    await expect(page.getByText("Sprint 规划已完成", { exact: true })).toBeVisible();
    await expect(page.getByRole("textbox")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "重试此成员任务" })).toHaveCount(0);
    await attachUiState(page, testInfo, "final-member-independent-readonly-transcript");

    await page.getByRole("button", { name: /游戏开发工作室.*负责人/ }).click();
    await expect(page.getByRole("textbox")).toBeEnabled();
    await expect(
      page.getByText("团队总结：Sprint 规划与质量门禁均已完成。", { exact: true }),
    ).toBeVisible();
  } finally {
    await cleanup(app, home);
  }
});

test("WB-TEAM-008 | Lead 总结必须晚于所需成员完成事件", async ({}, testInfo) => {
  const home = await createTestHome("team-lead-summary-order");
  await createWorkspace(home);
  let app: ElectronApplication | undefined;
  try {
    const opened = await openApp(home);
    app = opened.app;
    const page = opened.page;
    await setContentSize(app, page);
    const composer = await summonGameStudio(page);
    await page.evaluate(() => {
      const target = window as typeof window & { __privateTeamEvents?: unknown[] };
      target.__privateTeamEvents = [];
      window.workGui.events.onSessionEvent((event) => target.__privateTeamEvents?.push(event));
    });
    await attachUiState(page, testInfo, "entry-lead-before-member-delegation");
    await composer.fill("请制定 Sprint 规划并完成质量门禁检查");
    await composer.press("Enter");
    await expect(page.getByRole("button", { name: /发布运营.*已完成/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /质量保障.*已完成/ })).toBeVisible();
    await attachUiState(page, testInfo, "transition-member-results-returned");

    const events = await page.evaluate(() => {
      const target = window as typeof window & { __privateTeamEvents?: unknown[] };
      return (target.__privateTeamEvents ?? []) as ObservedEvent[];
    });
    await testInfo.attach("team-summary-order-events.json", {
      body: Buffer.from(`${JSON.stringify(events, null, 2)}\n`),
      contentType: "application/json",
    });
    await attachUiState(page, testInfo, "failure-lead-summary-overtook-member-events");
    const summaryIndex = events.findIndex(
      (event) => event.kind === "text_delta" && event.text === "团队总结：Sprint 规划与质量门禁均已完成。",
    );
    expect(summaryIndex).toBeGreaterThanOrEqual(0);
    for (const threadId of ["team-release", "team-quality"]) {
      const completedIndex = events.findIndex(
        (event) => event.kind === "subagent_thread_completed" && event.thread_id === threadId,
      );
      expect(completedIndex).toBeGreaterThanOrEqual(0);
      expect(summaryIndex, JSON.stringify(events)).toBeGreaterThan(completedIndex);
    }
    await attachUiState(page, testInfo, "final-lead-summary-after-required-members");
  } finally {
    await cleanup(app, home);
  }
});
