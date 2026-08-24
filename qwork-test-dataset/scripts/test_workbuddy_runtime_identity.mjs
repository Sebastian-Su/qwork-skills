import crypto from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { bindWorkBuddyRuntimeIdentity } from "./workbuddy-runtime-identity.mjs";

const root = await fs.mkdtemp(path.join(os.tmpdir(), "workbuddy-runtime-identity-"));
try {
  const asarPath = path.join(root, "WorkBuddy.app", "Contents", "Resources", "app.asar");
  await fs.mkdir(path.dirname(asarPath), { recursive: true });
  await fs.writeFile(asarPath, "frozen-5.3.8-asar");
  const asarSha256 = hash(Buffer.from("frozen-5.3.8-asar"));
  const manifestPath = path.join(root, "manifest.json");
  await fs.writeFile(manifestPath, JSON.stringify({
    schema_version: 1,
    product: { name: "WorkBuddy", version: "5.3.8" },
    bundle: { identifier: "com.workbuddy.workbuddy", build_version: "5.3.8" },
    app_asar: {
      source_locator: asarPath,
      sha256: asarSha256,
      integrity: { algorithm: "SHA256", hash: "b".repeat(64) },
    },
  }));
  const rendererUrl = pathToFileURL(`${asarPath}/renderer/index.html`).href;
  const identity = await bindWorkBuddyRuntimeIdentity({
    bundleManifestPath: manifestPath,
    productVersion: "5.3.8",
    rendererUrl,
  });
  if (identity.app_asar_sha256 !== asarSha256 || identity.renderer_authority !== "bundle-app-asar") {
    throw new Error("runtime identity did not bind the frozen app.asar");
  }
  await fs.writeFile(asarPath, "drifted-asar");
  let rejectedDrift = false;
  try {
    await bindWorkBuddyRuntimeIdentity({ bundleManifestPath: manifestPath, productVersion: "5.3.8", rendererUrl });
  } catch (error) {
    if (!String(error).includes("hash mismatch")) throw error;
    rejectedDrift = true;
  }
  if (!rejectedDrift) throw new Error("runtime identity accepted a drifted app.asar");
  console.log("WorkBuddy runtime identity: PASS");
} finally {
  await fs.rm(root, { recursive: true, force: true });
}

function hash(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}
