# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: expert-artifact-causality.spec.ts >> WB-EXPERT-007 | 只有真实工作区产物才显示产物卡并可打开预览
- Location: .agents/skills/qwork-test-dataset/data/e2e/expert-artifact-causality.spec.ts:13:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByTestId('main-content').getByRole('button', { name: /expert-output\.html/ })
Expected: visible
Timeout: 8000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 8000ms
  - waiting for getByTestId('main-content').getByRole('button', { name: /expert-output\.html/ })

```

```yaml
- banner:
  - button "收起侧栏":
    - img
  - button "搜索":
    - img
  - button "筛选":
    - img
- complementary:
  - text: QWork v0.1.0
  - navigation:
    - button "新建任务":
      - img
      - text: 新建任务
    - button "助理":
      - img
      - text: 助理
    - button "项目":
      - img
      - text: 项目
    - button "专家·技能·连接器":
      - img
      - text: 专家·技能·连接器
    - button "自动化":
      - img
      - text: 自动化
    - button "更多":
      - img
      - text: 更多 资料库·灵感
  - button "任务 (1)":
    - text: 任务 (1)
    - img
  - button "新聊天"
  - text: 刚刚
  - button "Delete thread":
    - img
  - button "空间 (0)":
    - text: 空间 (0)
    - img
  - button "新建空间":
    - img
  - text: 暂无空间
  - button "D Dev User"
  - button "消息中心":
    - img
  - button "连接 QWork":
    - img
- main:
  - toolbar "对话工具栏":
    - text: 新对话
    - button "对话内搜索（⌘F）":
      - img
    - button "分享任务":
      - img
    - combobox "历史提问":
      - img
    - button "展开右侧面板":
      - img
    - button "打开终端":
      - img
    - button "打开文件树":
      - img
  - paragraph: 先给出不产生文件的风险摘要
  - button "已完成 0s":
    - img
    - text: 已完成 0s
  - text: 高 高级开发工程师 已完成
  - paragraph: 收到：先给出不产生文件的风险摘要
  - button "复制":
    - img
  - button "赞":
    - img
  - button "踩":
    - img
  - button "朗读":
    - img
  - button "重试":
    - img
  - button "分享":
    - img
  - button "更多":
    - img
  - paragraph: __E2E_ARTIFACT__:expert-output.html
  - button "已完成 0s":
    - img
    - text: 已完成 0s
  - button "写入文件 ok · 0s":
    - img
    - text: 写入文件 ok · 0s
  - text: 高 高级开发工程师 已完成
  - paragraph:
    - text: 收到：
    - strong: E2E_ARTIFACT
    - text: :expert-output.html
  - button "复制":
    - img
  - button "赞":
    - img
  - button "踩":
    - img
  - button "朗读":
    - img
  - button "重试":
    - img
  - button "分享":
    - img
  - button "更多":
    - img
  - textbox "今天帮你做些什么？ @ 引用对话文件，/ 调用技能与指令"
  - button "更多操作":
    - img
  - button "默认权限":
    - img
    - text: 默认权限
    - img
  - button "GLM-5.2":
    - img
    - text: GLM-5.2
    - img
  - button "语音输入":
    - img
  - button "发送" [disabled]:
    - img
```

# Test source

```ts
  1  | import { expect, test, type ElectronApplication } from "@playwright/test";
  2  | import {
  3  |   attachUiState,
  4  |   setContentSize,
  5  | } from "../../../../../e2e/fixtures/workbuddy-ui";
  6  | import {
  7  |   cleanup,
  8  |   createTestHome,
  9  |   createWorkspace,
  10 |   openApp,
  11 | } from "./fixtures/launch-isolated";
  12 | 
  13 | test("WB-EXPERT-007 | 只有真实工作区产物才显示产物卡并可打开预览", async ({}, testInfo) => {
  14 |   const home = await createTestHome("expert-artifact-causality");
  15 |   await createWorkspace(home);
  16 |   let app: ElectronApplication | undefined;
  17 |   try {
  18 |     let page;
  19 |     ({ app, page } = await openApp(home));
  20 |     await setContentSize(app, page);
  21 |     await page.getByRole("button", { name: "专家·技能·连接器", exact: true }).click();
  22 |     await page.getByRole("button", { name: /高级开发工程师.*从证据出发/ }).click();
  23 |     await page
  24 |       .getByRole("dialog", { name: "高级开发工程师" })
  25 |       .getByRole("button", { name: "召唤 高级开发工程师" })
  26 |       .click();
  27 | 
  28 |     const composer = page.getByRole("textbox");
  29 |     await composer.fill("先给出不产生文件的风险摘要");
  30 |     await composer.press("Enter");
  31 |     await expect(page.getByText("收到：先给出不产生文件的风险摘要", { exact: true })).toBeVisible();
  32 |     await expect(page.getByTestId("main-content").getByRole("button", { name: /\.html|\.md/ })).toHaveCount(0);
  33 |     await attachUiState(page, testInfo, "entry-no-artifact-no-card");
  34 | 
  35 |     await composer.fill("__E2E_ARTIFACT__:expert-output.html");
  36 |     await composer.press("Enter");
  37 |     const artifact = page.getByTestId("main-content").getByRole("button", { name: /expert-output\.html/ });
> 38 |     await expect(artifact).toBeVisible();
     |                            ^ Error: expect(locator).toBeVisible() failed
  39 |     await expect.poll(async () =>
  40 |       (await page.evaluate(() => window.workGui.files.list())).map((file) => file.name),
  41 |     ).toContain("expert-output.html");
  42 |     await attachUiState(page, testInfo, "transition-real-artifact-card");
  43 | 
  44 |     await artifact.click();
  45 |     const preview = page.getByRole("complementary", { name: "工件预览" });
  46 |     await expect(preview).toBeVisible();
  47 |     await expect(preview.getByRole("tab", { name: "expert-output.html", exact: true })).toBeVisible();
  48 |     await expect(preview).toContainText("E2E workspace file");
  49 |     await attachUiState(page, testInfo, "final-real-artifact-preview");
  50 |   } finally {
  51 |     await cleanup(app, home);
  52 |   }
  53 | });
  54 | 
```