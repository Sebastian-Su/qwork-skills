#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";

const home = process.env.ZIQDO_CONFIG_HOME || process.cwd();
const sessions = new Map();
write({ type: "ready", capabilities: {} });

const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
lines.once("close", () => process.exit(0));
lines.on("line", (line) => {
  let message;
  try { message = JSON.parse(line); } catch { return; }
  if (message.type === "create_session") {
    const sessionPath = path.join(home, "sessions", "tool-failure", `${message.session_id}.jsonl`);
    sessions.set(message.session_id, { path: sessionPath, cwd: message.cwd || home });
    write({ type: "ack", ref: "create_session", session_id: message.session_id, session_path: sessionPath, resumed: false });
    return;
  }
  if (message.type === "set_model") {
    write({ type: "ack", ref: "set_model", session_id: message.session_id, model: message.model });
    return;
  }
  if (message.type === "mcp_status" || message.type === "mcp_reconnect") {
    write({ type: "mcp_status", ok: true, servers: [] });
    return;
  }
  if (message.type === "mcp_tools") {
    write({ type: "mcp_tools", tools: [] });
    return;
  }
  if (message.type === "subscribe_subagent_streams") {
    write({ type: "ack", ref: "subscribe_subagent_streams", session_id: message.session_id, enabled: message.enabled === true });
    return;
  }
  if (message.type === "close_session") {
    sessions.delete(message.session_id);
    return;
  }
  if (message.type !== "user_message" || !sessions.has(message.session_id)) return;
  const visible = visibleText(message.content);
  append(message.session_id, "user", contentText(message.content));
  event(message.session_id, "status", { status: "streaming" });
  if (visible === "__E2E_TOOL_FAILURE__") {
    event(message.session_id, "tool_call", {
      tool_id: "tool-failure-write",
      name: "write_file",
      input: { path: path.join(sessions.get(message.session_id).cwd, "must-not-exist.md"), content: "forbidden" },
      status: "running",
    });
    setTimeout(() => {
      event(message.session_id, "tool_result", {
        tool_id: "tool-failure-write",
        name: "write_file",
        output: "EACCES: permission denied, open must-not-exist.md",
        is_error: true,
        status: "error",
      });
      event(message.session_id, "status", { status: "idle" });
    }, 250);
    return;
  }
  const reply = `收到：${visible}`;
  append(message.session_id, "assistant", reply);
  event(message.session_id, "text_delta", { text: reply });
  event(message.session_id, "status", { status: "idle" });
});

function contentText(content) {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return String(content ?? "");
  return content.filter((part) => part?.type === "text").map((part) => String(part.text ?? "")).join("");
}

function visibleText(content) {
  const raw = contentText(content);
  const invocation = raw.match(/\s*<qwork_selected_skill_invocation\s+primary="([^"]+)"\s+skills="[^"]*"\s*>[\s\S]*?<\/qwork_selected_skill_invocation>\s*$/);
  let visible = invocation ? raw.replace(invocation[0], "").trim() : raw;
  if (invocation) {
    const prefix = `$${invocation[1]} `;
    if (visible.startsWith(prefix)) visible = visible.slice(prefix.length);
  }
  return visible.replace(/<qwork_team_runtime\b[^>]*>[\s\S]*?<\/qwork_team_runtime>\s*/gi, "").trim();
}

function append(sessionId, role, text) {
  const session = sessions.get(sessionId);
  fs.mkdirSync(path.dirname(session.path), { recursive: true });
  if (!fs.existsSync(session.path)) {
    fs.appendFileSync(session.path, `${JSON.stringify({ type: "session_meta", session_id: sessionId, model: "e2e-tool-failure", created_at_ms: Date.now(), updated_at_ms: Date.now(), workspace_root: session.cwd })}\n`);
  }
  fs.appendFileSync(session.path, `${JSON.stringify({ type: "message", message: { role, blocks: [{ type: "text", text }] } })}\n`);
}

function event(sessionId, kind, fields) { write({ type: "session_event", kind, session_id: sessionId, ...fields }); }
function write(message) { process.stdout.write(`${JSON.stringify(message)}\n`); }
