import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
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

const hangingQuery = "__E2E_HANG__";
const continuedQuery = "恢复后继续分析，并只回复恢复成功";

function task(page: Page) {
  return page
    .getByRole("complementary")
    .getByRole("button", { name: hangingQuery, exact: true });
}

async function controls(file: string): Promise<Record<string, unknown>[]> {
  return (await fs.readFile(file, "utf8"))
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line) as Record<string, unknown>);
}

test("WB-RECOVERY-005 | 未完成专家历史重启后不伪造续跑且只派发新的继续请求", async ({}, testInfo) => {
  const home = await createTestHome("stale-wait-recovery");
  await createWorkspace(home);
  const sidecarLog = path.join(home, "sidecar-control.jsonl");
  let app: ElectronApplication | undefined;
  try {
    let page;
    ({ app, page } = await openApp(home, { E2E_SIDECAR_CONTROL_LOG: sidecarLog }));
    await setContentSize(app, page);
    await page.getByRole("button", { name: "专家·技能·连接器", exact: true }).click();
    await page.getByRole("button", { name: /高级开发工程师.*从证据出发/ }).click();
    await page
      .getByRole("dialog", { name: "高级开发工程师" })
      .getByRole("button", { name: "召唤 高级开发工程师" })
      .click();
    const composer = page.getByRole("textbox");
    await composer.fill(hangingQuery);
    await composer.press("Enter");
    await expect(page.getByText("等待模型响应", { exact: true })).toBeVisible();
    await expect(composer).toBeDisabled();
    await attachUiState(page, testInfo, "entry-live-turn-waiting-before-restart");

    const beforeRestart = await controls(sidecarLog);
    const firstCreate = beforeRestart.find((message) => message.type === "create_session");
    const sessionId = String(firstCreate?.session_id ?? "");
    expect(sessionId).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(
      beforeRestart.filter((message) => message.type === "user_message"),
    ).toHaveLength(1);
    const transcript = path.join(home, "sessions", "e2e", `${sessionId}.jsonl`);
    const persistedBeforeRestart = await fs.readFile(transcript, "utf8");
    expect(persistedBeforeRestart).toContain(hangingQuery);
    expect(persistedBeforeRestart).not.toContain('"role":"assistant"');

    await app.close();
    app = undefined;
    ({ app, page } = await openApp(home, { E2E_SIDECAR_CONTROL_LOG: sidecarLog }));
    await setContentSize(app, page);
    await expect(task(page)).toBeVisible();
    await task(page).click();
    const messages = page.getByTestId("thread-message-list");
    await expect(messages.getByText(hangingQuery, { exact: true })).toHaveCount(1);
    await attachUiState(page, testInfo, "transition-cold-history-after-restart");
    await attachUiState(page, testInfo, "failure-stale-wait-must-be-terminal");
    await expect(page.getByText("等待模型响应", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "停止", exact: true })).toHaveCount(0);
    await expect(page.getByRole("textbox")).toBeEnabled();
    await attachUiState(page, testInfo, "transition-cold-history-idle-after-restart");

    await page.getByRole("textbox").fill(continuedQuery);
    await page.getByRole("textbox").press("Enter");
    await expect(page.getByText(`收到：${continuedQuery}`, { exact: true })).toBeVisible();
    await expect(page.getByText("等待模型响应", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("textbox")).toBeEnabled();
    await attachUiState(page, testInfo, "final-restored-session-continued-once");

    const afterContinue = await controls(sidecarLog);
    const creates = afterContinue.filter((message) => message.type === "create_session");
    expect(creates).toHaveLength(2);
    expect(creates[1]).toMatchObject({
      session_id: sessionId,
      resume: transcript,
    });
    const prompts = afterContinue.filter((message) => message.type === "user_message");
    expect(prompts.map((message) => message.content)).toEqual([
      hangingQuery,
      continuedQuery,
    ]);
  } finally {
    await cleanup(app, home);
  }
});
