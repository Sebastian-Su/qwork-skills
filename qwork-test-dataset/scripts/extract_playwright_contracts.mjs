#!/usr/bin/env node
/** Extract stable action/assertion contracts from Playwright/Vitest-style test calls. */
import crypto from "node:crypto";
import process from "node:process";
import { requireFromProject } from "./project-require.mjs";

const ts = requireFromProject("typescript");

const path = process.argv[2] || "input.spec.ts";
let input = "";
process.stdin.setEncoding("utf8");
for await (const chunk of process.stdin) input += chunk;
const source = ts.createSourceFile(path, input, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
const results = [];

function calleeParts(expression) {
  const parts = [];
  let current = expression;
  while (ts.isPropertyAccessExpression(current)) {
    parts.unshift(current.name.text);
    current = current.expression;
  }
  if (ts.isIdentifier(current)) parts.unshift(current.text);
  return parts;
}
function testKind(node) {
  if (!ts.isCallExpression(node)) return null;
  const parts = calleeParts(node.expression);
  if (!["test", "it"].includes(parts[0])) return null;
  if (parts.includes("describe")) return null;
  return parts.join(".");
}
function literalText(node) {
  if (!node) return null;
  return ts.isStringLiteralLike(node) || ts.isNoSubstitutionTemplateLiteral(node) ? node.text : null;
}
function compact(node, limit = 420) {
  const value = node.getText(source).replace(/\s+/g, " ").trim();
  return value.length > limit ? `${value.slice(0, limit - 1)}…` : value;
}
const actionMethods = new Set([
  "click", "dblclick", "fill", "press", "type", "check", "uncheck", "selectOption",
  "setInputFiles", "dragTo", "hover", "focus", "blur", "goto", "reload", "close",
]);
const assertionPrefixes = ["toBe", "toHave", "toContain", "toEqual", "toMatch", "toPass", "toThrow"];
function classifyCall(node) {
  const parts = calleeParts(node.expression);
  const last = parts.at(-1) || "";
  if (actionMethods.has(last)) return "action";
  if (assertionPrefixes.some((prefix) => last.startsWith(prefix))) return "assertion";
  const value = compact(node, 160);
  if (/\bexpect(?:\.poll|\.soft)?\s*\(/.test(value)) return "assertion";
  if (/^(?:test|it)(?:\.|\()/.test(value)) return null;
  return "helper";
}
function contractFor(node, kind) {
  const title = literalText(node.arguments[0]);
  if (!title) return null;
  const callback = node.arguments.find((arg, index) => index > 0 && (ts.isArrowFunction(arg) || ts.isFunctionExpression(arg)));
  if (!callback) return null;
  const events = [];
  function visitBody(candidate) {
    if (ts.isCallExpression(candidate)) {
      const eventKind = classifyCall(candidate);
      if (eventKind) {
        const position = source.getLineAndCharacterOfPosition(candidate.getStart(source));
        events.push({kind: eventKind, line: position.line + 1, expression: compact(candidate)});
        if (eventKind === "action" || eventKind === "assertion") return;
      }
    }
    ts.forEachChild(candidate, visitBody);
  }
  visitBody(callback.body);
  const start = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
  const end = source.getLineAndCharacterOfPosition(node.getEnd()).line + 1;
  return {
    title, kind, line_start: start, line_end: end,
    body_sha256: crypto.createHash("sha256").update(callback.body.getText(source)).digest("hex"),
    actions: events.filter((event) => event.kind === "action"),
    assertions: events.filter((event) => event.kind === "assertion"),
    helpers: events.filter((event) => event.kind === "helper"),
  };
}
function visit(node) {
  const kind = testKind(node);
  if (kind) {
    const contract = contractFor(node, kind);
    if (contract) results.push(contract);
  }
  ts.forEachChild(node, visit);
}
visit(source);
process.stdout.write(`${JSON.stringify({schema_version: 1, path, tests: results})}\n`);
