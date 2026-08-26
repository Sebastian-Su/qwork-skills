# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: sidebar-account-oracle-completeness.spec.ts >> WB-UI-ORACLE-SIDEBAR-001 | 侧栏工具、搜索、筛选与账户菜单逐字段匹配 WorkBuddy
- Location: .agents/skills/qwork-test-dataset/data/e2e/sidebar-account-oracle-completeness.spec.ts:71:1

# Error details

```
Error: every locally executable sidebar/account Oracle pointer must match

expect(received).toEqual(expected) // deep equality

- Expected  -  1
+ Received  + 42

- Array []
+ Array [
+   Object {
+     "actual": "rgb(122, 122, 122)",
+     "expected": "rgba(255, 255, 255, 0.65)",
+     "pointer": "/sidebar/toolbar/toggle/darkForeground",
+   },
+   Object {
+     "actual": "rgb(122, 122, 122)",
+     "expected": "rgba(255, 255, 255, 0.65)",
+     "pointer": "/sidebar/toolbar/search/darkForeground",
+   },
+   Object {
+     "actual": "rgb(122, 122, 122)",
+     "expected": "rgba(255, 255, 255, 0.65)",
+     "pointer": "/sidebar/toolbar/filter/darkForeground",
+   },
+   Object {
+     "actual": "rgba(38, 38, 38, 0.65)",
+     "expected": "rgba(255, 255, 255, 0.06)",
+     "pointer": "/sidebar/toolbar/darkHoverBackground",
+   },
+   Object {
+     "actual": "rgb(38, 38, 38)",
+     "expected": "rgb(31, 31, 31)",
+     "pointer": "/search/darkBackground",
+   },
+   Object {
+     "actual": "rgb(38, 38, 38)",
+     "expected": "rgb(36, 36, 36)",
+     "pointer": "/filter/darkBackground",
+   },
+   Object {
+     "actual": "rgb(38, 38, 38)",
+     "expected": "rgb(36, 36, 36)",
+     "pointer": "/accountMenu/darkBackground",
+   },
+   Object {
+     "actual": "rgba(0, 0, 0, 0) 0px 0px 0px 0px, rgba(0, 0, 0, 0) 0px 0px 0px 0px, rgba(235, 235, 235, 0.14) 0px 16px 44px 0px, rgba(235, 235, 235, 0.08) 0px 4px 12px 0px, rgba(56, 56, 56, 0.8) 0px 0px 0px 1px",
+     "expected": "rgba(0, 0, 0, 0.6) 0px 4px 16px",
+     "pointer": "/accountMenu/darkShadow",
+   },
+ ]
```

# Test source

