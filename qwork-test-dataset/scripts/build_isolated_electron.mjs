#!/usr/bin/env node

import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const scriptRoot = path.dirname(fileURLToPath(import.meta.url));
const skillRoot = path.resolve(scriptRoot, "..");
const repo = path.resolve(process.argv[2] || process.cwd());
const skillEntry = path.join(repo, ".agents/skills/qwork-test-dataset");
if (await fs.realpath(skillEntry) !== skillRoot) {
  throw new Error(`QWork Dataset Skill entry resolves to an unexpected entity: ${skillEntry}`);
}
const runRoot = path.resolve(
  process.argv[3] || path.join(skillRoot, "data/runs/isolated-electron"),
);
const appRoot = path.join(runRoot, "app");
const buildRoot = path.join(appRoot, "out");
const config = path.join(skillEntry, "scripts/electron-isolated-build.config.ts");

assertInside(skillRoot, runRoot);
await fs.rm(appRoot, { recursive: true, force: true });
await fs.mkdir(runRoot, { recursive: true });
await fs.mkdir(appRoot, { recursive: true });

await run(path.join(repo, "node_modules/.bin/electron-vite"), [
  "build",
  repo,
  "--config",
  config,
  "--logLevel",
  "warn",
], {
  ...process.env,
  NODE_OPTIONS: preserveSymlinks(process.env.NODE_OPTIONS),
  QWORK_E2E_REPO_ROOT: repo,
  QWORK_E2E_BUILD_ROOT: buildRoot,
});

await fs.symlink(path.join(repo, "node_modules"), path.join(appRoot, "node_modules"));
await fs.symlink(path.join(repo, "resources"), path.join(appRoot, "resources"));
await fs.symlink(path.join(repo, "build"), path.join(appRoot, "build"));
const sourcePackage = JSON.parse(
  await fs.readFile(path.join(repo, "package.json"), "utf8"),
);
const isolatedPackage = {
  name: `${sourcePackage.name || "qwork"}-isolated-e2e`,
  version: sourcePackage.version || "0.0.0",
  private: true,
  type: sourcePackage.type || "module",
  main: "out/main/index.js",
};
await fs.writeFile(
  path.join(appRoot, "package.json"),
  `${JSON.stringify(isolatedPackage, null, 2)}\n`,
  "utf8",
);
const manifest = {
  schema_version: 1,
  repo,
  run_root: runRoot,
  build_root: buildRoot,
  app_root: appRoot,
  entry: path.join(appRoot, "out/main/index.js"),
  source_revision: await git(repo, ["rev-parse", "HEAD"]),
  source_status: await git(repo, ["status", "--short", "--untracked-files=all"]),
  isolation: {
    output_outside_repo_out: !buildRoot.startsWith(path.join(repo, "out")),
    build_output_is_inside_transient_app: buildRoot.startsWith(`${appRoot}${path.sep}`),
    app_root_is_private_dataset_run: true,
    real_qwork_home_reused: false,
    real_provider_allowed: false,
  },
  runtime_assets: {
    build: path.join(repo, "build"),
    resources: path.join(repo, "resources"),
  },
};
await fs.writeFile(
  path.join(runRoot, "build-manifest.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
  "utf8",
);
process.stdout.write(`${JSON.stringify(manifest)}\n`);

function preserveSymlinks(value) {
  return `${value || ""} --preserve-symlinks`.trim();
}

function assertInside(parent, child) {
  const relative = path.relative(parent, child);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`run root must be inside the private Dataset Skill: ${child}`);
  }
}

function run(command, args, env) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd: repo, env, stdio: "inherit" });
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (code === 0) resolve();
      else reject(new Error(`${command} exited with ${code ?? signal}`));
    });
  });
}

async function git(cwd, args) {
  return new Promise((resolve, reject) => {
    const child = spawn("git", args, { cwd, stdio: ["ignore", "pipe", "pipe"] });
    let output = "";
    let error = "";
    child.stdout.on("data", (chunk) => { output += chunk; });
    child.stderr.on("data", (chunk) => { error += chunk; });
    child.once("error", reject);
    child.once("exit", (code) => {
      if (code === 0) resolve(output.trim());
      else reject(new Error(error.trim() || `git exited with ${code}`));
    });
  });
}
