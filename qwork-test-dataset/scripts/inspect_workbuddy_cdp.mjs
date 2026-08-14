import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { requireFromProject } from "./project-require.mjs";

const { chromium } = requireFromProject("playwright");

const endpoint = process.env.WORKBUDDY_CDP_URL ?? "http://127.0.0.1:19222";
const args = process.argv.slice(2);
if (args.length > 1 || args.some((arg) => arg.startsWith("-"))) {
  throw new Error("usage: node inspect_workbuddy_cdp.mjs [output-directory]; configure the endpoint with WORKBUDDY_CDP_URL");
}
const outputRoot = path.resolve(args[0] ?? ".agents/skills/qwork-test-dataset/data/evidence/workbuddy-cdp/5.3.12");
await fs.mkdir(outputRoot, { recursive: true });
const version = await fetch(`${endpoint}/json/version`).then((response) => response.json());
if (!String(version["User-Agent"] ?? "").includes("WorkBuddy/5.3.12")) {
  throw new Error(`unexpected WorkBuddy target: ${version["User-Agent"] ?? "unknown"}`);
}
const browser = await chromium.connectOverCDP(endpoint);
const page = browser.contexts().flatMap((context) => context.pages()).find((candidate) => candidate.url().startsWith("file:"));
if (!page) throw new Error("WorkBuddy renderer target is missing");
await page.bringToFront();
await page.waitForLoadState("domcontentloaded");
await page.waitForTimeout(500);

const records = [];
const seenStates = new Set();
const controlsByState = {};

async function dismissTransient() {
  await page.keyboard.press("Escape").catch(() => {});
  await page.evaluate(() => {
    for (const button of [...document.querySelectorAll("button")]) {
      const label = `${button.getAttribute("aria-label") ?? ""} ${button.getAttribute("title") ?? ""} ${button.textContent ?? ""}`;
      if (/关闭更新|稍后|close update/i.test(label) && button.getBoundingClientRect().width > 0) button.click();
    }
  }).catch(() => {});
  await page.waitForTimeout(120);
}

async function inspect(state, action = null) {
  if (seenStates.has(state)) return;
  seenStates.add(state);
  await page.waitForTimeout(300);
  const payload = await page.evaluate(() => {
    const visible = (element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
    };
    const summarize = (element, index) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      const text = (element.innerText || element.textContent || "").trim().replace(/\s+/g, " ").slice(0, 240);
      return {
        index,
        tag: element.tagName.toLowerCase(),
        role: element.getAttribute("role"),
        ariaLabel: element.getAttribute("aria-label"),
        title: element.getAttribute("title"),
        text,
        disabled: element.matches(":disabled,[aria-disabled=true]"),
        selected: element.matches("[aria-selected=true],[aria-checked=true],[data-state=active],[data-state=checked]"),
        box: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
        style: {
          color: style.color,
          backgroundColor: style.backgroundColor,
          border: style.border,
          borderRadius: style.borderRadius,
          boxShadow: style.boxShadow,
          opacity: style.opacity,
          padding: style.padding,
          gap: style.gap,
          fontFamily: style.fontFamily,
          fontSize: style.fontSize,
          fontWeight: style.fontWeight,
          lineHeight: style.lineHeight,
        },
      };
    };
    return {
      url: location.href,
      title: document.title,
      viewport: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio },
      bodyTextHashInput: document.body.innerText.slice(0, 20000),
      controls: [...document.querySelectorAll("button,a,input,textarea,select,[contenteditable=true],[role=button],[role=tab],[role=menuitem],[role=menuitemradio],[aria-label],[title]")].filter(visible).map(summarize),
      landmarks: [...document.querySelectorAll("header,nav,main,aside,section,dialog,[role=dialog],[role=navigation],[role=main],[role=toolbar],[role=menu]")].filter(visible).map(summarize),
    };
  });
  const screenshot = `${state}.png`;
  const screenshotPath = path.join(outputRoot, screenshot);
  await page.screenshot({ path: screenshotPath, animations: "disabled" });
  const bytes = await fs.readFile(screenshotPath);
  const record = {
    state,
    action,
    url: payload.url,
    title: payload.title,
    viewport: payload.viewport,
    body_text_sha256: crypto.createHash("sha256").update(payload.bodyTextHashInput).digest("hex"),
    screenshot,
    screenshot_sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
    controls: payload.controls,
    landmarks: payload.landmarks,
  };
  controlsByState[state] = payload.controls;
  records.push(record);
  await fs.writeFile(path.join(outputRoot, `${state}.json`), `${JSON.stringify(record, null, 2)}\n`);
}

