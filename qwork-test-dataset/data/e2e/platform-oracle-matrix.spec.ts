import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import {
  expect,
  test,
  type ElectronApplication,
  type Page,
  type TestInfo,
} from "@playwright/test";
import {
  attachUiState,
  boxOf,
  computedStyle,
  setContentSize,
} from "../../../../../e2e/fixtures/workbuddy-ui";
import {
  cleanup,
  createTestHome,
  createWorkspace,
  openApp,
} from "./fixtures/launch-isolated";

const execFileAsync = promisify(execFile);
const skillRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const matrixPath = path.join(skillRoot, "references/platform-oracle-matrix.json");
const comparatorPath = path.join(skillRoot, "scripts/compare_visual_frame.py");

type Platform = "darwin" | "win32";
type Theme = "light" | "dark";
type Capture = {
  id: string;
  platform: Platform;
  theme: Theme;
  dpi_percent: number;
  viewport: { width: number; height: number };
  state_set: string;
  baseline_root: string | null;
  baseline_status: string;
};
type PlatformMatrix = {
  policy: { max_diff_ratio: number; geometry_tolerance_css_px: number };
  state_sets: Record<string, string[]>;
  captures: Capture[];
};
type ShellOracle = {
  platform: {
    darwin: {
      titleBarStyle: string;
      shortcutModifier: string;
      fullscreenTrafficLightOffset: number;
      fullscreenExpandedToggle: { x: number; y: number; width: number; height: number };
      fullscreenCollapsedToggle: { x: number; y: number; width: number; height: number };
    };
    win32: {
      titleBarStyle: string;
      shortcutModifier: string;
      showTrafficLightSafeArea: boolean;
      pixelGoldenDpiPercent: number;
      smokeDpiPercent: number;
    };
  };
};
type SidebarOracle = {
  sidebar: { collapsed: { darwinFullscreenToggleX: number } };
};
type MatrixFailure = {
  capture_id: string;
  state: string;
  classification: "missing-approved-workbuddy-frame-set" | "pixel-mismatch";
  detail: string;
};

test("WB-UI-PLATFORM-DARWIN-001 @darwin | 原生全屏、快捷键与标题栏逐字段匹配 WorkBuddy", async ({}, testInfo) => {
  expect(process.platform, "this Case must run on its registered native platform").toBe("darwin");
  const shell = await readJson<ShellOracle>(path.resolve("e2e/oracles/workbuddy-5.3.5-shell-home.json"));
  const sidebar = await readJson<SidebarOracle>(path.resolve("e2e/oracles/workbuddy-5.3.5-sidebar-account.json"));
  const expected = shell.platform.darwin;
  const home = await createTestHome("platform-darwin-runtime");
  await createWorkspace(home);
  let app: ElectronApplication | undefined;
  try {
    ({ app } = await openApp(home));
    const page = await app.firstWindow();
    await setContentSize(app, page, { width: 1440, height: 900 });
    await assertBuiltTitleBarStyle(expected.titleBarStyle);
    expect(await observedShortcutModifier(app), "/platform/darwin/shortcutModifier").toBe(expected.shortcutModifier);

    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]?.setFullScreen(true));
    await expect.poll(() => page.evaluate(() => window.workGui.window.getState())).toMatchObject({ isFullScreen: true });
    await compareToggle(page.getByRole("button", { name: "收起侧栏", exact: true }), expected.fullscreenExpandedToggle, "fullscreenExpandedToggle");
    await compareTrafficOffset(page, expected.fullscreenTrafficLightOffset);
    await attachUiState(page, testInfo, "entry");

    await page.getByRole("button", { name: "收起侧栏", exact: true }).click();
    const expand = page.getByRole("button", { name: "展开侧栏", exact: true });
    await expect(expand).toBeVisible();
    await compareToggle(expand, expected.fullscreenCollapsedToggle, "fullscreenCollapsedToggle");
    expect((await boxOf(expand)).x, "/sidebar/collapsed/darwinFullscreenToggleX").toBe(
      sidebar.sidebar.collapsed.darwinFullscreenToggleX,
    );
    await attachUiState(page, testInfo, "transition");

    await triggerSidebarShortcut(app, page);
    await expect(page.getByRole("button", { name: "收起侧栏", exact: true })).toBeVisible();
    await compareToggle(page.getByRole("button", { name: "收起侧栏", exact: true }), expected.fullscreenExpandedToggle, "fullscreenExpandedToggle-after-shortcut");
    await attachUiState(page, testInfo, "final-state");
  } finally {
    await cleanup(app, home);
  }
});

