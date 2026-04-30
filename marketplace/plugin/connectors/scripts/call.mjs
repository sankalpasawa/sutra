#!/usr/bin/env node
// Sutra Connectors — call.mjs
//
// One-shot CLI for invoking a real provider call against a saved credential.
//
// Wave 6 (M1.11) reroute: the DEFAULT path now runs through an L1 governance
// gate — manifest lookup + evaluatePolicy(ctx, manifest, fleetPolicy) +
// AuditSink before any backend invocation, plus a 1 MB payload bound on the
// raw response (M1.5 parity). Direct backends (callSlack/callGmail) are
// preserved and reached AFTER the gate when verdict='allow'.
//
// `--dev-bypass` preserves the pre-Wave-6 direct-call path for local dev.
// It is gated behind SUTRA_DEV=1 in the environment AND emits a forensic
// DEV_CLI_BYPASS beacon to .enforcement/connector-audit.jsonl before
// running, so any bypass leaves a tamper-evident trail.
//
// Spec: holding/research/2026-04-30-core-connectors-hardening-spec.md §M1.11
//
// Usage:
//   node scripts/call.mjs <toolkit> <tool> [--key=value ...]
//   node scripts/call.mjs <toolkit> <tool> --dev-bypass [...]   (SUTRA_DEV=1 only)
//
// Examples:
//   node scripts/call.mjs slack read-channel --channel=#general --limit=5
//   node scripts/call.mjs gmail list-messages --maxResults=10
//   SUTRA_DEV=1 node scripts/call.mjs slack post-message --dev-bypass --channel=#test --text=hi
//
// Wired by `sutra call <toolkit> <tool> [...]` in bin/sutra.

