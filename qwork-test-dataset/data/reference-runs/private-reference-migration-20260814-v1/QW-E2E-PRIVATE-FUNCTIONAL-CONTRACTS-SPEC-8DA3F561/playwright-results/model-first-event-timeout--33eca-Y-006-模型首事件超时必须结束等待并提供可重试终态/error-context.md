# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: model-first-event-timeout.spec.ts >> WB-RECOVERY-006 | 模型首事件超时必须结束等待并提供可重试终态
- Location: .agents/skills/qwork-test-dataset/data/e2e/model-first-event-timeout.spec.ts:13:1

# Error details

```
Error: expect(locator).toHaveCount(expected) failed

Locator:  getByText('等待模型响应', { exact: true })
Expected: 0
Received: 1
Timeout:  8000ms

Call log:
  - Expect "toHaveCount" with timeout 8000ms
  - waiting for getByText('等待模型响应', { exact: true })
    20 × locator resolved to 1 element
       - unexpected value "1"

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
  13 | test("WB-RECOVERY-006 | 模型首事件超时必须结束等待并提供可重试终态", async ({}, testInfo) => {
  14 |   const home = await createTestHome("model-first-event-timeout");
  15 |   await createWorkspace(home);
  16 |   let app: ElectronApplication | undefined;
  17 |   try {
  18 |     const opened = await openApp(home);
  19 |     app = opened.app;
  20 |     const page = opened.page;
  21 |     await setContentSize(app, page);
  22 |     await page.getByRole("button", { name: "专家·技能·连接器", exact: true }).click();
  23 |     await page.getByRole("button", { name: /高级开发工程师.*从证据出发/ }).click();
  24 |     await page
  25 |       .getByRole("dialog", { name: "高级开发工程师" })
  26 |       .getByRole("button", { name: "召唤 高级开发工程师" })
  27 |       .click();
  28 | 
  29 |     const composer = page.getByRole("textbox");
  30 |     await composer.fill("__E2E_HANG__");
  31 |     await attachUiState(page, testInfo, "entry-expert-ready-before-timeout-probe");
  32 |     await composer.press("Enter");
  33 |     await expect(page.getByText("等待模型响应", { exact: true })).toBeVisible();
  34 |     await expect(page.getByRole("button", { name: "停止", exact: true })).toBeVisible();
  35 |     await attachUiState(page, testInfo, "transition-model-request-has-no-first-event");
  36 | 
  37 |     // The deterministic sidecar deliberately never emits thinking/tool/text,
  38 |     // terminal status, or error. Production must own a first-event watchdog;
  39 |     // an indefinite spinner is not a valid runtime state.
  40 |     await page.waitForTimeout(10_000);
  41 |     await attachUiState(page, testInfo, "failure-first-event-timeout-still-waiting");
> 42 |     await expect(page.getByText("等待模型响应", { exact: true })).toHaveCount(0);
     |                                                             ^ Error: expect(locator).toHaveCount(expected) failed
  43 |     await expect(page.getByRole("button", { name: "停止", exact: true })).toHaveCount(0);
  44 |     await expect(page.getByRole("button", { name: "重试", exact: true })).toBeVisible();
  45 |     await expect(composer).toBeEnabled();
  46 |   } finally {
  47 |     await cleanup(app, home);
  48 |   }
  49 | });
  50 | 
```