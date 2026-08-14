#!/usr/bin/env node

import { spawn } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { loadPrivateCaseAuthority, resolvePrivateRunRoot } from "./private-case-authority.mjs";
import { requireFromProject } from "./project-require.mjs";

const { parse: parseYaml } = requireFromProject("yaml");
const scriptRoot = path.dirname(fileURLToPath(import.meta.url));
const skillRoot = path.resolve(scriptRoot, "..");
const args = parseArgs(process.argv.slice(2));
const repo = path.resolve(args.repo || process.cwd());
const skillEntry = path.join(repo, ".agents/skills/qwork-test-dataset");
if (await fs.realpath(skillEntry) !== skillRoot) throw new Error("QWork Dataset Skill entry mismatch");
if (!args["run-group"]) throw new Error("--run-group is required");
const groupRoot = await resolvePrivateRunRoot({
  skillEntry,
  skillRoot,
  cwd: process.cwd(),
  value: args["run-group"],
});
const matrixPath = path.join(groupRoot, "matrix-report.json");
if (await exists(groupRoot)) throw new Error(`private reference matrix already exists: ${groupRoot}`);
await fs.mkdir(path.join(groupRoot, "_batch-logs"), { recursive: true });

const registry = parseYaml(await fs.readFile(path.join(skillRoot, "references/private-reference-runs.yaml"), "utf8"));
const coordinates = [];
for (const [expected, records] of [["pass", registry.runs], ["fail", registry.failed_runs]]) {
  for (const [caseId, reference] of Object.entries(records || {})) {
    const casePath = path.join(skillRoot, "data/datasets/cases", `${caseId}.json`);
    const record = JSON.parse(await fs.readFile(casePath, "utf8"));
    await loadPrivateCaseAuthority({ skillRoot, repo, caseId, title: record.title });
    coordinates.push({ case_id: caseId, title: record.title, expected, required_screenshot_states: reference.required_screenshot_states });
  }
}
coordinates.sort((left, right) => left.case_id.localeCompare(right.case_id));

const matrix = {
  schema_version: 1,
  status: "running",
  started_at: new Date().toISOString(),
  finished_at: null,
  repo,
  source_revision: await git("rev-parse", "HEAD"),
  zero_real_model_calls: true,
  coordinate_count: coordinates.length,
  results: [],
};
await checkpoint();

for (const coordinate of coordinates) {
  const runRoot = path.join(groupRoot, coordinate.case_id);
  const stdoutPath = path.join(groupRoot, "_batch-logs", `${coordinate.case_id}.stdout.log`);
  const stderrPath = path.join(groupRoot, "_batch-logs", `${coordinate.case_id}.stderr.log`);
  const execution = await run(process.execPath, [
    path.join(scriptRoot, "run_private_playwright_case.mjs"),
    "--repo", repo,
    "--case-id", coordinate.case_id,
    "--case-title", coordinate.title,
    "--run-root", runRoot,
  ]);
  await Promise.all([
    fs.writeFile(stdoutPath, execution.stdout, "utf8"),
    fs.writeFile(stderrPath, execution.stderr, "utf8"),
  ]);
  const reportPath = path.join(runRoot, "report.json");
  if (!(await exists(reportPath))) await fatal(coordinate, `runner produced no report (exit ${execution.code})`);
  const report = JSON.parse(await fs.readFile(reportPath, "utf8"));
  const screenshots = report.evidence?.screenshots || [];
  const integrityErrors = [];
  if (report.case_id !== coordinate.case_id || report.case_title !== coordinate.title) integrityErrors.push("Case identity mismatch");
  if (report.status !== coordinate.expected) integrityErrors.push(`expected ${coordinate.expected}, observed ${report.status}`);
  if (report.evidence?.integrity !== "complete") integrityErrors.push(...(report.evidence?.integrity_errors || ["evidence incomplete"]));
  if ((report.evidence?.traces || []).length !== 1) integrityErrors.push("trace count is not one");
  if (await exists(path.join(runRoot, "app"))) integrityErrors.push("transient app assembly was retained");
  for (const state of coordinate.required_screenshot_states) {
    if (!screenshots.some((item) => String(item.path || "").includes(state))) integrityErrors.push(`missing screenshot state ${state}`);
  }
  if (integrityErrors.length) await fatal(coordinate, integrityErrors.join("; "));
  matrix.results.push({
    ...coordinate,
    observed: report.status,
    runner_exit_code: execution.code,
    report: `skill://qwork-test-dataset/${path.relative(skillRoot, reportPath).split(path.sep).join("/")}`,
    report_sha256: `sha256:${await sha256(reportPath)}`,
    stdout_sha256: `sha256:${await sha256(stdoutPath)}`,
    stderr_sha256: `sha256:${await sha256(stderrPath)}`,
  });
  await checkpoint();
  process.stdout.write(`${JSON.stringify({ completed: matrix.results.length, total: coordinates.length, case_id: coordinate.case_id, status: report.status })}\n`);
}
matrix.status = "complete";
matrix.finished_at = new Date().toISOString();
await checkpoint();
process.stdout.write(`${JSON.stringify({ status: matrix.status, results: matrix.results.length, report: matrixPath })}\n`);

async function fatal(coordinate, reason) {
  matrix.status = "fatal";
  matrix.finished_at = new Date().toISOString();
  matrix.fatal = { case_id: coordinate.case_id, reason };
  await checkpoint();
  throw new Error(`${coordinate.case_id}: ${reason}`);
}

async function checkpoint() {
  const temp = `${matrixPath}.tmp`;
  await fs.writeFile(temp, `${JSON.stringify(matrix, null, 2)}\n`, "utf8");
  await fs.rename(temp, matrixPath);
}

function parseArgs(argv) {
  const values = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) throw new Error(`invalid arguments near ${key}`);
    values[key.slice(2)] = value;
  }
  return values;
}

async function exists(value) {
  try { await fs.lstat(value); return true; } catch (error) {
    if (error.code === "ENOENT") return false;
    throw error;
  }
}

async function sha256(value) {
  return crypto.createHash("sha256").update(await fs.readFile(value)).digest("hex");
}

function git(...gitArgs) {
  return run("git", gitArgs).then(({ code, stdout, stderr }) => {
    if (code !== 0) throw new Error(stderr || `git exited ${code}`);
    return stdout.trim();
  });
}

function run(command, commandArgs) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, commandArgs, { cwd: repo, env: process.env, stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.once("error", reject);
    child.once("exit", (code, signal) => resolve({ code: code ?? 1, signal, stdout, stderr }));
  });
}