test("WB-UI-PLATFORM-WIN32-001 @win32-100 | 100% DPI 标题栏、控制区与快捷键逐字段匹配 WorkBuddy", async ({}, testInfo) => {
  expect(process.platform, "this Case must run on its registered native platform").toBe("win32");
  const shell = await readJson<ShellOracle>(path.resolve("e2e/oracles/workbuddy-5.3.5-shell-home.json"));
  const expected = shell.platform.win32;
  const home = await createTestHome("platform-win32-100-runtime");
  await createWorkspace(home);
  let app: ElectronApplication | undefined;
  try {
    ({ app } = await openApp(home));
    const page = await app.firstWindow();
    await setContentSize(app, page, { width: 1440, height: 900 });
    await assertBuiltTitleBarStyle(expected.titleBarStyle);
    expect(await displayDpiPercent(app), "/platform/win32/pixelGoldenDpiPercent").toBe(expected.pixelGoldenDpiPercent);
    expect(expected.shortcutModifier).toBe("Ctrl");
    expect(expected.showTrafficLightSafeArea).toBe(false);
    await expect(page.getByTestId("traffic-light-safe-area")).toHaveCount(0);
    await expect(page.getByTestId("windows-window-controls")).toBeVisible();
    await attachUiState(page, testInfo, "entry");

    await page.getByRole("button", { name: "收起侧栏", exact: true }).click();
    await expect(page.getByRole("button", { name: "展开侧栏", exact: true })).toBeVisible();
    await attachUiState(page, testInfo, "transition");

    await page.keyboard.press(`${expected.shortcutModifier}+b`);
    await expect(page.getByRole("button", { name: "收起侧栏", exact: true })).toBeVisible();
    await attachUiState(page, testInfo, "final-state");
  } finally {
    await cleanup(app, home);
  }
});

test("WB-UI-PLATFORM-WIN32-002 @win32-125 | 125% DPI 冒烟保持标题栏与主题可用", async ({}, testInfo) => {
  expect(process.platform, "this Case must run on its registered native platform").toBe("win32");
  const shell = await readJson<ShellOracle>(path.resolve("e2e/oracles/workbuddy-5.3.5-shell-home.json"));
  const expected = shell.platform.win32;
  const home = await createTestHome("platform-win32-125-runtime");
  await createWorkspace(home);
  let app: ElectronApplication | undefined;
  try {
    ({ app } = await openApp(home));
    const page = await app.firstWindow();
    await setContentSize(app, page, { width: 1280, height: 800 });
    expect(await displayDpiPercent(app), "/platform/win32/smokeDpiPercent").toBe(expected.smokeDpiPercent);
    await expect(page.getByTestId("windows-window-controls")).toBeVisible();
    await attachUiState(page, testInfo, "entry");
    await setTheme(page, "dark");
    await attachUiState(page, testInfo, "transition");
    await setTheme(page, "light");
    await attachUiState(page, testInfo, "final-state");
  } finally {
    await cleanup(app, home);
  }
});

test("WB-UI-PIXEL-DARWIN-001 @darwin | 浅深主题与三档视口逐状态对比 WorkBuddy Golden", async ({}, testInfo) => {
  const failures = await runPixelMatrix("darwin", new Set([200]), testInfo);
  expect(failures, "approved WorkBuddy frame sets must exist and every exact Darwin frame comparison must pass").toEqual([]);
});

test("WB-UI-PIXEL-WIN32-001 @win32-100 | 100% DPI 浅深主题与三档视口逐状态对比 WorkBuddy Golden", async ({}, testInfo) => {
  const failures = await runPixelMatrix("win32", new Set([100]), testInfo);
  expect(failures, "approved WorkBuddy frame sets must exist and every exact Windows 100 percent frame comparison must pass").toEqual([]);
});

