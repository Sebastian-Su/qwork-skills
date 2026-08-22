import { expect, test, type ElectronApplication, type Locator } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import {
  attachUiState,
  boxOf,
  computedStyle,
  setContentSize,
} from "../../../../../e2e/fixtures/ui-contract";
import {
  cleanup,
  createTestHome,
  createWorkspace,
  openApp,
  repo,
} from "./fixtures/launch-isolated";

type Oracle = {
  source: { brandPolicy: string };
  sidebar: {
    expandedWidth: number;
    toolbar: {
      y: number;
      buttonSize: number;
      iconSize: number;
      gap: number;
      radius: number;
      order: string[];
      x: Record<string, number>;
      defaultBackground: string;
      darkForeground: string;
      darkHoverBackground: string;
      dragRegion: string;
    };
  };
  search: {
    width: number;
    height: number;
    radius: number;
    darkBackground: string;
    overlay: string;
    emptyQueryLimit: number;
  };
  filter: {
    width: number;
    height: number;
    anchor: { x: number; y: number };
    radius: number;
    padding: number;
    darkBackground: string;
    statusOptions: string[];
    timeOptions: string[];
  };
  accountMenu: {
    width: number;
    radius: number;
    anchorGap: number;
    viewportMargin: number;
    headerHeight: number;
    rowHeightRange: [number, number];
    padding: number;
    maxHeight: string;
    darkBackground: string;
    darkShadow: string;
    qworkRowOrder: string[];
  };
};

type Mismatch = { pointer: string; expected: unknown; actual: unknown };

