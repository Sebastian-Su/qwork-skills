#!/usr/bin/env node
/** Capture isolated QWork states corresponding to an explicitly frozen WorkBuddy UI Oracle. */
import crypto from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { requireFromProject } from "./project-require.mjs";

const { _electron: electron } = requireFromProject("@playwright/test");

const [repoArg, outputArg, requestedState, ...options] = process.argv.slice(2);
const workbuddyOption = options.indexOf("--workbuddy");
const workbuddyArg = workbuddyOption >= 0 ? options[workbuddyOption + 1] : undefined;
if (!repoArg || !outputArg || !requestedState || !workbuddyArg) {
  throw new Error(
    "usage: run_qwork_workbuddy_oracle.mjs <repo> <output> <state> --workbuddy <frozen-source>",
  );
}
const repo = path.resolve(repoArg);
const output = path.resolve(outputArg);
const workbuddyRoot = path.resolve(workbuddyArg);
const wbManifest = JSON.parse(await fs.readFile(path.join(workbuddyRoot, "manifest.json"), "utf8"));
const records = requestedState ? wbManifest.records.filter((item) => item.state === requestedState) : wbManifest.records;
if (!records.length) throw new Error(`unknown WorkBuddy state: ${requestedState}`);
await fs.mkdir(output, { recursive: true });
const configHome = await fs.mkdtemp(path.join(os.tmpdir(), "qwork-workbuddy-oracle-"));
const fakeSidecar = path.join(repo, "e2e/fixtures/fake-sidecar.mjs");
let app;
const results = [];
try {
  app = await electron.launch({
    args: [`--user-data-dir=${path.join(configHome, "electron-user-data")}`, repo],
    env: {
      ...process.env,
      ELECTRON_RUN_AS_NODE: undefined,
      ZIQDO_CONFIG_HOME: configHome,
      ZIQDO_BIN: process.execPath,
      ZIQDO_BIN_ARGS_PREFIX: JSON.stringify([fakeSidecar]),
      QWORK_ENV: "test",
      NODE_ENV: "test",
      QWORK_AUTH_BYPASS: "1",
      QWORK_PROJECT_ACCESS_TOKEN: "local-dev-token",
      WORK_GUI_E2E_SAFE_STORAGE_KEY: "qwork-private-workbuddy-oracle-v1",
      ELECTRON_DISABLE_SECURITY_WARNINGS: "true",
    },
  });
  const page = await app.firstWindow();
  page.setDefaultTimeout(8_000);
  await calibrateViewport(app, page, { width: 1680, height: 1084 });
  for (const record of records) {
    const stateDir = path.join(output, safe(record.state));
    await fs.mkdir(stateDir, { recursive: true });
    const result = { state: record.state, action: record.action, status: "pending", evidence: {} };
    try {
      await returnHome(page);
      result.evidence.entry = await capture(page, path.join(stateDir, "entry.png"), path.join(stateDir, "entry.json"));
      await navigate(page, record.state, record.action);
      result.evidence.transition = await capture(page, path.join(stateDir, "transition.png"), path.join(stateDir, "transition.json"));
      await page.waitForTimeout(250);
      result.evidence.final = await capture(page, path.join(stateDir, "final-state.png"), path.join(stateDir, "final-state.json"));
      result.status = "captured";
    } catch (error) {
      result.status = "navigation-failed";
      result.error = error instanceof Error ? error.message : String(error);
      result.evidence.failure = await capture(page, path.join(stateDir, "failure.png"), path.join(stateDir, "failure.json")).catch(() => null);
    }
    results.push(result);
  }
} finally {
  await app?.close().catch(() => undefined);
  await fs.rm(configHome, { recursive: true, force: true });
}
const manifest = {
  schema_version: 1,
  product: "QWork",
  compared_product: `WorkBuddy ${wbManifest.version}`,
  captured_at: new Date().toISOString(),
  repo_revision: (await import("node:child_process")).execFileSync("git", ["rev-parse", "HEAD"], { cwd: repo, encoding: "utf8" }).trim(),
  isolation: "temporary ZIQDO_CONFIG_HOME + deterministic fake sidecar; zero model calls",
  viewport_requested: { width: 1680, height: 1084 },
  state_count: results.length,
  captured_count: results.filter((item) => item.status === "captured").length,
  navigation_failed_count: results.filter((item) => item.status !== "captured").length,
  results,
};
await fs.writeFile(path.join(output, "capture-manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(JSON.stringify({ status: "ok", output, state_count: results.length, captured: manifest.captured_count, navigation_failed: manifest.navigation_failed_count }));

async function returnHome(page) {
  const button = page.getByRole("button", { name: "新建任务", exact: true });
  await button.waitFor({ state: "visible" });
  await button.click();
  await page.waitForTimeout(120);
}
async function calibrateViewport(app, page, desired) {
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]?.unmaximize());
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const actual = await page.evaluate(() => ({ width: innerWidth, height: innerHeight }));
    if (actual.width === desired.width && actual.height === desired.height) return;
    await app.evaluate(({ BrowserWindow }, values) => {
      const window = BrowserWindow.getAllWindows()[0];
      if (!window) return;
      const [contentWidth, contentHeight] = window.getContentSize();
      window.setContentSize(
        Math.max(1, contentWidth + values.width - values.actualWidth),
        Math.max(1, contentHeight + values.height - values.actualHeight),
      );
    }, { ...desired, actualWidth: actual.width, actualHeight: actual.height });
    await page.waitForTimeout(180);
  }
  const actual = await page.evaluate(() => ({ width: innerWidth, height: innerHeight }));
  throw new Error(`cannot calibrate renderer viewport to ${desired.width}x${desired.height}; got ${actual.width}x${actual.height}`);
}
async function navigate(page, state, action) {
  const top = {
    "surface-新建任务": "新建任务", "surface-助理": "助理", "surface-项目": "项目",
    "surface-专家-技能-连接器": "专家·技能·连接器", "surface-自动化": "自动化",
  }[state];
  if (top) {
    if (top !== "新建任务") await page.getByRole("button", { name: top, exact: true }).click();
    return;
  }
  if (state.startsWith("surface-market-")) {
    await page.getByRole("button", { name: "专家·技能·连接器", exact: true }).click();
    if (action.kind === "market-tab") await page.getByRole("tablist", { name: "专家中心内容" }).getByRole("tab", { name: action.label, exact: true }).click();
    if (action.kind === "expert-type") await page.getByRole("tablist", { name: "专家类型" }).getByRole("tab", { name: action.label, exact: true }).click();
    return;
  }
  if (state.startsWith("surface-automation-")) {
    await page.getByRole("button", { name: "自动化", exact: true }).click();
    await page.getByRole("tablist", { name: "自动化视图" }).getByRole("tab", { name: action.label, exact: true }).click();
    return;
  }
  if (state === "surface-更多-应用-灵感" || state === "surface-更多-资料库-灵感") {
    await page.getByRole("button", { name: "更多", exact: true }).click();
    await page.getByRole("menu", { name: "更多" }).waitFor({ state: "visible" });
    return;
  }
  if (state.startsWith("surface-library-")) {
    await page.getByRole("button", { name: "更多", exact: true }).click();
    await page.getByRole("menu", { name: "更多" }).getByRole("menuitem", { name: action.label, exact: true }).click();
    return;
  }
  if (state === "surface-资料库") throw new Error("QWork has no standalone 资料库 navigation entry");
  throw new Error(`QWork navigation contract is missing for ${state}`);
}
async function capture(page, pngPath, jsonPath) {
  const inspection = await page.evaluate(() => {
    const visible = (element) => { const rect = element.getBoundingClientRect(); const style = getComputedStyle(element); return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none"; };
    const summarize = (element) => { const rect = element.getBoundingClientRect(); return { tag: element.tagName.toLowerCase(), role: element.getAttribute("role"), ariaLabel: element.getAttribute("aria-label"), title: element.getAttribute("title"), text: (element.innerText || element.textContent || "").trim().replace(/\s+/g, " ").slice(0, 240), disabled: element.matches(":disabled,[aria-disabled=true]"), selected: element.matches("[aria-selected=true],[aria-checked=true],[data-state=active],[data-state=checked]"), box: { x: rect.x, y: rect.y, width: rect.width, height: rect.height } }; };
    const controls = [...document.querySelectorAll("button,a,input,textarea,select,[contenteditable=true],[role=button],[role=tab],[role=menuitem],[role=menuitemradio],[aria-label],[title]")].filter(visible).map(summarize);
    return { url: location.href, viewport: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio }, body_text: document.body.innerText.slice(0, 30000), controls };
  });
  const bytes = await page.screenshot({ path: pngPath, animations: "disabled" });
  const result = { ...inspection, screenshot: path.basename(pngPath), screenshot_sha256: crypto.createHash("sha256").update(bytes).digest("hex") };
  await fs.writeFile(jsonPath, `${JSON.stringify(result, null, 2)}\n`);
  return result;
}
function safe(value) { return value.replace(/[^\p{L}\p{N}._-]+/gu, "-"); }
