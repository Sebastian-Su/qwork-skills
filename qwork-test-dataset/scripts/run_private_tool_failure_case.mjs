#!/usr/bin/env node

import { spawn } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const scriptRoot = path.dirname(fileURLToPath(import.meta.url));
const skillRoot = path.resolve(scriptRoot, "..");
const args = process.argv.slice(2);
const values = Object.fromEntries(Array.from({ length: args.length / 2 }, (_, index) => [args[index * 2].replace(/^--/, ""), args[index * 2 + 1]]));
const repo = path.resolve(values.repo || process.cwd());
const runRoot = path.resolve(values["run-root"] || "");
const relative = path.relative(skillRoot, runRoot);
if (!values["run-root"] || !relative || relative.startsWith("..") || path.isAbsolute(relative)) throw new Error("--run-root must be inside the private Dataset Skill");

const child = spawn(process.execPath, [path.join(scriptRoot, "run_private_playwright_case.mjs"), ...args], { cwd: repo, env: process.env, stdio: ["ignore", "pipe", "pipe"] });
let stdout = "";
let stderr = "";
child.stdout.on("data", (chunk) => { stdout += chunk; });
child.stderr.on("data", (chunk) => { stderr += chunk; });
const code = await new Promise((resolve, reject) => { child.once("error", reject); child.once("exit", (value) => resolve(value ?? 1)); });
if (code !== 0) {
  process.stderr.write(stderr);
  process.stdout.write(stdout);
  process.exitCode = code;
} else {
  const reportPath = path.join(runRoot, "report.json");
  const report = JSON.parse(await fs.readFile(reportPath, "utf8"));
  const files = [
    ["skill://qwork-test-dataset/data/e2e/fixtures/launch-tool-failure-isolated.ts", path.join(skillRoot, "data/e2e/fixtures/launch-tool-failure-isolated.ts")],
    ["skill://qwork-test-dataset/data/e2e/fixtures/tool-failure-sidecar.mjs", path.join(skillRoot, "data/e2e/fixtures/tool-failure-sidecar.mjs")],
    ["skill://qwork-test-dataset/scripts/run_private_tool_failure_case.mjs", path.join(scriptRoot, "run_private_tool_failure_case.mjs")],
    ["skill://qwork-test-dataset/scripts/run_private_playwright_case.mjs", path.join(scriptRoot, "run_private_playwright_case.mjs")],
    ["skill://qwork-test-dataset/scripts/build_isolated_electron.mjs", path.join(scriptRoot, "build_isolated_electron.mjs")],
    ["skill://qwork-test-dataset/scripts/electron-isolated-build.config.ts", path.join(scriptRoot, "electron-isolated-build.config.ts")],
    ["skill://qwork-test-dataset/scripts/playwright-private.config.ts", path.join(scriptRoot, "playwright-private.config.ts")],
    ["repo://e2e/fixtures/workbuddy-ui.ts", path.join(repo, "e2e/fixtures/workbuddy-ui.ts")],
  ];
  report.deterministic_sidecar = "skill://qwork-test-dataset/data/e2e/fixtures/tool-failure-sidecar.mjs";
  report.authority.files = await Promise.all(files.map(async ([locator, file]) => ({ locator, sha256: `sha256:${crypto.createHash("sha256").update(await fs.readFile(file)).digest("hex")}` })));
  await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`);
  process.stderr.write(stderr);
  process.stdout.write(`${JSON.stringify({ status: report.status, report: reportPath })}\n`);
}
