import { expect, test, type ElectronApplication } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import {
  attachUiState,
  setContentSize,
  summonGameStudio,
} from "../../../../../e2e/fixtures/ui-contract";
import {
  cleanup,
  createTestHome,
  createWorkspace,
  openApp,
} from "./fixtures/launch-isolated";

test("WB-TEAM-009 | AskUser 只投影到 Lead 且 answer/skip 各回执一次", async ({}, testInfo) => {
  const home = await createTestHome("lead-ask-user-causality");
  await createWorkspace(home);
  const sidecarLog = path.join(home, "sidecar-control.jsonl");
  let app: ElectronApplication | undefined;
  try {
    const opened = await openApp(home, { E2E_SIDECAR_CONTROL_LOG: sidecarLog });
    app = opened.app;
    const page = opened.page;
    await setContentSize(app, page);
    const composer = await summonGameStudio(page);
    await page.evaluate(() => {
      const target = window as typeof window & { __privateAskEvents?: unknown[] };
      target.__privateAskEvents = [];
      window.workGui.events.onSessionEvent((event) => target.__privateAskEvents?.push(event));
    });
    await attachUiState(page, testInfo, "entry-team-lead-without-member-run");
    await composer.fill("__E2E_EXPERT_ASK__");
    await composer.press("Enter");

    const ask = page.getByRole("region", { name: "需要你的确认" });
    await expect(ask).toBeVisible();
    await expect(page.getByRole("button", { name: /游戏开发工作室.*负责人/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /发布运营|质量保障/ })).toHaveCount(0);
    await attachUiState(page, testInfo, "transition-lead-owned-question-visible");
    await ask.getByRole("radio", { name: "桌面端", exact: true }).check();
    await ask.getByRole("button", { name: "提交回答", exact: true }).click();
    await expect(page.getByText("已收到选择：桌面端", { exact: true })).toBeVisible();
    await expect(ask).toBeVisible();
    await ask.getByRole("button", { name: "跳过", exact: true }).click();
    await expect(page.getByText("已收到选择：", { exact: true })).toBeVisible();
    await attachUiState(page, testInfo, "final-answer-and-skip-returned-to-lead");

    const events = await page.evaluate(() => {
      const target = window as typeof window & { __privateAskEvents?: Array<Record<string, unknown>> };
      return target.__privateAskEvents ?? [];
    });
    const questions = events.filter((event) => event.kind === "ask_user_requested");
    expect(questions).toHaveLength(3);
    expect(events.some((event) => String(event.kind).startsWith("subagent_"))).toBe(false);
    expect(questions.every((event) => !event.thread_id && !event.agent_id)).toBe(true);

    const controls = (await fs.readFile(sidecarLog, "utf8"))
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line) as Record<string, unknown>);
    const replies = controls.filter(
      (message) => message.type === "user_message" && String(message.content).includes("<qwork_interaction_response"),
    );
    expect(replies).toHaveLength(2);
    expect(String(replies[0]?.content)).toContain('request_id="ask-e2e-1" action="answer"');
    expect(String(replies[1]?.content)).toContain('request_id="ask-e2e-2" action="skip"');
  } finally {
    await cleanup(app, home);
  }
});