```ts
  139 | 
  140 |     await toolbarButtons[1].click();
  141 |     const search = page.getByRole("dialog", { name: "搜索对话" });
  142 |     const searchBox = await boxOf(search);
  143 |     compareNumber("/search/width", searchBox.width, oracle.search.width);
  144 |     compareNumber("/search/height", searchBox.height, oracle.search.height);
  145 |     const searchStyle = await computedStyle(search, ["border-radius", "background-color"]);
  146 |     compare("/search/radius", px(searchStyle["border-radius"]), oracle.search.radius);
  147 |     compare("/search/darkBackground", searchStyle["background-color"], oracle.search.darkBackground);
  148 |     const searchOverlay = search.locator("..");
  149 |     compare("/search/overlay", (await computedStyle(searchOverlay, ["background-color"]))["background-color"], oracle.search.overlay);
  150 |     await attachUiState(page, testInfo, "transition-dark-search-exact-state");
  151 |     await page.keyboard.press("Escape");
  152 | 
  153 |     for (let index = 0; index <= oracle.search.emptyQueryLimit; index += 1) {
  154 |       await page.getByRole("button", { name: "新建任务", exact: true }).click();
  155 |       const composer = page.getByRole("textbox", { name: /今天帮你做些什么/ });
  156 |       await composer.fill(`oracle-search-${String(index).padStart(2, "0")}`);
  157 |       await composer.press("Enter");
  158 |       await expect(page.getByText(`收到：oracle-search-${String(index).padStart(2, "0")}`, { exact: true })).toBeVisible();
  159 |     }
  160 |     await page.getByRole("button", { name: "搜索", exact: true }).click();
  161 |     const emptyQueryButtons = page.getByRole("dialog", { name: "搜索对话" }).getByRole("button");
  162 |     compare("/search/emptyQueryLimit", (await emptyQueryButtons.count()) - 1, oracle.search.emptyQueryLimit);
  163 |     await page.keyboard.press("Escape");
  164 | 
  165 |     await page.getByRole("button", { name: "筛选", exact: true }).click();
  166 |     const filter = page.getByRole("dialog", { name: "筛选对话" });
  167 |     const filterBox = await boxOf(filter);
  168 |     compareNumber("/filter/width", filterBox.width, oracle.filter.width);
  169 |     compareNumber("/filter/height", filterBox.height, oracle.filter.height);
  170 |     compareNumber("/filter/anchor/x", filterBox.x, oracle.filter.anchor.x);
  171 |     compareNumber("/filter/anchor/y", filterBox.y, oracle.filter.anchor.y);
  172 |     const filterStyle = await computedStyle(filter, ["border-radius", "background-color", "padding"]);
  173 |     compare("/filter/radius", px(filterStyle["border-radius"]), oracle.filter.radius);
  174 |     compare("/filter/padding", px(filterStyle.padding), oracle.filter.padding);
  175 |     compare("/filter/darkBackground", filterStyle["background-color"], oracle.filter.darkBackground);
  176 |     const statusLabels: Record<string, string> = { all: "全部", running: "进行中", completed: "已完成", failed: "失败", pending: "待处理", cancelled: "已取消" };
  177 |     const timeLabels: Record<string, string> = { all: "全部时间", today: "今天", last7Days: "最近 7 天", last30Days: "最近 30 天" };
  178 |     compare(
  179 |       "/filter/statusOptions",
  180 |       await filter.locator("section").nth(0).getByRole("button").allTextContents(),
  181 |       oracle.filter.statusOptions.map((value) => statusLabels[value]),
  182 |     );
  183 |     compare(
  184 |       "/filter/timeOptions",
  185 |       await filter.locator("section").nth(1).getByRole("button").allTextContents(),
  186 |       oracle.filter.timeOptions.map((value) => timeLabels[value]),
  187 |     );
  188 |     await attachUiState(page, testInfo, "transition-dark-filter-exact-state");
  189 |     await page.keyboard.press("Escape");
  190 | 
  191 |     await accountTrigger.click();
  192 |     const menu = page.getByRole("menu", { name: "用户中心" });
  193 |     const panel = menu.locator("..");
  194 |     const menuBox = await boxOf(menu);
  195 |     const panelBox = await boxOf(panel);
  196 |     const triggerBox = await boxOf(accountTrigger);
  197 |     compareNumber("/accountMenu/width", menuBox.width, oracle.accountMenu.width);
  198 |     compareNumber("/accountMenu/anchorGap", triggerBox.y - panelBox.bottom, oracle.accountMenu.anchorGap, 0.25);
  199 |     compare("/accountMenu/viewportMargin:left", panelBox.x >= oracle.accountMenu.viewportMargin, true);
  200 |     compare("/accountMenu/viewportMargin:right", innerWidthOf(await page.evaluate(() => innerWidth)) - panelBox.right >= oracle.accountMenu.viewportMargin, true);
  201 |     const panelStyle = await computedStyle(panel, ["border-radius", "background-color", "box-shadow", "max-height"]);
  202 |     compare("/accountMenu/radius", px(panelStyle["border-radius"]), oracle.accountMenu.radius);
  203 |     compare("/accountMenu/darkBackground", panelStyle["background-color"], oracle.accountMenu.darkBackground);
  204 |     compare("/accountMenu/darkShadow", normalizeShadow(panelStyle["box-shadow"]), normalizeShadow(oracle.accountMenu.darkShadow));
  205 |     compare("/accountMenu/maxHeight", px(panelStyle["max-height"]), calcMaxHeight(oracle.accountMenu.maxHeight, await page.evaluate(() => innerHeight)));
  206 |     const menuStyle = await computedStyle(menu, ["padding"]);
  207 |     compare("/accountMenu/padding", px(menuStyle.padding), oracle.accountMenu.padding);
  208 |     compareNumber("/accountMenu/headerHeight", (await boxOf(menu.locator(":scope > div").first())).height, oracle.accountMenu.headerHeight, 0.25);
  209 | 
  210 |     const rows = menu.locator(":scope > *");
  211 |     const actualOrder: string[] = [];
  212 |     const rowHeights: number[] = [];
  213 |     for (let index = 0; index < await rows.count(); index += 1) {
  214 |       const row = rows.nth(index);
  215 |       actualOrder.push(await accountRowKind(row));
  216 |       const kind = actualOrder.at(-1);
  217 |       if (kind !== "profile" && kind !== "divider") rowHeights.push((await boxOf(row)).height);
  218 |     }
  219 |     compare("/accountMenu/qworkRowOrder", actualOrder, oracle.accountMenu.qworkRowOrder);
  220 |     for (const [index, height] of rowHeights.entries()) {
  221 |       const [minimum, maximum] = oracle.accountMenu.rowHeightRange;
  222 |       if (height < minimum || height > maximum) {
  223 |         mismatches.push({ pointer: `/accountMenu/rowHeightRange/rendered/${index}`, expected: oracle.accountMenu.rowHeightRange, actual: height });
  224 |       }
  225 |     }
  226 |     compare(
  227 |       "/source/brandPolicy",
  228 |       oracle.source.brandPolicy,
  229 |       "QWork identity, account data, and supported QWork actions are retained",
  230 |     );
  231 |     compare("/source/brandPolicy:QWork-identity", await page.getByRole("button", { name: "连接 QWork", exact: true }).count(), 1);
  232 |     compare("/source/brandPolicy:QWork-actions", await menu.getByRole("menuitem").count() >= 8, true);
  233 |     await attachUiState(page, testInfo, "final-dark-account-menu-exact-state");
  234 | 
  235 |     await testInfo.attach("oracle-mismatches.json", {
  236 |       body: Buffer.from(`${JSON.stringify(mismatches, null, 2)}\n`),
  237 |       contentType: "application/json",
  238 |     });
> 239 |     expect(mismatches, "every locally executable sidebar/account Oracle pointer must match").toEqual([]);
      |                                                                                              ^ Error: every locally executable sidebar/account Oracle pointer must match
  240 |   } finally {
  241 |     await cleanup(app, home);
  242 |   }
  243 | });
  244 | 
  245 | function same(actual: unknown, expected: unknown): boolean {
  246 |   return JSON.stringify(actual) === JSON.stringify(expected);
  247 | }
  248 | 
  249 | function px(value: string): number {
  250 |   const parsed = Number.parseFloat(value);
  251 |   return Number.isFinite(parsed) ? parsed : Number.NaN;
  252 | }
  253 | 
  254 | function normalizeColor(value: string): string {
  255 |   return value === "rgba(0, 0, 0, 0)" ? "transparent" : value;
  256 | }
  257 | 
  258 | function normalizeShadow(value: string): string {
  259 |   return value.trim().replace(/ 0px$/, "");
  260 | }
  261 | 
  262 | function calcMaxHeight(value: string, viewportHeight: number): number {
  263 |   const match = /^calc\(100vh - (\d+)px\)$/.exec(value);
  264 |   if (!match) return Number.NaN;
  265 |   return viewportHeight - Number(match[1]);
  266 | }
  267 | 
  268 | function innerWidthOf(value: number): number {
  269 |   return value;
  270 | }
  271 | 
  272 | async function accountRowKind(row: Locator): Promise<string> {
  273 |   if (await row.getByTestId("account-menu-username").count()) return "profile";
  274 |   if ((await row.getAttribute("role")) === "separator") return "divider";
  275 |   const text = (await row.innerText()).replace(/\s+/g, " ").trim();
  276 |   if (text.includes("升级")) return "entitlement";
  277 |   if (text.includes("Buddy 加油站")) return "buddyStation";
  278 |   if (text.includes("体验「项目」")) return "tryProject";
  279 |   if (text.includes("积分余额")) return "credits";
  280 |   if (text.includes("成长计划")) return "growth";
  281 |   if (text === "设置") return "settings";
  282 |   if (text.includes("浅色") && text.includes("深色")) return "appearance";
  283 |   if (text === "帮助与反馈") return "help";
  284 |   if (text === "检查更新") return "updates";
  285 |   if (text === "退出登录") return "logout";
  286 |   return `unknown:${text}`;
  287 | }
  288 | 
```