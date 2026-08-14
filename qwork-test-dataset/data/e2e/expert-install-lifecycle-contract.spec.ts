import { expect, test, type ElectronApplication } from "@playwright/test";
import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { installBundledExpertPackages } from "../../../../../src/main/experts/bundledExpertPackages";
import { canonicalExpertInstallPath } from "../../../../../src/main/experts/expertPackagePaths";
import { readSessionSelection, writeSessionSelection } from "../../../../../src/main/sidecar/sessionSelections";
import { cleanup, createTestHome, createWorkspace, openApp } from "./fixtures/launch-isolated";
import { validExpertManifest, writeExpertPackage } from "./fixtures/expert-package";

async function roots(prefix: string) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), `qwork-private-${prefix}-`));
  const stateHome = path.join(root, "state");
  const bundled = path.join(root, "bundled");
  await fs.mkdir(bundled, { recursive: true });
  return { root, stateHome, bundled };
}

test("PKG-INSTALL-001 | v2 注册表以 package@marketplace 和 user scope 指向唯一稳定路径", async () => {
  const fixture = await roots("install-registry");
  try {
    await writeExpertPackage(path.join(fixture.bundled, "stable-expert"), validExpertManifest("stable-expert"));
    await installBundledExpertPackages(fixture.stateHome, fixture.bundled, () => new Date("2026-08-14T00:00:00.000Z"));
    const registry = JSON.parse(await fs.readFile(path.join(fixture.stateHome, "plugins", "installed_plugins.json"), "utf8"));
    const installPath = canonicalExpertInstallPath(fixture.stateHome, "stable-expert@qwork-builtin");
    expect(registry).toMatchObject({
      version: 2,
      plugins: {
        "stable-expert@qwork-builtin": [{ scope: "user", version: "1.0.0", installPath }],
      },
    });
    expect(path.basename(installPath)).toBe("stable-expert");
    expect(installPath).not.toContain("1.0.0");
  } finally {
    await fs.rm(fixture.root, { recursive: true, force: true });
  }
});

test("PKG-INSTALL-002 | 更新经 staging 原子替换同一路径且不触发包内 Hook", async () => {
  const fixture = await roots("install-update");
  try {
    const source = path.join(fixture.bundled, "stable-update");
    await writeExpertPackage(source, validExpertManifest("stable-update"));
    const sentinel = path.join(fixture.root, "hook-ran.txt");
    await fs.mkdir(path.join(source, "hooks"), { recursive: true });
    await fs.writeFile(path.join(source, "hooks", "install.mjs"), `require('node:fs').writeFileSync(${JSON.stringify(sentinel)}, 'ran')`);
    await installBundledExpertPackages(fixture.stateHome, fixture.bundled);
    const stablePath = canonicalExpertInstallPath(fixture.stateHome, "stable-update@qwork-builtin");
    const next = validExpertManifest("stable-update", {
      package: { id: "stable-update", version: "2.0.0", publisher: "qwork-local" },
    });
    await writeExpertPackage(source, next);
    await installBundledExpertPackages(fixture.stateHome, fixture.bundled);
    expect(JSON.parse(await fs.readFile(path.join(stablePath, "ziqdo-plugin.json"), "utf8"))).toMatchObject({ package: { version: "2.0.0" } });
    expect(await fs.readdir(path.dirname(stablePath))).toEqual(["stable-update"]);
    await expect(fs.access(sentinel)).rejects.toThrow();
  } finally {
    await fs.rm(fixture.root, { recursive: true, force: true });
  }
});

test("PKG-INSTALL-003 | data 与安装树隔离且安装失败不改变活动版本", async () => {
  const fixture = await roots("install-rollback");
  try {
    const source = path.join(fixture.bundled, "rollback-expert");
    await writeExpertPackage(source, validExpertManifest("rollback-expert"));
    await installBundledExpertPackages(fixture.stateHome, fixture.bundled);
    const stablePath = canonicalExpertInstallPath(fixture.stateHome, "rollback-expert@qwork-builtin");
    const before = createHash("sha256").update(await fs.readFile(path.join(stablePath, "ziqdo-plugin.json"))).digest("hex");
    const dataFile = path.join(fixture.stateHome, "data", "rollback-expert", "state.json");
    await fs.mkdir(path.dirname(dataFile), { recursive: true });
    await fs.writeFile(dataFile, "{\"owned\":\"runtime\"}\n");
    await fs.rm(path.join(source, "agents", "rollback-expert.md"));
    await expect(installBundledExpertPackages(fixture.stateHome, fixture.bundled)).rejects.toThrow();
    const after = createHash("sha256").update(await fs.readFile(path.join(stablePath, "ziqdo-plugin.json"))).digest("hex");
    expect(after).toBe(before);
    expect(await fs.readFile(dataFile, "utf8")).toBe("{\"owned\":\"runtime\"}\n");
  } finally {
    await fs.rm(fixture.root, { recursive: true, force: true });
  }
});

test("PKG-PIN-001 | 会话以 expertKey 加版本与树哈希 pin 恢复时拒绝静默漂移", async () => {
  const fixture = await roots("session-pin");
  try {
    await writeSessionSelection(fixture.stateHome, "session-pin", {
      plugins: [],
      skills: [],
      expertKey: "stable-expert@experts",
      expertVersion: "1.0.0",
      expertTreeSha256: "a".repeat(64),
    } as never);
    const selected = await readSessionSelection(fixture.stateHome, "session-pin") as unknown as Record<string, unknown>;
    expect(selected).toMatchObject({
      expertKey: "stable-expert@experts",
      expertVersion: "1.0.0",
      expertTreeSha256: "a".repeat(64),
    });
  } finally {
    await fs.rm(fixture.root, { recursive: true, force: true });
  }
});

test("PKG-INSTALL-004 | 内置包与本地目录导入共用 Marketplace 注册契约", async () => {
  const home = await createTestHome("local-expert-import");
  await createWorkspace(home);
  const source = path.join(home, "local-source", "local-import-expert");
  await writeExpertPackage(source, validExpertManifest("local-import-expert", {
    identity: { kind: "individual", name: "本地导入专家", summary: "本地目录导入契约" },
  }));
  let app: ElectronApplication | undefined;
  try {
    const opened = await openApp(home);
    app = opened.app;
    const imported = await opened.page.evaluate(async (localSource) => {
      const experts = window.workGui.experts as unknown as {
        installLocal(source: string): Promise<{ key: string; installPath: string }>;
      };
      return experts.installLocal(localSource);
    }, source);
    expect(imported.key).toBe("local-import-expert@local");
    expect(imported.installPath).toBe(canonicalExpertInstallPath(home, imported.key));
    const registry = JSON.parse(await fs.readFile(path.join(home, "plugins", "installed_plugins.json"), "utf8"));
    expect(registry.plugins[imported.key]).toEqual([
      expect.objectContaining({ scope: "user", installPath: imported.installPath }),
    ]);
    expect(await opened.page.evaluate(() => window.workGui.experts.list())).toEqual(
      expect.arrayContaining([expect.objectContaining({ key: imported.key })]),
    );
  } finally {
    await cleanup(app, home);
  }
});
