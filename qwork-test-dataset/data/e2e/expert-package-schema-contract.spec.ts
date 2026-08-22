import { expect, test, type ElectronApplication } from "@playwright/test";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { installBundledExpertPackages } from "../../../../../src/main/experts/bundledExpertPackages";
import { parseExpertPackageManifest } from "../../../../../src/main/experts/expertPackages";
import { attachUiState } from "../../../../../e2e/fixtures/ui-contract";
import { cleanup, createTestHome, createWorkspace, openApp } from "./fixtures/launch-isolated";
import { validExpertManifest, writeExpertPackage } from "./fixtures/expert-package";

test("PKG-SCHEMA-001 | 只接受 ziqdo-plugin v1 严格清单并拒绝 WorkBuddy 原始 JSON", async () => {
  expect(() => parseExpertPackageManifest(validExpertManifest())).not.toThrow();
  expect(() => parseExpertPackageManifest({
    name: "WorkBuddy 原始专家",
    version: "1.0.0",
    agents: ["agents/expert.md"],
  })).toThrow();
  expect(() => parseExpertPackageManifest({
    ...validExpertManifest(),
    workbuddyRuntimeState: { running: true },
  })).toThrow(/unknown field/i);
  expect(() => parseExpertPackageManifest({
    ...validExpertManifest(),
    specVersion: "2.0",
  })).toThrow(/specVersion/i);
  expect(parseExpertPackageManifest(validExpertManifest("package-version-independent", {
    package: { id: "package-version-independent", version: "99.7.3", publisher: "qwork" },
  })).specVersion).toBe("1.0");
});

test("PKG-SCHEMA-002 | identity roster principal 与未知字段形成闭世界校验", async () => {
  expect(() => parseExpertPackageManifest(validExpertManifest("individual", {
    roster: [{ id: "member", agent: "agents/member.md", responsibility: "成员" }],
  }))).toThrow(/individual/i);

  const collective = validExpertManifest("collective", {
    identity: { kind: "collective", name: "契约团队", summary: "验证团队清单" },
    roster: [
      { id: "member", agent: "agents/member.md", responsibility: "成员一" },
      { id: "member", agent: "agents/member-2.md", responsibility: "成员二" },
    ],
    modelPolicy: { principal: "inherit", members: { member: "balanced" } },
  });
  expect(() => parseExpertPackageManifest(collective)).toThrow(/unique/i);

  expect(() => parseExpertPackageManifest({
    ...validExpertManifest(),
    package: { id: "contract-expert", version: "1.0.0", publisher: "qwork", extra: true },
  })).toThrow(/unknown field/i);

  const root = await fs.mkdtemp(path.join(os.tmpdir(), "qwork-private-missing-principal-"));
  try {
    const bundled = path.join(root, "bundled");
    const source = path.join(bundled, "missing-principal");
    await writeExpertPackage(source, validExpertManifest("missing-principal"));
    await fs.rm(path.join(source, "agents", "missing-principal.md"));
    await expect(installBundledExpertPackages(path.join(root, "state"), bundled)).rejects.toThrow();
  } finally {
    await fs.rm(root, { recursive: true, force: true });
  }
});

test("PKG-SCHEMA-003 | 资源路径留在包根且模型策略只允许四个抽象档位", async () => {
  for (const candidate of ["/tmp/avatar.png", "../avatar.png", "assets//avatar.png"]) {
    expect(() => parseExpertPackageManifest(validExpertManifest("path-expert", {
      presentation: { avatar: candidate, category: "测试", tags: [] },
    }))).toThrow(/package root/i);
  }
  for (const profile of ["inherit", "reasoning", "balanced", "fast"]) {
    expect(parseExpertPackageManifest(validExpertManifest("model-expert", {
      modelPolicy: { principal: profile, members: {} },
    })).modelPolicy.principal).toBe(profile);
  }
  expect(() => parseExpertPackageManifest(validExpertManifest("vendor-model", {
    modelPolicy: { principal: "qwen-max", members: {} },
  }))).toThrow(/supported model profile/i);
});

