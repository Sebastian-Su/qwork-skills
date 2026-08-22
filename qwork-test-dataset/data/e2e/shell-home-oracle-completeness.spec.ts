import { expect, test, type ElectronApplication, type Locator } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import {
  attachUiState,
  boxOf,
  computedStyle,
  setContentSize,
  startDraft,
} from "../../../../../e2e/fixtures/ui-contract";
import {
  cleanup,
  createTestHome,
  createWorkspace,
  openApp,
  repo,
} from "./fixtures/launch-isolated";

type ThemeOracle = {
  bodyBackground: string;
  bodyColor: string;
  titleColor: string;
  newTaskBackground: string;
  newTaskColor: string;
  activeSceneBackground: string;
  activeSceneColor: string;
  inactiveSceneColor?: string;
  quickActionBackground?: string;
  quickActionShadow?: string;
};

type Oracle = {
  source: { brandPolicy: string };
  shared: {
    homeTitle: { height: number; fontSize: number; fontWeight: number; fontFamily: string };
    scenePill: { width: number; height: number; radius: number; fontSize: number; activeFontWeight: number; inactiveFontWeight: number };
    quickAction: { height: number; radius: number; fontSize: number; horizontalPadding: number; gap: number };
    composer: { targetContainerWidth: number; targetContainerHeight: number; editorMinHeight: number; fontSize: number; placeholder: string };
  };
  light: ThemeOracle;
  dark: ThemeOracle;
  platform: { darwin: { windowedCollapsedTrafficLightOffset: number } };
};

type Mismatch = { pointer: string; expected: unknown; actual: unknown };

test("WB-UI-ORACLE-SHELL-HOME-001 | Shell 首页主题、排版、场景与 Composer 逐字段匹配 WorkBuddy", async ({}, testInfo) => {
  const oracle = JSON.parse(
    await fs.readFile(path.join(repo, "e2e/visual-baselines/shell-home-reference.json"), "utf8"),
  ) as Oracle;
  const home = await createTestHome("shell-home-oracle");
  await createWorkspace(home);
  const mismatches: Mismatch[] = [];
  let app: ElectronApplication | undefined;

  const compare = (pointer: string, actual: unknown, expected: unknown) => {
    if (JSON.stringify(actual) !== JSON.stringify(expected)) {
      mismatches.push({ pointer, expected, actual });
    }
  };
  const compareNumber = (pointer: string, actual: number, expected: number, tolerance = 2) => {
    if (Math.abs(actual - expected) > tolerance) {
      mismatches.push({ pointer, expected, actual });
    }
  };

  try {
    const opened = await openApp(home);
    app = opened.app;
    const page = opened.page;
    await setContentSize(app, page);
    await startDraft(page);

    const body = page.locator("body");
    const title = page.getByRole("heading", { name: "WorkBuddy, 我帮你", exact: true });
    const newTask = page.getByRole("button", { name: "新建任务", exact: true });
    const activeScene = page.getByRole("tab", { name: "日常办公", exact: true });
    const inactiveScene = page.getByRole("tab", { name: "代码开发", exact: true });
    const quickAction = page.getByRole("button", { name: "文档处理", exact: true });
    const surface = page.getByTestId("composer-surface");
    const editor = page.getByTestId("composer-editor");
    const composer = page.getByRole("textbox", { name: /今天帮你做些什么/ });

    await compareTheme("/light", oracle.light, {
      body,
      title,
      newTask,
      activeScene,
      inactiveScene,
      quickAction,
    }, compare);
    await compareGeometry(oracle, { title, activeScene, inactiveScene, quickAction, surface, editor, composer }, compare, compareNumber);
    compare("/shared/composer/placeholder", await composer.getAttribute("placeholder"), oracle.shared.composer.placeholder);
    compare(
      "/source/brandPolicy",
      oracle.source.brandPolicy,
      "QWork names, logos, account data, and campaign copy are retained",
    );
    compare("/source/brandPolicy:qwork-name", await page.getByText("QWork v0.1.0", { exact: true }).count(), 1);
    compare("/source/brandPolicy:account", await page.getByRole("button", { name: /Dev User|蓝湖|本地用户/ }).count(), 1);
    compare("/source/brandPolicy:campaign-copy", await title.textContent(), "WorkBuddy, 我帮你");
    await attachUiState(page, testInfo, "entry-light-shell-home-exact-state");

    if (process.platform === "darwin") {
      await page.getByRole("button", { name: "收起侧栏", exact: true }).click();
      await expect(page.getByRole("button", { name: "展开侧栏", exact: true })).toBeVisible();
      const chromeStyle = await computedStyle(page.getByTestId("window-chrome"), ["--mac-traffic-light-offset"]);
      compare(
        "/platform/darwin/windowedCollapsedTrafficLightOffset",
        px(chromeStyle["--mac-traffic-light-offset"]),
        oracle.platform.darwin.windowedCollapsedTrafficLightOffset,
      );
      await page.getByRole("button", { name: "展开侧栏", exact: true }).click();
    }

    const account = page.getByRole("button", { name: /Dev User|蓝湖|本地用户/ });
    await account.click();
    await page.getByRole("button", { name: "深色", exact: true }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);
    await compareTheme("/dark", oracle.dark, {
      body,
      title,
      newTask,
      activeScene,
      inactiveScene,
      quickAction,
    }, compare);
    await attachUiState(page, testInfo, "transition-dark-shell-home-exact-state");

    await composer.fill("逐字段验证 Composer 不发送真实模型请求");
    compare("/shared/composer:remains-draft", await composer.inputValue(), "逐字段验证 Composer 不发送真实模型请求");
    await attachUiState(page, testInfo, "final-dark-composer-draft-exact-state");

    await testInfo.attach("oracle-mismatches.json", {
      body: Buffer.from(`${JSON.stringify(mismatches, null, 2)}\n`),
      contentType: "application/json",
    });
    expect(mismatches, "every locally executable Shell/Home Oracle pointer must match").toEqual([]);
  } finally {
    await cleanup(app, home);
  }
});

