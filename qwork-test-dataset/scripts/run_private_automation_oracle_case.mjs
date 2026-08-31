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
const args = process.argv.slice(2);
const values = parseArgs(args);
const repo = path.resolve(values.repo || process.cwd());
const skillEntry = path.join(repo, ".agents/skills/qwork-test-dataset");
if (!values["run-root"]) throw new Error("--run-root is required");
const runRoot = await resolvePrivateRunRoot({
  skillEntry,
  skillRoot,
  cwd: process.cwd(),
  value: values["run-root"],
});

const result = await run(process.execPath, [path.join(scriptRoot, "run_private_playwright_case.mjs"), ...args]);
const reportPath = path.join(runRoot, "report.json");
const report = JSON.parse(await fs.readFile(reportPath, "utf8"));
const files = [
  ["skill://qwork-test-dataset/data/e2e/fixtures/launch-isolated.ts", path.join(skillRoot, "data/e2e/fixtures/launch-isolated.ts")],
  ["skill://qwork-test-dataset/scripts/run_private_automation_oracle_case.mjs", path.join(scriptRoot, "run_private_automation_oracle_case.mjs")],
  ["skill://qwork-test-dataset/scripts/run_private_playwright_case.mjs", path.join(scriptRoot, "run_private_playwright_case.mjs")],
  ["skill://qwork-test-dataset/scripts/build_isolated_electron.mjs", path.join(scriptRoot, "build_isolated_electron.mjs")],
  ["skill://qwork-test-dataset/scripts/electron-isolated-build.config.ts", path.join(scriptRoot, "electron-isolated-build.config.ts")],
  ["skill://qwork-test-dataset/scripts/playwright-private.config.ts", path.join(scriptRoot, "playwright-private.config.ts")],
  ["repo://e2e/fixtures/fake-sidecar.mjs", path.join(repo, "e2e/fixtures/fake-sidecar.mjs")],
  ["repo://e2e/fixtures/ui-contract.ts", path.join(repo, "e2e/fixtures/ui-contract.ts")],
  ["e2e/visual-baselines/automation-reference.json", path.join(repo, "e2e/visual-baselines/automation-reference.json")],
];
report.authority.files = await Promise.all(files.map(async ([locator, file]) => ({
  locator,
  sha256: `sha256:${crypto.createHash("sha256").update(await fs.readFile(file)).digest("hex")}`,
})));
await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
process.stderr.write(result.stderr);
process.stdout.write(`${JSON.stringify({ status: report.status, report: reportPath })}\n`);
process.exitCode = result.code;

function parseArgs(values) {
  const parsed = {};
  for (let index = 0; index < values.length; index += 2) {
    if (!values[index]?.startsWith("--") || values[index + 1] === undefined) throw new Error(`invalid arguments near ${values[index]}`);
    parsed[values[index].slice(2)] = values[index + 1];
  }
  return parsed;
}

function run(command, commandArgs) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, commandArgs, { cwd: repo, env: process.env, stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.once("error", reject);
    child.once("exit", (code) => resolve({ code: code ?? 1, stdout, stderr }));
  });
}
