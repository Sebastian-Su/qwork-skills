import { _electron as electron, type ElectronApplication, type Page } from "@playwright/test";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { captureElectronRuntime } from "./capture-electron-runtime";

const here = path.dirname(fileURLToPath(import.meta.url));
export const repo = path.resolve(here, "../../../../../../");
const appRoot = process.env.QWORK_E2E_APP_ROOT?.trim();
if (!appRoot) throw new Error("QWORK_E2E_APP_ROOT is required for private Electron E2E");
const sidecar = path.resolve(repo, "e2e/fixtures/fake-sidecar.mjs");

export async function createTestHome(prefix: string): Promise<string> {
  return fs.mkdtemp(path.join(os.tmpdir(), `qwork-private-${prefix}-`));
}

export async function createWorkspace(home: string): Promise<string> {
  const workspace = path.join(home, "workspace");
  await fs.mkdir(workspace, { recursive: true });
  await fs.writeFile(
    path.join(home, "work-gui.json"),
    `${JSON.stringify({ system: { defaultWorkspaceRoot: workspace } }, null, 2)}\n`,
    "utf8",
  );
  return workspace;
}

export async function openApp(
  home: string,
  extraEnv: NodeJS.ProcessEnv = {},
): Promise<{ app: ElectronApplication; page: Page }> {
  const app = await electron.launch({
    args: [
      ...(process.platform === "linux" ? ["--password-store=basic"] : []),
      "--enable-logging=stderr",
      `--user-data-dir=${path.join(home, "electron-user-data")}`,
      appRoot,
    ],
    timeout: 20_000,
    env: {
      ...process.env,
      QWORK_ENV: "test",
      NODE_ENV: "test",
      QWORK_AUTH_BYPASS: "1",
      // Bundled experts (e.g. 高级开发工程师/senior-developer) install only when a
      // plugins root is provisioned. "none" nulls that root, so expert UI flows
      // never find their expert. "plugins-only" seeds the agent plugins without
      // the heavier full skill mirror, matching what these specs assert against.
      QWORK_E2E_BUILTIN_MARKETPLACE: "plugins-only",
      QWORK_E2E_EMBEDDED_PYTHON: "0",
      QWORK_PROJECT_ACCESS_TOKEN: "private-e2e-token",
      QWORK_E2E_MODEL_CATALOG_JSON: JSON.stringify([
        { value: "z-ai/glm-5.2", label: "GLM-5.2" },
      ]),
      WORK_GUI_E2E_SAFE_STORAGE_KEY: "qwork-private-e2e-credentials-v1",
      NODE_OPTIONS: undefined,
      ELECTRON_RUN_AS_NODE: undefined,
      ELECTRON_RENDERER_URL: undefined,
      ZIQDO_CONFIG_HOME: home,
      ZIQDO_BIN: process.execPath,
      ZIQDO_BIN_ARGS_PREFIX: JSON.stringify([sidecar]),
      ...extraEnv,
    },
  });
  captureElectronRuntime(app);
  return { app, page: await app.firstWindow() };
}

export async function cleanup(
  app: ElectronApplication | undefined,
  home: string,
): Promise<void> {
  await app?.close().catch(() => undefined);
  await removeHomeWithRetries(home);
}

/**
 * Windows keeps the Electron lockfile handle open briefly after `app.close()`
 * resolves, so an immediate `fs.rm` races the OS and throws EBUSY/EPERM/ENOTEMPTY.
 * Retry with backoff so cleanup failure never masks a passing test body.
 */
async function removeHomeWithRetries(home: string): Promise<void> {
  const transient = new Set(["EBUSY", "EPERM", "ENOTEMPTY", "EACCES"]);
  for (let attempt = 0; attempt < 10; attempt += 1) {
    try {
      await fs.rm(home, { recursive: true, force: true });
      return;
    } catch (error) {
      const code = (error as NodeJS.ErrnoException).code ?? "";
      if (!transient.has(code) || attempt === 9) {
        if (attempt === 9) return; // best-effort: temp dir will be reclaimed by the OS
        throw error;
      }
      await new Promise((resolve) => setTimeout(resolve, 100 * (attempt + 1)));
    }
  }
}
