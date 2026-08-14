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

async function openFixture(prefix: string) {
  const home = await createTestHome(prefix);
  const workspace = await createWorkspace(home);
  const sidecarLog = path.join(home, "sidecar-control.jsonl");
  const opened = await openApp(home, { E2E_SIDECAR_CONTROL_LOG: sidecarLog });
  await setContentSize(opened.app, opened.page);
  return { ...opened, home, sidecarLog, workspace };
}

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

test("WB-EXPERT-001 + WB-EXPERT-002 | 专家详情与召唤保留草稿且不建会话", async ({}, testInfo) => {
  const fixture = await openFixture("expert-draft-causality");
  let app: ElectronApplication | undefined = fixture.app;
  try {
    const { page, sidecarLog, workspace } = fixture;
    const composer = page.getByRole("textbox");
    const draft = "保留这段未发送的专家需求";
    const attachment = path.join(workspace, "召唤前附件.txt");
    await fs.writeFile(attachment, "召唤前已存在的附件内容", "utf8");
    await fixture.app.evaluate(({ ipcMain }, selected) => {
      ipcMain.removeHandler("dialog:openFiles");
      ipcMain.handle("dialog:openFiles", () => [selected.attachment]);
      ipcMain.removeHandler("dialog:openDirectory");
      ipcMain.handle("dialog:openDirectory", () => selected.workspace);
    }, { attachment, workspace });
    await page.getByRole("button", { name: "更多操作", exact: true }).click();
    await page.getByRole("menuitem", { name: "添加文件", exact: true }).click();
    await expect(page.getByText("召唤前附件.txt", { exact: true })).toBeVisible();

    await composer.fill(draft);
    await page.getByRole("button", { name: "默认权限", exact: true }).click();
    await page.getByRole("switch", { name: "允许完全访问", exact: true }).click();
    await expect(page.getByRole("button", { name: "完全访问", exact: true })).toBeVisible();
    await page.keyboard.press("Escape");

    await page.getByRole("button", { name: "Qwen3.7-Plus", exact: true }).click();
    await page.getByRole("menuitemradio", { name: "Kimi-K3", exact: true }).click();

    const workspaceName = path.basename(workspace);
    const modelName = "Kimi-K3";
    await page.getByRole("button", { name: "选择工作空间", exact: true }).click();
    await page.getByRole("button", { name: "选择其他文件夹…", exact: true }).click();
    const workspaceButton = page.getByRole("button", { name: "选择工作空间", exact: true });
    await expect(workspaceButton).toContainText(workspaceName);
    await expect(page.getByRole("button", { name: modelName, exact: true })).toBeVisible();
    const before = {
      tasks: await taskCount(page),
      url: page.url(),
      userBubbles: await page.locator(".message-copy").count(),
      thinkingBlocks: await page.getByText("深度思考", { exact: true }).count(),
      toolCards: await page.locator('[data-testid="tool-call-details"]').count(),
      memberBars: await page.getByRole("navigation", { name: "专家团成员" }).count(),
    };
    await page.getByRole("button", { name: "专家·技能·连接器", exact: true }).click();
    await page.getByRole("button", { name: /高级开发工程师.*从证据出发/ }).click();
    const detail = page.getByRole("dialog", { name: "高级开发工程师" });
    await expect(detail).toContainText("能力介绍");
    await expect(detail.getByRole("button", { name: /^“/ })).toHaveCount(3);
    await attachUiState(page, testInfo, "entry-expert-detail-with-draft");

    await detail.getByRole("button", { name: "召唤 高级开发工程师" }).click();
    await expect(page.getByRole("dialog", { name: "高级开发工程师" })).toHaveCount(0);
    const dock = page.getByTestId("composer-dock");
    await attachUiState(page, testInfo, "transition-expert-selected-before-oracles");
    await expect.soft(page.getByRole("heading", { name: "WorkBuddy, 我帮你", exact: true })).toBeVisible();
    await expect.soft(composer).toHaveValue(draft);
    await expect.soft(dock).toContainText("高级开发工程师");
    await expect.soft(dock.getByRole("img", { name: "高级开发工程师头像", exact: true })).toBeVisible();
    await expect.soft(page.getByText("召唤前附件.txt", { exact: true })).toBeVisible();
    await expect.soft(workspaceButton).toContainText(workspaceName);
    await expect.soft(page.getByRole("button", { name: modelName, exact: true })).toBeVisible();
    await expect.soft(page.getByRole("button", { name: "完全访问", exact: true })).toBeVisible();

    await expect.soft(page.getByText(/^任务 \(\d+\)$/).first()).toHaveText(before.tasks);
    expect.soft(page.url()).toBe(before.url);
    expect.soft(page.url()).not.toMatch(/\/task\/[^/?#]+/);
    expect.soft(await page.locator(".message-copy").count()).toBe(before.userBubbles);
    expect.soft(await page.getByText("深度思考", { exact: true }).count()).toBe(before.thinkingBlocks);
    expect.soft(await page.locator('[data-testid="tool-call-details"]').count()).toBe(before.toolCards);
    expect.soft(await page.getByRole("navigation", { name: "专家团成员" }).count()).toBe(before.memberBars);
    await expect.soft(
      page.getByTestId("thread-message-list").getByText(draft, { exact: true }),
    ).toHaveCount(0);
    const inputValue = await composer.inputValue();
    expect.soft(inputValue).toBe(draft);
    expect.soft(inputValue).not.toContain("qwork_expert_identity");
    expect.soft(inputValue).not.toContain("ziqdo-plugin.json");
    expect.soft(inputValue).not.toContain("principal");
    expect.soft(inputValue).not.toContain("roster");
    const types = await controlTypes(sidecarLog);
    expect.soft(types).not.toContain("create_session");
    expect.soft(types).not.toContain("user_message");
    await attachUiState(page, testInfo, "final-expert-no-session-no-user-message");
  } finally {
    await cleanup(app, fixture.home);
  }
});

test("WB-TEAM-001B | 专家团卡片右上召唤只选择团队且不启动成员", async ({}, testInfo) => {
  const fixture = await openFixture("team-direct-summon-causality");
  let app: ElectronApplication | undefined = fixture.app;
  try {
    const { page, sidecarLog } = fixture;
    const before = await taskCount(page);
    await page.getByRole("button", { name: "专家·技能·连接器", exact: true }).click();
    await page.getByRole("tab", { name: "专家团", exact: true }).click();
    const card = page.getByRole("button", { name: /游戏开发工作室.*由负责人统筹/ });
    await attachUiState(page, testInfo, "entry-team-card");
    await card.getByRole("button", { name: "召唤游戏开发工作室" }).click();

    await expect(page.getByRole("dialog", { name: "游戏开发工作室" })).toHaveCount(0);
    await expect(page.getByTestId("composer-dock")).toContainText("游戏开发工作室");
    await expect(page.getByRole("textbox")).toBeEmpty();
    await attachUiState(page, testInfo, "transition-team-selected-without-run");

    await expect(page.getByText(/^任务 \(\d+\)$/).first()).toHaveText(before);
    const types = await controlTypes(sidecarLog);
    expect(types).not.toContain("create_session");
    expect(types).not.toContain("user_message");
    expect(types).not.toContain("subscribe_subagent_streams");
    await attachUiState(page, testInfo, "final-team-no-session-no-member-stream");
  } finally {
    await cleanup(app, fixture.home);
  }
});

test("WB-TEAM-002 | 专家团详情召唤保留草稿且无会话成员栏", async ({}, testInfo) => {
  const fixture = await openFixture("team-draft-causality");
  let app: ElectronApplication | undefined = fixture.app;
  try {
    const { page, sidecarLog } = fixture;
    const composer = page.getByRole("textbox");
    await composer.fill("保留这段未发送的团队需求");
    const before = await taskCount(page);
    await page.getByRole("button", { name: "专家·技能·连接器", exact: true }).click();
    await page.getByRole("tab", { name: "专家团", exact: true }).click();
    await page.getByRole("button", { name: /游戏开发工作室.*由负责人统筹/ }).click();
    const detail = page.getByRole("dialog", { name: "游戏开发工作室" });
    await expect(detail).toContainText("团队成员");
    await attachUiState(page, testInfo, "entry-team-detail-with-draft");

    await detail.getByRole("button", { name: "召唤 游戏开发工作室" }).click();
    await expect(composer).toHaveValue("保留这段未发送的团队需求");
    await expect(page.getByTestId("composer-dock")).toContainText("游戏开发工作室");
    await attachUiState(page, testInfo, "transition-team-selected-draft-preserved");

    await expect(page.getByText(/^任务 \(\d+\)$/).first()).toHaveText(before);
    await expect(
      page.getByTestId("thread-message-list").getByText("保留这段未发送的团队需求", { exact: true }),
    ).toHaveCount(0);
    const types = await controlTypes(sidecarLog);
    expect(types).not.toContain("create_session");
    expect(types).not.toContain("user_message");
    expect(types).not.toContain("subscribe_subagent_streams");
    await attachUiState(page, testInfo, "final-team-no-session-no-member-workspace");
  } finally {
    await cleanup(app, fixture.home);
  }
});
