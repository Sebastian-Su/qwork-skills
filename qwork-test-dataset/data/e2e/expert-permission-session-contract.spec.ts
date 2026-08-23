import { expect, test, type ElectronApplication } from "@playwright/test";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { AskUserQuestionRepository } from "../../../../../src/main/experts/AskUserQuestionRepository";
import { parseExpertPackageManifest } from "../../../../../src/main/experts/expertPackages";
import { resolveCanonicalExpertInstallPath } from "../../../../../src/main/experts/expertPackagePaths";
import { cleanup, createTestHome, createWorkspace, openApp } from "./fixtures/launch-isolated";
import { validExpertManifest } from "./fixtures/expert-package";

test("TEAM-PERMISSION-001 | Permission Ceiling 只能收窄且成员共享工作区与符号链接边界", async () => {
  expect(() => parseExpertPackageManifest(validExpertManifest("unsafe-permission", {
    guardrails: { workspace: "session", permissionCeiling: "full-access" },
  }))).toThrow(/permissionCeiling/i);
  expect(() => parseExpertPackageManifest(validExpertManifest("unsafe-workspace", {
    guardrails: { workspace: "outside-session", permissionCeiling: "session" },
  }))).toThrow(/workspace/i);

  const root = await fs.mkdtemp(path.join(os.tmpdir(), "qwork-private-symlink-boundary-"));
  try {
    const canonicalRoot = path.join(root, "plugins", "marketplaces", "experts", "plugins");
    const outside = path.join(root, "outside");
    await fs.mkdir(canonicalRoot, { recursive: true });
    await fs.mkdir(outside, { recursive: true });
    const linked = path.join(canonicalRoot, "linked-expert");
    await fs.symlink(outside, linked, "dir");
    await expect(resolveCanonicalExpertInstallPath(root, "linked-expert@experts", linked)).rejects.toThrow(/non-canonical/i);
  } finally {
    await fs.rm(root, { recursive: true, force: true });
  }
});

test("TEAM-PERMISSION-002 | 权限响应消息不携带凭据令牌", async () => {
  const home = await createTestHome("permission-no-token");
  await createWorkspace(home);
  const sidecarLog = path.join(home, "sidecar-control.jsonl");
  let app: ElectronApplication | undefined;
  try {
    const opened = await openApp(home, { E2E_SIDECAR_CONTROL_LOG: sidecarLog });
    app = opened.app;
    await opened.page.getByRole("button", { name: "新建任务", exact: true }).click();
    const composer = opened.page.getByPlaceholder(/今天帮你做些什么/);
    await composer.fill("__E2E_PERMISSION__:WriteFile");
    await composer.press("Enter");
    const dialog = opened.page.getByRole("region", { name: "权限询问" });
    await dialog.getByRole("button", { name: "允许", exact: true }).click();
    await expect(opened.page.getByText("permission:allowed:once", { exact: true })).toBeVisible();
    const messages = (await fs.readFile(sidecarLog, "utf8")).split("\n").filter(Boolean).map((line) => JSON.parse(line));
    const response = messages.find((item) => item.type === "permission_response");
    expect(response).toMatchObject({ decision: { decision: "allow", scope: "once" } });
    expect(JSON.stringify(response)).not.toMatch(/access[_-]?token|credential|api[_-]?key|secret/i);
  } finally {
    await cleanup(app, home);
  }
});

test("TEAM-ASKUSER-001 | Lead 问题去重排序且同一会话最多一个活动批次", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "qwork-private-ask-batch-"));
  try {
    const repository = new AskUserQuestionRepository(root);
    const event = (id: string, question: string) => ({
      kind: "tool_call",
      session_id: "team-session",
      tool_id: id,
      name: "AskUserQuestion",
      status: "started",
      input: { question, options: ["A", "B"] },
    });
    await repository.record(event("ask-2", "第二个问题"));
    await repository.record(event("ask-1", "第一个问题"));
    await repository.record(event("ask-1", "重复问题不得形成新卡"));
    const pending = await repository.pending("team-session");
    expect(pending).toHaveLength(1);
    expect(pending[0]).toMatchObject({ id: "ask-1", prompt: "第一个问题" });
    await repository.resolve("team-session", "ask-1", { action: "answer", text: "A" });
    expect(await repository.pending("team-session")).toEqual([
      expect.objectContaining({ id: "ask-2", prompt: "第二个问题" }),
    ]);
  } finally {
    await fs.rm(root, { recursive: true, force: true });
  }
});

test("TEAM-SESSION-DELETE-001 | 删除会话清理专家选择与 Team Projection 但保留安装包", async () => {
  const home = await createTestHome("delete-expert-session");
  await createWorkspace(home);
  let app: ElectronApplication | undefined;
  try {
    const opened = await openApp(home);
    app = opened.app;
    await opened.page.getByRole("button", { name: "新建任务", exact: true }).click();
    const composer = opened.page.getByPlaceholder(/今天帮你做些什么/);
    await composer.fill("创建待删除会话");
    await composer.press("Enter");
    await expect
      .poll(() => opened.page.evaluate(() => window.workGui.sessions.list()))
      .not.toHaveLength(0);
    const sessions = await opened.page.evaluate(() => window.workGui.sessions.list());
    const sessionId = String(sessions[0]?.session_id ?? "");
    expect(sessionId).not.toBe("");
    const packagePath = path.join(home, "plugins", "cache", "qwork-builtin", "senior-developer");
    await fs.access(packagePath);
    const projectionFile = path.join(home, "work-gui", "team-projections", `${encodeURIComponent(sessionId)}.json`);
    await fs.mkdir(path.dirname(projectionFile), { recursive: true });
    await fs.writeFile(projectionFile, `${JSON.stringify({ version: 1, sessionId, runs: {} })}\n`);
    await opened.page.evaluate((id) => window.workGui.sessions.delete(id), sessionId);
    await expect(fs.access(projectionFile)).rejects.toThrow();
    const selection = JSON.parse(await fs.readFile(path.join(home, "work-gui-session-selections.json"), "utf8"));
    expect(selection).not.toHaveProperty(sessionId);
    await fs.access(packagePath);
  } finally {
    await cleanup(app, home);
  }
});
