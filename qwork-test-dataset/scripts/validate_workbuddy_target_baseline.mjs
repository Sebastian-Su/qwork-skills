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
const darkThemeContractPath = resolveSkillUri(contract.normative_sources.cdp_dark_theme);
const [bundleBytes, cdpBytes, motionBytes, darkThemeContractBytes] = await Promise.all([
  fs.readFile(bundlePath), fs.readFile(cdpPath), fs.readFile(motionPath), fs.readFile(darkThemeContractPath),
]);
const bundle = JSON.parse(bundleBytes);
const cdp = JSON.parse(cdpBytes);
const motion = JSON.parse(motionBytes);
const darkThemeContract = parse(darkThemeContractBytes.toString("utf8"));

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
await validateDarkThemeContract(darkThemeContract);

console.log(JSON.stringify({
  status: "ok",
  target: "WorkBuddy 5.3.8",
  cdp_states: cdp.state_count,
  motion_records: motion.record_count,
  dark_theme_states: darkThemeContract.evidence.dark_surfaces.state_count,
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

async function validateDarkThemeContract(themeContract) {
  assert(themeContract.schema_version === 1, "unsupported dark theme contract schema");
  assert(themeContract.product === "WorkBuddy" && themeContract.version === contract.approved_target_version, "dark theme contract target drifted");
  assert(themeContract.runtime_identity.bundle_identifier === contract.bundle.identifier, "dark theme bundle identifier drifted");
  assert(themeContract.runtime_identity.app_asar_sha256 === contract.bundle.app_asar_sha256, "dark theme app.asar drifted");
  assert(themeContract.runtime_identity.electron_asar_integrity_sha256 === contract.bundle.electron_asar_integrity_sha256, "dark theme integrity drifted");
  assert(themeContract.selection_contract.follow_system_control_observed === false, "5.3.8 must not invent a follow-system control");
  assert(JSON.stringify(themeContract.selection_contract.modes_observed) === JSON.stringify(["light", "dark"]), "dark theme mode inventory drifted");
  assert(themeContract.dark_runtime_contract.vscode_theme_name === "IDE Night", "dark theme name drifted");
  assert(themeContract.dark_runtime_contract.vscode_theme_kind === "vscode-dark", "dark theme kind drifted");
  assert(themeContract.dark_runtime_contract.computed_color_scheme === "dark", "dark computed color scheme drifted");
  assert(themeContract.dark_runtime_contract.body_background === "rgb(24, 24, 24)", "dark body background drifted");
  assert(themeContract.acceptance_status.pixel_golden === "not-approved", "candidate dark screenshots must not self-approve as Golden");
  assert(themeContract.acceptance_status.release_conclusion === "not_evaluated", "dark release conclusion must fail closed until the matrix is complete");

  const evidenceEntries = Object.values(themeContract.evidence);
  for (const evidence of evidenceEntries) {
    const evidencePath = resolveSkillUri(evidence.uri);
    const bytes = await fs.readFile(evidencePath);
    assert(hash(bytes) === evidence.sha256, `dark theme evidence manifest drifted: ${evidence.uri}`);
  }

  const transitionPath = resolveSkillUri(themeContract.evidence.transition.uri);
  const transition = JSON.parse(await fs.readFile(transitionPath, "utf8"));
  assert(transition.result === "pass" && transition.target_theme === "dark", "dark transition evidence failed");
  assert(transition.frames?.length === themeContract.evidence.transition.frame_count, "dark transition frame closure drifted");
  await validateArtifacts(path.dirname(transitionPath), transition.frames, "file", "sha256");
  assertResolvedDark(transition.final_theme, "transition final theme");

  const surfacesPath = resolveSkillUri(themeContract.evidence.dark_surfaces.uri);
  const surfaces = JSON.parse(await fs.readFile(surfacesPath, "utf8"));
  assert(surfaces.state_count === 19 && surfaces.records?.length === 19, "dark surface closure is incomplete");
  assert(surfaces.theme_coverage?.per_record_binding === true && surfaces.theme_coverage?.expected_theme === "dark", "dark surface theme binding is missing");
  for (const record of surfaces.records) assertResolvedDark(record.resolved_theme, `dark surface ${record.state}`);
  await validateArtifacts(path.dirname(surfacesPath), surfaces.records, "screenshot", "screenshot_sha256");

  const restartPath = resolveSkillUri(themeContract.evidence.cold_restart.uri);
  const restart = JSON.parse(await fs.readFile(restartPath, "utf8"));
  assert(restart.result === "pass" && restart.observation === "cold-start-after-process-termination", "dark restart evidence failed");
  assertResolvedDark(restart.theme, "cold restart theme");
  await validateArtifacts(path.dirname(restartPath), [restart], "screenshot", "screenshot_sha256");

  const restorePath = resolveSkillUri(themeContract.evidence.restore.uri);
  const restore = JSON.parse(await fs.readFile(restorePath, "utf8"));
  assert(restore.result === "pass" && restore.target_theme === "light", "theme restore evidence failed");
  assert(restore.final_theme?.computed_color_scheme === "light" && restore.final_theme?.stored_theme?.theme === "light", "theme was not restored to light");
  await validateArtifacts(path.dirname(restorePath), restore.frames, "file", "sha256");
}

function assertResolvedDark(theme, label) {
  assert(theme?.computed_color_scheme === "dark" || theme?.resolved_theme === "dark", `${label} is not resolved dark`);
  assert(theme?.theme_name === "IDE Night", `${label} has the wrong theme name`);
  assert(theme?.theme_kind === "vscode-dark", `${label} has the wrong theme kind`);
  assert(theme?.stored_theme?.theme === "dark" && theme?.stored_theme?.followSystem === false, `${label} has the wrong stored theme`);
}

function hash(bytes) {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
