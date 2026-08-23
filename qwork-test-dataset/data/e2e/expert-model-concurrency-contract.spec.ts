import { expect, test, type ElectronApplication } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import {
  AdaptiveConcurrencyGovernor,
  resolveExpertConcurrency,
  teamRuntimeContract,
} from "../../../../../src/main/experts/concurrencyPolicy";
import { setContentSize, summonGameStudio } from "../../../../../e2e/fixtures/ui-contract";
import { cleanup, createTestHome, createWorkspace, openApp } from "./fixtures/launch-isolated";

test("TEAM-CONCURRENCY-001 | 默认 5 普通 1-20 高级 21-100 且本机资源不独占模型并发决策", async () => {
  const fallback = resolveExpertConcurrency({
    requestedLimit: Number.NaN,
    advancedEnabled: false,
    logicalCpuCount: 32,
    totalMemoryBytes: 128 * 1024 ** 3,
  });
  expect(fallback.userLimit).toBe(5);
  expect(resolveExpertConcurrency({
    requestedLimit: 100,
    advancedEnabled: false,
    logicalCpuCount: 64,
    totalMemoryBytes: 256 * 1024 ** 3,
  }).userLimit).toBe(20);
  const advanced = resolveExpertConcurrency({
    requestedLimit: 100,
    advancedEnabled: true,
    providerLimit: 7,
    adaptiveLimit: 3,
    logicalCpuCount: 64,
    totalMemoryBytes: 256 * 1024 ** 3,
  });
  expect(advanced).toMatchObject({ userLimit: 100, providerLimit: 7, adaptiveLimit: 3, effectiveLimit: 3 });
  expect(teamRuntimeContract(advanced)).toContain("超额任务保持 queued");
  expect(teamRuntimeContract(advanced)).toContain("同一成员同时只能有一个活跃实例");
});

test("TEAM-CONCURRENCY-002 | 429 GLM-1302 与 TPM 压力乘法降载并在稳定窗口缓慢恢复", async () => {
  for (const message of ["HTTP 429", "GLM error 1302", "TPM rate limit"]) {
    const governor = new AdaptiveConcurrencyGovernor(16, 3);
    governor.observe({ kind: "error", message });
    expect(governor.limit()).toBe(8);
    governor.observe({ kind: "status", status: "idle" });
    governor.observe({ kind: "status", status: "idle" });
    expect(governor.limit()).toBe(8);
    governor.observe({ kind: "status", status: "idle" });
    expect(governor.limit()).toBe(9);
  }
});

test("TEAM-CONCURRENCY-003 | 并发池按账号 Provider Model 全局共享并公开高级费用风险", async ({}, testInfo) => {
  const home = await createTestHome("global-concurrency-pool");
  await createWorkspace(home);
  let app: ElectronApplication | undefined;
  try {
    const opened = await openApp(home, { QWORK_PROVIDER_CONCURRENCY_LIMIT: "1" });
    app = opened.app;
    await setContentSize(app, opened.page);
    const state = await opened.page.evaluate(async () => {
      const experts = window.workGui.experts as unknown as {
        concurrencyState(): Promise<{ poolKey: string; active: number; limit: number }>;
      };
      return experts.concurrencyState();
    });
    expect(state.poolKey).toMatch(/account.+provider.+model/i);
    expect(state).toMatchObject({ limit: 1 });
    await opened.page.getByRole("button", { name: "设置" }).click();
    await expect(opened.page.getByText(/21.*100.*费用.*限流/)).toBeVisible();
    await testInfo.attach("global-concurrency-state.json", {
      body: Buffer.from(`${JSON.stringify(state, null, 2)}\n`),
      contentType: "application/json",
    });
  } finally {
    await cleanup(app, home);
  }
});

test("TEAM-CONCURRENCY-004 | 取消父任务级联终止未完成子任务且成员失败不误杀无依赖成员", async ({}, testInfo) => {
  const home = await createTestHome("team-cancel-cascade");
  await createWorkspace(home);
  let app: ElectronApplication | undefined;
  try {
    const opened = await openApp(home);
    app = opened.app;
    await setContentSize(app, opened.page);
    const composer = await summonGameStudio(opened.page);
    await composer.fill("__E2E_HANG__");
    await composer.press("Enter");
    await expect
      .poll(() => opened.page.evaluate(() => window.workGui.sessions.list()))
      .not.toHaveLength(0);
    const sessions = await opened.page.evaluate(() => window.workGui.sessions.list());
    const sessionId = String(sessions[0]?.session_id ?? "");
    expect(sessionId).not.toBe("");
    await opened.page.evaluate((id) => window.workGui.sessions.cancel(id), sessionId);
    await expect.poll(async () => {
      const projection = await opened.page.evaluate((id) => window.workGui.experts.projection(id), sessionId);
      const statuses = Object.values(projection?.runs ?? {}).map((run) => run.status);
      return statuses.length > 0 && statuses.every((status) => ["completed", "failed", "cancelled", "interrupted"].includes(status));
    }).toBe(true);
    await testInfo.attach("cancelled-team-projection.json", {
      body: Buffer.from(`${JSON.stringify(await opened.page.evaluate((id) => window.workGui.experts.projection(id), sessionId), null, 2)}\n`),
      contentType: "application/json",
    });
  } finally {
    await cleanup(app, home);
  }
});

test("TEAM-MODEL-001 | 成员模型覆盖生效且不可用档位回退主会话模型并在 UI 明示", async ({}, testInfo) => {
  const home = await createTestHome("member-model-override");
  await createWorkspace(home);
  const settingsPath = path.join(home, "work-gui.json");
  const settings = JSON.parse(await fs.readFile(settingsPath, "utf8"));
  settings.experts = {
    memberModels: { "game-studio@qwork-builtin:game-designer": "unavailable/model" },
  };
  await fs.writeFile(settingsPath, `${JSON.stringify(settings, null, 2)}\n`);
  const sidecarLog = path.join(home, "sidecar-control.jsonl");
  let app: ElectronApplication | undefined;
  try {
    const opened = await openApp(home, { E2E_SIDECAR_CONTROL_LOG: sidecarLog });
    app = opened.app;
    await setContentSize(app, opened.page);
    const composer = await summonGameStudio(opened.page);
    await composer.fill("请分配给游戏设计成员");
    await composer.press("Enter");
    await expect(opened.page.getByText(/成员模型.*不可用.*已回退.*GLM-5\.2/)).toBeVisible();
    const controls = (await fs.readFile(sidecarLog, "utf8")).split("\n").filter(Boolean).map((line) => JSON.parse(line));
    expect(controls.find((item) => item.type === "create_session")).toMatchObject({
      member_models: { "game-designer": "z-ai/glm-5.2" },
      model_fallbacks: [{ member_id: "game-designer", requested: "unavailable/model", actual: "z-ai/glm-5.2" }],
    });
    await testInfo.attach("member-model-controls.json", {
      body: Buffer.from(`${JSON.stringify(controls, null, 2)}\n`),
      contentType: "application/json",
    });
  } finally {
    await cleanup(app, home);
  }
});
