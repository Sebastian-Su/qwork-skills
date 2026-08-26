import fs from "node:fs/promises";
import path from "node:path";

export const TEMP_ROOT_NAME = "QWORK-E2E-TEMPORARY-DATA-DO-NOT-COMMIT";

export async function loadPrivateCaseAuthority({ skillRoot, repo, caseId, title }) {
  const [canonicalSkillRoot, canonicalRepo] = await Promise.all([
    fs.realpath(skillRoot),
    fs.realpath(repo),
  ]);
  const casePath = path.join(skillRoot, "data/datasets/cases", `${caseId}.json`);
  const record = JSON.parse(await fs.readFile(casePath, "utf8"));
  if (record.id !== caseId || record.title !== title) {
    throw new Error(`private Case identity mismatch: ${caseId}`);
  }
  if (!String(record.execution_contract?.route_id || "").startsWith("qwork.private-playwright.")) {
    throw new Error(`private Case does not use a private Playwright route: ${caseId}`);
  }
  const supporting = record.execution_contract?.observability?.source_contract?.supporting_contracts;
  if (!Array.isArray(supporting) || supporting.length === 0) {
    throw new Error(`private Case has no supporting authority: ${caseId}`);
  }
  const authorityFiles = supporting.map((item) => [item.path, resolveLocator(item.path, skillRoot, repo)]);
  for (const [locator, file] of authorityFiles) {
    const actual = await fs.realpath(file);
    if (
      actual !== file
      && !actual.startsWith(`${canonicalSkillRoot}${path.sep}`)
      && !actual.startsWith(`${canonicalRepo}${path.sep}`)
    ) {
      throw new Error(`private Case authority escapes approved roots: ${locator}`);
    }
  }
  return { record, authorityFiles };
}

export async function resolvePrivateRunRoot({ skillEntry, skillRoot, cwd, value }) {
  if (!path.isAbsolute(value)) {
    throw new Error("private E2E run root must be an absolute path");
  }
  const input = path.resolve(cwd, value);
  let ancestor = input;
  const missing = [];
  while (true) {
    try {
      const actual = await fs.realpath(ancestor);
      ancestor = actual;
      break;
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
      missing.unshift(path.basename(ancestor));
      const parent = path.dirname(ancestor);
      if (parent === ancestor) throw error;
      ancestor = parent;
    }
  }
  const resolved = path.join(ancestor, ...missing);
  const canonicalSkillRoot = await fs.realpath(skillRoot);
  const repoRoot = path.resolve(skillEntry, "../../..");
  for (const protectedRoot of [canonicalSkillRoot, repoRoot]) {
    const relative = path.relative(protectedRoot, resolved);
    if (!relative.startsWith("..") && !path.isAbsolute(relative)) {
      throw new Error(`private E2E run root resolves inside a protected Git or Skill root: ${resolved}`);
    }
  }
  const parts = resolved.split(path.sep);
  const markerIndex = parts.lastIndexOf(TEMP_ROOT_NAME);
  if (markerIndex < 0 || markerIndex === parts.length - 1) {
    throw new Error(`private E2E run root must be below ${TEMP_ROOT_NAME}: ${resolved}`);
  }
  return resolved;
}

function resolveLocator(locator, skillRoot, repo) {
  const skillPrefix = "skill://qwork-test-dataset/";
  if (locator.startsWith(skillPrefix)) return path.join(skillRoot, locator.slice(skillPrefix.length));
  if (locator.startsWith("repo://")) return path.join(repo, locator.slice("repo://".length));
  if (!locator.includes("://")) return path.join(repo, locator);
  throw new Error(`unsupported private Case authority locator: ${locator}`);
}