function candidates(state) {
  return (controlsByState[state] ?? []).filter((control) => control.box.width >= 12 && control.box.height >= 12);
}

async function clickControl(state, matcher) {
  const control = candidates(state).find(matcher);
  if (!control) return null;
  await page.mouse.click(control.box.x + control.box.width / 2, control.box.y + control.box.height / 2);
  return control;
}

await dismissTransient();
await inspect("00-entry");

// Read-only top-level navigation. Explicitly exclude actions with known mutation/external side effects.
const navLabels = [
  ["home", /新建任务|首页/],
  ["assistant", /^助理$|会话/],
  ["projects", /^项目$/],
  ["experts", /^专家$|专家中心/],
  ["skills", /^技能$|技能市场/],
  ["connectors", /^连接器$|连接器市场/],
  ["automations", /^自动化$/],
  ["more", /^更多$/],
];
for (const [state, pattern] of navLabels) {
  await dismissTransient();
  const source = records.at(-1)?.state ?? "00-entry";
  const clicked = await clickControl(source, (control) => pattern.test(`${control.ariaLabel ?? ""} ${control.title ?? ""} ${control.text ?? ""}`));
  if (!clicked) continue;
  await inspect(`nav-${state}`, { kind: "click", control: clicked });
  // Capture tab/menu states inside the current surface, but do not press create/install/connect/delete/send controls.
  const stateName = `nav-${state}`;
  const safeSubcontrols = candidates(stateName).filter((control) => {
    const label = `${control.ariaLabel ?? ""} ${control.title ?? ""} ${control.text ?? ""}`;
    const safeRole = control.role === "tab" || /专家团|专家$|定时任务|运行记录|推荐|SkillHub|套件|我的文件|我的邮箱|腾讯文档|知识库|灵感|搜索|筛选|排序|分类|展开|收起/.test(label);
    const mutation = /新建|添加|安装|连接|授权|删除|移除|发送|运行|执行|创建|提交|保存|确认|召唤|重试|完全访问|退出登录/.test(label);
    return safeRole && !mutation;
  }).slice(0, 18);
  for (let index = 0; index < safeSubcontrols.length; index += 1) {
    const control = safeSubcontrols[index];
    await page.mouse.click(control.box.x + control.box.width / 2, control.box.y + control.box.height / 2);
    const label = stable(control.ariaLabel || control.title || control.text || `control-${index + 1}`);
    await inspect(`${stateName}-${label}`, { kind: "safe-subcontrol", control });
    await page.keyboard.press("Escape").catch(() => {});
  }
}

const manifest = {
  schema_version: 1,
  product: "WorkBuddy",
  version: "5.3.12",
  authority_kind: "current-product-evidence",
  captured_at: new Date().toISOString(),
  cdp_endpoint: "127.0.0.1 loopback (port intentionally not authoritative)",
  user_agent: version["User-Agent"],
  mutation_policy: "navigation, tabs, menus, expand/collapse only; no create/install/connect/delete/send/run/auth mutation",
  state_count: records.length,
  records: records.map(({ controls, landmarks, ...record }) => ({ ...record, control_count: controls.length, landmark_count: landmarks.length })),
};
await fs.writeFile(path.join(outputRoot, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
await browser.close();
console.log(JSON.stringify({ status: "ok", outputRoot, stateCount: records.length, states: records.map((record) => record.state) }));

function stable(value) {
  return value.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]+/g, "-").replace(/^-|-$/g, "").slice(0, 48) || "state";
}
