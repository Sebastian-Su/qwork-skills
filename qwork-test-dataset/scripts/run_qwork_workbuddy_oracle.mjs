#!/usr/bin/env node
/** Capture isolated QWork states corresponding to an explicitly frozen WorkBuddy UI Oracle. */
import crypto from "node:crypto";
import fs from "node:fs/promises";
import http from "node:http";
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
const frozenTheme = wbManifest.theme_coverage?.expected_theme;
if (frozenTheme !== "light" && frozenTheme !== "dark") {
  throw new Error("WorkBuddy Oracle manifest must declare theme_coverage.expected_theme as light or dark");
}
const QWORK_EQUIVALENT_MENU_LABEL = {
  "ima知识库": "知识库",
  "乐享知识库": "知识库",
};
const records = requestedState === "all"
  ? wbManifest.records
  : wbManifest.records.filter((item) => item.state === requestedState);
if (!records.length) throw new Error(`unknown WorkBuddy state: ${requestedState}`);
await fs.mkdir(output, { recursive: true });
const configHome = await fs.mkdtemp(path.join(os.tmpdir(), "qwork-workbuddy-oracle-"));
const fakeSidecar = path.join(repo, "e2e/fixtures/fake-sidecar.mjs");
const projectFixture = await startProjectFixture();
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
      QWORK_E2E_PROCESS: "1",
      NODE_ENV: "test",
      QWORK_AUTH_BYPASS: "1",
      QWORK_E2E_BUILTIN_MARKETPLACE: "plugins-only",
      QWORK_E2E_EMBEDDED_PYTHON: "0",
      QWORK_PROJECT_API_URL: projectFixture.baseUrl,
      QWORK_PROJECT_ACCESS_TOKEN: "local-dev-token",
      WORK_GUI_E2E_SAFE_STORAGE_KEY: "qwork-private-workbuddy-oracle-v1",
      ELECTRON_DISABLE_SECURITY_WARNINGS: "true",
    },
  });
  const page = await app.firstWindow();
  page.setDefaultTimeout(8_000);
  await ensureFrozenTheme(page, frozenTheme);
  await calibrateViewport(app, page, { width: 1680, height: 1084 });
  for (const record of records) {
    const stateDir = path.join(output, safe(record.state));
    await fs.mkdir(stateDir, { recursive: true });
    const result = { state: record.state, action: record.action, status: "pending", evidence: {} };
    try {
      await returnHome(page);
      await calibrateViewport(app, page, { width: 1680, height: 1084 });
      result.evidence.entry = await capture(page, path.join(stateDir, "entry.png"), path.join(stateDir, "entry.json"));
      await navigate(page, record.state, record.action);
      await calibrateViewport(app, page, { width: 1680, height: 1084 });
      result.evidence.transition = await capture(page, path.join(stateDir, "transition.png"), path.join(stateDir, "transition.json"));
      await page.waitForTimeout(250);
      await ensureFinalState(page, record.state);
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
  await new Promise((resolve) => projectFixture.server.close(resolve));
  await fs.rm(configHome, { recursive: true, force: true });
}
const manifest = {
  schema_version: 1,
  product: "QWork",
  compared_product: `WorkBuddy ${wbManifest.version}`,
  captured_at: new Date().toISOString(),
  repo_revision: (await import("node:child_process")).execFileSync("git", ["rev-parse", "HEAD"], { cwd: repo, encoding: "utf8" }).trim(),
  isolation: "temporary ZIQDO_CONFIG_HOME + deterministic fake sidecar; zero model calls",
  expected_theme: frozenTheme,
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
async function ensureFrozenTheme(page, theme) {
  await page.getByRole("button", { name: "新建任务", exact: true }).waitFor({ state: "visible" });
  await page.evaluate(async (value) => {
    await window.workGui?.settings?.patch({ appearance: { theme: value } });
    window.localStorage.setItem("ziqdo.theme", value);
    const root = document.documentElement;
    root.classList.toggle("dark", value === "dark");
    root.classList.toggle("light", value === "light");
    root.dataset.themePreference = value;
    root.dataset.theme = value;
  }, theme);
  await page.waitForFunction((value) => document.documentElement.dataset.theme === value, theme);
}
async function ensureFinalState(page, state) {
  if (state !== "surface-更多-应用-灵感" && state !== "surface-更多-资料库-灵感") return;
  const menu = page.getByRole("menu", { name: "更多" });
  if (!(await menu.isVisible())) {
    await page.getByRole("button", { name: "更多", exact: true }).click();
  }
  await menu.waitFor({ state: "visible" });
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
    const qworkLabel = QWORK_EQUIVALENT_MENU_LABEL[action.label] ?? action.label;
    await page.getByRole("menu", { name: "更多" }).getByRole("menuitem", { name: qworkLabel, exact: true }).click();
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

async function startProjectFixture() {
  const now = "2026-08-31T00:00:00.000Z";
  const expertItems = expertCatalogFixture(now);
  const inspirationItems = await inspirationCatalogFixture(repo, now);
  const projectItems = oracleProjectFixtures(now);
  const onboardingProject = {
    id: "oracle-onboarding-project",
    organizationId: "oracle-organization",
    name: "新手项目",
    description: "",
    instruction: "",
    configRevision: 1,
    ownerId: "oracle-user",
    status: "active",
    inviteJoinMode: "approval",
    storageUsed: 0,
    storageLimit: 1024,
    version: 1,
    createdBy: "oracle-user",
    createdAt: now,
    updatedAt: now,
  };
  const server = http.createServer((request, response) => {
    response.setHeader("content-type", "application/json; charset=utf-8");
    const url = new URL(request.url ?? "/", "http://127.0.0.1");
    if (request.method === "GET" && url.pathname === "/api/v1/project-templates") {
      response.end(JSON.stringify({ templates: [] }));
      return;
    }
    if (request.method === "GET" && url.pathname === "/api/v1/projects") {
      response.end(JSON.stringify({ items: projectItems }));
      return;
    }
    if (request.method === "GET" && /^\/api\/v1\/projects\/[^/]+\/members$/.test(url.pathname)) {
      response.end(JSON.stringify({ members: [] }));
      return;
    }
    if (request.method === "GET" && /^\/api\/v1\/projects\/[^/]+\/tasks$/.test(url.pathname)) {
      response.end(JSON.stringify({ tasks: [] }));
      return;
    }
    if (request.method === "GET" && url.pathname === "/api/v1/inspirations") {
      const category = url.searchParams.get("category");
      const search = url.searchParams.get("search")?.trim().toLocaleLowerCase() ?? "";
      const offset = Math.max(0, Number.parseInt(url.searchParams.get("offset") ?? "0", 10) || 0);
      const limit = Math.max(1, Number.parseInt(url.searchParams.get("limit") ?? "100", 10) || 100);
      const filtered = inspirationItems.filter((item) => {
        if (category && item.category !== category) return false;
        if (search && !`${item.title} ${item.summary}`.toLocaleLowerCase().includes(search)) return false;
        return true;
      });
      response.end(JSON.stringify({
        items: filtered.slice(offset, offset + limit),
        total: filtered.length,
        offset,
        limit,
      }));
      return;
    }
    if (request.method === "POST" && url.pathname === "/api/v1/onboarding/project") {
      response.end(JSON.stringify({
        project: onboardingProject,
        seedVersion: 1,
        created: false,
        reset: false,
      }));
      return;
    }
    if (request.method === "GET" && url.pathname === "/expert/api/v1/client/experts/catalog") {
      const kind = url.searchParams.get("kind");
      const category = url.searchParams.get("category");
      const search = url.searchParams.get("search")?.trim().toLocaleLowerCase() ?? "";
      const offset = Math.max(0, Number.parseInt(url.searchParams.get("offset") ?? "0", 10) || 0);
      const limit = Math.max(1, Number.parseInt(url.searchParams.get("limit") ?? "48", 10) || 48);
      const filtered = expertItems.filter((item) => {
        if (kind && item.kind !== kind) return false;
        if (category && item.category !== category) return false;
        if (search && !`${item.name} ${item.description} ${item.author}`.toLocaleLowerCase().includes(search)) return false;
        return true;
      });
      response.end(JSON.stringify({
        items: filtered.slice(offset, offset + limit),
        total: filtered.length,
        offset,
        limit,
      }));
      return;
    }
    response.statusCode = 404;
    response.end(JSON.stringify({
      error: {
        code: "not_found",
        message: `oracle fixture route missing: ${request.method ?? "UNKNOWN"} ${url.pathname}`,
      },
    }));
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  if (!address || typeof address === "string") {
    await new Promise((resolve) => server.close(resolve));
    throw new Error("project fixture did not bind an ephemeral TCP port");
  }
  return { server, baseUrl: `http://127.0.0.1:${address.port}` };
}

async function inspirationCatalogFixture(qworkRepo, publishedAt) {
  const registryPath = path.join(
    qworkRepo,
    "src/renderer/src/pages/inspiration-cloud/registry.json",
  );
  const registry = JSON.parse(await fs.readFile(registryPath, "utf8"));
  if (!Array.isArray(registry.cases)) {
    throw new Error(`invalid inspiration registry fixture: ${registryPath}`);
  }
  return registry.cases.map((item, index) => ({
    id: item.id,
    inspirationKey: item.id,
    title: item.title,
    summary: item.subtitle ?? "",
    category: item.categories?.[0] ?? "other",
    artifactType: item.artifact_type ?? "conversation",
    scenario: item.scene?.name,
    sceneId: item.scene?.id,
    catalogRank: index,
    scopeType: "global",
    visibility: "public",
    sourceType: "builtin",
    status: "published",
    currentVersion: "v1",
    favoriteCount: 0,
    useCount: 0,
    viewCount: 0,
    reportCount: 0,
    favorite: false,
    createdAt: publishedAt,
    updatedAt: publishedAt,
    publishedAt,
  }));
}

function oracleProjectFixtures(now) {
  return ["产品协作", "市场研究", "团队知识", "交付管理"].map((name, index) => ({
    id: `oracle-project-${index + 1}`,
    organizationId: "oracle-organization",
    name,
    description: "WorkBuddy 5.3.8 UI Oracle 结构夹具",
    instruction: "",
    connectorIds: [],
    expertIds: [],
    skillIds: [],
    configRevision: 1,
    ownerId: "oracle-user",
    status: "active",
    inviteJoinMode: "approval",
    storageUsed: 0,
    storageLimit: 1024,
    version: 1,
    createdBy: "oracle-user",
    createdAt: now,
    updatedAt: now,
  }));
}

function expertCatalogFixture(publishedAt) {
  const entries = [
    ["公益专家", "腾讯公益", "腾讯专家", "individual", "找项目、做捐赠、打理小红花花园，都能找我。"],
    ["工作台搭建师", "小台", "OPC·一人公司", "individual", "为不同人群定制专属数字工作台，覆盖学习、职场与生活管理。"],
    ["高级开发工程师", "吴八哥", "技术工程", "individual", "精通多种语言和框架，以严谨的工程纪律交付高质量代码。"],
    ["美团生活助手", "美团", "腾讯专家", "individual", "领取优惠券、搜索附近团购美食并下单。"],
    ["超级合伙人", "FBSIr", "OPC·一人公司", "individual", "带上目标或真实材料，立即得到可使用成品。"],
    ["妈妈问答", "福帮手", "行业顾问", "individual", "整理与妈妈有关的照片、视频、录音和家庭资料。"],
    ["资讯速递专家", "数字生命卡兹克", "内容创作", "individual", "自动整理中文简报，免配置免登录。"],
    ["世界观架构师 / 连续性编辑", "小说故事创作专家", "内容创作", "individual", "搭建三维理论塑角色，靠追踪系统防矛盾。"],
    ["创业伙伴", "林正刚", "OPC·一人公司", "individual", "从读书中听痛点，帮助创业判断。"],
    ["长文档写作与改稿专家", "福帮手", "内容创作", "individual", "推进长文档录入、项目续接、改稿与交付检查。"],
    ["微信小程序开发者", "小程达", "技术工程", "individual", "精通微信小程序开发框架和生态。"],
    ["战略咨询合伙人", "战略咨询顾问", "行业顾问", "individual", "按需破题、取证、测算与撰写专业级方案。"],
    ["Python 全栈工程师", "技术专家", "技术工程", "individual", "精通后端 API、数据分析与自动化。"],
    ["项目来了，先把路理清", "MAI Lab并购Agent", "项目质量", "individual", "拆解资料、画交易结构、核数字与股权。"],
    ["数据分析专家", "鹏城信息AI专家", "数据智能", "individual", "提供数据清洗、统计建模、可视化分析和报告撰写。"],
    ["论文写作导师", "论文舟", "教育学习", "individual", "基于可核验材料辅助论文结构、润色和审稿回复。"],
    ["内容创作专家团", "WorkBuddy", "内容创作", "collective", "覆盖选题、写作、编辑和发布的内容创作团队。"],
    ["交易分析团队", "WorkBuddy", "金融投资", "collective", "面向市场研究与交易复盘的分析团队。"],
    ["腾讯自选股股票投研专家团", "腾讯", "金融投资", "collective", "提供股票研究与市场信息整理。"],
    ["财税合规专家团", "WorkBuddy", "法务安全", "collective", "覆盖财税与合规问题的专业团队。"],
    ["深度研究团队", "WorkBuddy", "数据智能", "collective", "从多源信息形成可复核研究结论。"],
    ["花叔数据分析专家团", "WorkBuddy", "数据智能", "collective", "负责数据清洗、分析与可视化交付。"],
    ["专业文档生成团队", "WorkBuddy", "内容创作", "collective", "协作完成专业文档生产和质量检查。"],
    ["产品设计协作团", "WorkBuddy", "产品设计", "collective", "协作完成产品分析、交互设计和方案评审。"],
    ["技术工程协作团", "WorkBuddy", "技术工程", "collective", "协作完成架构、实现、测试和交付。"],
    ["营销增长协作团", "WorkBuddy", "营销增长", "collective", "协作制定增长策略并复盘效果。"],
    ["销售商务协作团", "WorkBuddy", "销售商务", "collective", "协作推进客户研究、方案和商务沟通。"],
    ["运营人力协作团", "WorkBuddy", "运营人力", "collective", "协作梳理运营流程与团队机制。"],
    ["项目质量协作团", "WorkBuddy", "项目质量", "collective", "协作跟踪计划、风险、测试与验收。"],
    ["行业顾问协作团", "WorkBuddy", "行业顾问", "collective", "协作形成行业研究和决策材料。"],
    ["游戏空间协作团", "WorkBuddy", "游戏空间", "collective", "协作推进游戏策划、制作和发布。"],
  ];
  return entries.map(([name, author, category, kind, description], index) => {
    const id = `oracle-expert-${String(index + 1).padStart(3, "0")}`;
    return {
      id,
      expertId: id,
      runtimeExpertId: id,
      kind,
      memberCount: kind === "collective" ? 3 : 0,
      versionId: "version-1",
      expertKey: `oracle:workbuddy-5.3.8:${id}`,
      source: "workbuddy-5.3.8-frozen-ui-oracle",
      name,
      description,
      version: "1.0.0",
      artifactSha256: "a".repeat(64),
      downloadPath: `/expert/api/v1/client/experts/${id}/versions/version-1/download`,
      scopeType: "global",
      author,
      category,
      installable: true,
      downloads: 1000 - index,
      stars: 100 - index,
      catalogRank: index,
      publishedAt,
      packageSize: 1024,
      expandedSize: 2048,
      fileCount: 1,
      treeSha256: "b".repeat(64),
    };
  });
}
