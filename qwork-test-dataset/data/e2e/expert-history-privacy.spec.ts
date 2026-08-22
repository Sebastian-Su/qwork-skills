import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
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

const query = "用一句话介绍你自己，你叫什么，能做什么";
const forbidden = /qwork_expert_identity|qwork_team_runtime|package_id=|principal=/i;

function currentTask(page: Page) {
  return page.getByRole("complementary").getByRole("button", { name: /自我介绍|用一句话介绍/ }).first();
}

test("WB-HISTORY-001 + WB-RECOVERY-004 | 重启后的标题消息与历史均不泄漏内部身份契约", async ({}, testInfo) => {
  const home = await createTestHome("expert-history-privacy");
  await createWorkspace(home);
  const sidecarLog = path.join(home, "sidecar-control.jsonl");
  let app: ElectronApplication | undefined;
  try {
    let page;
    ({ app, page } = await openApp(home, { E2E_SIDECAR_CONTROL_LOG: sidecarLog }));
    await setContentSize(app, page);
    await attachUiState(page, testInfo, "entry-home-before-expert-navigation");
    await page.getByRole("button", { name: "专家·技能·连接器", exact: true }).click();
    await page.getByRole("button", { name: /高级开发工程师.*从证据出发/ }).click();
    await page
      .getByRole("dialog", { name: "高级开发工程师" })
      .getByRole("button", { name: "召唤 高级开发工程师" })
      .click();
    await page.getByRole("textbox").fill(query);
    await page.getByRole("textbox").press("Enter");
    await expect(page.getByText(`收到：${query}`, { exact: true })).toBeVisible();
    await expect(currentTask(page)).toBeVisible();
    expect(await page.getByTestId("main-content").innerText()).not.toMatch(forbidden);
    await attachUiState(page, testInfo, "entry-completed-expert-history");

    const controls = (await fs.readFile(sidecarLog, "utf8"))
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line) as Record<string, unknown>);
    const create = controls.find((message) => message.type === "create_session");
    expect(create?.plugin_dirs).toEqual(expect.arrayContaining([expect.stringMatching(/senior-developer/)]));
    const prompt = controls.find((message) => message.type === "user_message");
    expect(prompt?.content).toBe(query);
    expect(JSON.stringify(prompt)).not.toMatch(forbidden);

    const sessionId = String(create?.session_id ?? "");
    expect(sessionId).toMatch(/^[A-Za-z0-9_-]+$/);
    const transcript = path.join(home, "sessions", "e2e", `${sessionId}.jsonl`);
    const transcriptLines = (await fs.readFile(transcript, "utf8")).trimEnd().split("\n");
    transcriptLines.splice(1, 0, JSON.stringify({
      type: "message",
      message: {
        role: "user",
        blocks: [{
          type: "text",
          text: '<qwork_expert_identity package_id="senior-developer" kind="individual" principal="senior-developer">\n内部身份说明\n</qwork_expert_identity>',
        }],
      },
    }));
    await fs.writeFile(transcript, `${transcriptLines.join("\n")}\n`, "utf8");

    await app.close();
    app = undefined;
    ({ app, page } = await openApp(home, { E2E_SIDECAR_CONTROL_LOG: sidecarLog }));
    await setContentSize(app, page);
    const task = currentTask(page);
    await expect(task).toBeVisible();
    expect(await task.innerText()).not.toMatch(forbidden);
    await attachUiState(page, testInfo, "transition-restarted-task-title-private");

    await task.click();
    const messages = page.getByTestId("thread-message-list");
    await expect(messages.getByText(query, { exact: true })).toHaveCount(1);
    await expect(messages.getByText(`收到：${query}`, { exact: true })).toHaveCount(1);
    expect(await page.getByTestId("main-content").innerText()).not.toMatch(forbidden);
    await expect(page.getByText("等待模型响应", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("textbox")).toBeEnabled();
    await attachUiState(page, testInfo, "final-reloaded-history-private-and-idle");
  } finally {
    await cleanup(app, home);
  }
});
