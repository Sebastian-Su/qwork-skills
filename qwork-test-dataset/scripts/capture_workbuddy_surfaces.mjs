import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { requireFromProject } from "./project-require.mjs";

const { chromium } = requireFromProject("playwright");

const endpoint = process.env.WORKBUDDY_CDP_URL ?? "http://127.0.0.1:19222";
const args = process.argv.slice(2);
if (args.length > 1 || args.some((arg) => arg.startsWith("-"))) {
  throw new Error("usage: node capture_workbuddy_surfaces.mjs [output-directory]; configure the endpoint with WORKBUDDY_CDP_URL");
}
const outputRoot = path.resolve(args[0] ?? ".agents/skills/qwork-test-dataset/data/evidence/workbuddy-cdp/5.3.12-surfaces");
await fs.mkdir(outputRoot, { recursive: true });
const version = await fetch(`${endpoint}/json/version`).then((response) => response.json());
if (!String(version["User-Agent"] ?? "").includes("WorkBuddy/5.3.12")) throw new Error("unexpected WorkBuddy CDP target");
const browser = await chromium.connectOverCDP(endpoint);
const page = browser.contexts().flatMap((context) => context.pages()).find((candidate) => candidate.url().startsWith("file:"));
if (!page) throw new Error("WorkBuddy renderer target is unavailable");
page.setDefaultTimeout(5000);
await page.bringToFront();
await dismissReadOnlyOverlays();

const topTabs = ["新建任务", "助理", "项目", "专家·技能·连接器", "自动化", "资料库", "更多 应用·灵感"];
const records = [];

async function ensureExpandedSidebar() {
  await dismissReadOnlyOverlays();
  const tabs = page.getByRole("tab");
  if ((await tabs.count()) >= 7) return;
  const expand = page.getByRole("button", { name: /展开侧边栏|显示侧边栏/ }).first();
  if (await expand.isVisible().catch(() => false)) {
    await expand.click();
  } else {
    const buttons = page.locator("button").filter({ visible: true });
    const count = await buttons.count();
    let clicked = false;
    for (let index = 0; index < count; index += 1) {
      const button = buttons.nth(index);
      const box = await button.boundingBox();
      if (box && box.y < 50 && box.width === 32 && box.height === 32) {
        await button.click();
        clicked = true;
        break;
      }
    }
    if (!clicked) throw new Error("expanded sidebar locator is unavailable");
  }
  await page.waitForTimeout(300);
}

async function dismissReadOnlyOverlays() {
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const overlay = page.locator(".connector-detail-modal-overlay").filter({ visible: true }).last();
    if (!(await overlay.isVisible().catch(() => false))) return;
    const close = overlay.locator("button.connector-detail-close").last();
    if (await close.isVisible().catch(() => false)) await close.click({ timeout: 3000 });
    else throw new Error("connector detail overlay is visible but its explicit close button is missing");
    await page.waitForTimeout(180);
  }
  const remaining = page.locator(".connector-detail-modal-overlay").filter({ visible: true }).last();
  if (await remaining.isVisible().catch(() => false)) {
    throw new Error("read-only exploration overlay could not be dismissed safely");
  }
}

