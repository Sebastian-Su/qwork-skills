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
} from "./fixtures/launch-team-terminal-isolated";

type TeamEvent = { kind?: string; thread_id?: string; status?: string; reason?: string; error?: string | null };

test("WB-TEAM-007 | completed/failed/blocked/interrupted 四类成员终态与 ZiqDo 事件一致", async ({}, testInfo) => {
  const home = await createTestHome("team-terminal-matrix");
  await createWorkspace(home);
  let app: ElectronApplication | undefined;
  try {
    const opened = await openApp(home);
    app = opened.app;
    const page = opened.page;
    await setContentSize(app, page);
    const composer = await summonGameStudio(page);
    await page.evaluate(() => {
      const target = window as typeof window & { __privateTerminalEvents?: unknown[] };
      target.__privateTerminalEvents = [];
      window.workGui.events.onSessionEvent((event) => target.__privateTerminalEvents?.push(event));
    });
    await attachUiState(page, testInfo, "entry-lead-before-terminal-events");
    await composer.fill("__E2E_TEAM_TERMINAL_MATRIX__");
    await composer.press("Enter");

    const terminalButtons = [
      page.getByRole("button", { name: /完成成员.*已完成/ }),
      page.getByRole("button", { name: /失败成员.*失败/ }),
      page.getByRole("button", { name: /阻塞成员.*待确认/ }),
      page.getByRole("button", { name: /中断成员.*已中断/ }),
    ];
    for (const button of terminalButtons) await expect(button).toBeVisible();
    await attachUiState(page, testInfo, "transition-four-terminal-statuses-from-sidecar");

    const events = await page.evaluate(() => {
      const target = window as typeof window & { __privateTerminalEvents?: TeamEvent[] };
      return target.__privateTerminalEvents ?? [];
    });
    await testInfo.attach("team-terminal-events.json", {
      body: Buffer.from(`${JSON.stringify(events, null, 2)}\n`),
      contentType: "application/json",
    });
    const terminalByThread = new Map<string, string>();
    for (const event of events) {
      if (event.kind === "subagent_thread_blocked" && event.thread_id) terminalByThread.set(event.thread_id, "blocked");
      if (event.kind === "subagent_thread_completed" && event.thread_id) terminalByThread.set(event.thread_id, event.status ?? "completed");
    }
    expect(Object.fromEntries(terminalByThread)).toEqual({
      "terminal-completed": "completed",
      "terminal-failed": "failed",
      "terminal-blocked": "blocked",
      "terminal-interrupted": "interrupted",
    });

    await terminalButtons[1].click();
    await expect(page.getByRole("heading", { name: "失败成员" })).toBeVisible();
    await expect(page.locator("article").getByText("失败", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "重试此成员任务" })).toBeVisible();
    await terminalButtons[2].click();
    await expect(page.getByRole("heading", { name: "阻塞成员" })).toBeVisible();
    await expect(page.locator("article").getByText("待确认", { exact: true })).toBeVisible();
    await terminalButtons[3].click();
    await expect(page.getByRole("heading", { name: "中断成员" })).toBeVisible();
    await expect(page.locator("article").getByText("已中断", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "重试此成员任务" })).toBeVisible();
    await attachUiState(page, testInfo, "final-terminal-pages-match-events");
  } finally {
    await cleanup(app, home);
  }
});
