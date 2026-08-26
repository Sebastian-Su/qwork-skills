# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: shell-home-oracle-completeness.spec.ts >> WB-UI-ORACLE-SHELL-HOME-001 | Shell 首页主题、排版、场景与 Composer 逐字段匹配 WorkBuddy
- Location: .agents/skills/qwork-test-dataset/data/e2e/shell-home-oracle-completeness.spec.ts:47:1

# Error details

```
Error: every locally executable Shell/Home Oracle pointer must match

expect(received).toEqual(expected) // deep equality

- Expected  -  1
+ Received  + 52

- Array []
+ Array [
+   Object {
+     "actual": "rgb(250, 250, 250)",
+     "expected": "rgb(255, 255, 255)",
+     "pointer": "/light/bodyBackground",
+   },
+   Object {
+     "actual": "rgb(33, 33, 33)",
+     "expected": "rgb(59, 59, 59)",
+     "pointer": "/light/bodyColor",
+   },
+   Object {
+     "actual": 30,
+     "expected": 29,
+     "pointer": "/shared/homeTitle/fontSize",
+   },
+   Object {
+     "actual": "PingFang SC, Arial, sans-serif",
+     "expected": "PingFang SC, -apple-system, system-ui, Helvetica Neue, sans-serif",
+     "pointer": "/shared/homeTitle/fontFamily",
+   },
+   Object {
+     "actual": 800,
+     "expected": 960,
+     "pointer": "/shared/composer/targetContainerWidth",
+   },
+   Object {
+     "actual": 0,
+     "expected": 70,
+     "pointer": "/shared/composer/editorMinHeight",
+   },
+   Object {
+     "actual": "rgb(235, 235, 235)",
+     "expected": "rgba(228, 228, 228, 0.92)",
+     "pointer": "/dark/bodyColor",
+   },
+   Object {
+     "actual": "rgb(0, 0, 0)",
+     "expected": "rgb(255, 255, 255)",
+     "pointer": "/dark/titleColor",
+   },
+   Object {
+     "actual": "rgba(255, 255, 255, 0.1)",
+     "expected": "color(srgb 1 1 1 / 0.12)",
+     "pointer": "/dark/newTaskBackground",
+   },
+   Object {
+     "actual": "rgba(255, 255, 255, 0.2)",
+     "expected": "rgba(255, 255, 255, 0.18)",
+     "pointer": "/dark/activeSceneBackground",
+   },
+ ]
```

# Test source