async function compareTheme(
  prefix: string,
  oracle: ThemeOracle,
  locators: {
    body: Locator;
    title: Locator;
    newTask: Locator;
    activeScene: Locator;
    inactiveScene: Locator;
    quickAction: Locator;
  },
  compare: (pointer: string, actual: unknown, expected: unknown) => void,
) {
  const body = await computedStyle(locators.body, ["background-color", "color"]);
  const title = await computedStyle(locators.title, ["color"]);
  const newTask = await computedStyle(locators.newTask, ["background-color", "color"]);
  const active = await computedStyle(locators.activeScene, ["background-color", "color"]);
  const inactive = await computedStyle(locators.inactiveScene, ["color"]);
  const quick = await computedStyle(locators.quickAction, ["background-color", "box-shadow"]);
  compare(`${prefix}/bodyBackground`, body["background-color"], oracle.bodyBackground);
  compare(`${prefix}/bodyColor`, body.color, oracle.bodyColor);
  compare(`${prefix}/titleColor`, title.color, oracle.titleColor);
  compare(`${prefix}/newTaskBackground`, newTask["background-color"], oracle.newTaskBackground);
  compare(`${prefix}/newTaskColor`, newTask.color, oracle.newTaskColor);
  compare(`${prefix}/activeSceneBackground`, active["background-color"], oracle.activeSceneBackground);
  compare(`${prefix}/activeSceneColor`, active.color, oracle.activeSceneColor);
  if (oracle.inactiveSceneColor !== undefined) compare(`${prefix}/inactiveSceneColor`, inactive.color, oracle.inactiveSceneColor);
  if (oracle.quickActionBackground !== undefined) compare(`${prefix}/quickActionBackground`, quick["background-color"], oracle.quickActionBackground);
  if (oracle.quickActionShadow !== undefined) compare(`${prefix}/quickActionShadow`, normalizeShadow(quick["box-shadow"]), normalizeShadow(oracle.quickActionShadow));
}

