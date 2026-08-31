#!/usr/bin/env node

import { spawn } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { resolvePrivateRunRoot } from "./private-case-authority.mjs";

const scriptRoot = path.dirname(fileURLToPath(import.meta.url));
const skillRoot = path.resolve(scriptRoot, "..");
const values = parseArgs(process.argv.slice(2));
const repo = path.resolve(values.repo || process.cwd());
const skillEntry = path.join(repo, ".agents/skills/qwork-test-dataset");
if (!values["run-root"]) throw new Error("--run-root is required");
const runRoot = await resolvePrivateRunRoot({
  skillEntry,
  skillRoot,
  cwd: process.cwd(),
  value: values["run-root"],
});

const result = await run(process.execPath, [
  path.join(scriptRoot, "run_private_playwright_case.mjs"),
  ...process.argv.slice(2),
]);
if (result.code !== 0) {
  process.stderr.write(result.stderr);
  process.stdout.write(result.stdout);
  process.exitCode = result.code;
} else {
  const reportPath = path.join(runRoot, "report.json");
  const report = JSON.parse(await fs.readFile(reportPath, "utf8"));
  const authorityFiles = [
    ["skill://qwork-test-dataset/data/e2e/fixtures/launch-team-terminal-isolated.ts", path.join(skillRoot, "data/e2e/fixtures/launch-team-terminal-isolated.ts")],
    ["skill://qwork-test-dataset/data/e2e/fixtures/team-terminal-sidecar.mjs", path.join(skillRoot, "data/e2e/fixtures/team-terminal-sidecar.mjs")],
    ["skill://qwork-test-dataset/scripts/run_private_team_terminal_case.mjs", path.join(scriptRoot, "run_private_team_terminal_case.mjs")],
    ["skill://qwork-test-dataset/scripts/run_private_playwright_case.mjs", path.join(scriptRoot, "run_private_playwright_case.mjs")],
    ["skill://qwork-test-dataset/scripts/build_isolated_electron.mjs", path.join(scriptRoot, "build_isolated_electron.mjs")],
    ["skill://qwork-test-dataset/scripts/electron-isolated-build.config.ts", path.join(scriptRoot, "electron-isolated-build.config.ts")],
    ["skill://qwork-test-dataset/scripts/playwright-private.config.ts", path.join(scriptRoot, "playwright-private.config.ts")],
    ["repo://e2e/fixtures/ui-contract.ts", path.join(repo, "e2e/fixtures/ui-contract.ts")],
  ];
  report.deterministic_sidecar = "skill://qwork-test-dataset/data/e2e/fixtures/team-terminal-sidecar.mjs";
  report.authority.files = await Promise.all(authorityFiles.map(async ([locator, file]) => ({
    locator,
    sha256: `sha256:${await sha256(file)}`,
  })));
  await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  process.stderr.write(result.stderr);
  process.stdout.write(`${JSON.stringify({ status: report.status, report: reportPath })}\n`);
}

function parseArgs(argv) {
  const values = {};
  for (let index = 0; index < argv.length; index += 2) {
    if (!argv[index]?.startsWith("--") || argv[index + 1] === undefined) throw new Error(`invalid arguments near ${argv[index]}`);
    values[argv[index].slice(2)] = argv[index + 1];
  }
  return values;
}

async function sha256(file) {
  return crypto.createHash("sha256").update(await fs.readFile(file)).digest("hex");
}

function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd: repo, env: process.env, stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.once("error", reject);
    child.once("exit", (code) => resolve({ code: code ?? 1, stdout, stderr }));
  });
}