import {
  readFileSync,
  writeFileSync,
  readdirSync,
  appendFileSync,
  mkdirSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { homedir } from "node:os";
import { nanoid } from "nanoid";

import {
  AuditSink,
  ComposioAdapter,
  CredentialLoader,
  FleetPolicyCache,
  SecretStoreAge,
  evaluatePolicy,
  parseManifest,
} from "../lib/index.js";

// ───────────────────────────────────────────────────────────────────────────
// Argv parsing — extract --dev-bypass (and its env gate) BEFORE positionals
// so `node call.mjs slack read-channel --dev-bypass --channel=#x` works.
// ───────────────────────────────────────────────────────────────────────────
const argv = process.argv.slice(2);

const devBypassIdx = argv.indexOf("--dev-bypass");
const devBypassRequested = devBypassIdx >= 0;
if (devBypassRequested) {
  argv.splice(devBypassIdx, 1);
}

const [toolkit, tool, ...rawArgs] = argv;

if (!toolkit || !tool || toolkit === "--help" || toolkit === "-h") {
  console.error("usage: call.mjs <toolkit> <tool> [--key=value ...] [--dev-bypass]");
  console.error("");
  console.error("Default path: routes through L1 policy + audit gate.");
  console.error("--dev-bypass: skips L1 (requires SUTRA_DEV=1; emits forensic beacon).");
  console.error("");
  console.error("Examples:");
  console.error("  call.mjs slack read-channel --channel=#general --limit=5");
  console.error("  call.mjs slack post-message --channel=#test --text=hello");
  console.error("  call.mjs gmail list-messages --maxResults=10");
  process.exit(2);
}

// Parse --k=v style flags. Bare flags like --foo become {foo: true}.
const args = {};
for (const raw of rawArgs) {
  const m = raw.match(/^--([^=]+)(?:=(.*))?$/);
  if (m) args[m[1]] = m[2] === undefined ? true : m[2];
}

// ───────────────────────────────────────────────────────────────────────────
// Paths + constants
// ───────────────────────────────────────────────────────────────────────────
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const MANIFESTS_DIR = join(__dirname, "..", "manifests");
const KEY_DIR = join(homedir(), ".sutra-connectors", "keys");
const OAUTH_DIR = join(homedir(), ".sutra-connectors", "oauth");
const AUDIT_LOG_PATH = ".enforcement/connector-audit.jsonl";
const MAX_PAYLOAD_BYTES = 1_000_000;

// ───────────────────────────────────────────────────────────────────────────
// Entry point dispatch
// ───────────────────────────────────────────────────────────────────────────
try {
  if (devBypassRequested) {
    if (process.env.SUTRA_DEV !== "1") {
      console.error("✘ --dev-bypass requires SUTRA_DEV=1 in env");
      console.error("  This flag bypasses L1 policy/audit and is intended for local dev only.");
      process.exit(2);
    }
    emitDevBypassBeacon();
    console.error("call.mjs: --dev-bypass active (SUTRA_DEV=1); beacon emitted to audit log");
    await runDevBypass(toolkit, tool, args);
  } else {
    await runWithL1Gate(toolkit, tool, args);
  }
} catch (e) {
  console.error(`✘ ${e?.message ?? e}`);
  process.exit(1);
}

// ───────────────────────────────────────────────────────────────────────────
// L1 governance path (default) — Wave 6
// ───────────────────────────────────────────────────────────────────────────
async function runWithL1Gate(toolkit, tool, args) {
  // 1. Load manifest for the requested toolkit. Manifest absence = unknown
  //    connector → block + audit.
  const manifests = loadManifests();
  const manifest = manifests.find((m) => m.name === toolkit);
  const ctx = buildCtx(toolkit, tool, args);
  const audit = new AuditSink({
    path: AUDIT_LOG_PATH,
    redactPaths: manifest?.redactPaths ?? [],
  });

  if (!manifest) {
    await safeAudit(audit, {
      ts: ctx.ts,
      clientId: ctx.clientId,
      tier: ctx.tier,
      depth: ctx.depth,
      capability: ctx.capability,
      outcome: "blocked",
      reason: "unknown-connector",
      sessionId: ctx.sessionId,
      redactedArgsHash: "",
    }, ctx.args);
    console.error(`✘ no manifest for toolkit '${toolkit}' (unknown-connector)`);
    console.error(`  Available: ${manifests.map((m) => m.name).join(", ") || "(none)"}`);
    process.exit(1);
  }

  // 2. Fleet policy — CLI uses an empty in-memory policy. Production
  //    fleet-policy delivery is out of scope for the dev/CLI surface; the
  //    important property is that evaluatePolicy still runs (no-op for
  //    freezes) so the path is identical in shape to a Mode-B Router call.
  const fleetPolicy = await loadEmptyFleetPolicy();

  // 3. Policy evaluation. block / require-approval → audit + exit 1.
  //    allow → continue to credential load + backend.
  const decision = evaluatePolicy(ctx, manifest, fleetPolicy);

  if (decision.verdict === "block") {
    await safeAudit(audit, {
      ts: ctx.ts,
      clientId: ctx.clientId,
      tier: ctx.tier,
      depth: ctx.depth,
      capability: ctx.capability,
      outcome: "blocked",
      reason: decision.reason,
      sessionId: ctx.sessionId,
      redactedArgsHash: "",
    }, ctx.args);
    console.error(`✘ L1 blocked: ${decision.reason}`);
    process.exit(1);
  }

  if (decision.verdict === "require-approval") {
    await safeAudit(audit, {
      ts: ctx.ts,
      clientId: ctx.clientId,
      tier: ctx.tier,
      depth: ctx.depth,
      capability: ctx.capability,
      outcome: "blocked",
      reason: "approval-required",
      sessionId: ctx.sessionId,
      redactedArgsHash: "",
    }, ctx.args);
    console.error(
      `✘ L1 blocked: approval-required (depth=${ctx.depth}, capability=${ctx.capability})`,
    );
    console.error(
      "  Founder approval flow is the Router's responsibility (Mode B); the CLI surface does not mint tokens.",
    );
    process.exit(1);
  }

  // 4. Verdict = allow. Load credential via CredentialLoader (.age preferred,
  //    .json fallback emits MIGRATION_PENDING beacon).
  const credentialLoader = makeCredentialLoader();
  let cred;
  try {
    cred = await credentialLoader.load(toolkit);
  } catch (e) {
    await safeAudit(audit, {
      ts: ctx.ts,
      clientId: ctx.clientId,
      tier: ctx.tier,
      depth: ctx.depth,
      capability: ctx.capability,
      outcome: "error",
      reason: "credential-not-found",
      sessionId: ctx.sessionId,
      redactedArgsHash: "",
      errorClass: e?.constructor?.name ?? "Error",
    }, ctx.args);
    console.error(`✘ no credential for ${toolkit}: ${e?.message ?? e}`);
    console.error(`  Run: sutra connect ${toolkit}`);
    process.exit(1);
  }

  // 5. Backend dispatch — direct adapters for slack/gmail; everything else is
  //    not yet wired (composio path ships through the Router proper, not
  //    this CLI). Errors → audit error + propagate.
  let result;
  // For gmail we need to persist refreshed tokens back; CredentialLoader.save
  // dual-writes .age + .json. callGmail's existing legacy signature accepts
  // a credFile; we adapt it to a save callback that funnels through loader.
  const gmailJsonShadow = join(OAUTH_DIR, `${toolkit}.json`);
  try {
    if (toolkit === "slack") {
      result = await callSlack(cred, tool, args);
    } else if (toolkit === "gmail") {
      result = await callGmail(cred, tool, args, gmailJsonShadow, credentialLoader);
    } else {
      await safeAudit(audit, {
        ts: ctx.ts,
        clientId: ctx.clientId,
        tier: ctx.tier,
        depth: ctx.depth,
        capability: ctx.capability,
        outcome: "error",
        reason: `no-direct-backend:${toolkit}`,
        sessionId: ctx.sessionId,
        redactedArgsHash: "",
        errorClass: "NoDirectBackendError",
      }, ctx.args);
      console.error(`✘ no CLI dispatcher for toolkit '${toolkit}'`);
      console.error(`  Add a backend at lib/backends/${toolkit}-direct.ts and a case here.`);
      process.exit(1);
    }
  } catch (e) {
    await safeAudit(audit, {
      ts: ctx.ts,
      clientId: ctx.clientId,
      tier: ctx.tier,
      depth: ctx.depth,
      capability: ctx.capability,
      outcome: "error",
      reason: e?.message ?? "backend-error",
      sessionId: ctx.sessionId,
      redactedArgsHash: "",
      errorClass: e?.constructor?.name ?? "Error",
    }, ctx.args);
    throw e;
  }

  // 6. Payload bound (M1.5 parity).
  let valueBytes = 0;
  try {
    valueBytes = Buffer.byteLength(JSON.stringify(result));
  } catch {
    valueBytes = MAX_PAYLOAD_BYTES + 1;
  }
  if (valueBytes > MAX_PAYLOAD_BYTES) {
    await safeAudit(audit, {
      ts: ctx.ts,
      clientId: ctx.clientId,
      tier: ctx.tier,
      depth: ctx.depth,
      capability: ctx.capability,
      outcome: "error",
      reason: `payload-too-large:${valueBytes}>${MAX_PAYLOAD_BYTES}`,
      sessionId: ctx.sessionId,
      redactedArgsHash: "",
      errorClass: "PayloadTooLargeError",
    }, ctx.args);
    console.error(`✘ L1 error: payload-too-large (${valueBytes} bytes)`);
    process.exit(1);
  }

  // 7. Success — audit + emit result.
  await safeAudit(audit, {
    ts: ctx.ts,
    clientId: ctx.clientId,
    tier: ctx.tier,
    depth: ctx.depth,
    capability: ctx.capability,
    outcome: "allowed",
    sessionId: ctx.sessionId,
    redactedArgsHash: "",
  }, ctx.args);

  console.log(JSON.stringify(result, null, 2));
  process.exit(0);
}

// ───────────────────────────────────────────────────────────────────────────
// --dev-bypass path — preserves the pre-Wave-6 direct-call surface
// ───────────────────────────────────────────────────────────────────────────
async function runDevBypass(toolkit, tool, args) {
  // Read .json plaintext directly (legacy). CredentialLoader is intentionally
  // skipped on this path so the bypass mirrors the pre-Wave-6 behavior
  // verbatim — no audit beacon for migration, no .age preference.
  const credFile = join(OAUTH_DIR, `${toolkit}.json`);
  let cred;
  try {
    cred = JSON.parse(readFileSync(credFile, "utf8"));
  } catch (e) {
    console.error(`✘ no credential for ${toolkit} at ${credFile}`);
    console.error(`  Run: sutra connect ${toolkit}`);
    process.exit(1);
  }

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
  process.exit(0);
}

// ───────────────────────────────────────────────────────────────────────────
// Helpers — manifest loader, ctx builder, fleet-policy stub, audit beacon
// ───────────────────────────────────────────────────────────────────────────
function loadManifests() {
  const out = [];
  let entries = [];
  try {
    entries = readdirSync(MANIFESTS_DIR);
  } catch {
    return out;
  }
  for (const f of entries) {
    if (!f.endsWith(".yaml") && !f.endsWith(".yml")) continue;
    try {
      const raw = readFileSync(join(MANIFESTS_DIR, f), "utf8");
      out.push(parseManifest(raw));
    } catch (e) {
      // Skip malformed manifest files; surface to stderr for forensics.
      console.error(`call.mjs: failed to parse manifest ${f}: ${e?.message ?? e}`);
    }
  }
  return out;
}

function buildCtx(toolkit, tool, args) {
  const sessionId =
    typeof process.env.SESSION_ID === "string" && process.env.SESSION_ID.length > 0
      ? process.env.SESSION_ID
      : `cli-${nanoid()}`;
  // Capability id pattern: '<toolkit>:<tool>:<resource?>'. Resource portion is
  // best-effort — many CLI invocations narrow via --channel / --label / --to.
  // We carry the most common one (channel) into the capability id so manifest
  // resourcePattern checks have something to match against; the rest of the
  // args propagate through ctx.args and the manifest's tierAccess globs.
  let resource = "";
  if (typeof args.channel === "string" && args.channel.length > 0) {
    resource = args.channel.startsWith("#") ? args.channel : `#${args.channel}`;
  } else if (typeof args.label === "string") {
    resource = args.label;
  }
  const capability = resource ? `${toolkit}:${tool}:${resource}` : `${toolkit}:${tool}`;
  return {
    clientId: process.env.SUTRA_CLIENT_ID ?? "asawa-holding",
    tier: process.env.SUTRA_TIER ?? "T1",
    depth: 5,
    capability,
    args,
    ts: Date.now(),
    sessionId,
    idempotency_key: nanoid(),
    event_id: nanoid(),
  };
}

async function loadEmptyFleetPolicy() {
  const cache = new FleetPolicyCache(
    {
      load: async () => ({
        version: "cli-empty",
        lastUpdated: Date.now(),
        freezes: [],
      }),
      watch: () => () => {},
    },
    60_000, // staleAfterMs — irrelevant for one-shot CLI but must be > 0
  );
  await cache.refresh();
  return cache.current();
}

function makeCredentialLoader() {
  const store = new SecretStoreAge({
    identityPath: join(KEY_DIR, "sutra-identity.key"),
    recipientPath: join(KEY_DIR, "sutra-recipient.txt"),
  });
  return new CredentialLoader({ secretStore: store, keyDir: OAUTH_DIR });
}

async function safeAudit(audit, event, rawArgs) {
  try {
    await audit.append(event, rawArgs);
  } catch {
    /* sink already has its own fallback path; never crash the CLI */
  }
}

function emitDevBypassBeacon() {
  const beacon = {
    ts: Date.now(),
    event: "DEV_CLI_BYPASS",
    pid: process.pid,
    cwd: process.cwd(),
    argv: process.argv,
    sutra_dev: process.env.SUTRA_DEV,
  };
  try {
    const parent = dirname(AUDIT_LOG_PATH);
    if (parent.length > 0) mkdirSync(parent, { recursive: true });
    appendFileSync(AUDIT_LOG_PATH, JSON.stringify(beacon) + "\n");
  } catch {
    /* best-effort */
  }
}

// ───────────────────────────────────────────────────────────────────────────
// Slack direct backend (preserved verbatim from pre-Wave-6)
// ───────────────────────────────────────────────────────────────────────────
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

// ───────────────────────────────────────────────────────────────────────────
// Gmail direct backend (preserved; persistence path now optionally goes
// through CredentialLoader.save for dual-write parity)
// ───────────────────────────────────────────────────────────────────────────
async function callGmail(cred, tool, args, credFile, credentialLoader) {
  if (cred.type !== "gmail-oauth") {
    throw new Error(`expected cred.type='gmail-oauth', got '${cred.type}'`);
  }

  // Pre-emptive refresh if access_token near expiry (60s skew).
  if (Date.now() > cred.expiresAt - 60_000) {
    cred = await refreshGmail(cred, credFile, credentialLoader);
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
    cred = await refreshGmail(cred, credFile, credentialLoader);
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

async function refreshGmail(cred, credFile, credentialLoader) {
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
    obtained_at: cred.obtained_at ?? Date.now(),
  };
  // Persist refreshed token. Prefer CredentialLoader.save (dual-write
  // .age + .json) when available so the encrypted shadow stays current; fall
  // back to direct .json write for the --dev-bypass path that has no loader.
  if (credentialLoader) {
    try {
      await credentialLoader.save("gmail", newCred);
    } catch (e) {
      // Loader save failed — fall back to plaintext write so refresh isn't
      // silently lost; surface the failure to stderr.
      console.error(`call.mjs: credential save (.age) failed: ${e?.message ?? e}; falling back to .json`);
      writeFileSync(credFile, JSON.stringify(newCred, null, 2), { mode: 0o600 });
    }
  } else {
    writeFileSync(credFile, JSON.stringify(newCred, null, 2), { mode: 0o600 });
  }
  return newCred;
}
