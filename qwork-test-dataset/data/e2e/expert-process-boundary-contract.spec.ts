import { expect, test } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../../../");

async function source(relative: string): Promise<string> {
  return fs.readFile(path.join(repo, relative), "utf8");
}

test("EXPERT-BOUNDARY-001 | Renderer 无 Node Electron 与 ipcRenderer 原语", async () => {
  const rendererRoot = path.join(repo, "src", "renderer");
  const files: string[] = [];
  const visit = async (dir: string): Promise<void> => {
    for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
      const candidate = path.join(dir, entry.name);
      if (entry.isDirectory()) await visit(candidate);
      else if (/\.[cm]?[jt]sx?$/u.test(entry.name)) files.push(candidate);
    }
  };
  await visit(rendererRoot);
  const violations: string[] = [];
  for (const file of files) {
    const content = await fs.readFile(file, "utf8");
    if (/from\s+["'](?:electron|node:)|require\(["'](?:electron|node:)|\bipcRenderer\b/u.test(content)) {
      violations.push(path.relative(repo, file));
    }
  }
  expect(violations).toEqual([]);
});

test("EXPERT-BOUNDARY-002 | 专家 IPC 同时具备共享契约 preload 白名单 main handler 与可信 sender", async () => {
  const [api, channels, preload, mainIpc, trustedHandler] = await Promise.all([
    source("src/shared/api.ts"),
    source("src/shared/channels.ts"),
    source("src/preload/index.ts"),
    source("src/main/ipc/index.ts"),
    source("src/main/ipc/trustedHandler.ts"),
  ]);
  for (const capability of ["expertList", "expertMarketState", "expertSetSort", "expertProjection"]) {
    expect(channels).toContain(`${capability}:`);
    expect(preload).toContain(`INVOKE.${capability}`);
    expect(mainIpc).toContain(`handle(INVOKE.${capability}`);
  }
  expect(api).toContain("experts: {");
  expect(mainIpc).toContain("registerTrustedHandler(");
  expect(trustedHandler).toContain("isTrustedSender");
});

test("EXPERT-BOUNDARY-003 | 文件边界在主进程最早校验工作区与 Expert Package 根", async () => {
  const [paths, runtime, filesystem] = await Promise.all([
    source("src/main/experts/expertPackagePaths.ts"),
    source("src/main/experts/expertRuntimeContract.ts"),
    source("src/main/filesystem.ts"),
  ]);
  expect(paths).toContain("resolveCanonicalExpertInstallPath");
  expect(paths).toContain("realpath");
  expect(runtime).toContain("containedRealPath");
  expect(filesystem).toMatch(/workspace|allowedRoot|root/i);
  expect(`${paths}\n${runtime}\n${filesystem}`).toMatch(/symbolic link|symlink|realpath/i);
});

test("EXPERT-BOUNDARY-004 | 专家会话要求 Runtime 明示 SessionStart 隐藏上下文能力", async () => {
  const [protocol, supervisor, providerOracle] = await Promise.all([
    source("src/shared/protocol.ts"),
    source("src/main/sidecar/SidecarSupervisor.ts"),
    source("src/main/experts/expertRuntimeContract.live.test.ts"),
  ]);

  expect(protocol).toContain("session_start_additional_context?: boolean");
  expect(supervisor).toContain('supportsCapability("session_start_additional_context")');
  expect(supervisor).toContain("未声明 SessionStart 专家身份上下文能力");
  expect(providerOracle).toContain('qwork_expert_identity package_id="douyin-strategist"');
  expect(providerOracle).toContain("expertIdentityCount: 1");
  expect(providerOracle).toContain("controlHasExpertIdentity: false");
  expect(providerOracle).toContain("controlHasDouyinIdentity: false");
});
