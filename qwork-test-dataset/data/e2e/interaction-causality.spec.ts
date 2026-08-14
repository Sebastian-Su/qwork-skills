import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import {
  attachUiState,
  setContentSize,
  summonGameStudio,
} from "../../../../../e2e/fixtures/workbuddy-ui";
import {
  cleanup,
  createTestHome,
  createWorkspace,
  openApp,
} from "./fixtures/launch-isolated";

async function send(page: Page, value: string): Promise<void> {
  const composer = page.getByRole("textbox");
  await composer.fill(value);
  await composer.press("Enter");
}

test("WB-EXEC-006 | 权限允许拒绝与 Lead AskUser 回答跳过均产生唯一协议回执", async ({}, testInfo) => {
  const home = await createTestHome("interaction-causality");
  await createWorkspace(home);
  const sidecarLog = path.join(home, "sidecar-control.jsonl");
  let app: ElectronApplication | undefined;
  try {
    let page;
    ({ app, page } = await openApp(home, { E2E_SIDECAR_CONTROL_LOG: sidecarLog }));
    await setContentSize(app, page);

    await send(page, "__E2E_PERMISSION__:Bash");
    const permission = page.getByRole("region", { name: "权限询问" });
    await expect(permission).toBeVisible();
    await expect(permission).toContainText(/Bash.*E2E permission request/s);
    await expect(permission.getByRole("checkbox", { name: "记住选择" })).toBeVisible();
    await attachUiState(page, testInfo, "entry-permission-allowable");
    await permission.getByRole("button", { name: "允许", exact: true }).click();
    await expect(page.getByText("permission:allowed:once", { exact: true })).toBeVisible();

    await send(page, "__E2E_PERMISSION__:WriteFile");
    await expect(permission).toBeVisible();
    await permission.getByRole("button", { name: "拒绝", exact: true }).click();
    await expect(page.getByText("permission:denied", { exact: true })).toBeVisible();
    await attachUiState(page, testInfo, "transition-permission-denied-with-terminal-reply");

    await page.getByRole("button", { name: "新建任务", exact: true }).click();
    const teamComposer = await summonGameStudio(page);
    await teamComposer.fill("__E2E_EXPERT_ASK__");
    await teamComposer.press("Enter");
    const ask = page.getByRole("region", { name: "需要你的确认" });
    await expect(ask).toBeVisible();
    await expect(ask).toContainText("目标平台是桌面端还是移动端？");
    await expect(page.getByRole("button", { name: /游戏开发工作室.*负责人/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /发布运营|质量保障/ })).toHaveCount(0);
    const askBox = await ask.boundingBox();
    const composerBox = await page.getByPlaceholder(/今天帮你做些什么/).boundingBox();
    expect(askBox).not.toBeNull();
    expect(composerBox).not.toBeNull();
    expect(askBox!.y + askBox!.height).toBeLessThanOrEqual(composerBox!.y);
    await ask.getByRole("button", { name: /1 桌面端/ }).click();
    await expect(page.getByText("已收到选择：桌面端", { exact: true })).toBeVisible();
    await expect(ask).toBeVisible();
    await ask.getByRole("button", { name: "跳过", exact: true }).click();
    await expect(page.getByText("已收到选择：", { exact: true })).toBeVisible();
    await attachUiState(page, testInfo, "final-lead-answer-and-skip");

    const controls = (await fs.readFile(sidecarLog, "utf8"))
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line) as Record<string, unknown>);
    const permissionResponses = controls.filter((message) => message.type === "permission_response");
    expect(permissionResponses).toHaveLength(2);
    expect(
      permissionResponses.map((message) =>
        (message.decision as { decision?: string } | undefined)?.decision,
      ),
    ).toEqual(["allow", "deny"]);
    const interactionResponses = controls.filter(
      (message) => message.type === "user_message" && String(message.content).includes("<qwork_interaction_response"),
    );
    expect(interactionResponses).toHaveLength(2);
    expect(String(interactionResponses[0]?.content)).toContain('action="answer"');
    expect(String(interactionResponses[1]?.content)).toContain('action="skip"');
  } finally {
    await cleanup(app, home);
  }
});
