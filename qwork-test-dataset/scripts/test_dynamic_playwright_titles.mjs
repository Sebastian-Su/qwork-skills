import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const script = path.join(path.dirname(fileURLToPath(import.meta.url)), "extract_playwright_contracts.mjs");
const source = `
for (const format of ["docx", "xlsx", "pptx"] as const) {
  test(\`任务产出 \${format.toUpperCase()} 自动打开右侧预览\`, async () => {
    await page.getByRole("button", { name: "打开" }).click();
    await expect(page.getByRole("main")).toBeVisible();
  });
}`;
const result = spawnSync(process.execPath, [script, "dynamic.spec.ts"], { input: source, encoding: "utf8" });
if (result.status !== 0) throw new Error(result.stderr);
const titles = JSON.parse(result.stdout).tests.map((item) => item.title);
const expected = ["任务产出 DOCX 自动打开右侧预览", "任务产出 XLSX 自动打开右侧预览", "任务产出 PPTX 自动打开右侧预览"];
if (JSON.stringify(titles) !== JSON.stringify(expected)) throw new Error(`dynamic titles drifted: ${JSON.stringify(titles)}`);

const helperSource = `
test("helper-bound UI contract", async () => {
  await verifyDrawer();
});
async function verifyDrawer() {
  await openDrawer();
  await expect(page.getByRole("dialog")).toBeVisible();
}
async function openDrawer() {
  await page.getByRole("button", { name: "打开" }).click();
}`;
const helperResult = spawnSync(process.execPath, [script, "helper.spec.ts"], { input: helperSource, encoding: "utf8" });
if (helperResult.status !== 0) throw new Error(helperResult.stderr);
const helperContract = JSON.parse(helperResult.stdout).tests[0];
if (helperContract.actions.length !== 1 || helperContract.assertions.length !== 1) {
  throw new Error(`helper contract was not expanded: ${JSON.stringify(helperContract)}`);
}
console.log("dynamic Playwright titles: PASS");

for (const [values, expectedTitles] of [
  ["[false, true]", ["catalog install", "permission above expert"]],
  ["[true] as const", ["permission above expert"]],
]) {
  const conditional = `for (const overlay of ${values}) test(overlay ? "permission above expert" : "catalog install", async () => {
    await page.getByRole("button", { name: "拒绝" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();
  });`;
  const result = spawnSync(process.execPath, [script, "conditional.spec.ts"], { input: conditional, encoding: "utf8" });
  if (result.status !== 0) throw new Error(result.stderr);
  const contracts = JSON.parse(result.stdout).tests;
  if (JSON.stringify(contracts.map((item) => item.title)) !== JSON.stringify(expectedTitles)) {
    throw new Error(`conditional titles missing: ${result.stdout}`);
  }
  if (contracts.some((item) => item.actions.length !== 1 || item.assertions.length !== 1)) {
    throw new Error("conditional title lost its action/assertion contract");
  }
}