```ts
  38  |     composer: { targetContainerWidth: number; targetContainerHeight: number; editorMinHeight: number; fontSize: number; placeholder: string };
  39  |   };
  40  |   light: ThemeOracle;
  41  |   dark: ThemeOracle;
  42  |   platform: { darwin: { windowedCollapsedTrafficLightOffset: number } };
  43  | };
  44  | 
  45  | type Mismatch = { pointer: string; expected: unknown; actual: unknown };
  46  | 
  47  | test("WB-UI-ORACLE-SHELL-HOME-001 | Shell 首页主题、排版、场景与 Composer 逐字段匹配 WorkBuddy", async ({}, testInfo) => {
  48  |   const oracle = JSON.parse(
  49  |     await fs.readFile(path.join(repo, "e2e/oracles/workbuddy-5.3.5-shell-home.json"), "utf8"),
  50  |   ) as Oracle;
  51  |   const home = await createTestHome("shell-home-oracle");
  52  |   await createWorkspace(home);
  53  |   const mismatches: Mismatch[] = [];
  54  |   let app: ElectronApplication | undefined;
  55  | 
  56  |   const compare = (pointer: string, actual: unknown, expected: unknown) => {
  57  |     if (JSON.stringify(actual) !== JSON.stringify(expected)) {
  58  |       mismatches.push({ pointer, expected, actual });
  59  |     }
  60  |   };
  61  |   const compareNumber = (pointer: string, actual: number, expected: number, tolerance = 2) => {
  62  |     if (Math.abs(actual - expected) > tolerance) {
  63  |       mismatches.push({ pointer, expected, actual });
  64  |     }
  65  |   };
  66  | 
  67  |   try {
  68  |     const opened = await openApp(home);
  69  |     app = opened.app;
  70  |     const page = opened.page;
  71  |     await setContentSize(app, page);
  72  |     await startDraft(page);
  73  | 
  74  |     const body = page.locator("body");
  75  |     const title = page.getByRole("heading", { name: "WorkBuddy, 我帮你", exact: true });
  76  |     const newTask = page.getByRole("button", { name: "新建任务", exact: true });
  77  |     const activeScene = page.getByRole("tab", { name: "日常办公", exact: true });
  78  |     const inactiveScene = page.getByRole("tab", { name: "代码开发", exact: true });
  79  |     const quickAction = page.getByRole("button", { name: "文档处理", exact: true });
  80  |     const surface = page.getByTestId("composer-surface");
  81  |     const editor = page.getByTestId("composer-editor");
  82  |     const composer = page.getByRole("textbox", { name: /今天帮你做些什么/ });
  83  | 
  84  |     await compareTheme("/light", oracle.light, {
  85  |       body,
  86  |       title,
  87  |       newTask,
  88  |       activeScene,
  89  |       inactiveScene,
  90  |       quickAction,
  91  |     }, compare);
  92  |     await compareGeometry(oracle, { title, activeScene, inactiveScene, quickAction, surface, editor, composer }, compare, compareNumber);
  93  |     compare("/shared/composer/placeholder", await composer.getAttribute("placeholder"), oracle.shared.composer.placeholder);
  94  |     compare(
  95  |       "/source/brandPolicy",
  96  |       oracle.source.brandPolicy,
  97  |       "QWork names, logos, account data, and campaign copy are retained",
  98  |     );
  99  |     compare("/source/brandPolicy:qwork-name", await page.getByText("QWork v0.1.0", { exact: true }).count(), 1);
  100 |     compare("/source/brandPolicy:account", await page.getByRole("button", { name: /Dev User|蓝湖|本地用户/ }).count(), 1);
  101 |     compare("/source/brandPolicy:campaign-copy", await title.textContent(), "WorkBuddy, 我帮你");
  102 |     await attachUiState(page, testInfo, "entry-light-shell-home-exact-state");
  103 | 
  104 |     if (process.platform === "darwin") {
  105 |       await page.getByRole("button", { name: "收起侧栏", exact: true }).click();
  106 |       await expect(page.getByRole("button", { name: "展开侧栏", exact: true })).toBeVisible();
  107 |       const chromeStyle = await computedStyle(page.getByTestId("window-chrome"), ["--mac-traffic-light-offset"]);
  108 |       compare(
  109 |         "/platform/darwin/windowedCollapsedTrafficLightOffset",
  110 |         px(chromeStyle["--mac-traffic-light-offset"]),
  111 |         oracle.platform.darwin.windowedCollapsedTrafficLightOffset,
  112 |       );
  113 |       await page.getByRole("button", { name: "展开侧栏", exact: true }).click();
  114 |     }
  115 | 
  116 |     const account = page.getByRole("button", { name: /Dev User|蓝湖|本地用户/ });
  117 |     await account.click();
  118 |     await page.getByRole("button", { name: "深色", exact: true }).click();
  119 |     await expect(page.locator("html")).toHaveClass(/dark/);
  120 |     await compareTheme("/dark", oracle.dark, {
  121 |       body,
  122 |       title,
  123 |       newTask,
  124 |       activeScene,
  125 |       inactiveScene,
  126 |       quickAction,
  127 |     }, compare);
  128 |     await attachUiState(page, testInfo, "transition-dark-shell-home-exact-state");
  129 | 
  130 |     await composer.fill("逐字段验证 Composer 不发送真实模型请求");
  131 |     compare("/shared/composer:remains-draft", await composer.inputValue(), "逐字段验证 Composer 不发送真实模型请求");
  132 |     await attachUiState(page, testInfo, "final-dark-composer-draft-exact-state");
  133 | 
  134 |     await testInfo.attach("oracle-mismatches.json", {
  135 |       body: Buffer.from(`${JSON.stringify(mismatches, null, 2)}\n`),
  136 |       contentType: "application/json",
  137 |     });
> 138 |     expect(mismatches, "every locally executable Shell/Home Oracle pointer must match").toEqual([]);
      |                                                                                         ^ Error: every locally executable Shell/Home Oracle pointer must match
  139 |   } finally {
  140 |     await cleanup(app, home);
  141 |   }
  142 | });
  143 | 
  144 | async function compareTheme(
  145 |   prefix: string,
  146 |   oracle: ThemeOracle,
  147 |   locators: {
  148 |     body: Locator;
  149 |     title: Locator;
  150 |     newTask: Locator;
  151 |     activeScene: Locator;
  152 |     inactiveScene: Locator;
  153 |     quickAction: Locator;
  154 |   },
  155 |   compare: (pointer: string, actual: unknown, expected: unknown) => void,
  156 | ) {
  157 |   const body = await computedStyle(locators.body, ["background-color", "color"]);
  158 |   const title = await computedStyle(locators.title, ["color"]);
  159 |   const newTask = await computedStyle(locators.newTask, ["background-color", "color"]);
  160 |   const active = await computedStyle(locators.activeScene, ["background-color", "color"]);
  161 |   const inactive = await computedStyle(locators.inactiveScene, ["color"]);
  162 |   const quick = await computedStyle(locators.quickAction, ["background-color", "box-shadow"]);
  163 |   compare(`${prefix}/bodyBackground`, body["background-color"], oracle.bodyBackground);
  164 |   compare(`${prefix}/bodyColor`, body.color, oracle.bodyColor);
  165 |   compare(`${prefix}/titleColor`, title.color, oracle.titleColor);
  166 |   compare(`${prefix}/newTaskBackground`, newTask["background-color"], oracle.newTaskBackground);
  167 |   compare(`${prefix}/newTaskColor`, newTask.color, oracle.newTaskColor);
  168 |   compare(`${prefix}/activeSceneBackground`, active["background-color"], oracle.activeSceneBackground);
  169 |   compare(`${prefix}/activeSceneColor`, active.color, oracle.activeSceneColor);
  170 |   if (oracle.inactiveSceneColor !== undefined) compare(`${prefix}/inactiveSceneColor`, inactive.color, oracle.inactiveSceneColor);
  171 |   if (oracle.quickActionBackground !== undefined) compare(`${prefix}/quickActionBackground`, quick["background-color"], oracle.quickActionBackground);
  172 |   if (oracle.quickActionShadow !== undefined) compare(`${prefix}/quickActionShadow`, normalizeShadow(quick["box-shadow"]), normalizeShadow(oracle.quickActionShadow));
  173 | }
  174 | 
  175 | async function compareGeometry(
  176 |   oracle: Oracle,
  177 |   locators: {
  178 |     title: Locator;
  179 |     activeScene: Locator;
  180 |     inactiveScene: Locator;
  181 |     quickAction: Locator;
  182 |     surface: Locator;
  183 |     editor: Locator;
  184 |     composer: Locator;
  185 |   },
  186 |   compare: (pointer: string, actual: unknown, expected: unknown) => void,
  187 |   compareNumber: (pointer: string, actual: number, expected: number, tolerance?: number) => void,
  188 | ) {
  189 |   const titleBox = await boxOf(locators.title);
  190 |   const titleStyle = await computedStyle(locators.title, ["font-size", "font-weight", "font-family"]);
  191 |   compareNumber("/shared/homeTitle/height", titleBox.height, oracle.shared.homeTitle.height);
  192 |   compare("/shared/homeTitle/fontSize", px(titleStyle["font-size"]), oracle.shared.homeTitle.fontSize);
  193 |   compare("/shared/homeTitle/fontWeight", Number(titleStyle["font-weight"]), oracle.shared.homeTitle.fontWeight);
  194 |   compare("/shared/homeTitle/fontFamily", normalizeFontFamily(titleStyle["font-family"]), normalizeFontFamily(oracle.shared.homeTitle.fontFamily));
  195 | 
  196 |   const activeBox = await boxOf(locators.activeScene);
  197 |   const activeStyle = await computedStyle(locators.activeScene, ["border-radius", "font-size", "font-weight"]);
  198 |   const inactiveStyle = await computedStyle(locators.inactiveScene, ["font-weight"]);
  199 |   compareNumber("/shared/scenePill/width", activeBox.width, oracle.shared.scenePill.width);
  200 |   compareNumber("/shared/scenePill/height", activeBox.height, oracle.shared.scenePill.height);
  201 |   compare("/shared/scenePill/radius", px(activeStyle["border-radius"]), oracle.shared.scenePill.radius);
  202 |   compare("/shared/scenePill/fontSize", px(activeStyle["font-size"]), oracle.shared.scenePill.fontSize);
  203 |   compare("/shared/scenePill/activeFontWeight", Number(activeStyle["font-weight"]), oracle.shared.scenePill.activeFontWeight);
  204 |   compare("/shared/scenePill/inactiveFontWeight", Number(inactiveStyle["font-weight"]), oracle.shared.scenePill.inactiveFontWeight);
  205 | 
  206 |   const quickBox = await boxOf(locators.quickAction);
  207 |   const quickStyle = await computedStyle(locators.quickAction, ["border-radius", "font-size", "padding-left", "padding-right", "column-gap"]);
  208 |   compareNumber("/shared/quickAction/height", quickBox.height, oracle.shared.quickAction.height);
  209 |   compare("/shared/quickAction/radius", px(quickStyle["border-radius"]), oracle.shared.quickAction.radius);
  210 |   compare("/shared/quickAction/fontSize", px(quickStyle["font-size"]), oracle.shared.quickAction.fontSize);
  211 |   compare("/shared/quickAction/horizontalPadding:left", px(quickStyle["padding-left"]), oracle.shared.quickAction.horizontalPadding);
  212 |   compare("/shared/quickAction/horizontalPadding:right", px(quickStyle["padding-right"]), oracle.shared.quickAction.horizontalPadding);
  213 |   compare("/shared/quickAction/gap", px(quickStyle["column-gap"]), oracle.shared.quickAction.gap);
  214 | 
  215 |   const surfaceBox = await boxOf(locators.surface);
  216 |   const editorStyle = await computedStyle(locators.editor, ["min-height"]);
  217 |   const composerStyle = await computedStyle(locators.composer, ["font-size"]);
  218 |   compareNumber("/shared/composer/targetContainerWidth", surfaceBox.width, oracle.shared.composer.targetContainerWidth);
  219 |   compareNumber("/shared/composer/targetContainerHeight", surfaceBox.height, oracle.shared.composer.targetContainerHeight);
  220 |   compare("/shared/composer/editorMinHeight", px(editorStyle["min-height"]), oracle.shared.composer.editorMinHeight);
  221 |   compare("/shared/composer/fontSize", px(composerStyle["font-size"]), oracle.shared.composer.fontSize);
  222 | }
  223 | 
  224 | function px(value: string): number {
  225 |   const parsed = Number.parseFloat(value);
  226 |   return Number.isFinite(parsed) ? parsed : Number.NaN;
  227 | }
  228 | 
  229 | function normalizeFontFamily(value: string): string {
  230 |   return value.replace(/["']/g, "").replace(/\s*,\s*/g, ", ").trim();
  231 | }
  232 | 
  233 | function normalizeShadow(value: string): string {
  234 |   return value
  235 |     .trim()
  236 |     .replace(/^(?:rgba\(0, 0, 0, 0\) 0px 0px 0px 0px,\s*)+/, "")
  237 |     .replace(/ 0px$/, "");
  238 | }
```