import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { requireFromProject } from "./project-require.mjs";
import { bindWorkBuddyRuntimeIdentity, calibrateWorkBuddyViewport } from "./workbuddy-runtime-identity.mjs";

const { chromium } = requireFromProject("playwright");

const endpoint = process.env.WORKBUDDY_CDP_URL ?? "http://127.0.0.1:19222";
const expectedVersion = process.env.WORKBUDDY_EXPECTED_VERSION;
const args = process.argv.slice(2);
if (args.length !== 1 || args.some((arg) => arg.startsWith("-"))) {
  throw new Error("usage: node capture_workbuddy_motion_contract.mjs <output-directory>");
}

const versionPayload = await fetch(`${endpoint}/json/version`).then((response) => response.json());
const userAgent = String(versionPayload["User-Agent"] ?? "");
const versionMatch = userAgent.match(/\bWorkBuddy\/([^\s]+)/);
if (!versionMatch) throw new Error(`unexpected WorkBuddy target: ${userAgent || "unknown"}`);
const productVersion = versionMatch[1];
if (expectedVersion && productVersion !== expectedVersion) {
  throw new Error(`unexpected WorkBuddy version: ${productVersion} != ${expectedVersion}`);
}

const outputRoot = path.resolve(args[0]);
await fs.mkdir(outputRoot, { recursive: false });
const browser = await chromium.connectOverCDP(endpoint);
const page = browser.contexts().flatMap((context) => context.pages()).find((candidate) => candidate.url().startsWith("file:"));
if (!page) throw new Error("WorkBuddy renderer target is unavailable");
const runtimeIdentity = await bindWorkBuddyRuntimeIdentity({
  bundleManifestPath: process.env.WORKBUDDY_BUNDLE_MANIFEST,
  productVersion,
  rendererUrl: page.url(),
});
const viewportCalibration = await calibrateWorkBuddyViewport(page, process.env.WORKBUDDY_VIEWPORT);
page.setDefaultTimeout(7000);
await page.bringToFront();

const initialNavigation = await selectedTopTab();
const initialSidebarExpanded = await page.getByRole("tab", { name: "新建任务", exact: true }).isVisible().catch(() => false);
const records = [];

try {
  await captureStaticContract();
  await captureSidebarTransition();
  await ensureSidebarExpanded();
  await captureMarketTransitions();
} finally {
  await restoreState();
  await viewportCalibration.restore();
  await browser.close();
}

