import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import {
  attachUiState,
  boxOf,
  setContentSize,
} from "../../../../../e2e/fixtures/workbuddy-ui";
import {
  cleanup,
  createTestHome,
  createWorkspace,
  openApp,
  repo,
} from "./fixtures/launch-isolated";

type SourceControl = {
  tag: string;
  role: string | null;
  ariaLabel: string | null;
  title: string | null;
  text: string;
  box: { x: number; y: number; width: number; height: number };
};

type SourceState = {
  state: string;
  controls: SourceControl[];
};

type Mismatch = { pointer: string; expected: unknown; actual: unknown };

const SOURCE_STATE = path.join(
  repo,
  ".agents/skills/qwork-test-dataset/data/evidence/workbuddy-cdp/5.3.12-surfaces-v4/surface-library-灵感.json",
);

test("WB-UI-INSPIRATION-001 | 灵感搜索、分类、收藏与卡片全集逐状态匹配 WorkBuddy", async ({}, testInfo) => {
  const source = JSON.parse(await fs.readFile(SOURCE_STATE, "utf8")) as SourceState;
  const sourceCategories = source.controls
    .filter((control) => control.role === "tab" && control.box.x >= 288 && control.box.y >= 180);
  const categories = sourceCategories
    .map((control) => control.text);
  const sourceFavoriteButtons = source.controls.filter(
    (control) => control.tag === "button" && control.ariaLabel === "Add to favorites",
  );
  const sourceSearch = source.controls.find((control) => control.tag === "input");
  const sourceFavoritesView = source.controls.find((control) => control.text === "我的收藏");
  if (!sourceSearch || !sourceFavoritesView || sourceFavoriteButtons.length === 0) {
    throw new Error("frozen WorkBuddy inspiration source is incomplete");
  }

  const mismatches: Mismatch[] = [];
  const compare = (pointer: string, actual: unknown, expected: unknown) => {
    if (JSON.stringify(actual) !== JSON.stringify(expected)) {
      mismatches.push({ pointer, expected, actual });
    }
  };
  const compareNumber = (pointer: string, actual: number | null, expected: number, tolerance = 2) => {
    if (actual === null || Math.abs(actual - expected) > tolerance) {
      mismatches.push({ pointer, expected, actual });
    }
  };

  const home = await createTestHome("inspiration-causality");
  await createWorkspace(home);
  const sidecarLog = path.join(home, "sidecar-control.jsonl");
  let app: ElectronApplication | undefined;

  const open = async () => {
    const opened = await openApp(home, { E2E_SIDECAR_CONTROL_LOG: sidecarLog });
    app = opened.app;
    await setContentSize(opened.app, opened.page);
    await openInspiration(opened.page);
    return opened.page;
  };

  try {
    let page = await open();
    const main = page.getByTestId("main-content");
    const search = main.getByPlaceholder("搜索灵感");
    const renderedCategories = main.getByRole("tablist", { name: "灵感分类" }).getByRole("tab");
    const cards = main.getByRole("article");
    const favoriteButtons = main.getByRole("button", { name: /收藏|Add to favorites/ });
    const favoritesView = main.getByRole("button", { name: "我的收藏", exact: true });

    compare("/surface/heading", await main.getByRole("heading", { name: "灵感", exact: true }).count(), 1);
    compare("/categories/labels", await renderedCategories.allTextContents(), categories);
    compare("/catalog/cardCount", await cards.count(), sourceFavoriteButtons.length);
    compare("/favorites/accessibilityName", await main.getByRole("button", { name: "Add to favorites" }).count(), sourceFavoriteButtons.length);
    compare("/favorites/view/count", await favoritesView.count(), 1);
    compareNumber("/search/width", await widthOf(search), sourceSearch.box.width);
    compareNumber("/search/height", await heightOf(search), sourceSearch.box.height);
    compareNumber("/favorites/view/width", await widthOf(favoritesView), sourceFavoritesView.box.width);
    compareNumber("/favorites/view/height", await heightOf(favoritesView), sourceFavoritesView.box.height);
    compareNumber("/categories/height", await heightOf(renderedCategories.first()), sourceCategories[0].box.height);
    compareNumber("/favorites/button/width", await widthOf(favoriteButtons.first()), sourceFavoriteButtons[0].box.width);
    compareNumber("/favorites/button/height", await heightOf(favoriteButtons.first()), sourceFavoriteButtons[0].box.height);
    await attachUiState(page, testInfo, "entry-inspiration-source-closed-world");

    const beforeCategoryCount = await cards.count();
    const personalTab = renderedCategories.filter({ hasText: /^个人工作台$/ });
    if (await personalTab.count()) {
      await personalTab.click();
      compare("/categories/personal/selected", await personalTab.getAttribute("aria-selected"), "true");
      const afterCategoryCount = await cards.count();
      compare("/categories/personal/nonEmpty", afterCategoryCount > 0, true);
      compare("/categories/personal/reducesCatalog", afterCategoryCount < beforeCategoryCount, true);
    } else {
      mismatches.push({ pointer: "/categories/personal/selected", expected: "true", actual: "missing" });
    }

    if (await search.count()) {
      await search.fill("生活全能工作台");
      compare("/search/exactResultCount", await cards.count(), 1);
      compare("/search/exactResult", await main.getByRole("article", { name: "生活全能工作台" }).count(), 1);
    } else {
      mismatches.push({ pointer: "/search/exactResultCount", expected: 1, actual: "missing-search" });
    }
    await attachUiState(page, testInfo, "transition-inspiration-filtered-and-favorited");

    if (await search.count()) await search.fill("");
    const firstFavorite = favoriteButtons.first();
    if (await firstFavorite.count()) {
      await firstFavorite.click();
      compare("/favorites/toggled", await main.getByRole("button", { name: /已收藏/ }).count(), 1);
      if (await favoritesView.count()) {
        await favoritesView.click();
        compare("/favorites/view/cardCount", await cards.count(), 1);
      } else {
        mismatches.push({ pointer: "/favorites/view/cardCount", expected: 1, actual: "missing-view" });
      }
    } else {
      mismatches.push({ pointer: "/favorites/toggled", expected: 1, actual: "missing-button" });
    }

    await app.close();
    app = undefined;
    page = await open();
    const restartedMain = page.getByTestId("main-content");
    const restartedFavorites = restartedMain.getByRole("button", { name: "我的收藏", exact: true });
    if (await restartedFavorites.count()) {
      await restartedFavorites.click();
      compare("/favorites/restart/cardCount", await restartedMain.getByRole("article").count(), 1);
    } else {
      compare("/favorites/restart/cardCount", "missing-view", 1);
    }
    compare(
      "/forbidden/sidecarRequests",
      (await sidecarControlTypes(sidecarLog)).filter((type) => type !== "shutdown"),
      [],
    );
    await attachUiState(page, testInfo, "final-inspiration-favorite-persists-after-restart");

    await testInfo.attach("interaction-mismatches.json", {
      body: Buffer.from(`${JSON.stringify(mismatches, null, 2)}\n`),
      contentType: "application/json",
    });
    expect(mismatches, "every WorkBuddy inspiration interaction and closed-world UI invariant must match").toEqual([]);
  } finally {
    await cleanup(app, home);
  }
});

async function openInspiration(page: Page): Promise<void> {
  await page.getByRole("button", { name: "更多", exact: true }).click();
  await page.getByRole("menu", { name: "更多" }).getByRole("menuitem", { name: "灵感", exact: true }).click();
  await expect(page.getByTestId("main-content")).toBeVisible();
}

async function widthOf(locator: Locator): Promise<number | null> {
  return (await locator.count()) ? (await boxOf(locator.first())).width : null;
}

async function heightOf(locator: Locator): Promise<number | null> {
  return (await locator.count()) ? (await boxOf(locator.first())).height : null;
}

async function sidecarControlTypes(log: string): Promise<string[]> {
  return (await fs.readFile(log, "utf8").catch(() => ""))
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line) as { type?: string })
    .map((message) => message.type ?? "unknown");
}
