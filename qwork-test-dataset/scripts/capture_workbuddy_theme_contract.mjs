import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { requireFromProject } from "./project-require.mjs";
import { bindWorkBuddyRuntimeIdentity, calibrateWorkBuddyViewport } from "./workbuddy-runtime-identity.mjs";

const { chromium } = requireFromProject("playwright");
const outputRoot = path.resolve(process.argv[2] || ".agents/skills/qwork-test-dataset/data/evidence/workbuddy-theme/candidate-transition");
const targetTheme = process.argv[3] || "dark";
if (!["light", "dark"].includes(targetTheme)) throw new Error("target theme must be light or dark");
await fs.mkdir(outputRoot, { recursive: true });

const endpoint = process.env.WORKBUDDY_CDP_URL ?? "http://127.0.0.1:19222";
const versionPayload = await fetch(`${endpoint}/json/version`).then((response) => response.json());
const userAgent = String(versionPayload["User-Agent"] || "");
const match = userAgent.match(/\bWorkBuddy\/([^\s]+)/);
if (!match || match[1] !== "5.3.8") throw new Error(`unexpected WorkBuddy target: ${userAgent}`);
const browser = await chromium.connectOverCDP(endpoint);
const page = browser.contexts().flatMap((context) => context.pages()).find((candidate) => candidate.url().startsWith("file:"));
if (!page) throw new Error("WorkBuddy renderer target is unavailable");
const runtimeIdentity = await bindWorkBuddyRuntimeIdentity({
  bundleManifestPath: process.env.WORKBUDDY_BUNDLE_MANIFEST,
  productVersion: match[1],
  rendererUrl: page.url(),
});
const calibration = await calibrateWorkBuddyViewport(page, process.env.WORKBUDDY_VIEWPORT);
await page.bringToFront();
await page.keyboard.press("Escape").catch(() => {});
const frames = [];

async function readTheme() {
  return page.evaluate(() => {
    const raw = localStorage.getItem("agent-ui-theme");
    let stored = null;
    try { stored = raw ? JSON.parse(raw) : null; } catch { stored = raw; }
    return {
      html_class: document.documentElement.className,
      html_style: document.documentElement.getAttribute("style"),
      body_class: document.body.className,
      theme_name: document.body.getAttribute("data-vscode-theme-name"),
      theme_kind: document.body.getAttribute("data-vscode-theme-kind"),
      prefers_dark: matchMedia("(prefers-color-scheme: dark)").matches,
      computed_color_scheme: getComputedStyle(document.documentElement).colorScheme,
      body_background: getComputedStyle(document.body).backgroundColor,
      body_color: getComputedStyle(document.body).color,
      stored_theme: stored,
    };
  });
}

async function capture(label, elapsedMs = null) {
  const file = `${label}.png`;
  const absolute = path.join(outputRoot, file);
  await page.screenshot({ path: absolute, animations: "allow" });
  const bytes = await fs.readFile(absolute);
  const theme = await readTheme();
  frames.push({ label, elapsed_ms: elapsedMs, file, sha256: hash(bytes), theme });
}

const initialTheme = await readTheme();
await capture("entry-before-theme-menu");
const viewport = await page.evaluate(() => ({ width: innerWidth, height: innerHeight, dpr: devicePixelRatio }));
const updateToastClose = page.locator("button.update-toast-close").filter({ visible: true }).last();
if (await updateToastClose.isVisible().catch(() => false)) {
  await updateToastClose.click();
  await page.waitForTimeout(150);
}
const userMenuTrigger = page.locator("button.user-menu-trigger--workbuddy").filter({ visible: true }).last();
if (!(await userMenuTrigger.isVisible().catch(() => false))) {
  throw new Error("WorkBuddy 5.3.8 user menu trigger is unavailable");
}
await userMenuTrigger.click();
await page.waitForTimeout(200);
const lightControl = page.getByText("浅色", { exact: true }).filter({ visible: true }).last();
const darkControl = page.getByText("深色", { exact: true }).filter({ visible: true }).last();
if (!(await lightControl.isVisible().catch(() => false)) || !(await darkControl.isVisible().catch(() => false))) {
  throw new Error("WorkBuddy 5.3.8 appearance menu does not expose both 浅色 and 深色");
}
const controlBoxes = { light: await lightControl.boundingBox(), dark: await darkControl.boundingBox() };
await capture("appearance-menu-before-selection");
const control = targetTheme === "dark" ? darkControl : lightControl;
const started = Date.now();
await control.click();
for (const checkpoint of [0, 16, 33, 50, 100, 150, 200, 300, 500]) {
  const remaining = checkpoint - (Date.now() - started);
  if (remaining > 0) await page.waitForTimeout(remaining);
  await capture(`theme-${targetTheme}-${String(checkpoint).padStart(3, "0")}ms`, Date.now() - started);
}
const expectedName = targetTheme === "dark" ? "IDE Night" : "IDE Light";
const expectedKind = targetTheme === "dark" ? "vscode-dark" : "vscode-light";
await page.waitForFunction(([name, kind]) => document.body.getAttribute("data-vscode-theme-name") === name && document.body.getAttribute("data-vscode-theme-kind") === kind, [expectedName, expectedKind]);
const finalTheme = await readTheme();
const passed = finalTheme.theme_name === expectedName
  && finalTheme.theme_kind === expectedKind
  && finalTheme.computed_color_scheme === targetTheme
  && finalTheme.stored_theme?.theme === targetTheme
  && finalTheme.stored_theme?.followSystem === false;
const manifest = {
  schema_version: 1,
  product: "WorkBuddy",
  version: "5.3.8",
  authority_kind: "current-product-evidence",
  authority_domains: ["ui-theme", "ui-motion", "ui-visual"],
  captured_at: new Date().toISOString(),
  runtime_identity: runtimeIdentity,
  viewport,
  viewport_calibration: calibration.calibration,
  mutation_policy: "appearance selection only; no account, create, install, connect, delete, send, run or authorization mutation",
  selection_path: "user menu -> 外观 -> 浅色|深色",
  available_modes: ["light", "dark"],
  follow_system_control_observed: false,
  target_theme: targetTheme,
  initial_theme: initialTheme,
  final_theme: finalTheme,
  control_boxes: controlBoxes,
  frame_count: frames.length,
  frames,
  result: passed ? "pass" : "fail",
};
await fs.writeFile(path.join(outputRoot, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
await calibration.restore();
await browser.close();
console.log(JSON.stringify({ status: manifest.result, outputRoot, targetTheme, frameCount: frames.length, finalTheme }));
if (!passed) process.exitCode = 1;

function hash(value) { return crypto.createHash("sha256").update(value).digest("hex"); }
