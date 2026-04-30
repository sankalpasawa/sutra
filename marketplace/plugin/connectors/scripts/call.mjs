#!/usr/bin/env node
// Sutra Connectors — call.mjs
//
// Plain-JS one-shot CLI for invoking a real provider call against a saved
// credential. Bypasses Sutra L1 governance (policy/audit/fleet) — this is the
// dev/smoke surface, not the production-agent path. AI-agent invocations go
// through ConnectorRouter (TS) when wired into the Claude Code session.
//
// Usage:
//   node scripts/call.mjs <toolkit> <tool> [--key=value ...]
//
// Examples:
//   node scripts/call.mjs slack read-channel --channel=#general --limit=5
//   node scripts/call.mjs slack post-message --channel=#test --text="hello"
//   node scripts/call.mjs gmail list-messages --maxResults=10
//   node scripts/call.mjs gmail get-message --id=18a1b2c3d4e5f
//   node scripts/call.mjs gmail send-message --to=you@example.com --subject="..." --body="..."
//
// Wired by `sutra call <toolkit> <tool> [...]` in bin/sutra.

import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

const [,, toolkit, tool, ...rawArgs] = process.argv;

if (!toolkit || !tool || toolkit === "--help" || toolkit === "-h") {
  console.error("usage: call.mjs <toolkit> <tool> [--key=value ...]");
  console.error("");
  console.error("Examples:");
  console.error("  call.mjs slack read-channel --channel=#general --limit=5");
  console.error("  call.mjs slack post-message --channel=#test --text=hello");
  console.error("  call.mjs gmail list-messages --maxResults=10");
  console.error("  call.mjs gmail get-message --id=<message-id>");
  process.exit(2);
}

// Parse --k=v style flags. Bare flags like --foo become {foo: true}.
const args = {};
for (const raw of rawArgs) {
  const m = raw.match(/^--([^=]+)(?:=(.*))?$/);
  if (m) args[m[1]] = m[2] === undefined ? true : m[2];
}

const credFile = join(homedir(), ".sutra-connectors", "oauth", `${toolkit}.json`);
if (!existsSync(credFile)) {
  console.error(`✘ no credential for ${toolkit} at ${credFile}`);
  console.error(`  Run: sutra connect ${toolkit}`);
  process.exit(1);
}

let cred;
try {
  cred = JSON.parse(readFileSync(credFile, "utf8"));
} catch (e) {
  console.error(`✘ malformed credential at ${credFile}: ${e.message}`);
  process.exit(1);
}

try {
  let result;
  switch (toolkit) {
    case "slack":
      result = await callSlack(cred, tool, args);
      break;
    case "gmail":
      result = await callGmail(cred, tool, args, credFile);
      break;
    default:
      console.error(`✘ no CLI dispatcher for toolkit '${toolkit}'`);
      console.error(`  Add a backend at lib/backends/${toolkit}-direct.ts and a case here.`);
      process.exit(1);
  }
  console.log(JSON.stringify(result, null, 2));
} catch (e) {
  console.error(`✘ ${e.message}`);
  process.exit(1);
}

