import fs from "node:fs/promises";
import path from "node:path";

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
  const input = path.resolve(cwd, value);
  let relative = null;
  for (const base of [skillRoot, skillEntry]) {
    const candidate = path.relative(base, input);
    if (candidate && !candidate.startsWith("..") && !path.isAbsolute(candidate)) {
      relative = candidate;
      break;
    }
  }
  if (!relative || !(relative === "data/runs" || relative.startsWith(`data/runs${path.sep}`))) {
    throw new Error(`run root must be inside the private Dataset data/runs directory: ${input}`);
  }
  if (relative === "data/runs") {
    throw new Error("run root must identify one unique run below data/runs");
  }
  const resolved = path.join(skillRoot, relative);
  let ancestor = resolved;
  while (true) {
    try {
      const actual = await fs.realpath(ancestor);
      const approved = await fs.realpath(path.join(skillRoot, "data/runs"));
      if (actual !== approved && !actual.startsWith(`${approved}${path.sep}`)) {
        throw new Error(`run root existing ancestor escapes private Dataset data/runs: ${ancestor}`);
      }
      break;
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
      const parent = path.dirname(ancestor);
      if (parent === ancestor) throw error;
      ancestor = parent;
    }
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
