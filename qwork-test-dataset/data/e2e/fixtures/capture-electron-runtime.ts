import type { ElectronApplication } from "@playwright/test";
import fs from "node:fs";

export function captureElectronRuntime(app: ElectronApplication): void {
  const target = process.env.QWORK_E2E_RUNTIME_LOG?.trim();
  if (!target) throw new Error("QWORK_E2E_RUNTIME_LOG is required for private Electron E2E");
  const stream = fs.createWriteStream(target, { flags: "a" });
  const child = app.process();
  fs.appendFileSync(target, `[qwork-e2e] electron pid=${child.pid ?? "unknown"}\n`);
  child.stdout?.pipe(stream, { end: false });
  child.stderr?.pipe(stream, { end: false });
  child.once("exit", (code, signal) => {
    fs.appendFileSync(target, `[qwork-e2e] electron exit code=${code ?? "null"} signal=${signal ?? "null"}\n`);
  });
  app.on("close", () => stream.end());
}