test("WB-UI-ORACLE-SIDEBAR-001 | 侧栏工具、搜索、筛选与账户菜单逐字段匹配 WorkBuddy", async ({}, testInfo) => {
  const oracle = JSON.parse(
    await fs.readFile(path.join(repo, "e2e/visual-baselines/sidebar-account-reference.json"), "utf8"),
  ) as Oracle;
  const home = await createTestHome("sidebar-account-oracle");
  await createWorkspace(home);
  const mismatches: Mismatch[] = [];
  let app: ElectronApplication | undefined;

  const compare = (pointer: string, actual: unknown, expected: unknown) => {
    if (!same(actual, expected)) mismatches.push({ pointer, expected, actual });
  };
  const compareNumber = (pointer: string, actual: number, expected: number, tolerance = 2) => {
    if (Math.abs(actual - expected) > tolerance) mismatches.push({ pointer, expected, actual });
  };

  try {
    const opened = await openApp(home);
    app = opened.app;
    const page = opened.page;
    await setContentSize(app, page);

    const rail = page.getByRole("complementary");
    compareNumber("/sidebar/expandedWidth", (await boxOf(rail)).width, oracle.sidebar.expandedWidth);

    const accountTrigger = page.getByRole("button", { name: /Dev User|蓝湖|本地用户/ });
    await accountTrigger.click();
    await page.getByRole("button", { name: "深色", exact: true }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);

    const toolbarNames = ["收起侧栏", "搜索", "筛选"] as const;
    const toolbarKeys = oracle.sidebar.toolbar.order;
    const toolbarButtons = toolbarNames.map((name) => page.getByRole("button", { name, exact: true }));
    compare("/sidebar/toolbar/order", toolbarKeys, ["toggle", "search", "filter"]);
    compare(
      "/sidebar/toolbar/order:rendered",
      await Promise.all(toolbarButtons.map((button) => button.getAttribute("title"))),
      toolbarNames,
    );
    for (const [index, button] of toolbarButtons.entries()) {
      const key = toolbarKeys[index];
      const box = await boxOf(button);
      compareNumber(`/sidebar/toolbar/x/${key}`, box.x, oracle.sidebar.toolbar.x[key]);
      compareNumber(`/sidebar/toolbar/${key}/y`, box.y, oracle.sidebar.toolbar.y);
      compareNumber(`/sidebar/toolbar/${key}/width`, box.width, oracle.sidebar.toolbar.buttonSize);
      compareNumber(`/sidebar/toolbar/${key}/height`, box.height, oracle.sidebar.toolbar.buttonSize);
      compareNumber(`/sidebar/toolbar/${key}/iconSize`, (await boxOf(button.locator("svg"))).width, oracle.sidebar.toolbar.iconSize);
      compare(
        `/sidebar/toolbar/${key}/dragRegion`,
        (await button.getAttribute("data-no-drag")) !== null,
        oracle.sidebar.toolbar.dragRegion === "no-drag",
      );
      const style = await computedStyle(button, ["border-radius", "background-color", "color"]);
      compare(`/sidebar/toolbar/${key}/radius`, px(style["border-radius"]), oracle.sidebar.toolbar.radius);
      compare(`/sidebar/toolbar/${key}/defaultBackground`, normalizeColor(style["background-color"]), oracle.sidebar.toolbar.defaultBackground);
      compare(`/sidebar/toolbar/${key}/darkForeground`, style.color, oracle.sidebar.toolbar.darkForeground);
      if (index > 0) {
        const previous = await boxOf(toolbarButtons[index - 1]);
        compareNumber(`/sidebar/toolbar/gap/${key}`, box.x - previous.right, oracle.sidebar.toolbar.gap, 0.25);
      }
    }
    await toolbarButtons[1].hover();
    compare(
      "/sidebar/toolbar/darkHoverBackground",
      (await computedStyle(toolbarButtons[1], ["background-color"]))["background-color"],
      oracle.sidebar.toolbar.darkHoverBackground,
    );
    await attachUiState(page, testInfo, "entry-dark-toolbar-exact-state");

    await toolbarButtons[1].click();
    const search = page.getByRole("dialog", { name: "搜索对话" });
    const searchBox = await boxOf(search);
    compareNumber("/search/width", searchBox.width, oracle.search.width);
    compareNumber("/search/height", searchBox.height, oracle.search.height);
    const searchStyle = await computedStyle(search, ["border-radius", "background-color"]);
    compare("/search/radius", px(searchStyle["border-radius"]), oracle.search.radius);
    compare("/search/darkBackground", searchStyle["background-color"], oracle.search.darkBackground);
    const searchOverlay = search.locator("..");
    compare("/search/overlay", (await computedStyle(searchOverlay, ["background-color"]))["background-color"], oracle.search.overlay);
    await attachUiState(page, testInfo, "transition-dark-search-exact-state");
    await page.keyboard.press("Escape");

    for (let index = 0; index <= oracle.search.emptyQueryLimit; index += 1) {
      await page.getByRole("button", { name: "新建任务", exact: true }).click();
      const composer = page.getByRole("textbox", { name: /今天帮你做些什么/ });
      await composer.fill(`oracle-search-${String(index).padStart(2, "0")}`);
      await composer.press("Enter");
      await expect(page.getByText(`收到：oracle-search-${String(index).padStart(2, "0")}`, { exact: true })).toBeVisible();
    }
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    const emptyQueryButtons = page.getByRole("dialog", { name: "搜索对话" }).getByRole("button");
    compare("/search/emptyQueryLimit", (await emptyQueryButtons.count()) - 1, oracle.search.emptyQueryLimit);
    await page.keyboard.press("Escape");

    await page.getByRole("button", { name: "筛选", exact: true }).click();
    const filter = page.getByRole("dialog", { name: "筛选对话" });
    const filterBox = await boxOf(filter);
    compareNumber("/filter/width", filterBox.width, oracle.filter.width);
    compareNumber("/filter/height", filterBox.height, oracle.filter.height);
    compareNumber("/filter/anchor/x", filterBox.x, oracle.filter.anchor.x);
    compareNumber("/filter/anchor/y", filterBox.y, oracle.filter.anchor.y);
    const filterStyle = await computedStyle(filter, ["border-radius", "background-color", "padding"]);
    compare("/filter/radius", px(filterStyle["border-radius"]), oracle.filter.radius);
    compare("/filter/padding", px(filterStyle.padding), oracle.filter.padding);
    compare("/filter/darkBackground", filterStyle["background-color"], oracle.filter.darkBackground);
    const statusLabels: Record<string, string> = { all: "全部", running: "进行中", completed: "已完成", failed: "失败", pending: "待处理", cancelled: "已取消" };
    const timeLabels: Record<string, string> = { all: "全部时间", today: "今天", last7Days: "最近 7 天", last30Days: "最近 30 天" };
    compare(
      "/filter/statusOptions",
      await filter.locator("section").nth(0).getByRole("button").allTextContents(),
      oracle.filter.statusOptions.map((value) => statusLabels[value]),
    );
    compare(
      "/filter/timeOptions",
      await filter.locator("section").nth(1).getByRole("button").allTextContents(),
      oracle.filter.timeOptions.map((value) => timeLabels[value]),
    );
    await attachUiState(page, testInfo, "transition-dark-filter-exact-state");
    await page.keyboard.press("Escape");

    await accountTrigger.click();
    const menu = page.getByRole("menu", { name: "用户中心" });
    const panel = menu.locator("..");
    const menuBox = await boxOf(menu);
    const panelBox = await boxOf(panel);
    const triggerBox = await boxOf(accountTrigger);
    compareNumber("/accountMenu/width", menuBox.width, oracle.accountMenu.width);
    compareNumber("/accountMenu/anchorGap", triggerBox.y - panelBox.bottom, oracle.accountMenu.anchorGap, 0.25);
    compare("/accountMenu/viewportMargin:left", panelBox.x >= oracle.accountMenu.viewportMargin, true);
    compare("/accountMenu/viewportMargin:right", innerWidthOf(await page.evaluate(() => innerWidth)) - panelBox.right >= oracle.accountMenu.viewportMargin, true);
    const panelStyle = await computedStyle(panel, ["border-radius", "background-color", "box-shadow", "max-height"]);
    compare("/accountMenu/radius", px(panelStyle["border-radius"]), oracle.accountMenu.radius);
    compare("/accountMenu/darkBackground", panelStyle["background-color"], oracle.accountMenu.darkBackground);
    compare("/accountMenu/darkShadow", normalizeShadow(panelStyle["box-shadow"]), normalizeShadow(oracle.accountMenu.darkShadow));
    compare("/accountMenu/maxHeight", px(panelStyle["max-height"]), calcMaxHeight(oracle.accountMenu.maxHeight, await page.evaluate(() => innerHeight)));
    const menuStyle = await computedStyle(menu, ["padding"]);
    compare("/accountMenu/padding", px(menuStyle.padding), oracle.accountMenu.padding);
    compareNumber("/accountMenu/headerHeight", (await boxOf(menu.locator(":scope > div").first())).height, oracle.accountMenu.headerHeight, 0.25);

    const rows = menu.locator(":scope > *");
    const actualOrder: string[] = [];
    const rowHeights: number[] = [];
    for (let index = 0; index < await rows.count(); index += 1) {
      const row = rows.nth(index);
      actualOrder.push(await accountRowKind(row));
      const kind = actualOrder.at(-1);
      if (kind !== "profile" && kind !== "divider") rowHeights.push((await boxOf(row)).height);
    }
    compare("/accountMenu/qworkRowOrder", actualOrder, oracle.accountMenu.qworkRowOrder);
    for (const [index, height] of rowHeights.entries()) {
      const [minimum, maximum] = oracle.accountMenu.rowHeightRange;
      if (height < minimum || height > maximum) {
        mismatches.push({ pointer: `/accountMenu/rowHeightRange/rendered/${index}`, expected: oracle.accountMenu.rowHeightRange, actual: height });
      }
    }
    compare(
      "/source/brandPolicy",
      oracle.source.brandPolicy,
      "QWork identity, account data, and supported QWork actions are retained",
    );
    compare("/source/brandPolicy:QWork-identity", await page.getByRole("button", { name: "连接 QWork", exact: true }).count(), 1);
    compare("/source/brandPolicy:QWork-actions", await menu.getByRole("menuitem").count() >= 8, true);
    await attachUiState(page, testInfo, "final-dark-account-menu-exact-state");

    await testInfo.attach("oracle-mismatches.json", {
      body: Buffer.from(`${JSON.stringify(mismatches, null, 2)}\n`),
      contentType: "application/json",
    });
    expect(mismatches, "every locally executable sidebar/account Oracle pointer must match").toEqual([]);
  } finally {
    await cleanup(app, home);
  }
});

