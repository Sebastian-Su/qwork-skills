#!/usr/bin/env node

import { spawn } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { loadPrivateCaseAuthority, resolvePrivateRunRoot } from "./private-case-authority.mjs";

const scriptRoot = path.dirname(fileURLToPath(import.meta.url));
const skillRoot = path.resolve(scriptRoot, "..");
const values = parseArgs(process.argv.slice(2));
const repo = path.resolve(values.repo || process.cwd());
const skillEntry = path.join(repo, ".agents/skills/qwork-test-dataset");
if (await fs.realpath(skillEntry) !== skillRoot) {
  throw new Error(`QWork Dataset Skill entry resolves to an unexpected entity: ${skillEntry}`);
}
const caseId = values["case-id"]?.trim();
const title = values["case-title"]?.trim();
if (!caseId) throw new Error("--case-id is required");
if (!title) throw new Error("--case-title is required");
if (!values["run-root"]) throw new Error("--run-root is required");
const runRoot = await resolvePrivateRunRoot({
  skillEntry,
  skillRoot,
  cwd: process.cwd(),
  value: values["run-root"],
});

const reportPath = path.join(runRoot, "report.json");
const buildManifestPath = path.join(runRoot, "build-manifest.json");
const rawReportPath = path.join(runRoot, "playwright-report.json");
const stderrPath = path.join(runRoot, "playwright.stderr.log");
const runtimeLogPath = path.join(runRoot, "electron-runtime.log");
const screenshotRoot = path.join(runRoot, "screenshots");
const resultRoot = path.join(runRoot, "playwright-results");
const { authorityFiles } = await loadPrivateCaseAuthority({ skillRoot, repo, caseId, title });
for (const artifact of [reportPath, buildManifestPath, rawReportPath, stderrPath, runtimeLogPath, screenshotRoot, resultRoot]) {
  if (await exists(artifact)) {
    throw new Error(`private E2E evidence already exists; audit before retry: ${artifact}`);
  }
}
await fs.mkdir(runRoot, { recursive: true });
await fs.writeFile(runtimeLogPath, "", "utf8");

await run(process.execPath, [
  path.join(scriptRoot, "build_isolated_electron.mjs"),
  repo,
  runRoot,
], { ...process.env }, false);

const appRoot = path.join(runRoot, "app");
const playwright = path.join(repo, "node_modules/.bin/playwright");
const config = path.join(skillEntry, "scripts/playwright-private.config.ts");
const startedAt = new Date().toISOString();
const execution = await run(playwright, [
  "test",
  "--config",
  config,
  "--grep",
  escapeRegex(title),
  "--reporter=json",
], {
  ...process.env,
  NODE_OPTIONS: preserveSymlinks(process.env.NODE_OPTIONS),
  DEBUG: playwrightDebug(process.env.DEBUG),
  ELECTRON_RUN_AS_NODE: undefined,
  QWORK_E2E_APP_ROOT: appRoot,
  QWORK_E2E_OUTPUT_DIR: resultRoot,
  WORKBUDDY_EVIDENCE_DIR: screenshotRoot,
  QWORK_E2E_RUNTIME_LOG: runtimeLogPath,
}, true);
await fs.writeFile(rawReportPath, execution.stdout, "utf8");
await fs.writeFile(stderrPath, execution.stderr, "utf8");
await fs.rm(appRoot, { recursive: true, force: true });
if (await exists(appRoot)) throw new Error(`private Electron app assembly cleanup failed: ${appRoot}`);

