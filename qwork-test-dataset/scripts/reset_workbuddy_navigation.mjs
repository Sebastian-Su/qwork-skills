import { requireFromProject } from "./project-require.mjs";

const { chromium } = requireFromProject("playwright");
const endpoint = process.env.WORKBUDDY_CDP_URL ?? "http://127.0.0.1:19222";
const browser = await chromium.connectOverCDP(endpoint);
const page = browser.contexts().flatMap((context) => context.pages()).find((candidate) => candidate.url().startsWith("file:"));
if (!page) throw new Error("WorkBuddy renderer target unavailable");
page.setDefaultTimeout(5000);
await page.bringToFront();
for (let attempt = 0; attempt < 4; attempt += 1) {
  const connectorClose = page.locator("button.connector-detail-close").last();
  if (await connectorClose.isVisible().catch(() => false)) await connectorClose.click();
  else await page.keyboard.press("Escape").catch(() => {});
  await page.waitForTimeout(180);
}
if (await page.locator(".connector-detail-modal-overlay").filter({ visible: true }).isVisible().catch(() => false)) {
  throw new Error("connector detail overlay remains visible after explicit close attempts");
}
const hasSidebar = await page.getByRole("tablist", { name: "Agents tabs" }).isVisible().catch(() => false);
if (!hasSidebar) {
  const topButtons = page.locator("button").filter({ visible: true });
  const count = await topButtons.count();
  let clicked = false;
  for (let index = 0; index < count; index += 1) {
    const button = topButtons.nth(index);
    const box = await button.boundingBox();
    if (box && box.y < 50 && box.width === 32 && box.height === 32) {
      await button.click();
      clicked = true;
      break;
    }
  }
  if (!clicked) await page.mouse.click(112, 28);
}
await page.getByRole("tablist", { name: "Agents tabs" }).waitFor({ state: "visible", timeout: 5000 });
await browser.close();
console.log(JSON.stringify({ status: "ok", sidebar: "expanded" }));
