import fs from "node:fs/promises";
import path from "node:path";

export function validExpertManifest(
  id = "contract-expert",
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    $schema: "https://ziqdo.dev/schemas/expert-package/v1.json",
    specVersion: "1.0",
    package: { id, version: "1.0.0", publisher: "qwork-local" },
    identity: { kind: "individual", name: "契约专家", summary: "验证专家包契约" },
    entrypoint: { principal: id },
    roster: [],
    coordination: {
      activation: "on-demand",
      recommendedParallelism: 1,
      taskPolicy: "shared-board",
      questionPolicy: "lead-mediated",
    },
    modelPolicy: { principal: "inherit", members: {} },
    capabilities: { skills: [], plugins: [], tools: [] },
    guardrails: { workspace: "session", permissionCeiling: "session" },
    presentation: { category: "测试", tags: ["契约"] },
    ...overrides,
  };
}

export async function writeExpertPackage(
  root: string,
  manifest: Record<string, unknown>,
): Promise<void> {
  const principal = String((manifest.entrypoint as { principal: string }).principal);
  await fs.mkdir(path.join(root, "agents"), { recursive: true });
  await fs.writeFile(path.join(root, "agents", `${principal}.md`), `# ${principal}\n`, "utf8");
  await fs.writeFile(
    path.join(root, "ziqdo-plugin.json"),
    `${JSON.stringify(manifest, null, 2)}\n`,
    "utf8",
  );
}
