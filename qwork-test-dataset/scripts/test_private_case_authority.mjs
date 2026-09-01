#!/usr/bin/env node

import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { loadPrivateCaseAuthority, resolvePrivateRunRoot } from "./private-case-authority.mjs";

const root = await fs.mkdtemp(path.join(os.tmpdir(), "qwork-private-authority-"));
try {
  const skillRoot = path.join(root, "skill");
  const repo = path.join(root, "repo");
  await fs.mkdir(path.join(skillRoot, "data/datasets/cases"), { recursive: true });
  await fs.mkdir(path.join(skillRoot, "scripts"), { recursive: true });
  await fs.mkdir(path.join(repo, "e2e/fixtures"), { recursive: true });
  await fs.writeFile(path.join(skillRoot, "scripts/special.mjs"), "export {};\n");
  await fs.writeFile(path.join(repo, "e2e/fixtures/fake.mjs"), "export {};\n");
  await fs.writeFile(path.join(skillRoot, "data/datasets/cases/CASE-1.json"), JSON.stringify({
    id: "CASE-1",
    title: "special private route",
    execution_contract: {
      route_id: "qwork.private-playwright.special.1",
      observability: { source_contract: { supporting_contracts: [
        { path: "skill://qwork-test-dataset/scripts/special.mjs" },
        { path: "repo://e2e/fixtures/fake.mjs" },
      ] } },
    },
  }));
  const value = await loadPrivateCaseAuthority({ skillRoot, repo, caseId: "CASE-1", title: "special private route" });
  assert.deepEqual(value.authorityFiles.map(([locator]) => locator), [
    "skill://qwork-test-dataset/scripts/special.mjs",
    "repo://e2e/fixtures/fake.mjs",
  ]);
  const projectEntry = path.join(repo, ".agents/skills/qwork-test-dataset");
  const externalRoot = path.join(root, "QWORK-E2E-TEMPORARY-DATA-DO-NOT-COMMIT");
  await fs.mkdir(externalRoot);
  const runRoot = await resolvePrivateRunRoot({
    skillEntry: projectEntry,
    skillRoot,
    cwd: repo,
    value: path.join(externalRoot, "run-1"),
  });
  assert.equal(runRoot, path.join(await fs.realpath(externalRoot), "run-1"));
  await assert.rejects(
    resolvePrivateRunRoot({
      skillEntry: projectEntry,
      skillRoot,
      cwd: repo,
      value: path.join(skillRoot, "data/runs/run-1"),
    }),
    /protected Git or Skill root/,
  );
  for (const runner of [
    "run_private_team_terminal_case.mjs",
    "run_private_tool_failure_case.mjs",
    "run_private_automation_oracle_case.mjs",
    "run_private_sidebar_oracle_case.mjs",
  ]) {
    const content = await fs.readFile(new URL(`./${runner}`, import.meta.url), "utf8");
    assert.match(content, /resolvePrivateRunRoot/, `${runner} must use the shared run-root authority`);
    assert.doesNotMatch(
      content,
      /run root must be inside the private Dataset Skill/,
      `${runner} must not require mutable evidence inside the Skill`,
    );
  }
  console.log("private Case authority test: PASS");
} finally {
  await fs.rm(root, { recursive: true, force: true });
}
