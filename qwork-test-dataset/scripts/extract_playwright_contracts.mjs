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
function expandedTitles(node) {
  if (!node) return [];
  const literal = literalText(node);
  if (literal !== null) return [literal];
  if (!ts.isTemplateExpression(node)) return [];
  const variables = new Set();
  for (const span of node.templateSpans) {
    const expression = span.expression;
    if (ts.isIdentifier(expression)) variables.add(expression.text);
    else if (ts.isCallExpression(expression)
      && ts.isPropertyAccessExpression(expression.expression)
      && expression.expression.name.text === "toUpperCase"
      && ts.isIdentifier(expression.expression.expression)) {
      variables.add(expression.expression.expression.text);
    } else return [];
  }
  if (variables.size !== 1) return [];
  const variable = [...variables][0];
  let parent = node.parent;
  while (parent && !ts.isForOfStatement(parent)) parent = parent.parent;
  if (!parent || !ts.isVariableDeclarationList(parent.initializer)) return [];
  const declaration = parent.initializer.declarations[0];
  if (!declaration || !ts.isIdentifier(declaration.name) || declaration.name.text !== variable) return [];
  let valuesExpression = parent.expression;
  while (ts.isAsExpression(valuesExpression) || ts.isParenthesizedExpression(valuesExpression)) valuesExpression = valuesExpression.expression;
  if (!ts.isArrayLiteralExpression(valuesExpression)) return [];
  const values = valuesExpression.elements.map(literalText);
  if (values.some((value) => value === null)) return [];
  return values.map((value) => {
    let title = node.head.text;
    for (const span of node.templateSpans) {
      const upper = ts.isCallExpression(span.expression);
      title += upper ? value.toUpperCase() : value;
      title += span.literal.text;
    }
    return title;
  });
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
  const titles = expandedTitles(node.arguments[0]);
  if (!titles.length) return [];
  const callback = node.arguments.find((arg, index) => index > 0 && (ts.isArrowFunction(arg) || ts.isFunctionExpression(arg)));
  if (!callback) return [];
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
  const base = {
    kind, line_start: start, line_end: end,
    body_sha256: crypto.createHash("sha256").update(callback.body.getText(source)).digest("hex"),
    actions: events.filter((event) => event.kind === "action"),
    assertions: events.filter((event) => event.kind === "assertion"),
    helpers: events.filter((event) => event.kind === "helper"),
  };
  return titles.map((title) => ({ title, ...base }));
}
function visit(node) {
  const kind = testKind(node);
  if (kind) {
    results.push(...contractFor(node, kind));
  }
  ts.forEachChild(node, visit);
}
visit(source);
process.stdout.write(`${JSON.stringify({schema_version: 1, path, tests: results})}\n`);