test("PKG-PRESENTATION-001 | author 缺失时 UI 回退 publisher 且 presentation 不改变权限", async ({}, testInfo) => {
  const home = await createTestHome("expert-author-fallback");
  await createWorkspace(home);
  const installPath = path.join(home, "plugins", "marketplaces", "experts", "plugins", "author-fallback");
  const manifest = validExpertManifest("author-fallback", {
    package: { id: "author-fallback", version: "1.0.0", publisher: "可信发布方" },
    identity: { kind: "individual", name: "作者回退专家", summary: "作者缺失时展示发布方" },
    presentation: { category: "测试", tags: ["作者"] },
  });
  await writeExpertPackage(installPath, manifest);
  await fs.mkdir(path.join(home, "plugins"), { recursive: true });
  await fs.writeFile(path.join(home, "plugins", "installed_plugins.json"), `${JSON.stringify({
    version: 2,
    plugins: {
      "author-fallback@experts": [{ scope: "user", version: "1.0.0", installPath }],
    },
  })}\n`);
  let app: ElectronApplication | undefined;
  try {
    const opened = await openApp(home);
    app = opened.app;
    await attachUiState(opened.page, testInfo, "entry");
    await opened.page.getByRole("button", { name: "专家·技能·连接器", exact: true }).click();
    const card = opened.page.getByRole("listitem").filter({ hasText: "作者回退专家" });
    await expect(card).toBeVisible();
    await attachUiState(opened.page, testInfo, "transition");
    await expect(card).toContainText("可信发布方");
    await attachUiState(opened.page, testInfo, "final-state");
    const experts = await opened.page.evaluate(() => window.workGui.experts.list());
    const expert = experts.find((item) => item.key === "author-fallback@experts");
    expect(expert).toMatchObject({ publisher: "可信发布方" });
    expect(expert).not.toHaveProperty("author");
    expect(parseExpertPackageManifest(manifest)).toMatchObject({
      guardrails: { workspace: "session", permissionCeiling: "session" },
      capabilities: { skills: [], plugins: [], tools: [] },
    });
  } finally {
    await cleanup(app, home);
  }
});

test("PKG-SCHEMA-004 | coordination 是机器契约且 Agent Markdown 不能改写能力与调度", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "qwork-private-coordination-contract-"));
  try {
    const manifest = validExpertManifest("coordination-expert", {
      identity: { kind: "collective", name: "协调团队", summary: "机器协调契约" },
      roster: [{ id: "member", agent: "agents/member.md", responsibility: "成员" }],
      coordination: {
        activation: "on-demand",
        recommendedParallelism: 2,
        taskPolicy: "shared-board",
        questionPolicy: "lead-mediated",
      },
      modelPolicy: { principal: "inherit", members: { member: "balanced" } },
      capabilities: { skills: ["declared-skill"], plugins: [], tools: ["Read"] },
    });
    await writeExpertPackage(root, manifest);
    await fs.writeFile(path.join(root, "agents", "coordination-expert.md"), [
      "# 角色说明",
      "recommendedParallelism: 99",
      "permissionCeiling: full-access",
      "tools: [Bash]",
    ].join("\n"));
    const parsed = parseExpertPackageManifest(JSON.parse(await fs.readFile(path.join(root, "ziqdo-plugin.json"), "utf8")));
    expect(parsed).toMatchObject({
      coordination: { recommendedParallelism: 2, taskPolicy: "shared-board", questionPolicy: "lead-mediated" },
      capabilities: { skills: ["declared-skill"], plugins: [], tools: ["Read"] },
      guardrails: { workspace: "session", permissionCeiling: "session" },
    });
  } finally {
    await fs.rm(root, { recursive: true, force: true });
  }
});
