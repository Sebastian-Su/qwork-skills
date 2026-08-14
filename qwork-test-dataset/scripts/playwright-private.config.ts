import path from "node:path";
import { fileURLToPath } from "node:url";

delete process.env.ELECTRON_RUN_AS_NODE;
const skillRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

export default {
  testDir: path.join(skillRoot, "data/e2e"),
  outputDir: process.env.QWORK_E2E_OUTPUT_DIR || path.join(skillRoot, "data/runs/private-playwright/results"),
  timeout: 90_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: { trace: "on", screenshot: "only-on-failure" },
};
