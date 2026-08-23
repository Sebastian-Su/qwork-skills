#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";

const configHome = process.env.ZIQDO_CONFIG_HOME || process.cwd();
const sessions = new Map();

write({
  type: "ready",
  capabilities: { subagent_concurrency_limit: true },
});

const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
lines.once("close", () => process.exit(0));
lines.on("line", (line) => {
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    return;
  }
  if (message.type === "create_session") {
    const sessionPath = typeof message.resume === "string" && message.resume
      ? message.resume
      : path.join(configHome, "sessions", "team-terminal", `${message.session_id}.jsonl`);
    sessions.set(message.session_id, { path: sessionPath, cwd: message.cwd || configHome });
    write({
      type: "ack",
      ref: "create_session",
      session_id: message.session_id,
      session_path: sessionPath,
      resumed: Boolean(message.resume),
    });
    return;
  }
  if (message.type === "set_model") {
    write({ type: "ack", ref: "set_model", session_id: message.session_id, model: message.model });
    return;
  }
  if (message.type === "subscribe_subagent_streams") {
    write({
      type: "ack",
      ref: "subscribe_subagent_streams",
      session_id: message.session_id,
      enabled: message.enabled === true,
    });
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
  if (message.type === "close_session") {
    sessions.delete(message.session_id);
    return;
  }
  if (message.type === "cancel" || message.type === "interrupt") {
    event(message.session_id, "status", { status: "cancelled" });
    event(message.session_id, "status", { status: "idle" });
    return;
  }
  if (message.type !== "user_message" || !sessions.has(message.session_id)) return;

  const content = visibleText(message.content);
  appendMessage(message.session_id, "user", contentText(message.content));
  event(message.session_id, "status", { status: "streaming" });
  if (content !== "__E2E_TEAM_TERMINAL_MATRIX__") {
    const reply = `收到：${content}`;
    appendMessage(message.session_id, "assistant", reply);
    event(message.session_id, "text_delta", { text: reply });
    event(message.session_id, "status", { status: "idle" });
    return;
  }

  const members = [
    { thread_id: "terminal-completed", agent_id: "completed-member", name: "完成成员", status: "completed" },
    { thread_id: "terminal-failed", agent_id: "failed-member", name: "失败成员", status: "failed", error: "依赖检查失败" },
    { thread_id: "terminal-blocked", agent_id: "blocked-member", name: "阻塞成员", status: "blocked", error: "等待 Lead 提供发布范围" },
    { thread_id: "terminal-interrupted", agent_id: "interrupted-member", name: "中断成员", status: "interrupted", error: "sidecar 重启导致中断" },
  ];
  for (const member of members) {
    event(message.session_id, "subagent_thread_started", {
      thread_id: member.thread_id,
      agent_id: member.agent_id,
      name: member.name,
      model: "e2e-terminal-matrix",
    });
    event(message.session_id, "subagent_text_delta", {
      thread_id: member.thread_id,
      delta: `${member.name}运行输出`,
    });
    if (member.status === "blocked") {
      event(message.session_id, "subagent_thread_blocked", {
        thread_id: member.thread_id,
        reason: member.error,
      });
    } else {
      event(message.session_id, "subagent_thread_completed", {
        thread_id: member.thread_id,
        status: member.status,
        error: member.error || null,
        input_tokens: 10,
        output_tokens: 5,
      });
    }
  }
  const summary = "四类成员终态已由 ZiqDo 事件上报。";
  appendMessage(message.session_id, "assistant", summary);
  event(message.session_id, "text_delta", { text: summary });
  event(message.session_id, "status", { status: "idle" });
});

function contentText(content) {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return String(content ?? "");
  return content.filter((part) => part?.type === "text").map((part) => String(part.text ?? "")).join("");
}

function visibleText(content) {
  const raw = contentText(content);
  // Mirror the authoritative fake-sidecar visiblePromptText: strip the trailing
  // connector-invocation envelope first, then the skill-invocation, then the
  // personalization / global-memory / team-runtime envelopes. Missing any of
  // these left QWork's private envelopes wrapping the trigger word, so the
  // literal "__E2E_TEAM_TERMINAL_MATRIX__" never matched and the sidecar fell
  // back to a generic echo (bug WB-TEAM-007 fixture gap).
  let visible = raw
    .replace(
      /\s*<qwork_selected_connector_invocation\s+connectors="[^"]*"\s*>[\s\S]*?<\/qwork_selected_connector_invocation>\s*$/,
      "",
    )
    .trim();
  const invocation = visible.match(
    /\s*<qwork_selected_skill_invocation\s+primary="([^"]+)"\s+skills="[^"]*"\s*>[\s\S]*?<\/qwork_selected_skill_invocation>\s*$/,
  );
  if (invocation) {
    visible = visible.replace(invocation[0], "").trim();
    const prefix = `$${invocation[1]} `;
    if (visible.startsWith(prefix)) visible = visible.slice(prefix.length);
  }
  return visible
    .replace(
      /<!-- qwork:personalization:start -->[\s\S]*?<!-- qwork:personalization:end -->\s*/gi,
      "",
    )
    .replace(
      /<!-- qwork:global-memory:start -->[\s\S]*?<!-- qwork:global-memory:end -->\s*/gi,
      "",
    )
    .replace(/<qwork_team_runtime\b[^>]*>[\s\S]*?<\/qwork_team_runtime>\s*/gi, "")
    .trim();
}

function appendMessage(sessionId, role, text) {
  const session = sessions.get(sessionId);
  if (!session) return;
  fs.mkdirSync(path.dirname(session.path), { recursive: true });
  if (!fs.existsSync(session.path)) {
    fs.appendFileSync(session.path, `${JSON.stringify({
      type: "session_meta",
      session_id: sessionId,
      model: "e2e-terminal-matrix",
      created_at_ms: Date.now(),
      updated_at_ms: Date.now(),
      workspace_root: session.cwd,
    })}\n`, "utf8");
  }
  fs.appendFileSync(session.path, `${JSON.stringify({
    type: "message",
    message: { role, blocks: [{ type: "text", text }] },
  })}\n`, "utf8");
}

function event(sessionId, kind, fields) {
  write({ type: "session_event", kind, session_id: sessionId, ...fields });
}

function write(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}
