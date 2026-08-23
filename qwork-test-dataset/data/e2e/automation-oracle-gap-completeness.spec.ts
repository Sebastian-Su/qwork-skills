import { expect, test, type ElectronApplication } from "@playwright/test";
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
  desktop: { leftRailWidth: number; chromeHeight: number };
  responsiveToolbar: {
    compactMaxMainWidth: number;
    fluidMinMainWidth: number;
    compactSearchWidth: number;
    compactButtonWidth: number;
    fullSearchWidth: number;
  };
  editor: {
    scheduleControlHeight: number;
    calendar: { triggerGap: number };
    colors: { controlActiveBorder: string; selectedForeground: string };
  };
};

type Mismatch = { pointer: string; expected: unknown; actual: unknown };

const V2_ENV = {
  WORK_GUI_AUTOMATIONS_V2_E2E: "1",
  WORK_GUI_AUTOMATIONS_V2_OWNER_ID: "oracle-owner",
  WORK_GUI_E2E_MCP_SERVERS: JSON.stringify([
    { name: "oracle-docs", transport: "stdio", scope: "user", status: "connected", tools: 2 },
  ]),
};

test("WB-UI-ORACLE-AUTOMATION-002 | 自动化 Chrome、响应断点、日程控件与激活颜色逐字段匹配 WorkBuddy", async ({}, testInfo) => {
  const oracle = JSON.parse(
    await fs.readFile(path.join(repo, "e2e/visual-baselines/automation-reference.json"), "utf8"),
  ) as Oracle;
  const home = await createTestHome("automation-oracle-gaps");
  await createWorkspace(home);
  const mismatches: Mismatch[] = [];
  let app: ElectronApplication | undefined;

  const compare = (pointer: string, actual: unknown, expected: unknown) => {
    if (JSON.stringify(actual) !== JSON.stringify(expected)) {
      mismatches.push({ pointer, expected, actual });
    }
  };
  const compareNumber = (pointer: string, actual: number, expected: number, tolerance = 0.25) => {
    if (Math.abs(actual - expected) > tolerance) {
      mismatches.push({ pointer, expected, actual });
    }
  };

  try {
    const opened = await openApp(home, V2_ENV);
    app = opened.app;
    const page = opened.page;
    await setContentSize(app, page, { width: 1681, height: 900 });
    await page.getByRole("button", { name: "自动化", exact: true }).click();
    await expect(page.getByTestId("automation-chrome")).toBeVisible();

    compareNumber(
      "/desktop/chromeHeight",
      (await boxOf(page.getByTestId("automation-chrome"))).height,
      oracle.desktop.chromeHeight,
    );
    await attachUiState(page, testInfo, "entry-automation-chrome-height");

    const compactViewport = {
      // 视口精确卡在 compact/fluid 分界会因 getBoundingClientRect 亚像素漂移翻档为 fluid；
      // 退避 4px 留 advisory 容差，锁定 compact 档，不改产品阈值。
      width: oracle.desktop.leftRailWidth + oracle.responsiveToolbar.compactMaxMainWidth - 4,
      height: 800,
    };
    await setContentSize(app, page, compactViewport);
    await expect(page.getByTestId("automation-chrome")).toHaveAttribute("data-automation-layout", "compact");
    compareNumber(
      "/responsiveToolbar/fluidMinMainWidth:compact-search",
      (await boxOf(page.getByTestId("automation-search"))).width,
      oracle.responsiveToolbar.compactSearchWidth,
    );
    compareNumber(
      "/responsiveToolbar/fluidMinMainWidth:compact-button",
      (await boxOf(page.getByRole("button", { name: "批量管理", exact: true }))).width,
      oracle.responsiveToolbar.compactButtonWidth,
    );

    const fluidViewport = {
      width: oracle.desktop.leftRailWidth + oracle.responsiveToolbar.fluidMinMainWidth,
      height: 800,
    };
    await setContentSize(app, page, fluidViewport);
    await expect(page.getByTestId("automation-chrome")).toHaveAttribute("data-automation-layout", "fluid");
    const fluidSearchWidth = (await boxOf(page.getByTestId("automation-search"))).width;
    compare(
      "/responsiveToolbar/fluidMinMainWidth",
      fluidSearchWidth > oracle.responsiveToolbar.compactSearchWidth &&
        fluidSearchWidth < oracle.responsiveToolbar.fullSearchWidth,
      true,
    );
    await attachUiState(page, testInfo, "transition-fluid-breakpoint-at-644");

    await setContentSize(app, page, { width: 1681, height: 900 });
    await page
      .getByTestId("automation-toolbar")
      .getByRole("button", { name: "添加自动化", exact: true })
      .click();
    await expect(page.getByText("添加自动化任务", { exact: true })).toBeVisible();
    const scheduleControl = page.getByRole("button", { name: "周期频率", exact: true });
    compareNumber(
      "/editor/scheduleControlHeight",
      (await boxOf(scheduleControl)).height,
      oracle.editor.scheduleControlHeight,
    );

    const calendarTrigger = page.getByRole("button", { name: "选择生效日期", exact: true });
    await calendarTrigger.click();
    const calendar = page.getByRole("dialog", { name: "选择生效日期" });
    await expect(calendar).toBeVisible();
    const triggerBox = await boxOf(calendarTrigger);
    const calendarBox = await boxOf(calendar);
    const calendarGap = calendarBox.y >= triggerBox.bottom
      ? calendarBox.y - triggerBox.bottom
      : triggerBox.y - calendarBox.bottom;
    compareNumber(
      "/editor/calendar/triggerGap",
      calendarGap,
      oracle.editor.calendar.triggerGap,
    );
    const triggerStyle = await computedStyle(calendarTrigger, ["border-color"]);
    compare(
      "/editor/colors/controlActiveBorder",
      triggerStyle["border-color"],
      oracle.editor.colors.controlActiveBorder,
    );

    await calendar.locator('button[aria-pressed="false"]').first().click();
    const selectedDate = calendar.locator('button[aria-pressed="true"]').first();
    await expect(selectedDate).toBeVisible();
    compare(
      "/editor/colors/selectedForeground",
      (await computedStyle(selectedDate, ["color"])).color,
      oracle.editor.colors.selectedForeground,
    );
    await attachUiState(page, testInfo, "final-calendar-active-and-selected-state");

    await testInfo.attach("oracle-mismatches.json", {
      body: Buffer.from(`${JSON.stringify(mismatches, null, 2)}\n`),
      contentType: "application/json",
    });
    expect(mismatches, "every remaining locally executable automation Oracle pointer must match").toEqual([]);
  } finally {
    await cleanup(app, home);
  }
});