const manifest = {
  schema_version: 1,
  product: "WorkBuddy",
  version: productVersion,
  authority_kind: "current-product-evidence",
  authority_domains: ["ui-motion", "ui-theme", "ui-interaction", "ui-geometry"],
  captured_at: new Date().toISOString(),
  user_agent: userAgent,
  runtime_identity: runtimeIdentity,
  viewport_calibration: viewportCalibration.calibration,
  viewport: await readViewportFromRecords(records),
  mutation_policy: "transient navigation, hover, tab and sidebar interactions only; original top navigation and sidebar expansion are restored; no create/install/connect/delete/send/run/auth mutation",
  clean_room_rule: "Only observable styles, timings, geometry, hashes and product behavior may become QWork contracts; WorkBuddy implementation and asset bytes must not be copied.",
  initial_state: { selected_top_tab: initialNavigation, sidebar_expanded: initialSidebarExpanded },
  record_count: records.length,
  records,
};
await fs.writeFile(path.join(outputRoot, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(JSON.stringify({ status: "ok", outputRoot, version: productVersion, recordCount: records.length, records: records.map((record) => record.id) }));

async function captureStaticContract() {
  const payload = await page.evaluate(() => {
    const themeSelectors = [];
    const keyframes = [];
    const inaccessibleStyleSheets = [];
    const visit = (rules, sheetIndex, parent = null) => {
      for (const rule of [...rules]) {
        if (rule.type === CSSRule.STYLE_RULE) {
          const selector = String(rule.selectorText ?? "");
          if (selector.includes("data-vscode-theme-name") || selector.includes("prefers-color-scheme")) {
            const declarations = {};
            for (const property of [...rule.style]) {
              if (property.startsWith("--cb-") || property.startsWith("--vscode-") || property === "color-scheme") {
                declarations[property] = rule.style.getPropertyValue(property).trim();
              }
            }
            if (Object.keys(declarations).length) themeSelectors.push({ sheetIndex, parent, selector, declarations });
          }
        } else if (rule.type === CSSRule.KEYFRAMES_RULE) {
          keyframes.push({
            sheetIndex,
            parent,
            name: rule.name,
            frames: [...rule.cssRules].map((frame) => ({
              key: frame.keyText,
              declarations: Object.fromEntries([...frame.style].map((property) => [property, frame.style.getPropertyValue(property).trim()])),
            })),
          });
        }
        if (rule.cssRules) visit(rule.cssRules, sheetIndex, String(rule.conditionText ?? rule.name ?? parent ?? ""));
      }
    };
    for (const [sheetIndex, sheet] of [...document.styleSheets].entries()) {
      try {
        visit(sheet.cssRules, sheetIndex);
      } catch (error) {
        inaccessibleStyleSheets.push({ sheetIndex, href: sheet.href, error: String(error) });
      }
    }
    const computedTokens = (element) => {
      const style = getComputedStyle(element);
      const tokens = {};
      for (const property of [...style]) {
        if (property.startsWith("--cb-") || property.startsWith("--vscode-")) {
          const value = style.getPropertyValue(property).trim();
          if (value) tokens[property] = value;
        }
      }
      return tokens;
    };
    return {
      url: location.href,
      viewport: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio },
      theme: {
        html_attributes: Object.fromEntries([...document.documentElement.attributes].map((attribute) => [attribute.name, attribute.value])),
        body_attributes: Object.fromEntries([...document.body.attributes].map((attribute) => [attribute.name, attribute.value])),
        prefers_dark: matchMedia("(prefers-color-scheme: dark)").matches,
        computed_color_scheme: getComputedStyle(document.documentElement).colorScheme,
        root_tokens: computedTokens(document.documentElement),
        body_tokens: computedTokens(document.body),
        selector_rules: themeSelectors,
      },
      keyframes,
      inaccessible_style_sheets: inaccessibleStyleSheets,
      motion_candidates: collectMotionCandidates(),
    };

    function collectMotionCandidates() {
      const visible = (element) => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
      };
      const activeTime = (value) => String(value).split(",").some((part) => Number.parseFloat(part) > 0);
      return [...document.querySelectorAll("body *")]
        .filter(visible)
        .map((element) => {
          const style = getComputedStyle(element);
          return { element, style };
        })
        .filter(({ style }) => activeTime(style.transitionDuration) || (style.animationName !== "none" && activeTime(style.animationDuration)))
        .slice(0, 2500)
        .map(({ element, style }) => summarize(element, style));
    }

    function summarize(element, style = getComputedStyle(element)) {
      const rect = element.getBoundingClientRect();
      return {
        path: structuralPath(element),
        tag: element.tagName.toLowerCase(),
        role: element.getAttribute("role"),
        aria_label: element.getAttribute("aria-label"),
        classes: [...element.classList].slice(0, 8),
        box: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
        transition: {
          property: style.transitionProperty,
          duration: style.transitionDuration,
          delay: style.transitionDelay,
          timing_function: style.transitionTimingFunction,
          behavior: style.transitionBehavior,
        },
        animation: {
          name: style.animationName,
          duration: style.animationDuration,
          delay: style.animationDelay,
          timing_function: style.animationTimingFunction,
          iteration_count: style.animationIterationCount,
          direction: style.animationDirection,
          fill_mode: style.animationFillMode,
          play_state: style.animationPlayState,
        },
        visual: {
          opacity: style.opacity,
          transform: style.transform,
          background_color: style.backgroundColor,
          color: style.color,
          border_radius: style.borderRadius,
          box_shadow: style.boxShadow,
        },
      };
    }

    function structuralPath(element) {
      const parts = [];
      let current = element;
      while (current && current !== document.body && parts.length < 8) {
        const tag = current.tagName.toLowerCase();
        const siblings = current.parentElement ? [...current.parentElement.children].filter((item) => item.tagName === current.tagName) : [];
        const suffix = siblings.length > 1 ? `:nth-of-type(${siblings.indexOf(current) + 1})` : "";
        parts.unshift(`${tag}${suffix}`);
        current = current.parentElement;
      }
      return `body>${parts.join(">")}`;
    }
  });
  const sanitized = sanitizeLabels(payload);
  await writeRecord("static-theme-motion-contract", "static-observation", sanitized);
}

