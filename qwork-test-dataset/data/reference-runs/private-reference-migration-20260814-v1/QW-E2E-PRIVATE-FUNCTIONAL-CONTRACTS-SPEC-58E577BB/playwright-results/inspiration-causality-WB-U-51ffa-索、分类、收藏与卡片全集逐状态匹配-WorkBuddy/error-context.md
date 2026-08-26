# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: inspiration-causality.spec.ts >> WB-UI-INSPIRATION-001 | 灵感搜索、分类、收藏与卡片全集逐状态匹配 WorkBuddy
- Location: .agents/skills/qwork-test-dataset/data/e2e/inspiration-causality.spec.ts:38:1

# Error details

```
Error: every WorkBuddy inspiration interaction and closed-world UI invariant must match

expect(received).toEqual(expected) // deep equality

- Expected  -   1
+ Received  + 112

- Array []
+ Array [
+   Object {
+     "actual": 0,
+     "expected": 1,
+     "pointer": "/surface/heading",
+   },
+   Object {
+     "actual": Array [
+       "精选",
+       "日常办公",
+       "代码开发",
+       "设计创意",
+       "文档处理",
+       "金融服务",
+       "数据分析",
+       "个人工作台",
+       "深度研究",
+       "视频生成",
+       "幻灯片",
+       "产品管理",
+       "学习成长",
+       "生活方式",
+     ],
+     "expected": Array [
+       "全部",
+       "精选",
+       "个人工作台",
+       "办公协同",
+       "投资理财",
+       "内容创作",
+       "数据分析",
+       "效率工具",
+       "开发工具",
+       "知识与学习",
+       "信息与资讯",
+       "商业运营",
+       "旅行出行",
+       "智能体能力",
+     ],
+     "pointer": "/categories/labels",
+   },
+   Object {
+     "actual": 6,
+     "expected": 497,
+     "pointer": "/catalog/cardCount",
+   },
+   Object {
+     "actual": 0,
+     "expected": 497,
+     "pointer": "/favorites/accessibilityName",
+   },
+   Object {
+     "actual": 0,
+     "expected": 1,
+     "pointer": "/favorites/view/count",
+   },
+   Object {
+     "actual": 214,
+     "expected": 220,
+     "pointer": "/search/width",
+   },
+   Object {
+     "actual": 20,
+     "expected": 36,
+     "pointer": "/search/height",
+   },
+   Object {
+     "actual": null,
+     "expected": 81.046875,
+     "pointer": "/favorites/view/width",
+   },
+   Object {
+     "actual": null,
+     "expected": 36,
+     "pointer": "/favorites/view/height",
+   },
+   Object {
+     "actual": 32,
+     "expected": 28,
+     "pointer": "/categories/height",
+   },
+   Object {
+     "actual": 67.375,
+     "expected": 20,
+     "pointer": "/favorites/button/width",
+   },
+   Object {
+     "actual": 32,
+     "expected": 20,
+     "pointer": "/favorites/button/height",
+   },
+   Object {
+     "actual": false,
+     "expected": true,
+     "pointer": "/categories/personal/reducesCatalog",
+   },
+   Object {
+     "actual": 6,
+     "expected": 1,
+     "pointer": "/search/exactResultCount",
+   },
+   Object {
+     "actual": "missing-view",
+     "expected": 1,
+     "pointer": "/favorites/view/cardCount",
+   },
+   Object {
+     "actual": "missing-view",
+     "expected": 1,
+     "pointer": "/favorites/restart/cardCount",
+   },
+ ]
```

# Test source

