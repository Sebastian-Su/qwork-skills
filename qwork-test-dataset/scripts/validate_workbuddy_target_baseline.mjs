import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { requireFromProject } from "./project-require.mjs";

const { parse } = requireFromProject("yaml");
const skillRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const contractPath = path.join(skillRoot, "references", "workbuddy-target-baseline.yaml");
const contract = parse(await fs.readFile(contractPath, "utf8"));

assert(contract.schema_version === 1, "unsupported target baseline schema");
assert(contract.product === "WorkBuddy", "target product must be WorkBuddy");
assert(contract.approved_target_version === "5.3.8", "approved target must be 5.3.8");

const bundlePath = resolveSkillUri(contract.normative_sources.bundle_manifest);
const cdpPath = resolveSkillUri(contract.normative_sources.cdp_ui);
const motionPath = resolveSkillUri(contract.normative_sources.cdp_motion);
const [bundleBytes, cdpBytes, motionBytes] = await Promise.all([
  fs.readFile(bundlePath), fs.readFile(cdpPath), fs.readFile(motionPath),
]);
const bundle = JSON.parse(bundleBytes);
const cdp = JSON.parse(cdpBytes);
const motion = JSON.parse(motionBytes);

assert(bundle.product?.version === contract.approved_target_version, "bundle version drifted");
assert(bundle.bundle?.identifier === contract.bundle.identifier, "bundle identifier drifted");
assert(bundle.bundle?.build_version === contract.bundle.build_version, "bundle build version drifted");
assert(bundle.app_asar?.sha256 === contract.bundle.app_asar_sha256, "app.asar hash drifted");
assert(bundle.app_asar?.integrity?.hash === contract.bundle.electron_asar_integrity_sha256, "Electron asar integrity drifted");

for (const [kind, manifest] of [["CDP", cdp], ["motion", motion]]) {
  assert(manifest.product === "WorkBuddy", `${kind} product drifted`);
  assert(manifest.version === contract.approved_target_version, `${kind} version drifted`);
  const runtime = manifest.runtime_identity ?? {};
  assert(runtime.bundle_manifest_sha256 === hash(bundleBytes), `${kind} bundle manifest binding drifted`);
  assert(runtime.bundle_identifier === contract.bundle.identifier, `${kind} bundle identifier binding drifted`);
  assert(runtime.bundle_version === contract.approved_target_version, `${kind} bundle version binding drifted`);
  assert(runtime.app_asar_sha256 === contract.bundle.app_asar_sha256, `${kind} app.asar binding drifted`);
  assert(runtime.app_asar_integrity_sha256 === contract.bundle.electron_asar_integrity_sha256, `${kind} integrity binding drifted`);
  assert(runtime.renderer_authority === "bundle-app-asar", `${kind} renderer authority drifted`);
}

assert(cdp.state_count === cdp.records?.length && cdp.state_count === 19, "5.3.8 CDP state closure is incomplete");
assert(motion.record_count === motion.records?.length && motion.record_count === 7, "5.3.8 motion closure is incomplete");
for (const record of cdp.records) {
  assert(JSON.stringify(record.viewport) === JSON.stringify(contract.acceptance_policy.normative_viewport), `CDP viewport drifted: ${record.state}`);
}
assert(JSON.stringify(motion.viewport) === JSON.stringify(contract.acceptance_policy.normative_viewport), "motion viewport drifted");
await validateArtifacts(path.dirname(cdpPath), cdp.records, "screenshot", "screenshot_sha256");
await validateMotionArtifacts(path.dirname(motionPath), motion.records);

console.log(JSON.stringify({
  status: "ok",
  target: "WorkBuddy 5.3.8",
  cdp_states: cdp.state_count,
  motion_records: motion.record_count,
  app_asar_sha256: contract.bundle.app_asar_sha256,
}));

function resolveSkillUri(uri) {
  const prefix = "skill://qwork-test-dataset/";
  assert(typeof uri === "string" && uri.startsWith(prefix), `invalid skill URI: ${uri}`);
  const resolved = path.resolve(skillRoot, uri.slice(prefix.length));
  assert(resolved.startsWith(`${skillRoot}${path.sep}`), `skill URI escapes root: ${uri}`);
  return resolved;
}

async function validateArtifacts(root, records, fileKey, hashKey) {
  for (const record of records) {
    const file = path.resolve(root, String(record[fileKey] ?? ""));
    assert(file.startsWith(`${root}${path.sep}`), `artifact escapes snapshot: ${file}`);
    assert(hash(await fs.readFile(file)) === record[hashKey], `artifact hash drifted: ${path.basename(file)}`);
  }
}

async function validateMotionArtifacts(root, records) {
  for (const record of records) {
    const file = path.resolve(root, String(record.file ?? ""));
    assert(file.startsWith(`${root}${path.sep}`), `motion artifact escapes snapshot: ${file}`);
    const artifact = JSON.parse(await fs.readFile(file, "utf8"));
    assert(hash(Buffer.from(JSON.stringify(artifact.payload))) === record.payload_sha256, `motion payload hash drifted: ${path.basename(file)}`);
  }
}

function hash(bytes) {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
