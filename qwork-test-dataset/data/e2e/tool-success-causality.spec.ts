import { expect, test, type ElectronApplication } from "@playwright/test";
import {
  attachUiState,
  setContentSize,
} from "../../../../../e2e/fixtures/workbuddy-ui";
import {
  cleanup,
  createTestHome,
  createWorkspace,
  openApp,
} from "./fixtures/launch-isolated";

type ToolEvent = {
  kind?: string;
  tool_id?: string;
  name?: string;
  status?: string;
  is_error?: boolean;
  input?: unknown;
  output?: unknown;
};

test("WB-EXEC-004 | ZiqDo 工具成功事件形成完成态、耗时、输入输出与产物入口", async ({}, testInfo) => {
  const home = await createTestHome("tool-success-causality");
  await createWorkspace(home);
  let app: ElectronApplication | undefined;
  try {
    const opened = await openApp(home);
    app = opened.app;
    const page = opened.page;
    await setContentSize(app, page);
    await page.getByRole("button", { name: "专家·技能·连接器", exact: true }).click();
    await page.getByRole("button", { name: /高级开发工程师.*从证据出发/ }).click();
    await page
      .getByRole("dialog", { name: "高级开发工程师" })
      .getByRole("button", { name: "召唤 高级开发工程师" })
      .click();
    await page.evaluate(() => {
      const target = window as typeof window & { __privateToolEvents?: unknown[] };
      target.__privateToolEvents = [];
      window.workGui.events.onSessionEvent((event) => target.__privateToolEvents?.push(event));
    });
    await attachUiState(page, testInfo, "entry-expert-before-tool-call");

    const composer = page.getByRole("textbox");
    await composer.fill("__E2E_TOOL_ARTIFACT__:accepted-output.md");
    await composer.press("Enter");
    const tool = page.getByRole("button", { name: /写入文件.*ok.*(?:ms|s)/ });
    await expect(tool).toBeVisible();
    await tool.click();
    const details = page.getByTestId("tool-call-details");
    await expect(details).toContainText("accepted-output.md");
    await expect(details).toContainText("after!");
    await expect(details).toContainText("ok");
    await attachUiState(page, testInfo, "transition-success-details-and-duration");

    const artifact = page.getByTestId("main-content").getByRole("button", { name: "accepted-output.md" });
    await expect(artifact).toBeVisible();
    await artifact.click();
    const preview = page.getByRole("complementary", { name: "工件预览" });
    await expect(preview).toBeVisible();
    await expect(preview.getByRole("tab", { name: "accepted-output.md", exact: true })).toBeVisible();
    await expect(preview).toContainText("after!");
    await attachUiState(page, testInfo, "final-artifact-entry-opens-preview");

    const events = await page.evaluate(() => {
      const target = window as typeof window & { __privateToolEvents?: ToolEvent[] };
      return target.__privateToolEvents ?? [];
    });
    const callIndex = events.findIndex((event) => event.kind === "tool_call" && event.name === "write_file");
    const resultIndex = events.findIndex((event) => event.kind === "tool_result" && event.name === "write_file");
    expect(callIndex).toBeGreaterThanOrEqual(0);
    expect(resultIndex).toBeGreaterThan(callIndex);
    expect(events[resultIndex]).toMatchObject({ status: "ok", is_error: false, output: "ok" });
    await testInfo.attach("tool-success-events.json", {
      body: Buffer.from(`${JSON.stringify(events, null, 2)}\n`),
      contentType: "application/json",
    });
  } finally {
    await cleanup(app, home);
  }
});