```ts
  59  |   const compareNumber = (pointer: string, actual: number | null, expected: number, tolerance = 2) => {
  60  |     if (actual === null || Math.abs(actual - expected) > tolerance) {
  61  |       mismatches.push({ pointer, expected, actual });
  62  |     }
  63  |   };
  64  | 
  65  |   const home = await createTestHome("inspiration-causality");
  66  |   await createWorkspace(home);
  67  |   const sidecarLog = path.join(home, "sidecar-control.jsonl");
  68  |   let app: ElectronApplication | undefined;
  69  | 
  70  |   const open = async () => {
  71  |     const opened = await openApp(home, { E2E_SIDECAR_CONTROL_LOG: sidecarLog });
  72  |     app = opened.app;
  73  |     await setContentSize(opened.app, opened.page);
  74  |     await openInspiration(opened.page);
  75  |     return opened.page;
  76  |   };
  77  | 
  78  |   try {
  79  |     let page = await open();
  80  |     const main = page.getByTestId("main-content");
  81  |     const search = main.getByPlaceholder("搜索灵感");
  82  |     const renderedCategories = main.getByRole("tablist", { name: "灵感分类" }).getByRole("tab");
  83  |     const cards = main.getByRole("article");
  84  |     const favoriteButtons = main.getByRole("button", { name: /收藏|Add to favorites/ });
  85  |     const favoritesView = main.getByRole("button", { name: "我的收藏", exact: true });
  86  | 
  87  |     compare("/surface/heading", await main.getByRole("heading", { name: "灵感", exact: true }).count(), 1);
  88  |     compare("/categories/labels", await renderedCategories.allTextContents(), categories);
  89  |     compare("/catalog/cardCount", await cards.count(), sourceFavoriteButtons.length);
  90  |     compare("/favorites/accessibilityName", await main.getByRole("button", { name: "Add to favorites" }).count(), sourceFavoriteButtons.length);
  91  |     compare("/favorites/view/count", await favoritesView.count(), 1);
  92  |     compareNumber("/search/width", await widthOf(search), sourceSearch.box.width);
  93  |     compareNumber("/search/height", await heightOf(search), sourceSearch.box.height);
  94  |     compareNumber("/favorites/view/width", await widthOf(favoritesView), sourceFavoritesView.box.width);
  95  |     compareNumber("/favorites/view/height", await heightOf(favoritesView), sourceFavoritesView.box.height);
  96  |     compareNumber("/categories/height", await heightOf(renderedCategories.first()), sourceCategories[0].box.height);
  97  |     compareNumber("/favorites/button/width", await widthOf(favoriteButtons.first()), sourceFavoriteButtons[0].box.width);
  98  |     compareNumber("/favorites/button/height", await heightOf(favoriteButtons.first()), sourceFavoriteButtons[0].box.height);
  99  |     await attachUiState(page, testInfo, "entry-inspiration-source-closed-world");
  100 | 
  101 |     const beforeCategoryCount = await cards.count();
  102 |     const personalTab = renderedCategories.filter({ hasText: /^个人工作台$/ });
  103 |     if (await personalTab.count()) {
  104 |       await personalTab.click();
  105 |       compare("/categories/personal/selected", await personalTab.getAttribute("aria-selected"), "true");
  106 |       const afterCategoryCount = await cards.count();
  107 |       compare("/categories/personal/nonEmpty", afterCategoryCount > 0, true);
  108 |       compare("/categories/personal/reducesCatalog", afterCategoryCount < beforeCategoryCount, true);
  109 |     } else {
  110 |       mismatches.push({ pointer: "/categories/personal/selected", expected: "true", actual: "missing" });
  111 |     }
  112 | 
  113 |     if (await search.count()) {
  114 |       await search.fill("生活全能工作台");
  115 |       compare("/search/exactResultCount", await cards.count(), 1);
  116 |       compare("/search/exactResult", await main.getByRole("article", { name: "生活全能工作台" }).count(), 1);
  117 |     } else {
  118 |       mismatches.push({ pointer: "/search/exactResultCount", expected: 1, actual: "missing-search" });
  119 |     }
  120 |     await attachUiState(page, testInfo, "transition-inspiration-filtered-and-favorited");
  121 | 
  122 |     if (await search.count()) await search.fill("");
  123 |     const firstFavorite = favoriteButtons.first();
  124 |     if (await firstFavorite.count()) {
  125 |       await firstFavorite.click();
  126 |       compare("/favorites/toggled", await main.getByRole("button", { name: /已收藏/ }).count(), 1);
  127 |       if (await favoritesView.count()) {
  128 |         await favoritesView.click();
  129 |         compare("/favorites/view/cardCount", await cards.count(), 1);
  130 |       } else {
  131 |         mismatches.push({ pointer: "/favorites/view/cardCount", expected: 1, actual: "missing-view" });
  132 |       }
  133 |     } else {
  134 |       mismatches.push({ pointer: "/favorites/toggled", expected: 1, actual: "missing-button" });
  135 |     }
  136 | 
  137 |     await app.close();
  138 |     app = undefined;
  139 |     page = await open();
  140 |     const restartedMain = page.getByTestId("main-content");
  141 |     const restartedFavorites = restartedMain.getByRole("button", { name: "我的收藏", exact: true });
  142 |     if (await restartedFavorites.count()) {
  143 |       await restartedFavorites.click();
  144 |       compare("/favorites/restart/cardCount", await restartedMain.getByRole("article").count(), 1);
  145 |     } else {
  146 |       compare("/favorites/restart/cardCount", "missing-view", 1);
  147 |     }
  148 |     compare(
  149 |       "/forbidden/sidecarRequests",
  150 |       (await sidecarControlTypes(sidecarLog)).filter((type) => type !== "shutdown"),
  151 |       [],
  152 |     );
  153 |     await attachUiState(page, testInfo, "final-inspiration-favorite-persists-after-restart");
  154 | 
  155 |     await testInfo.attach("interaction-mismatches.json", {
  156 |       body: Buffer.from(`${JSON.stringify(mismatches, null, 2)}\n`),
  157 |       contentType: "application/json",
  158 |     });
> 159 |     expect(mismatches, "every WorkBuddy inspiration interaction and closed-world UI invariant must match").toEqual([]);
      |                                                                                                            ^ Error: every WorkBuddy inspiration interaction and closed-world UI invariant must match
  160 |   } finally {
  161 |     await cleanup(app, home);
  162 |   }
  163 | });
  164 | 
  165 | async function openInspiration(page: Page): Promise<void> {
  166 |   await page.getByRole("button", { name: "更多", exact: true }).click();
  167 |   await page.getByRole("menu", { name: "更多" }).getByRole("menuitem", { name: "灵感", exact: true }).click();
  168 |   await expect(page.getByTestId("main-content")).toBeVisible();
  169 | }
  170 | 
  171 | async function widthOf(locator: Locator): Promise<number | null> {
  172 |   return (await locator.count()) ? (await boxOf(locator.first())).width : null;
  173 | }
  174 | 
  175 | async function heightOf(locator: Locator): Promise<number | null> {
  176 |   return (await locator.count()) ? (await boxOf(locator.first())).height : null;
  177 | }
  178 | 
  179 | async function sidecarControlTypes(log: string): Promise<string[]> {
  180 |   return (await fs.readFile(log, "utf8").catch(() => ""))
  181 |     .split("\n")
  182 |     .filter(Boolean)
  183 |     .map((line) => JSON.parse(line) as { type?: string })
  184 |     .map((message) => message.type ?? "unknown");
  185 | }
  186 | 
```