let playwrightReport;
try {
  playwrightReport = JSON.parse(execution.stdout);
} catch (error) {
  throw new Error(`Playwright did not emit a JSON report: ${error.message}`);
}
const observed = collectTests(playwrightReport.suites || []);
if (observed.length !== 1 || observed[0].title !== title) {
  throw new Error(`private Case must select exactly one test: ${JSON.stringify(observed)}`);
}
const screenshots = await artifacts(screenshotRoot, ".png", runRoot);
const traces = await artifacts(resultRoot, "trace.zip", runRoot);
const evidenceIntegrityErrors = [];
if (screenshots.length < 3) evidenceIntegrityErrors.push(`private Case must produce at least three state screenshots, found ${screenshots.length}`);
if (traces.length !== 1) evidenceIntegrityErrors.push(`private Case must produce one Playwright trace, found ${traces.length}`);
const buildManifest = JSON.parse(await fs.readFile(buildManifestPath, "utf8"));
const specFile = observed[0].file;
const privateE2eRoot = path.join(skillRoot, "data/e2e");
const specPath = path.resolve(privateE2eRoot, specFile || "");
const specRelative = path.relative(privateE2eRoot, specPath);
if (!specFile || !specRelative || specRelative.startsWith("..") || path.isAbsolute(specRelative)) {
  throw new Error(`selected test is outside the private Dataset E2E root: ${specFile}`);
}
const specLocator = `skill://qwork-test-dataset/data/e2e/${specRelative.split(path.sep).join("/")}`;
const report = {
  schema_version: 1,
  case_id: caseId,
  case_title: title,
  status: execution.code === 0 && observed[0].status === "expected" && evidenceIntegrityErrors.length === 0 ? "pass" : "fail",
  started_at: startedAt,
  finished_at: new Date().toISOString(),
  exit_code: execution.code,
  zero_real_model_calls: true,
  isolated_qwork_home: true,
  deterministic_sidecar: "repo://e2e/fixtures/fake-sidecar.mjs",
  source: {
    spec: specLocator,
    spec_sha256: `sha256:${await sha256(specPath)}`,
    implementation_revision: buildManifest.source_revision,
  },
  authority: {
    files: await Promise.all(authorityFiles.map(async ([locator, file]) => ({
      locator,
      sha256: `sha256:${await sha256(file)}`,
    }))),
  },
  selected_tests: observed,
  evidence: {
    integrity: evidenceIntegrityErrors.length === 0 ? "complete" : "incomplete",
    integrity_errors: evidenceIntegrityErrors,
    build_manifest: { path: "build-manifest.json", sha256: `sha256:${await sha256(buildManifestPath)}` },
    playwright_report: { path: "playwright-report.json", sha256: `sha256:${await sha256(rawReportPath)}` },
    stderr: { path: "playwright.stderr.log", sha256: `sha256:${await sha256(stderrPath)}` },
    electron_runtime: {
      path: "electron-runtime.log",
      sha256: `sha256:${await sha256(runtimeLogPath)}`,
    },
    screenshots,
    traces,
  },
  cleanup: {
    case_owned_qwork_home_removed_by_fixture: true,
    app_process_closed_by_fixture: true,
    app_assembly_removed: true,
  },
};
await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
process.stdout.write(`${JSON.stringify({ status: report.status, report: reportPath })}\n`);
process.exitCode = report.status === "pass" ? 0 : 1;

function preserveSymlinks(value) {
  return `${value || ""} --preserve-symlinks`.trim();
}

function playwrightDebug(value) {
  return [value, "pw:browser*"].filter(Boolean).join(",");
}

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) throw new Error(`invalid arguments near ${key}`);
    result[key.slice(2)] = value;
  }
  return result;
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
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

async function artifacts(root, suffix, relativeTo) {
  if (!(await exists(root))) return [];
  const values = [];
  async function visit(current) {
    for (const entry of await fs.readdir(current, { withFileTypes: true })) {
      const target = path.join(current, entry.name);
      if (entry.isDirectory()) await visit(target);
      else if (entry.isFile() && entry.name.endsWith(suffix)) {
        values.push({ path: path.relative(relativeTo, target), sha256: `sha256:${await sha256(target)}` });
      }
    }
  }
  await visit(root);
  return values.sort((a, b) => a.path.localeCompare(b.path));
}

function collectTests(suites, prefix = []) {
  const values = [];
  for (const suite of suites) {
    const next = suite.title ? [...prefix, suite.title] : prefix;
    values.push(...collectTests(suite.suites || [], next));
    for (const spec of suite.specs || []) {
      for (const test of spec.tests || []) {
        const result = test.results?.at(-1);
        values.push({
          title: spec.title,
          file: spec.file || suite.file || null,
          path: [...next, spec.title].join(" > "),
          status: test.status,
          duration_ms: result?.duration ?? null,
        });
      }
    }
  }
  return values;
}

function run(command, args, env, capture) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: repo,
      env,
      stdio: capture ? ["ignore", "pipe", "pipe"] : "inherit",
    });
    let stdout = "";
    let stderr = "";
    child.stdout?.on("data", (chunk) => { stdout += chunk; });
    child.stderr?.on("data", (chunk) => { stderr += chunk; });
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (!capture && code !== 0) reject(new Error(`${command} exited with ${code ?? signal}`));
      else resolve({ code: code ?? 1, signal, stdout, stderr });
    });
  });
}
