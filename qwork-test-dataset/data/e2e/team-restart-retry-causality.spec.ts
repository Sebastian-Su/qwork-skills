import { expect, test, type ElectronApplication } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import { attachUiState, setContentSize, summonGameStudio } from "../../../../../e2e/fixtures/ui-contract";
import { cleanup, createTestHome, createWorkspace, openApp } from "./fixtures/launch-isolated";

test("WB-RECOVERY-002/003 | 重启将 running 成员转为 interrupted 且重试新实例关联旧实例", async ({}, testInfo) => {
  const home = await createTestHome("team-restart-retry");
  await createWorkspace(home);
  const sidecarLog = path.join(home, "sidecar-control.jsonl");
  let app: ElectronApplication | undefined;
  try {
    let opened = await openApp(home, { E2E_SIDECAR_CONTROL_LOG: sidecarLog });
    app = opened.app;
    let page = opened.page;
    await setContentSize(app, page);
    const composer = await summonGameStudio(page);
    await composer.fill("继续推进发布准备，等待我确认");
    await composer.press("Enter");
    const running = page.getByRole("button", { name: /发布运营.*运行中/ });
    await expect(running).toBeVisible();
    const before = await projection(page);
    expect(Object.keys(before?.runs ?? {})).toEqual(["team-release-retry"]);
    expect(before?.runs["team-release-retry"]?.status).toBe("running");
    await testInfo.attach("projection-before-restart.json", { body: Buffer.from(`${JSON.stringify(before, null, 2)}\n`), contentType: "application/json" });
    await attachUiState(page, testInfo, "entry-running-member-before-restart");

    await app.close();
    app = undefined;
    opened = await openApp(home, { E2E_SIDECAR_CONTROL_LOG: sidecarLog });
    app = opened.app;
    page = opened.page;
    await setContentSize(app, page);
    await page.getByRole("button", { name: "继续推进发布准备，等待我确认", exact: true }).click();
    const interrupted = page.getByRole("button", { name: /发布运营.*已中断/ });
    await expect(interrupted).toBeVisible();
    await interrupted.click();
    await expect(page.locator("article").getByText("已中断", { exact: true })).toBeVisible();
    await expect(page.getByText("等待用户确认", { exact: true })).toBeVisible();
    const afterRestart = await projection(page);
    expect(Object.keys(afterRestart?.runs ?? {})).toEqual(["team-release-retry"]);
    expect(afterRestart?.runs["team-release-retry"]?.status).toBe("interrupted");
    await testInfo.attach("projection-after-restart.json", { body: Buffer.from(`${JSON.stringify(afterRestart, null, 2)}\n`), contentType: "application/json" });
    await attachUiState(page, testInfo, "transition-old-instance-interrupted-not-completed");

    await page.getByRole("button", { name: "重试此成员任务" }).click();
    const completedRetry = page.getByRole("button", { name: /发布运营.*已完成/ });
    await expect(completedRetry).toBeVisible();
    await expect(interrupted).toBeVisible();
    const finalProjection = await projection(page);
    const runs = Object.values(finalProjection?.runs ?? {});
    expect(runs).toHaveLength(2);
    const oldRun = finalProjection?.runs["team-release-retry"];
    const newRun = runs.find((run) => run.threadId !== "team-release-retry");
    expect(oldRun?.status).toBe("interrupted");
    expect(newRun).toMatchObject({
      memberId: oldRun?.memberId,
      status: "completed",
      retryOf: "team-release-retry",
      text: "发布准备重试完成",
    });
    expect(newRun?.threadId).not.toBe(oldRun?.threadId);
    await testInfo.attach("projection-after-retry.json", { body: Buffer.from(`${JSON.stringify(finalProjection, null, 2)}\n`), contentType: "application/json" });
    const controls = (await fs.readFile(sidecarLog, "utf8")).split("\n").filter(Boolean).map((line) => JSON.parse(line) as Record<string, unknown>);
    const retryPrompts = controls.filter((message) => message.type === "user_message" && String(message.content).includes("<qwork_member_retry"));
    expect(retryPrompts).toHaveLength(1);
    expect(String(retryPrompts[0]?.content)).toContain('retry_of="team-release-retry"');
    await testInfo.attach("retry-control-message.json", { body: Buffer.from(`${JSON.stringify(retryPrompts, null, 2)}\n`), contentType: "application/json" });
    await attachUiState(page, testInfo, "final-old-and-new-instances-coexist-linked");
  } finally {
    await cleanup(app, home);
  }
});

async function projection(page: import("@playwright/test").Page) {
  return page.evaluate(async () => {
    const sessions = await window.workGui.sessions.list();
    const sessionId = sessions[0]?.session_id;
    const id = typeof sessionId === "string" ? sessionId : sessionId?.["0"];
    return id ? window.workGui.experts.projection(id) : null;
  });
}
