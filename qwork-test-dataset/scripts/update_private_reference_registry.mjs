#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { requireFromProject } from "./project-require.mjs";

const { parse, stringify } = requireFromProject("yaml");
const scriptRoot = path.dirname(fileURLToPath(import.meta.url));
const skillRoot = path.resolve(scriptRoot, "..");
const matrixPath = path.resolve(process.argv[2] || "");
if (!process.argv[2]) throw new Error("matrix report path is required");
const matrix = JSON.parse(await fs.readFile(matrixPath, "utf8"));
if (matrix.status !== "complete" || matrix.results?.length !== matrix.coordinate_count) {
  throw new Error("private reference matrix is not complete");
}
const registryPath = path.join(skillRoot, "references/private-reference-runs.yaml");
const registry = parse(await fs.readFile(registryPath, "utf8"));
const registeredIds = new Set([
  ...Object.keys(registry.runs || {}),
  ...Object.keys(registry.failed_runs || {}),
]);
const matrixIds = new Set(matrix.results.map((item) => item.case_id));
if (registeredIds.size !== matrixIds.size || [...registeredIds].some((id) => !matrixIds.has(id))) {
  throw new Error("matrix Case set differs from the private reference registry");
}
const groupId = path.basename(path.dirname(matrixPath));
for (const result of matrix.results) {
  const bucket = result.expected === "pass" ? registry.runs : registry.failed_runs;
  const other = result.expected === "pass" ? registry.failed_runs : registry.runs;
  if (!bucket?.[result.case_id] || other?.[result.case_id]) {
    throw new Error(`reference classification mismatch: ${result.case_id}`);
  }
  if (result.observed !== result.expected) {
    throw new Error(`matrix outcome mismatch: ${result.case_id}`);
  }
  bucket[result.case_id].run_id = `${groupId}/${result.case_id}`;
  bucket[result.case_id].report = result.report;
  bucket[result.case_id].report_sha256 = result.report_sha256;
}
const temp = `${registryPath}.tmp`;
await fs.writeFile(temp, stringify(registry, { lineWidth: 0 }), "utf8");
await fs.rename(temp, registryPath);
process.stdout.write(`${JSON.stringify({ status: "ok", updated: matrix.results.length, registry: registryPath })}\n`);
