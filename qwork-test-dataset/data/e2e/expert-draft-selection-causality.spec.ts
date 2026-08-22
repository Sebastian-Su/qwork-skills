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

async function controlTypes(sidecarLog: string): Promise<string[]> {
  return (await fs.readFile(sidecarLog, "utf8").catch(() => ""))
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line) as { type?: string })
    .map((message) => message.type ?? "unknown");
}

async function taskCount(page: Page): Promise<string> {
  return (await page.getByText(/^任务 \(\d+\)$/).first().textContent()) ?? "";
}

test("PHASE2-DRAFT-SELECTION-001 | 示例问题只预填且专家可移除与替换", async ({}, testInfo) => {
  const home = await createTestHome("expert-draft-selection");
  await createWorkspace(home);
  const sidecarLog = path.join(home, "sidecar-control.jsonl");
  const opened = await openApp(home, { E2E_SIDECAR_CONTROL_LOG: sidecarLog });
  let app: ElectronApplication | undefined = opened.app;
  try {
    const { page } = opened;
    await setContentSize(app, page);
    const composer = page.getByRole("textbox");
    const before = { tasks: await taskCount(page), url: page.url() };

    await page.getByRole("button", { name: "专家·技能·连接器", exact: true }).click();
    await page.getByRole("button", { name: /高级开发工程师.*从证据出发/ }).click();
    const detail = page.getByRole("dialog", { name: "高级开发工程师" });
    await attachUiState(page, testInfo, "entry-expert-sample-question");
    await detail.getByRole("button", {
      name: /帮我开发一个功能.*先给出实现计划再动手写代码/,
    }).click();

    const sample = "“帮我开发一个功能，我会描述需求，请你先给出实现计划再动手写代码。”";
    await expect(composer).toHaveValue(sample);
    await expect(page.getByTestId("composer-dock")).toContainText("高级开发工程师");
    await attachUiState(page, testInfo, "transition-sample-prefilled-expert-selected");

    await page.getByRole("button", { name: "移除高级开发工程师", exact: true }).click();
    await expect(page.getByTestId("composer-dock")).not.toContainText("高级开发工程师");
    await expect(composer).toHaveValue(sample);

    await page.getByRole("button", { name: "专家·技能·连接器", exact: true }).click();
    await page.getByRole("tab", { name: "专家团", exact: true }).click();
    await page.getByRole("button", { name: /游戏开发工作室.*由负责人统筹/ })
      .getByRole("button", { name: "召唤游戏开发工作室", exact: true })
      .click();

    await expect(page.getByTestId("composer-dock")).toContainText("游戏开发工作室");
    await expect(page.getByTestId("composer-dock")).not.toContainText("高级开发工程师");
    await expect(composer).toHaveValue(sample);
    await expect(page.getByText(/^任务 \(\d+\)$/).first()).toHaveText(before.tasks);
    expect(page.url()).toBe(before.url);
    expect(page.url()).not.toMatch(/\/task\/[^/?#]+/);
    await expect(page.getByTestId("thread-message-list").getByText(sample, { exact: true })).toHaveCount(0);
    const types = await controlTypes(sidecarLog);
    expect(types).not.toContain("create_session");
    expect(types).not.toContain("user_message");
    expect(types).not.toContain("subscribe_subagent_streams");
    await attachUiState(page, testInfo, "final-team-replaces-expert-without-runtime");
  } finally {
    await cleanup(app, home);
  }
});
