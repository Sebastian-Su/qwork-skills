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
console.log("dynamic Playwright titles: PASS");
