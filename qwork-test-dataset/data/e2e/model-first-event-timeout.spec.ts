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

test("WB-RECOVERY-006 | 模型首事件超时必须结束等待并提供可重试终态", async ({}, testInfo) => {
  const home = await createTestHome("model-first-event-timeout");
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

    const composer = page.getByRole("textbox");
    await composer.fill("__E2E_HANG__");
    await attachUiState(page, testInfo, "entry-expert-ready-before-timeout-probe");
    await composer.press("Enter");
    await expect(page.getByText("等待模型响应", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "停止", exact: true })).toBeVisible();
    await attachUiState(page, testInfo, "transition-model-request-has-no-first-event");

    // The deterministic sidecar deliberately never emits thinking/tool/text,
    // terminal status, or error. Production must own a first-event watchdog;
    // an indefinite spinner is not a valid runtime state.
    await page.waitForTimeout(10_000);
    await attachUiState(page, testInfo, "failure-first-event-timeout-still-waiting");
    await expect(page.getByText("等待模型响应", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "停止", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "重试", exact: true })).toBeVisible();
    await expect(composer).toBeEnabled();
  } finally {
    await cleanup(app, home);
  }
});
