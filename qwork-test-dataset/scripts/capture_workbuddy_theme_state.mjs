import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { requireFromProject } from "./project-require.mjs";
import { bindWorkBuddyRuntimeIdentity } from "./workbuddy-runtime-identity.mjs";

const { chromium } = requireFromProject("playwright");
const outputRoot = path.resolve(process.argv[2] || ".agents/skills/qwork-test-dataset/data/evidence/workbuddy-theme/candidate-state");
const expectedTheme = process.argv[3] || "dark";
await fs.mkdir(outputRoot, { recursive: true });
const endpoint = process.env.WORKBUDDY_CDP_URL ?? "http://127.0.0.1:19222";
const versionPayload = await fetch(`${endpoint}/json/version`).then((response) => response.json());
const userAgent = String(versionPayload["User-Agent"] || "");
const match = userAgent.match(/\bWorkBuddy\/([^\s]+)/);
if (!match || match[1] !== "5.3.8") throw new Error(`unexpected WorkBuddy target: ${userAgent}`);
const browser = await chromium.connectOverCDP(endpoint);
const page = browser.contexts().flatMap((context) => context.pages()).find((candidate) => candidate.url().startsWith("file:"));
if (!page) throw new Error("WorkBuddy renderer target is unavailable");
const runtimeIdentity = await bindWorkBuddyRuntimeIdentity({ bundleManifestPath: process.env.WORKBUDDY_BUNDLE_MANIFEST, productVersion: match[1], rendererUrl: page.url() });
await page.bringToFront();
const theme = await page.evaluate(() => {
  let storedTheme = null;
  try { storedTheme = JSON.parse(localStorage.getItem("agent-ui-theme") || "null"); } catch {}
  return {
    resolved_theme: getComputedStyle(document.documentElement).colorScheme,
    html_class: document.documentElement.className,
    body_class: document.body.className,
    theme_name: document.body.getAttribute("data-vscode-theme-name"),
    theme_kind: document.body.getAttribute("data-vscode-theme-kind"),
    prefers_dark: matchMedia("(prefers-color-scheme: dark)").matches,
    body_background: getComputedStyle(document.body).backgroundColor,
    body_color: getComputedStyle(document.body).color,
    stored_theme: storedTheme,
  };
});
const screenshot = "cold-start-theme.png";
await page.screenshot({ path: path.join(outputRoot, screenshot), animations: "disabled" });
const screenshotSha256 = hash(await fs.readFile(path.join(outputRoot, screenshot)));
const passed = theme.resolved_theme === expectedTheme && theme.stored_theme?.theme === expectedTheme && theme.stored_theme?.followSystem === false;
const manifest = { schema_version: 1, product: "WorkBuddy", version: "5.3.8", captured_at: new Date().toISOString(), observation: "cold-start-after-process-termination", runtime_identity: runtimeIdentity, expected_theme: expectedTheme, theme, screenshot, screenshot_sha256: screenshotSha256, result: passed ? "pass" : "fail" };
await fs.writeFile(path.join(outputRoot, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
await browser.close();
console.log(JSON.stringify({ status: manifest.result, outputRoot, theme }));
if (!passed) process.exitCode = 1;
function hash(value) { return crypto.createHash("sha256").update(value).digest("hex"); }
