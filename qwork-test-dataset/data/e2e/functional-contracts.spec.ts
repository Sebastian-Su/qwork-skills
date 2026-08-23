import { expect, test, type ElectronApplication } from "@playwright/test";
import {
  attachUiState,
  setContentSize,
} from "../../../../../e2e/fixtures/ui-contract";
import {
  cleanup,
  createTestHome,
  createWorkspace,
  openApp,
} from "./fixtures/launch-isolated";

test("WB-EXEC-001 + WB-RECOVERY-001 | 专家等待态可停止且恢复输入", async ({}, testInfo) => {
  const home = await createTestHome("expert-wait-stop");
  await createWorkspace(home);
  let app: ElectronApplication | undefined;
  try {
    let page;
    ({ app, page } = await openApp(home));
    await setContentSize(app, page);
    await page.getByRole("button", { name: "专家·技能·连接器", exact: true }).click();
    await page.getByRole("button", { name: /高级开发工程师.*从证据出发/ }).click();
    await page
      .getByRole("dialog", { name: "高级开发工程师" })
      .getByRole("button", { name: "召唤 高级开发工程师" })
      .click();

    const composer = page.getByRole("textbox");
    await composer.fill("__E2E_HANG__");
    await attachUiState(page, testInfo, "entry-expert-selected");
    await composer.press("Enter");

    await expect(page.getByRole("group", { name: "当前执行专家" })).toContainText("高级开发工程师");
    await expect(page.getByText("等待模型响应", { exact: true })).toBeVisible();
    await expect(composer).toBeDisabled();
    const stop = page.getByRole("button", { name: "停止生成", exact: true });
    await expect(stop).toBeVisible();
    await attachUiState(page, testInfo, "transition-waiting");
    await stop.click();

    await expect(page.getByText("已取消", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "重试", exact: true })).toBeVisible();
    await expect(composer).toBeEnabled();
    await expect(page.getByText("等待模型响应", { exact: true })).toHaveCount(0);
    await attachUiState(page, testInfo, "final-stopped-recoverable");
  } finally {
    await cleanup(app, home);
  }
});
