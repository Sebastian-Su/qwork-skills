import fs from "node:fs";
import path from "node:path";
import { requireFromProject } from "./project-require.mjs";

const Ajv = requireFromProject("ajv");
const YAML = requireFromProject("yaml");

const root = path.resolve(process.argv[2] ?? ".agents/skills/qwork-test-dataset");
const schema = YAML.parse(fs.readFileSync(path.join(root, "references/case-schema.yaml"), "utf8"));
// Ajv 6 supports draft-07 semantics. Remove only the draft-2020 meta declaration;
// all project keywords used here are compatible or independently checked below.
delete schema.$schema;
const ajv = new Ajv({ allErrors: true, jsonPointers: true, schemaId: "auto", unknownFormats: "ignore" });
let validate;
try {
  validate = ajv.compile(schema);
} catch (error) {
  console.error(`case schema compile failed: ${error.message}`);
  process.exit(1);
}
const caseDir = path.join(root, "data/datasets/cases");
const files = fs.readdirSync(caseDir).filter((name) => name.endsWith(".json")).sort();
const errors = [];
for (const file of files) {
  const value = JSON.parse(fs.readFileSync(path.join(caseDir, file), "utf8"));
  if (!validate(value)) {
    for (const error of validate.errors ?? []) errors.push(`${value.id ?? file}${error.dataPath}: ${error.message}`);
  }
  if (value.schema_version !== 3) errors.push(`${value.id}: schema_version must be 3`);
  const execution = value.execution_contract ?? {};
  const required = ["contract_version", "readiness", "route_id", "target", "authorization", "preflight", "launch", "navigation", "fixtures", "observability", "reference_run", "cleanup", "blockers"];
  for (const key of required) if (!(key in execution)) errors.push(`${value.id}: execution_contract missing ${key}`);
  if (!["ready", "partial", "missing", "stale", "blocked", "not_applicable"].includes(execution.readiness)) errors.push(`${value.id}: invalid execution readiness`);
  if (execution.readiness === "ready" && execution.reference_run?.status !== "passed") errors.push(`${value.id}: ready requires passed reference run`);
  const sourceContract = execution.observability?.source_contract;
  const isPlaywright = String(execution.route_id ?? "").startsWith("qwork.playwright.") ||
    String(execution.route_id ?? "").startsWith("qwork.private-playwright.");
  const isRequirementCase = String(execution.route_id ?? "").startsWith("qwork.requirement.");
  if (isPlaywright && !sourceContract) {
    errors.push(`${value.id}: Playwright route requires a source_contract`);
  }
  if (!isPlaywright && sourceContract !== null) {
    errors.push(`${value.id}: source requirement route must not invent a Playwright source_contract`);
  }
  if (isRequirementCase) {
    const requirements = new Map((value.derived_requirements ?? []).map((item) => [item.requirement_id, item]));
    const oracles = new Map((value.oracles ?? []).map((item) => [item.requirement_id, item]));
    const probes = new Map((value.causal_probe_plan ?? []).map((item) => [item.requirement_id, item]));
    const requirementIds = [...requirements.keys()].sort();
    const oracleIds = [...oracles.keys()].sort();
    const probeIds = [...probes.keys()].sort();
    if (requirements.size !== (value.derived_requirements ?? []).length) errors.push(`${value.id}: duplicate derived requirement in causal Case`);
    if (oracles.size !== (value.oracles ?? []).length) errors.push(`${value.id}: duplicate Oracle requirement in causal Case`);
    if (probes.size !== (value.causal_probe_plan ?? []).length) errors.push(`${value.id}: duplicate causal probe requirement`);
    if (JSON.stringify(requirementIds) !== JSON.stringify(oracleIds) || JSON.stringify(oracleIds) !== JSON.stringify(probeIds)) {
      errors.push(`${value.id}: Requirement, Oracle and causal probe sets must be identical`);
    }
    const actions = (value.steps ?? []).map((item) => String(item.action ?? ""));
    if (actions.length === 2 && actions[1] === value.title) errors.push(`${value.id}: causal Case must not be launch plus title only`);
    if (!actions.some((item) => item.includes("capture the pre-trigger baseline"))) errors.push(`${value.id}: causal Case lacks pre-trigger baseline`);
    if (!actions.some((item) => item.includes("perform the source-defined scenario trigger"))) errors.push(`${value.id}: causal Case lacks source-bound trigger`);
    for (const requirementId of requirementIds) {
      const oracle = oracles.get(requirementId);
      const probe = probes.get(requirementId);
      if (probe?.then !== oracle?.assertion || probe?.oracle_type !== oracle?.type) {
        errors.push(`${value.id}: causal probe differs from Oracle ${requirementId}`);
      }
      if (!actions.some((item) => item.includes(requirementId) && item.includes(String(oracle?.assertion ?? "")))) {
        errors.push(`${value.id}: no exact post-trigger step for ${requirementId}`);
      }
      if (!(value.expected_outcomes ?? []).includes(oracle?.assertion)) errors.push(`${value.id}: exact outcome missing for ${requirementId}`);
      if (!(value.forbidden_outcomes ?? []).some((item) => String(item).includes(requirementId) && String(item).includes(String(oracle?.assertion ?? "")))) {
        errors.push(`${value.id}: counterfactual failure missing for ${requirementId}`);
      }
    }
  }
  const sourceIds = new Set((value.sources ?? []).map((item) => item.source_id));
  const oracleContract = execution.observability?.oracle_contract;
  const spec = String(sourceContract?.spec ?? "");
  const isCurrentCdpCase = sourceIds.has("WORKBUDDY-CDP-5-3-12-V4");
  const isPlatformPixelCase =
    spec === "skill://qwork-test-dataset/data/e2e/platform-oracle-matrix.spec.ts" &&
    String(value.title ?? "").startsWith("WB-UI-PIXEL-");
  if ((isCurrentCdpCase || isPlatformPixelCase) && !oracleContract) {
    errors.push(`${value.id}: pixel-comparison Case requires an oracle_contract`);
  }
  if (!isCurrentCdpCase && !isPlatformPixelCase && oracleContract != null) {
    errors.push(`${value.id}: non-pixel Case must not invent an oracle_contract`);
  }
  const markedLive = String(execution.route_id ?? "").startsWith("qwork.playwright.") &&
    (spec.includes(".live.spec.ts") || spec.includes("-live.spec.ts") || spec.includes("auth-real-login") || spec === "e2e/real-expert-agent.spec.ts" || String(value.title ?? "").toLowerCase().includes("@live"));
  if (markedLive && execution.authorization?.required !== true) {
    errors.push(`${value.id}: live-marked Playwright Case must require authorization`);
  }
  if (sourceContract && sourceContract.line_end < sourceContract.line_start) {
    errors.push(`${value.id}: source_contract line_end precedes line_start`);
  }
}
if (errors.length) {
  console.error(`AJV/schema v3 validation failed (${errors.length}):`);
  for (const error of errors.slice(0, 300)) console.error(`- ${error}`);
  process.exit(1);
}
console.log(JSON.stringify({ status: "ok", case_count: files.length, validator: "ajv-6.15.0+execution-v3" }));