async function compareGeometry(
  oracle: Oracle,
  locators: {
    title: Locator;
    activeScene: Locator;
    inactiveScene: Locator;
    quickAction: Locator;
    surface: Locator;
    editor: Locator;
    composer: Locator;
  },
  compare: (pointer: string, actual: unknown, expected: unknown) => void,
  compareNumber: (pointer: string, actual: number, expected: number, tolerance?: number) => void,
) {
  const titleBox = await boxOf(locators.title);
  const titleStyle = await computedStyle(locators.title, ["font-size", "font-weight", "font-family"]);
  compareNumber("/shared/homeTitle/height", titleBox.height, oracle.shared.homeTitle.height);
  compare("/shared/homeTitle/fontSize", px(titleStyle["font-size"]), oracle.shared.homeTitle.fontSize);
  compare("/shared/homeTitle/fontWeight", Number(titleStyle["font-weight"]), oracle.shared.homeTitle.fontWeight);
  compare("/shared/homeTitle/fontFamily", normalizeFontFamily(titleStyle["font-family"]), normalizeFontFamily(oracle.shared.homeTitle.fontFamily));

  const activeBox = await boxOf(locators.activeScene);
  const activeStyle = await computedStyle(locators.activeScene, ["border-radius", "font-size", "font-weight"]);
  const inactiveStyle = await computedStyle(locators.inactiveScene, ["font-weight"]);
  compareNumber("/shared/scenePill/width", activeBox.width, oracle.shared.scenePill.width);
  compareNumber("/shared/scenePill/height", activeBox.height, oracle.shared.scenePill.height);
  compare("/shared/scenePill/radius", px(activeStyle["border-radius"]), oracle.shared.scenePill.radius);
  compare("/shared/scenePill/fontSize", px(activeStyle["font-size"]), oracle.shared.scenePill.fontSize);
  compare("/shared/scenePill/activeFontWeight", Number(activeStyle["font-weight"]), oracle.shared.scenePill.activeFontWeight);
  compare("/shared/scenePill/inactiveFontWeight", Number(inactiveStyle["font-weight"]), oracle.shared.scenePill.inactiveFontWeight);

  const quickBox = await boxOf(locators.quickAction);
  const quickStyle = await computedStyle(locators.quickAction, ["border-radius", "font-size", "padding-left", "padding-right", "column-gap"]);
  compareNumber("/shared/quickAction/height", quickBox.height, oracle.shared.quickAction.height);
  compare("/shared/quickAction/radius", px(quickStyle["border-radius"]), oracle.shared.quickAction.radius);
  compare("/shared/quickAction/fontSize", px(quickStyle["font-size"]), oracle.shared.quickAction.fontSize);
  compare("/shared/quickAction/horizontalPadding:left", px(quickStyle["padding-left"]), oracle.shared.quickAction.horizontalPadding);
  compare("/shared/quickAction/horizontalPadding:right", px(quickStyle["padding-right"]), oracle.shared.quickAction.horizontalPadding);
  compare("/shared/quickAction/gap", px(quickStyle["column-gap"]), oracle.shared.quickAction.gap);

  const surfaceBox = await boxOf(locators.surface);
  const editorStyle = await computedStyle(locators.editor, ["min-height"]);
  const composerStyle = await computedStyle(locators.composer, ["font-size"]);
  compareNumber("/shared/composer/targetContainerWidth", surfaceBox.width, oracle.shared.composer.targetContainerWidth);
  compareNumber("/shared/composer/targetContainerHeight", surfaceBox.height, oracle.shared.composer.targetContainerHeight);
  compare("/shared/composer/editorMinHeight", px(editorStyle["min-height"]), oracle.shared.composer.editorMinHeight);
  compare("/shared/composer/fontSize", px(composerStyle["font-size"]), oracle.shared.composer.fontSize);
}

function px(value: string): number {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}

function normalizeFontFamily(value: string): string {
  return value.replace(/["']/g, "").replace(/\s*,\s*/g, ", ").trim();
}

function normalizeShadow(value: string): string {
  return value
    .trim()
    .replace(/^(?:rgba\(0, 0, 0, 0\) 0px 0px 0px 0px,\s*)+/, "")
    .replace(/ 0px$/, "");
}