// ── Slack ───────────────────────────────────────────────────────────────────
async function callSlack(cred, tool, args) {
  if (cred.type !== "slack-bot") {
    throw new Error(`expected cred.type='slack-bot', got '${cred.type}'`);
  }
  const methodMap = {
    "read-channel": { method: "conversations.history", normalize: a => ({ channel: a.channel, limit: a.limit ? Number(a.limit) : 50 }) },
    "post-message": { method: "chat.postMessage",    normalize: a => ({ channel: a.channel, text: a.text, ...(a.thread_ts ? { thread_ts: a.thread_ts } : {}) }) },
    "get-user":     { method: "users.info",          normalize: a => ({ user: a.user }) },
  };
  const m = methodMap[tool];
  if (!m) throw new Error(`unsupported slack tool: ${tool}. Try: ${Object.keys(methodMap).join(", ")}`);
  const r = await fetch(`https://slack.com/api/${m.method}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${cred.token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(m.normalize(args)),
  });
  const json = await r.json();
  if (!json.ok) throw new Error(`slack ${m.method}: ${json.error || "unknown error"}`);
  return json;
}

// ── Gmail ───────────────────────────────────────────────────────────────────
async function callGmail(cred, tool, args, credFile) {
  if (cred.type !== "gmail-oauth") {
    throw new Error(`expected cred.type='gmail-oauth', got '${cred.type}'`);
  }

  // Pre-emptive refresh if access_token near expiry (60s skew).
  if (Date.now() > cred.expiresAt - 60_000) {
    cred = await refreshGmail(cred, credFile);
  }

  const dispatch = async (token) => {
    switch (tool) {
      case "list-messages": {
        const params = new URLSearchParams();
        if (args.q) params.set("q", String(args.q));
        if (args.labelIds) params.set("labelIds", String(args.labelIds));
        if (args.maxResults) params.set("maxResults", String(args.maxResults));
        return await gFetch(`https://gmail.googleapis.com/gmail/v1/users/me/messages?${params}`, token);
      }
      case "list-by-label": {
        if (!args.label) throw new Error("--label is required");
        const params = new URLSearchParams({ labelIds: String(args.label) });
        if (args.maxResults) params.set("maxResults", String(args.maxResults));
        return await gFetch(`https://gmail.googleapis.com/gmail/v1/users/me/messages?${params}`, token);
      }
      case "get-message": {
        if (!args.id) throw new Error("--id is required");
        return await gFetch(`https://gmail.googleapis.com/gmail/v1/users/me/messages/${encodeURIComponent(args.id)}`, token);
      }
      case "get-thread": {
        if (!args.id) throw new Error("--id is required");
        return await gFetch(`https://gmail.googleapis.com/gmail/v1/users/me/threads/${encodeURIComponent(args.id)}`, token);
      }
      case "send-message": {
        if (!args.to || !args.subject || !args.body) {
          throw new Error("--to, --subject, --body all required");
        }
        const mime = `To: ${args.to}\r\nSubject: ${args.subject}\r\n\r\n${args.body}`;
        const raw = Buffer.from(mime, "utf8")
          .toString("base64")
          .replace(/\+/g, "-")
          .replace(/\//g, "_")
          .replace(/=+$/, "");
        return await gFetch(
          `https://gmail.googleapis.com/gmail/v1/users/me/messages/send`,
          token,
          { method: "POST", body: { raw } },
        );
      }
      case "get-profile": {
        return await gFetch(`https://gmail.googleapis.com/gmail/v1/users/me/profile`, token);
      }
      default:
        throw new Error(`unsupported gmail tool: ${tool}. Try: list-messages, list-by-label, get-message, get-thread, send-message, get-profile`);
    }
  };

  // First attempt with current token.
  try {
    return await dispatch(cred.accessToken);
  } catch (e) {
    if (!e.is401) throw e;
    // Reactive refresh + single retry.
    cred = await refreshGmail(cred, credFile);
    return await dispatch(cred.accessToken);
  }
}

async function gFetch(url, token, opts = {}) {
  const init = {
    method: opts.method || "GET",
    headers: { Authorization: `Bearer ${token}` },
  };
  if (opts.body) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(opts.body);
  }
  const r = await fetch(url, init);
  if (r.status === 401) {
    const e = new Error(`Gmail 401`);
    e.is401 = true;
    throw e;
  }
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`Gmail ${r.status}: ${text}`);
  }
  return r.json();
}

async function refreshGmail(cred, credFile) {
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    client_id: cred.clientId,
    client_secret: cred.clientSecret,
    refresh_token: cred.refreshToken,
  }).toString();
  const r = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!r.ok) {
    const errText = await r.text();
    throw new Error(`refresh ${r.status}: ${errText}`);
  }
  const j = await r.json();
  const newCred = {
    ...cred,
    accessToken: j.access_token,
    expiresAt: Date.now() + (j.expires_in || 3600) * 1000,
  };
  // Persist back to disk so next call picks up the fresh token.
  writeFileSync(credFile, JSON.stringify(newCred, null, 2), { mode: 0o600 });
  return newCred;
}
