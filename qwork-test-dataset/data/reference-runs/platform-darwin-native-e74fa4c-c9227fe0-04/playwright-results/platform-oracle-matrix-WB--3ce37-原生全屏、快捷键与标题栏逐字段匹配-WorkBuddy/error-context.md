# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: platform-oracle-matrix.spec.ts >> WB-UI-PLATFORM-DARWIN-001 @darwin | 原生全屏、快捷键与标题栏逐字段匹配 WorkBuddy
- Location: .agents/skills/qwork-test-dataset/data/e2e/platform-oracle-matrix.spec.ts:76:1

# Error details

```
Error: expect(received).toMatchObject(expected)

- Expected  - 1
+ Received  + 1

  Object {
-   "isFullScreen": true,
+   "isFullScreen": false,
  }

Call Log:
- Timeout 15000ms exceeded while waiting on the predicate
```

# Test source

```ts
  26  | const execFileAsync = promisify(execFile);
  27  | const skillRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
  28  | const matrixPath = path.join(skillRoot, "references/platform-oracle-matrix.json");
  29  | const comparatorPath = path.join(skillRoot, "scripts/compare_visual_frame.py");
  30  | 
  31  | type Platform = "darwin" | "win32";
  32  | type Theme = "light" | "dark";
  33  | type Capture = {
  34  |   id: string;
  35  |   platform: Platform;
  36  |   theme: Theme;
  37  |   dpi_percent: number;
  38  |   viewport: { width: number; height: number };
  39  |   state_set: string;
  40  |   baseline_root: string | null;
  41  |   baseline_status: string;
  42  | };
  43  | type PlatformMatrix = {
  44  |   policy: { max_diff_ratio: number; geometry_tolerance_css_px: number };
  45  |   state_sets: Record<string, string[]>;
  46  |   captures: Capture[];
  47  | };
  48  | type ShellOracle = {
  49  |   platform: {
  50  |     darwin: {
  51  |       titleBarStyle: string;
  52  |       shortcutModifier: string;
  53  |       fullscreenTrafficLightOffset: number;
  54  |       fullscreenExpandedToggle: { x: number; y: number; width: number; height: number };
  55  |       fullscreenCollapsedToggle: { x: number; y: number; width: number; height: number };
  56  |     };
  57  |     win32: {
  58  |       titleBarStyle: string;
  59  |       shortcutModifier: string;
  60  |       showTrafficLightSafeArea: boolean;
  61  |       pixelGoldenDpiPercent: number;
  62  |       smokeDpiPercent: number;
  63  |     };
  64  |   };
  65  | };
  66  | type SidebarOracle = {
  67  |   sidebar: { collapsed: { darwinFullscreenToggleX: number } };
  68  | };
  69  | type MatrixFailure = {
  70  |   capture_id: string;
  71  |   state: string;
  72  |   classification: "missing-approved-workbuddy-frame-set" | "pixel-mismatch";
  73  |   detail: string;
  74  | };
  75  | 
  76  | test("WB-UI-PLATFORM-DARWIN-001 @darwin | 原生全屏、快捷键与标题栏逐字段匹配 WorkBuddy", async ({}, testInfo) => {
  77  |   expect(process.platform, "this Case must run on its registered native platform").toBe("darwin");
  78  |   const shell = await readJson<ShellOracle>(path.resolve("e2e/oracles/workbuddy-5.3.5-shell-home.json"));
  79  |   const sidebar = await readJson<SidebarOracle>(path.resolve("e2e/oracles/workbuddy-5.3.5-sidebar-account.json"));
  80  |   const expected = shell.platform.darwin;
  81  |   const home = await createTestHome("platform-darwin-runtime");
  82  |   await createWorkspace(home);
  83  |   let app: ElectronApplication | undefined;
  84  |   try {
  85  |     ({ app } = await openApp(home));
  86  |     const page = await app.firstWindow();
  87  |     await setContentSize(app, page, { width: 1440, height: 900 });
  88  |     await page.bringToFront();
  89  |     await attachUiState(page, testInfo, "entry");
  90  |     const nativeCapability = await app.evaluate(({ app: electronApp, BrowserWindow }) => {
  91  |       const window = BrowserWindow.getAllWindows()[0];
  92  |       electronApp.focus({ steal: true });
  93  |       window?.show();
  94  |       window?.focus();
  95  |       return {
  96  |         exists: Boolean(window),
  97  |         visible: window?.isVisible() ?? false,
  98  |         focused: window?.isFocused() ?? false,
  99  |         fullScreenable: window?.isFullScreenable() ?? false,
  100 |         resizable: window?.isResizable() ?? false,
  101 |         maximizable: window?.isMaximizable() ?? false,
  102 |         bounds: window?.getBounds() ?? null,
  103 |       };
  104 |     });
  105 |     await testInfo.attach("native-fullscreen-capability.json", {
  106 |       body: Buffer.from(`${JSON.stringify(nativeCapability, null, 2)}\n`),
  107 |       contentType: "application/json",
  108 |     });
  109 |     expect(nativeCapability, "macOS native fullscreen preflight").toMatchObject({
  110 |       exists: true,
  111 |       visible: true,
  112 |       fullScreenable: true,
  113 |       resizable: true,
  114 |     });
  115 |     await assertBuiltTitleBarStyle(expected.titleBarStyle);
  116 |     expect(await observedShortcutModifier(app), "/platform/darwin/shortcutModifier").toBe(expected.shortcutModifier);
  117 | 
  118 |     const requestResult = await page.evaluate(() => window.workGui.system.setFullScreen(true));
  119 |     await testInfo.attach("native-fullscreen-request.json", {
  120 |       body: Buffer.from(`${JSON.stringify({ requestResult }, null, 2)}\n`),
  121 |       contentType: "application/json",
  122 |     });
  123 |     await expect.poll(
  124 |       () => page.evaluate(() => window.workGui.window.getState()),
  125 |       { timeout: 15_000 },
> 126 |     ).toMatchObject({ isFullScreen: true });
      |       ^ Error: expect(received).toMatchObject(expected)
  127 |     await compareToggle(page.getByRole("button", { name: "收起侧栏", exact: true }), expected.fullscreenExpandedToggle, "fullscreenExpandedToggle");
  128 |     await compareTrafficOffset(page, expected.fullscreenTrafficLightOffset);
  129 |     await attachUiState(page, testInfo, "transition");
  130 | 
  131 |     await page.getByRole("button", { name: "收起侧栏", exact: true }).click();
  132 |     const expand = page.getByRole("button", { name: "展开侧栏", exact: true });
  133 |     await expect(expand).toBeVisible();
  134 |     await compareToggle(expand, expected.fullscreenCollapsedToggle, "fullscreenCollapsedToggle");
  135 |     expect((await boxOf(expand)).x, "/sidebar/collapsed/darwinFullscreenToggleX").toBe(
  136 |       sidebar.sidebar.collapsed.darwinFullscreenToggleX,
  137 |     );
  138 |     await attachUiState(page, testInfo, "transition-collapsed");
  139 | 
  140 |     await triggerSidebarShortcut(app, page);
  141 |     await expect(page.getByRole("button", { name: "收起侧栏", exact: true })).toBeVisible();
  142 |     await compareToggle(page.getByRole("button", { name: "收起侧栏", exact: true }), expected.fullscreenExpandedToggle, "fullscreenExpandedToggle-after-shortcut");
  143 |     await attachUiState(page, testInfo, "final-state");
  144 |   } finally {
  145 |     await cleanup(app, home);
  146 |   }
  147 | });
  148 | 
  149 | test("WB-UI-PLATFORM-WIN32-001 @win32-100 | 100% DPI 标题栏、控制区与快捷键逐字段匹配 WorkBuddy", async ({}, testInfo) => {
  150 |   expect(process.platform, "this Case must run on its registered native platform").toBe("win32");
  151 |   const shell = await readJson<ShellOracle>(path.resolve("e2e/oracles/workbuddy-5.3.5-shell-home.json"));
  152 |   const expected = shell.platform.win32;
  153 |   const home = await createTestHome("platform-win32-100-runtime");
  154 |   await createWorkspace(home);
  155 |   let app: ElectronApplication | undefined;
  156 |   try {
  157 |     ({ app } = await openApp(home));
  158 |     const page = await app.firstWindow();
  159 |     await setContentSize(app, page, { width: 1440, height: 900 });
  160 |     await assertBuiltTitleBarStyle(expected.titleBarStyle);
  161 |     expect(await displayDpiPercent(app), "/platform/win32/pixelGoldenDpiPercent").toBe(expected.pixelGoldenDpiPercent);
  162 |     expect(expected.shortcutModifier).toBe("Ctrl");
  163 |     expect(expected.showTrafficLightSafeArea).toBe(false);
  164 |     await expect(page.getByTestId("traffic-light-safe-area")).toHaveCount(0);
  165 |     await expect(page.getByTestId("windows-window-controls")).toBeVisible();
  166 |     await attachUiState(page, testInfo, "entry");
  167 | 
  168 |     await page.getByRole("button", { name: "收起侧栏", exact: true }).click();
  169 |     await expect(page.getByRole("button", { name: "展开侧栏", exact: true })).toBeVisible();
  170 |     await attachUiState(page, testInfo, "transition");
  171 | 
  172 |     await page.keyboard.press(`${expected.shortcutModifier}+b`);
  173 |     await expect(page.getByRole("button", { name: "收起侧栏", exact: true })).toBeVisible();
  174 |     await attachUiState(page, testInfo, "final-state");
  175 |   } finally {
  176 |     await cleanup(app, home);
  177 |   }
  178 | });
  179 | 
  180 | test("WB-UI-PLATFORM-WIN32-002 @win32-125 | 125% DPI 冒烟保持标题栏与主题可用", async ({}, testInfo) => {
  181 |   expect(process.platform, "this Case must run on its registered native platform").toBe("win32");
  182 |   const shell = await readJson<ShellOracle>(path.resolve("e2e/oracles/workbuddy-5.3.5-shell-home.json"));
  183 |   const expected = shell.platform.win32;
  184 |   const home = await createTestHome("platform-win32-125-runtime");
  185 |   await createWorkspace(home);
  186 |   let app: ElectronApplication | undefined;
  187 |   try {
  188 |     ({ app } = await openApp(home));
  189 |     const page = await app.firstWindow();
  190 |     await setContentSize(app, page, { width: 1280, height: 800 });
  191 |     expect(await displayDpiPercent(app), "/platform/win32/smokeDpiPercent").toBe(expected.smokeDpiPercent);
  192 |     await expect(page.getByTestId("windows-window-controls")).toBeVisible();
  193 |     await attachUiState(page, testInfo, "entry");
  194 |     await setTheme(page, "dark");
  195 |     await attachUiState(page, testInfo, "transition");
  196 |     await setTheme(page, "light");
  197 |     await attachUiState(page, testInfo, "final-state");
  198 |   } finally {
  199 |     await cleanup(app, home);
  200 |   }
  201 | });
  202 | 
  203 | test("WB-UI-PIXEL-DARWIN-001 @darwin | 浅深主题与三档视口逐状态对比 WorkBuddy Golden", async ({}, testInfo) => {
  204 |   const failures = await runPixelMatrix("darwin", new Set([200]), testInfo);
  205 |   expect(failures, "approved WorkBuddy frame sets must exist and every exact Darwin frame comparison must pass").toEqual([]);
  206 | });
  207 | 
  208 | test("WB-UI-PIXEL-WIN32-001 @win32-100 | 100% DPI 浅深主题与三档视口逐状态对比 WorkBuddy Golden", async ({}, testInfo) => {
  209 |   const failures = await runPixelMatrix("win32", new Set([100]), testInfo);
  210 |   expect(failures, "approved WorkBuddy frame sets must exist and every exact Windows 100 percent frame comparison must pass").toEqual([]);
  211 | });
  212 | 
  213 | test("WB-UI-PIXEL-WIN32-002 @win32-125 | 125% DPI 浅深主题逐状态对比 WorkBuddy Golden", async ({}, testInfo) => {
  214 |   const failures = await runPixelMatrix("win32", new Set([125]), testInfo);
  215 |   expect(failures, "approved WorkBuddy frame sets must exist and every exact Windows 125 percent frame comparison must pass").toEqual([]);
  216 | });
  217 | 
  218 | async function runPixelMatrix(platform: Platform, dpis: Set<number>, testInfo: TestInfo): Promise<MatrixFailure[]> {
  219 |   expect(process.platform, "this Case must run on its registered native platform").toBe(platform);
  220 |   const matrix = await readJson<PlatformMatrix>(matrixPath);
  221 |   const captures = matrix.captures.filter((capture) => capture.platform === platform && dpis.has(capture.dpi_percent));
  222 |   expect(captures.length, "the platform/DPI route must resolve at least one frozen coordinate").toBeGreaterThan(0);
  223 |   const home = await createTestHome(`pixel-${platform}-${[...dpis].join("-")}`);
  224 |   await createWorkspace(home);
  225 |   const failures: MatrixFailure[] = [];
  226 |   let app: ElectronApplication | undefined;
```