test("WB-UI-PIXEL-WIN32-002 @win32-125 | 125% DPI 浅深主题逐状态对比 WorkBuddy Golden", async ({}, testInfo) => {
  const failures = await runPixelMatrix("win32", new Set([125]), testInfo);
  expect(failures, "approved WorkBuddy frame sets must exist and every exact Windows 125 percent frame comparison must pass").toEqual([]);
});

async function runPixelMatrix(platform: Platform, dpis: Set<number>, testInfo: TestInfo): Promise<MatrixFailure[]> {
  expect(process.platform, "this Case must run on its registered native platform").toBe(platform);
  const matrix = await readJson<PlatformMatrix>(matrixPath);
  const captures = matrix.captures.filter((capture) => capture.platform === platform && dpis.has(capture.dpi_percent));
  expect(captures.length, "the platform/DPI route must resolve at least one frozen coordinate").toBeGreaterThan(0);
  const home = await createTestHome(`pixel-${platform}-${[...dpis].join("-")}`);
  await createWorkspace(home);
  const failures: MatrixFailure[] = [];
  let app: ElectronApplication | undefined;
  let attachedEntry = false;
  try {
    ({ app } = await openApp(home));
    const page = await app.firstWindow();
    const observedDpi = await displayDpiPercent(app);
    for (const capture of captures) {
      expect(observedDpi, `${capture.id} must run at its frozen native DPI`).toBe(capture.dpi_percent);
      await setContentSize(app, page, capture.viewport);
      await setTheme(page, capture.theme);
      const states = matrix.state_sets[capture.state_set];
      expect(states, `unknown state set ${capture.state_set}`).toBeTruthy();
      for (const state of states) {
        await enterState(page, state);
        const actual = testInfo.outputPath(`${capture.id}-${state}.png`);
        await page.screenshot({ path: actual, animations: "disabled" });
        await attachUiState(page, testInfo, `${capture.id}-${state}`);
        if (!attachedEntry) {
          await attachUiState(page, testInfo, "entry");
          attachedEntry = true;
        }
        if (!capture.baseline_root) {
          failures.push({
            capture_id: capture.id,
            state,
            classification: "missing-approved-workbuddy-frame-set",
            detail: capture.baseline_status,
          });
        } else {
          const baselineRoot = resolveInsideSkill(capture.baseline_root);
          const baseline = path.join(baselineRoot, `${state}.png`);
          const output = testInfo.outputPath(`${capture.id}-${state}-comparison`);
          try {
            await execFileAsync("python3", [
              comparatorPath,
              "--actual", actual,
              "--baseline", baseline,
              "--output", output,
              "--max-diff-ratio", String(matrix.policy.max_diff_ratio),
            ]);
          } catch (error) {
            failures.push({
              capture_id: capture.id,
              state,
              classification: "pixel-mismatch",
              detail: error instanceof Error ? error.message : String(error),
            });
          }
        }
        await leaveState(page, state);
      }
    }
    await attachUiState(page, testInfo, "final-state");
    await testInfo.attach("platform-pixel-matrix-result.json", {
      body: Buffer.from(`${JSON.stringify({ platform, dpis: [...dpis], captures: captures.map(({ id }) => id), failures }, null, 2)}\n`),
      contentType: "application/json",
    });
  } finally {
    await cleanup(app, home);
  }
  return failures;
}

async function enterState(page: Page, state: string): Promise<void> {
  if (state === "shell-home") return;
  if (state === "sidebar-hover") {
    await page.getByRole("button", { name: "搜索", exact: true }).hover();
    return;
  }
  if (state === "sidebar-collapsed") {
    await page.getByRole("button", { name: "收起侧栏", exact: true }).click();
    await expect(page.getByRole("button", { name: "展开侧栏", exact: true })).toBeVisible();
    return;
  }
  if (state === "search-dialog") {
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "搜索对话" })).toBeVisible();
    return;
  }
  if (state === "filter-popover") {
    await page.getByRole("button", { name: "筛选", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "筛选对话" })).toBeVisible();
    return;
  }
  if (state === "account-menu") {
    await accountButton(page).click();
    await expect(page.getByRole("menu", { name: "用户中心" })).toBeVisible();
    return;
  }
  throw new Error(`unsupported visual state: ${state}`);
}

