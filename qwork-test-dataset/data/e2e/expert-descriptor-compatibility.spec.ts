import { expect, test } from "@playwright/test";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { loadExpertDescriptor } from "../../../../../src/main/experts/loadExpertDescriptor";
import { validExpertManifest } from "./fixtures/expert-package";

async function withPackage(files: Record<string, string>, check: (root: string) => Promise<void>) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "qwork-descriptor-contract-"));
  try {
    for (const [name, body] of Object.entries(files)) {
      const file = path.join(root, ...name.split("/"));
      await fs.mkdir(path.dirname(file), { recursive: true });
      await fs.writeFile(file, body);
    }
    await check(root);
  } finally {
    await fs.rm(root, { recursive: true, force: true });
  }
}

// Approved migration changes only the descriptor location, never installed artifact bytes.
// These filesystem contracts do not replace packaged Electron or live-team acceptance.
test("EXPERT-DESCRIPTOR-001 | 新包读取新目录且不生成旧清单", async () => {
  const body = JSON.stringify(validExpertManifest(), null, 2) + "\n";
  await withPackage({ ".qwork-plugin/plugin.json": body }, async (root) => {
    expect(await loadExpertDescriptor(root)).toMatchObject({ relativePath: ".qwork-plugin/plugin.json", value: JSON.parse(body) });
    expect(await fs.readFile(path.join(root, ".qwork-plugin", "plugin.json"), "utf8")).toBe(body);
    expect((await fs.readdir(root)).sort()).toEqual([".qwork-plugin"]);
  });
});

test("EXPERT-DESCRIPTOR-002 | 旧包只读回退且保留原字节和运行入口", async () => {
  const body = JSON.stringify(validExpertManifest(), null, 2) + "\n";
  const runtime = JSON.stringify({ name: "contract-expert", hooks: { SessionStart: [] } });
  await withPackage({ "ziqdo-plugin.json": body, "manifest.json": body, ".claude-plugin/plugin.json": runtime }, async (root) => {
    expect((await loadExpertDescriptor(root)).relativePath).toBe("ziqdo-plugin.json");
    expect(await fs.readFile(path.join(root, "ziqdo-plugin.json"), "utf8")).toBe(body);
    expect(await fs.readFile(path.join(root, "manifest.json"), "utf8")).toBe(body);
    expect(await fs.readFile(path.join(root, ".claude-plugin", "plugin.json"), "utf8")).toBe(runtime);
    await expect(fs.access(path.join(root, ".qwork-plugin"))).rejects.toMatchObject({ code: "ENOENT" });
  });
});

test("EXPERT-DESCRIPTOR-003 | 同内容优先新清单且冲突拒绝而不改写", async () => {
  const value = validExpertManifest();
  const current = JSON.stringify(value);
  const legacy = JSON.stringify(Object.fromEntries(Object.entries(value).reverse()), null, 2);
  await withPackage({ ".qwork-plugin/plugin.json": current, "ziqdo-plugin.json": legacy }, async (root) => {
    expect((await loadExpertDescriptor(root)).relativePath).toBe(".qwork-plugin/plugin.json");
    await fs.writeFile(path.join(root, "ziqdo-plugin.json"), "{}");
    await expect(loadExpertDescriptor(root)).rejects.toThrow(/conflict/);
    expect(await fs.readFile(path.join(root, ".qwork-plugin", "plugin.json"), "utf8")).toBe(current);
    expect(await fs.readFile(path.join(root, "ziqdo-plugin.json"), "utf8")).toBe("{}");
  });
});

test("EXPERT-DESCRIPTOR-004 | manifest 不独立启用且旧副本冲突不得绕过", async () => {
  const body = JSON.stringify(validExpertManifest());
  await withPackage({ "manifest.json": body }, async (root) => {
    await expect(loadExpertDescriptor(root)).rejects.toMatchObject({ code: "ENOENT" });
  });
  await withPackage({ "ziqdo-plugin.json": body, "manifest.json": "{}" }, async (root) => {
    await expect(loadExpertDescriptor(root)).rejects.toThrow(/conflict/);
  });
  await withPackage({ ".qwork-plugin/plugin.json": body, "manifest.json": "unrelated" }, async (root) => {
    expect((await loadExpertDescriptor(root)).relativePath).toBe(".qwork-plugin/plugin.json");
  });
});