async function captureSidebarTransition() {
  await ensureSidebarExpanded();
  const collapse = page.getByRole("button", { name: /收起侧边栏/ }).first();
  if (!(await collapse.isVisible().catch(() => false))) {
    await writeRecord("sidebar-collapse-expand", "not-evaluated", { reason: "collapse control is not visible" });
    return;
  }
  const collapseFrames = await clickAndSample(collapse, "collapse");
  const expand = page.getByRole("button", { name: /展开侧边栏|显示侧边栏/ }).first();
  let expandFrames;
  if (await expand.isVisible().catch(() => false)) {
    expandFrames = await clickAndSample(expand, "expand");
  } else {
    const box = await page.evaluate(() => {
      const control = [...document.querySelectorAll("button")].find((button) => {
        const rect = button.getBoundingClientRect();
        const style = getComputedStyle(button);
        return rect.width >= 28 && rect.width <= 36 && rect.height >= 28 && rect.height <= 36
          && rect.y < 56 && rect.x < 320 && style.visibility !== "hidden" && style.display !== "none";
      });
      if (!control) return null;
      const rect = control.getBoundingClientRect();
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
    });
    if (!box) {
      await writeRecord("sidebar-collapse-expand", "failed-to-restore", { collapse_frames: collapseFrames });
      throw new Error("sidebar collapsed but its geometric expand control is missing");
    }
    expandFrames = await triggerAndSample(
      () => page.mouse.click(box.x + box.width / 2, box.y + box.height / 2),
      "expand",
    );
  }
  if (!(await page.getByRole("tab", { name: "新建任务", exact: true }).isVisible().catch(() => false))) {
    throw new Error("sidebar expand transition did not restore the navigation tabs");
  }
  await writeRecord("sidebar-collapse-expand", "transient-click-and-restore", {
    collapse_frames: collapseFrames,
    expand_frames: expandFrames,
  });
}

async function captureMarketTransitions() {
  await ensureSidebarExpanded();
  const market = page.getByRole("tab", { name: "专家·技能·连接器", exact: true });
  if (!(await market.isVisible().catch(() => false))) {
    await writeRecord("market-navigation", "not-evaluated", { reason: "market top tab is not visible" });
    return;
  }
  const marketFrames = await clickAndSample(market, "open-market");
  await page.waitForTimeout(2500);
  const stable = await captureFrame("market-stable", 2500);
  await page.screenshot({ path: path.join(outputRoot, "market-stable.png"), animations: "allow" });
  await writeRecord("market-navigation", "transient-tab-navigation", { frames: [...marketFrames, stable], screenshot: "market-stable.png" });

  for (const label of ["技能", "连接器", "专家"]) {
    const tab = page.getByRole("tab", { name: label, exact: true }).last();
    if (!(await tab.isVisible().catch(() => false))) {
      await writeRecord(`market-tab-${label}`, "not-evaluated", { reason: `tab is not visible in ${productVersion}` });
      continue;
    }
    const frames = await clickAndSample(tab, `market-tab-${label}`);
    await writeRecord(`market-tab-${label}`, "transient-tab-navigation", { frames });
  }

  const expertTeam = page.getByRole("tab", { name: "专家团", exact: true }).last();
  const expertTeamVisible = await expertTeam.isVisible().catch(() => false);
  await writeRecord("market-expert-team-secondary-tab", expertTeamVisible ? "observed" : "absent-in-current-product", {
    visible: expertTeamVisible,
    evidence: "role=tab exact accessible name 专家团 after current market data reached its stable observation window",
  });
}

async function clickAndSample(locator, action) {
  return triggerAndSample(() => locator.click(), action);
}

async function triggerAndSample(trigger, action) {
  const frames = [await captureFrame(`${action}-before`, -1)];
  await trigger();
  const started = Date.now();
  for (const delay of [0, 16, 33, 50, 100, 150, 200, 300, 500]) {
    const remaining = delay - (Date.now() - started);
    if (remaining > 0) await page.waitForTimeout(remaining);
    frames.push(await captureFrame(action, Date.now() - started));
  }
  return frames;
}

async function captureFrame(action, elapsedMs) {
  const payload = await page.evaluate(() => {
    const box = (element) => {
      if (!element) return null;
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return {
        path: element.getAttribute("aria-label") || element.getAttribute("role") || element.tagName.toLowerCase(),
        box: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
        opacity: style.opacity,
        transform: style.transform,
        background_color: style.backgroundColor,
        transition_property: style.transitionProperty,
        transition_duration: style.transitionDuration,
        transition_delay: style.transitionDelay,
        transition_timing_function: style.transitionTimingFunction,
        animation_name: style.animationName,
        animation_duration: style.animationDuration,
        animation_timing_function: style.animationTimingFunction,
      };
    };
    const selectedTabs = [...document.querySelectorAll('[role="tab"][aria-selected="true"]')].map((element) => (element.textContent || "").trim()).filter(Boolean);
    const candidates = [
      document.querySelector('[role="tablist"][aria-label="Agents tabs"]'),
      document.querySelector("aside"),
      document.querySelector("main"),
      document.querySelector('[role="main"]'),
      document.querySelector("body > div"),
    ].filter(Boolean);
    return {
      viewport: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio },
      selected_tabs: selectedTabs,
      targets: candidates.map(box),
    };
  });
  return sanitizeLabels({ action, elapsed_ms: elapsedMs, ...payload });
}