async function leaveState(page: Page, state: string): Promise<void> {
  if (state === "sidebar-collapsed") {
    await page.getByRole("button", { name: "展开侧栏", exact: true }).click();
    return;
  }
  if (["search-dialog", "filter-popover", "account-menu"].includes(state)) {
    await page.keyboard.press("Escape");
    return;
  }
  if (state === "sidebar-hover") await page.mouse.move(600, 400);
}

async function setTheme(page: Page, theme: Theme): Promise<void> {
  if ((await page.locator("html").getAttribute("data-theme")) === theme) return;
  await accountButton(page).click();
  await page.getByRole("button", { name: theme === "dark" ? "深色" : "浅色", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
}

function accountButton(page: Page) {
  return page.getByRole("button", { name: /Dev User|蓝湖|本地用户/ });
}

async function compareToggle(locator: ReturnType<Page["getByRole"]>, expected: { x: number; y: number; width: number; height: number }, pointer: string): Promise<void> {
  const actual = await boxOf(locator);
  for (const field of ["x", "y", "width", "height"] as const) {
    expect(Math.abs(actual[field] - expected[field]), `/platform/darwin/${pointer}/${field}`).toBeLessThanOrEqual(2);
  }
}

async function compareTrafficOffset(page: Page, expected: number): Promise<void> {
  const style = await computedStyle(page.getByTestId("window-chrome"), ["--mac-traffic-light-offset"]);
  expect(Number.parseFloat(style["--mac-traffic-light-offset"]), "/platform/darwin/fullscreenTrafficLightOffset").toBe(expected);
}

async function triggerSidebarShortcut(app: ElectronApplication, page: Page): Promise<void> {
  await app.evaluate(({ BrowserWindow, Menu }) => {
    const window = BrowserWindow.getAllWindows()[0];
    const item = Menu.getApplicationMenu()?.getMenuItemById("view.toggleSidebar");
    if (!window || !item) throw new Error("native sidebar menu is missing");
    item.click(undefined, window, undefined);
  });
  await page.bringToFront();
}

async function observedShortcutModifier(app: ElectronApplication): Promise<string> {
  const accelerator = await app.evaluate(({ Menu }) => Menu.getApplicationMenu()?.getMenuItemById("view.toggleSidebar")?.accelerator ?? null);
  if (!accelerator?.startsWith("CmdOrCtrl+")) throw new Error(`unexpected native accelerator: ${accelerator}`);
  return "Command";
}

async function displayDpiPercent(app: ElectronApplication): Promise<number> {
  return app.evaluate(({ BrowserWindow, screen }) => {
    const window = BrowserWindow.getAllWindows()[0];
    if (!window) throw new Error("main window is missing");
    return Math.round(screen.getDisplayMatching(window.getBounds()).scaleFactor * 100);
  });
}

async function assertBuiltTitleBarStyle(expected: string): Promise<void> {
  const appRoot = process.env.QWORK_E2E_APP_ROOT?.trim();
  if (!appRoot) throw new Error("QWORK_E2E_APP_ROOT is required");
  const bundle = await fs.readFile(path.join(appRoot, "out/main/index.js"), "utf8");
  const values = [...bundle.matchAll(/titleBarStyle\s*:\s*["']([^"']+)["']/g)].map((match) => match[1]);
  expect(values, "the executed main-process bundle must preserve the platform titleBarStyle contract").toContain(expected);
}

function resolveInsideSkill(relative: string): string {
  const target = path.resolve(skillRoot, relative);
  const rel = path.relative(skillRoot, target);
  if (!rel || rel.startsWith("..") || path.isAbsolute(rel)) throw new Error(`baseline root escapes Dataset Skill: ${relative}`);
  return target;
}

async function readJson<T>(target: string): Promise<T> {
  return JSON.parse(await fs.readFile(target, "utf8")) as T;
}
