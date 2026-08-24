import crypto from "node:crypto";
import fsSync from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

export async function bindWorkBuddyRuntimeIdentity({ bundleManifestPath, productVersion, rendererUrl }) {
  if (!bundleManifestPath) throw new Error("WORKBUDDY_BUNDLE_MANIFEST is required");
  const manifestPath = path.resolve(bundleManifestPath);
  const manifestBytes = await fs.readFile(manifestPath);
  const manifest = JSON.parse(manifestBytes.toString("utf8"));
  const bundleVersion = String(manifest.product?.version ?? "");
  if (manifest.schema_version !== 1 || manifest.product?.name !== "WorkBuddy" || !bundleVersion) {
    throw new Error("invalid WorkBuddy bundle manifest");
  }
  if (bundleVersion !== productVersion) {
    throw new Error(`WorkBuddy bundle/CDP version mismatch: ${bundleVersion} != ${productVersion}`);
  }

  const appAsar = manifest.app_asar ?? {};
  const appAsarPath = path.resolve(String(appAsar.source_locator ?? ""));
  const expectedAsarSha256 = String(appAsar.sha256 ?? "");
  const actualAsarSha256 = await hashFile(appAsarPath);
  if (!/^[a-f0-9]{64}$/.test(expectedAsarSha256) || actualAsarSha256 !== expectedAsarSha256) {
    throw new Error(`WorkBuddy app.asar hash mismatch: ${actualAsarSha256} != ${expectedAsarSha256 || "missing"}`);
  }

  const integrity = appAsar.integrity ?? {};
  const integrityHash = String(integrity.hash ?? "");
  if (integrity.algorithm !== "SHA256" || !/^[a-f0-9]{64}$/.test(integrityHash)) {
    throw new Error("WorkBuddy app.asar integrity metadata is missing or invalid");
  }
  const rendererEntryPath = path.resolve(fileURLToPath(rendererUrl));
  const expectedRendererEntry = `${appAsarPath}${path.sep}renderer${path.sep}index.html`;
  if (rendererEntryPath !== expectedRendererEntry) {
    throw new Error(`renderer is not loaded from the frozen app.asar: ${rendererEntryPath}`);
  }

  return {
    bundle_manifest_sha256: hash(manifestBytes),
    bundle_identifier: String(manifest.bundle?.identifier ?? ""),
    bundle_version: bundleVersion,
    app_asar_sha256: actualAsarSha256,
    app_asar_integrity_sha256: integrityHash,
    renderer_entry_path: rendererEntryPath,
    renderer_authority: "bundle-app-asar",
  };
}

export async function calibrateWorkBuddyViewport(page, viewportSpec) {
  const match = String(viewportSpec ?? "").match(/^(\d+)x(\d+)$/);
  if (!match) throw new Error("WORKBUDDY_VIEWPORT is required as <width>x<height>");
  const desired = { width: Number(match[1]), height: Number(match[2]) };
  const desiredDpr = Number(process.env.WORKBUDDY_DPR ?? "2");
  let session;
  let initial;
  let pageSession;
  try {
    pageSession = await page.context().newCDPSession(page);
    const targetInfo = (await pageSession.send("Target.getTargetInfo")).targetInfo;
    session = await page.context().browser().newBrowserCDPSession();
    initial = await session.send("Browser.getWindowForTarget", { targetId: targetInfo.targetId });
  } catch (error) {
    if (!String(error).includes("Browser.getWindowForTarget")) throw error;
    pageSession ??= await page.context().newCDPSession(page);
    await pageSession.send("Emulation.setDeviceMetricsOverride", {
      width: desired.width,
      height: desired.height,
      deviceScaleFactor: desiredDpr,
      mobile: false,
    });
    const actual = await page.evaluate(() => ({ width: innerWidth, height: innerHeight, dpr: devicePixelRatio }));
    if (actual.width !== desired.width || actual.height !== desired.height || actual.dpr !== desiredDpr) {
      throw new Error(`cannot emulate WorkBuddy viewport to ${desired.width}x${desired.height}@${desiredDpr}; got ${actual.width}x${actual.height}@${actual.dpr}`);
    }
    return {
      viewport: actual,
      calibration: "renderer-device-metrics",
      restore: () => pageSession.send("Emulation.clearDeviceMetricsOverride").catch(() => {}),
    };
  }
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const actual = await page.evaluate(() => ({ width: innerWidth, height: innerHeight, dpr: devicePixelRatio }));
    if (actual.width === desired.width && actual.height === desired.height && actual.dpr === desiredDpr) {
      return { viewport: actual, calibration: "native-window-bounds", restore: () => restoreBounds(session, initial) };
    }
    const current = await session.send("Browser.getWindowBounds", { windowId: initial.windowId });
    const bounds = current.bounds;
    await session.send("Browser.setWindowBounds", {
      windowId: initial.windowId,
      bounds: {
        windowState: "normal",
        width: Math.max(1, Number(bounds.width ?? actual.width) + desired.width - actual.width),
        height: Math.max(1, Number(bounds.height ?? actual.height) + desired.height - actual.height),
      },
    });
    await page.waitForTimeout(250);
  }
  const actual = await page.evaluate(() => ({ width: innerWidth, height: innerHeight }));
  throw new Error(`cannot calibrate WorkBuddy viewport to ${desired.width}x${desired.height}; got ${actual.width}x${actual.height}`);
}

async function restoreBounds(session, initial) {
  await session.send("Browser.setWindowBounds", { windowId: initial.windowId, bounds: initial.bounds }).catch(() => {});
}

async function hashFile(file) {
  const digest = crypto.createHash("sha256");
  for await (const chunk of fsSync.createReadStream(file)) digest.update(chunk);
  return digest.digest("hex");
}

function hash(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}