for (const label of topTabs) {
  await ensureExpandedSidebar();
  const tab = page.getByRole("tab", { name: label, exact: true });
  if (!(await tab.isVisible().catch(() => false))) throw new Error(`top navigation tab missing: ${label}`);
  await tab.click();
  await page.waitForTimeout(500);
  const surface = slug(label);
  records.push(await capture(`surface-${surface}`, { kind: "top-tab", label }));
  if (label === "专家·技能·连接器") {
    for (const sublabel of ["专家", "技能", "连接器"]) {
      const tabKey = { "专家": "experts", "技能": "skills", "连接器": "connectors" }[sublabel];
      const dropdownControl = page.locator(`button.wb-dropdown__item-hit[data-track-props*='"tab":"${tabKey}"']`).last();
      const pageTab = page.getByRole("tab", { name: sublabel, exact: true }).last();
      const control = (await dropdownControl.isVisible().catch(() => false))
        ? dropdownControl
        : pageTab;
      if (!(await control.isVisible().catch(() => false))) continue;
      await control.click();
      await page.waitForTimeout(400);
      records.push(await capture(`surface-market-${slug(sublabel)}`, { kind: "market-tab", label: sublabel }));
      if (sublabel === "专家") {
        for (const secondary of ["专家", "专家团"]) {
          const secondaryControl = page.getByText(secondary, { exact: true }).filter({ visible: true }).last();
          if (!(await secondaryControl.isVisible().catch(() => false))) continue;
          await secondaryControl.click();
          await page.waitForTimeout(350);
          records.push(await capture(`surface-market-${slug(secondary)}-list`, { kind: "expert-type", label: secondary }));
        }
      }
    }
  }
  if (label === "自动化") {
    for (const sublabel of ["定时任务", "运行记录"]) {
      const control = page.getByText(sublabel, { exact: true }).filter({ visible: true }).last();
      if (!(await control.isVisible().catch(() => false))) continue;
      await control.click();
      await page.waitForTimeout(350);
      records.push(await capture(`surface-automation-${slug(sublabel)}`, { kind: "automation-tab", label: sublabel }));
    }
  }
  if (label === "资料库" || label === "更多 应用·灵感") {
    const safeLabels = ["我的文件", "我的邮箱", "腾讯文档", "ima知识库", "乐享知识库", "灵感"];
    for (const sublabel of safeLabels) {
      const control = page.getByText(sublabel, { exact: true }).filter({ visible: true }).last();
      if (!(await control.isVisible().catch(() => false))) continue;
      await control.click();
      await page.waitForTimeout(400);
      records.push(await capture(`surface-library-${slug(sublabel)}`, { kind: "library-entry", label: sublabel }));
      // Reopen the parent surface before locating the next entry.
      await tab.click();
      await page.waitForTimeout(250);
    }
  }
}

await fs.writeFile(path.join(outputRoot, "manifest.json"), `${JSON.stringify({
  schema_version: 1,
  product: "WorkBuddy",
  version: "5.3.12",
  authority_kind: "current-product-evidence",
  captured_at: new Date().toISOString(),
  user_agent: version["User-Agent"],
  mutation_policy: "navigation and read-only tabs only; no create/install/connect/delete/send/run/auth mutation",
  state_count: records.length,
  records,
}, null, 2)}\n`);
await browser.close();
console.log(JSON.stringify({ status: "ok", outputRoot, stateCount: records.length, states: records.map((record) => record.state) }));

async function capture(state, action) {
  const inspection = await page.evaluate(() => {
    const visible = (element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
    };
    const summarize = (element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return {
        tag: element.tagName.toLowerCase(), role: element.getAttribute("role"), ariaLabel: element.getAttribute("aria-label"), title: element.getAttribute("title"), text: (element.innerText || element.textContent || "").trim().replace(/\s+/g, " ").slice(0, 240),
        disabled: element.matches(":disabled,[aria-disabled=true]"), selected: element.matches("[aria-selected=true],[aria-checked=true],[data-state=active],[data-state=checked]"),
        box: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
        style: { color: style.color, backgroundColor: style.backgroundColor, border: style.border, borderRadius: style.borderRadius, boxShadow: style.boxShadow, opacity: style.opacity, padding: style.padding, gap: style.gap, fontFamily: style.fontFamily, fontSize: style.fontSize, fontWeight: style.fontWeight, lineHeight: style.lineHeight },
      };
    };
    const controls = [...document.querySelectorAll("button,a,input,textarea,select,[contenteditable=true],[role=button],[role=tab],[role=menuitem],[role=menuitemradio],[aria-label],[title]")].filter(visible).map(summarize);
    return { url: location.href, viewport: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio }, bodyText: document.body.innerText.slice(0, 30000), controls, landmarks: [...document.querySelectorAll("header,nav,main,aside,section,dialog,[role=dialog],[role=navigation],[role=main],[role=toolbar],[role=menu]")].filter(visible).map(summarize) };
  });
  const screenshot = `${state}.png`;
  const file = path.join(outputRoot, screenshot);
  await page.screenshot({ path: file, animations: "disabled" });
  const bytes = await fs.readFile(file);
  const record = { state, action, url: inspection.url, viewport: inspection.viewport, body_text_sha256: hash(Buffer.from(inspection.bodyText)), screenshot, screenshot_sha256: hash(bytes), control_count: inspection.controls.length, landmark_count: inspection.landmarks.length };
  await fs.writeFile(path.join(outputRoot, `${state}.json`), `${JSON.stringify({ ...record, controls: inspection.controls, landmarks: inspection.landmarks }, null, 2)}\n`);
  return record;
}

function hash(value) { return crypto.createHash("sha256").update(value).digest("hex"); }
function slug(value) { return value.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]+/g, "-").replace(/^-|-$/g, ""); }
