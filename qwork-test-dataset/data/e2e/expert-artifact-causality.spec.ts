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

test("WB-EXPERT-007 | 只有真实工作区产物才显示产物卡并可打开预览", async ({}, testInfo) => {
  const home = await createTestHome("expert-artifact-causality");
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
    await composer.fill("先给出不产生文件的风险摘要");
    await composer.press("Enter");
    await expect(page.getByText("收到：先给出不产生文件的风险摘要", { exact: true })).toBeVisible();
    await expect(page.getByTestId("main-content").getByRole("button", { name: /\.html|\.md/ })).toHaveCount(0);
    await attachUiState(page, testInfo, "entry-no-artifact-no-card");

    await composer.fill("__E2E_ARTIFACT__:expert-output.html");
    await composer.press("Enter");
    const artifact = page.getByTestId("main-content").getByRole("button", { name: /expert-output\.html/ });
    await expect(artifact).toBeVisible();
    await expect.poll(async () =>
      (await page.evaluate(() => window.workGui.files.list())).map((file) => file.name),
    ).toContain("expert-output.html");
    await attachUiState(page, testInfo, "transition-real-artifact-card");

    await artifact.click();
    const preview = page.getByRole("complementary", { name: "工件预览" });
    await expect(preview).toBeVisible();
    await expect(preview.getByRole("tab", { name: "expert-output.html", exact: true })).toBeVisible();
    await expect(preview).toContainText("E2E workspace file");
    await attachUiState(page, testInfo, "final-real-artifact-preview");
  } finally {
    await cleanup(app, home);
  }
});