function same(actual: unknown, expected: unknown): boolean {
  return JSON.stringify(actual) === JSON.stringify(expected);
}

function px(value: string): number {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}

function normalizeColor(value: string): string {
  return value === "rgba(0, 0, 0, 0)" ? "transparent" : value;
}

function normalizeShadow(value: string): string {
  return value.trim().replace(/ 0px$/, "");
}

function calcMaxHeight(value: string, viewportHeight: number): number {
  const match = /^calc\(100vh - (\d+)px\)$/.exec(value);
  if (!match) return Number.NaN;
  return viewportHeight - Number(match[1]);
}

function innerWidthOf(value: number): number {
  return value;
}

async function accountRowKind(row: Locator): Promise<string> {
  if (await row.getByTestId("account-menu-username").count()) return "profile";
  if ((await row.getAttribute("role")) === "separator") return "divider";
  const text = (await row.innerText()).replace(/\s+/g, " ").trim();
  if (text.includes("升级")) return "entitlement";
  if (text.includes("Buddy 加油站")) return "buddyStation";
  if (text.includes("体验「项目」")) return "tryProject";
  if (text.includes("积分余额")) return "credits";
  if (text.includes("成长计划")) return "growth";
  if (text === "设置") return "settings";
  if (text.includes("浅色") && text.includes("深色")) return "appearance";
  if (text === "帮助与反馈") return "help";
  if (text === "检查更新") return "updates";
  if (text === "退出登录") return "logout";
  return `unknown:${text}`;
}
