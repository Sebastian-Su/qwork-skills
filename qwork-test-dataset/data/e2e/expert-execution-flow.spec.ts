import { expect, test, type ElectronApplication } from "@playwright/test";
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

const query = "请检查项目结构并给出风险和下一步建议";

test("WB-EXEC-002/003 + WB-EXPERT-005/006 | 专家真实事件依序形成思考、工具和最终总结", async ({}, testInfo) => {
  const home = await createTestHome("expert-execution-flow");
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
    await composer.fill(query);
    await composer.press("Enter");
    await expect(page.getByTestId("thread-message-list").getByText(query, { exact: true })).toBeVisible();
    await expect(page.getByRole("group", { name: "当前执行专家" })).toContainText("高级开发工程师");

    const thinking = page.getByRole("button", { name: /深度思考/ }).first();
    await expect(thinking).toBeVisible();
    await thinking.click();
    await expect(page.getByText("正在分析项目结构与验收目标", { exact: true })).toBeVisible();
    await attachUiState(page, testInfo, "entry-thinking-streaming");

    const tool = page.getByRole("button", { name: /读取项目文件.*执行中/ });
    await expect(tool).toBeVisible();
    await tool.click();
    await expect(page.getByTestId("tool-call-details")).toContainText("src/**/*");
    await attachUiState(page, testInfo, "transition-tool-running-with-input");

    await expect(page.getByText("已读取 12 个文件", { exact: true })).toBeVisible();
    await expect(
      page.getByText("分析完成：已核对项目结构、关键风险与下一步建议。", { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /已完成 \d+s/ })).toBeVisible();
    await expect(thinking).toBeVisible();
    const main = page.getByTestId("main-content");
    for (const action of ["复制", "赞", "踩", "朗读", "重试", "分享", "更多"]) {
      await expect(main.getByRole("button", { name: action, exact: true })).toBeVisible();
    }
    const controls = (await fs.readFile(sidecarLog, "utf8"))
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line) as Record<string, unknown>);
    const create = controls.find((message) => message.type === "create_session");
    expect(String(create?.model)).toMatch(/qwen3\.7-plus$/);
    const meta = page.getByTestId("turn-meta-footer");
    await expect(meta).toContainText("Qwen3.7-Plus");
    await expect(meta).toContainText(/共消耗/);
    await expect(composer).toBeEnabled();
    await attachUiState(page, testInfo, "final-expert-summary-actions-and-metadata");

    const prompts = controls.filter((message) => message.type === "user_message");
    expect(prompts).toHaveLength(1);
    expect(prompts[0]?.content).toBe(query);
    expect(JSON.stringify(prompts)).not.toMatch(/qwork_expert_identity|qwork_team_runtime/);
    expect(controls.filter((message) => message.type === "create_session")).toHaveLength(1);
  } finally {
    await cleanup(app, home);
  }
});