async function writeRecord(id, observation, payload) {
  const file = `${safeSlug(id)}.json`;
  const record = { id, observation, file, payload_sha256: hash(Buffer.from(JSON.stringify(payload))) };
  await fs.writeFile(path.join(outputRoot, file), `${JSON.stringify({ ...record, payload }, null, 2)}\n`);
  records.push(record);
}

function sanitizeLabels(value) {
  const fixedLabels = new Set([
    "收起侧边栏", "展开侧边栏", "显示侧边栏", "搜索", "筛选", "Agents tabs",
    "新建任务", "助理", "项目", "专家·技能·连接器", "专家", "专家团", "技能", "连接器",
    "自动化", "资料库", "更多", "应用·灵感", "我的专家", "概览", "进入全屏", "收起右栏", "关闭",
  ]);
  const visit = (input) => {
    if (Array.isArray(input)) return input.map(visit);
    if (!input || typeof input !== "object") return input;
    const output = {};
    for (const [key, item] of Object.entries(input)) {
      if (key === "aria_label" && typeof item === "string" && item && !fixedLabels.has(item)) {
        output.aria_label = null;
        output.aria_label_sha256 = hash(Buffer.from(item));
      } else if (key === "selected_tabs" && Array.isArray(item)) {
        output[key] = item.map((label) => fixedLabels.has(label) ? label : `sha256:${hash(Buffer.from(label))}`);
      } else {
        output[key] = visit(item);
      }
    }
    return output;
  };
  return visit(value);
}

async function ensureSidebarExpanded() {
  const tab = page.getByRole("tab", { name: "新建任务", exact: true });
  if (await tab.isVisible().catch(() => false)) return;
  const expand = page.getByRole("button", { name: /展开侧边栏|显示侧边栏/ }).first();
  if (await expand.isVisible().catch(() => false)) {
    await expand.click();
  } else {
    const restored = await page.evaluate(() => {
      const visibleButtons = [...document.querySelectorAll("button")].filter((button) => {
        const rect = button.getBoundingClientRect();
        const style = getComputedStyle(button);
        return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
      });
      const control = visibleButtons.find((button) => {
        const rect = button.getBoundingClientRect();
        return rect.y < 56 && rect.x < 320 && rect.width >= 28 && rect.width <= 36 && rect.height >= 28 && rect.height <= 36;
      });
      if (!control) return false;
      control.click();
      return true;
    });
    if (!restored) throw new Error("sidebar cannot be restored safely");
  }
  await page.waitForTimeout(350);
  if (!(await tab.isVisible().catch(() => false))) throw new Error("sidebar expand action did not reveal the navigation tabs");
}

async function selectedTopTab() {
  return page.evaluate(() => {
    const tablist = document.querySelector('[role="tablist"][aria-label="Agents tabs"]');
    const selected = tablist?.querySelector('[role="tab"][aria-selected="true"]');
    return (selected?.textContent || "").trim() || null;
  });
}

async function restoreState() {
  if (initialNavigation) {
    await ensureSidebarExpanded();
    const original = page.getByRole("tab", { name: initialNavigation, exact: true });
    if (await original.isVisible().catch(() => false)) {
      await original.click().catch(() => {});
      await page.waitForTimeout(300);
    }
  }
  const currentlyExpanded = await page.getByRole("tab", { name: "新建任务", exact: true }).isVisible().catch(() => false);
  if (!initialSidebarExpanded && currentlyExpanded) {
    const collapse = page.getByRole("button", { name: /收起侧边栏/ }).first();
    if (await collapse.isVisible().catch(() => false)) await collapse.click().catch(() => {});
  } else if (initialSidebarExpanded && !currentlyExpanded) {
    await ensureSidebarExpanded();
  }
}

async function readViewportFromRecords(items) {
  const staticRecord = items.find((record) => record.id === "static-theme-motion-contract");
  if (!staticRecord) return null;
  const payload = JSON.parse(await fs.readFile(path.join(outputRoot, staticRecord.file), "utf8"));
  return payload.payload.viewport;
}

function hash(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function safeSlug(value) {
  return value.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]+/g, "-").replace(/^-|-$/g, "");
}
