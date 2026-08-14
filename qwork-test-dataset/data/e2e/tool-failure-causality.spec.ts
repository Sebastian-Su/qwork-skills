import { expect, test, type ElectronApplication } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import { attachUiState, setContentSize } from "../../../../../e2e/fixtures/workbuddy-ui";
import { cleanup, createTestHome, createWorkspace, openApp } from "./fixtures/launch-tool-failure-isolated";

type ToolEvent = { kind?: string; tool_id?: string; name?: string; status?: string; is_error?: boolean; output?: unknown };

test("WB-EXEC-005 | ZiqDo 工具失败事件形成红色错误摘要且不伪造完成或产物", async ({}, testInfo) => {
  const home = await createTestHome("tool-failure-causality");
  const workspace = await createWorkspace(home);
  let app: ElectronApplication | undefined;
  try {
    const opened = await openApp(home);
    app = opened.app;
    const page = opened.page;
    await setContentSize(app, page);
    await page.getByRole("button", { name: "专家·技能·连接器", exact: true }).click();
    await page.getByRole("button", { name: /高级开发工程师.*从证据出发/ }).click();
    await page.getByRole("dialog", { name: "高级开发工程师" }).getByRole("button", { name: "召唤 高级开发工程师" }).click();
    await page.evaluate(() => {
      const target = window as typeof window & { __privateToolFailureEvents?: unknown[] };
      target.__privateToolFailureEvents = [];
      window.workGui.events.onSessionEvent((event) => target.__privateToolFailureEvents?.push(event));
    });
    await attachUiState(page, testInfo, "entry-expert-before-failed-tool");
    const composer = page.getByRole("textbox");
    await composer.fill("__E2E_TOOL_FAILURE__");
    await composer.press("Enter");

    const tool = page.getByRole("button", { name: /写入文件.*error.*(?:ms|s)/ });
    await expect(tool).toBeVisible();
    await expect(tool).toHaveClass(/text-danger/);
    await expect(tool).not.toContainText("ok");
    await tool.click();
    const details = page.getByTestId("tool-call-details");
    await expect(details).toContainText("EACCES: permission denied");
    await expect(details.locator("pre")).toHaveClass(/text-danger/);
    await attachUiState(page, testInfo, "transition-error-summary-and-danger-state");

    await expect(page.getByTestId("main-content").getByRole("button", { name: "must-not-exist.md" })).toHaveCount(0);
    await expect.poll(async () => fs.stat(path.join(workspace, "must-not-exist.md")).then(() => true).catch(() => false)).toBe(false);
    const events = await page.evaluate(() => {
      const target = window as typeof window & { __privateToolFailureEvents?: ToolEvent[] };
      return target.__privateToolFailureEvents ?? [];
    });
    const callIndex = events.findIndex((event) => event.kind === "tool_call" && event.tool_id === "tool-failure-write");
    const resultIndex = events.findIndex((event) => event.kind === "tool_result" && event.tool_id === "tool-failure-write");
    expect(resultIndex).toBeGreaterThan(callIndex);
    expect(events[resultIndex]).toMatchObject({ status: "error", is_error: true });
    await testInfo.attach("tool-failure-events.json", { body: Buffer.from(`${JSON.stringify(events, null, 2)}\n`), contentType: "application/json" });
    await attachUiState(page, testInfo, "final-no-completed-state-no-artifact");
  } finally {
    await cleanup(app, home);
  }
});
