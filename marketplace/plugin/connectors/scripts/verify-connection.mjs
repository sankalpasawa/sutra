#!/usr/bin/env node
// Sutra Connectors — verify-connection.mjs
//
// One-shot smoke test for a saved credential. Reads via CredentialLoader.load()
// — prefers ~/.sutra-connectors/oauth/<toolkit>.age (encrypted) and falls back
// to <toolkit>.json (plaintext, migration window). Makes ONE auth-check call
// against the provider (Slack auth.test, Gmail /profile). Exits 0 on success,
// 1 on failure.
//
// Usage:
//   node scripts/verify-connection.mjs <toolkit>
//
// Wired by `sutra connect-test <toolkit>` in bin/sutra.

import { join } from "node:path";
import { homedir } from "node:os";

import { CredentialLoader, SecretStoreAge } from "../lib/index.js";
import { assertAgeAvailable } from "./preflight-age.mjs";

// M2 step 2 — defense in depth: bin/sutra preflight catches this too, but
// `node scripts/verify-connection.mjs ...` bypasses bin/sutra. Fail loudly
// before any secret-store path tries to spawn age.
assertAgeAvailable();

const toolkit = process.argv[2];
if (!toolkit) {
  console.error("usage: verify-connection.mjs <toolkit>");
  process.exit(2);
}

// Wave 5 (M1.10): route reads through CredentialLoader so we honor the
// .age-first / .json-fallback policy and emit a MIGRATION_PENDING beacon
// when the plaintext shadow is consumed. Discriminator (`cred.type`) values
// continue to match the shipped contract — Wave 3's discriminated union
// matched verify-connection.mjs's existing checks verbatim.
const keyDir = join(homedir(), ".sutra-connectors", "keys");
const oauthDir = join(homedir(), ".sutra-connectors", "oauth");
const store = new SecretStoreAge({
  identityPath: join(keyDir, "sutra-identity.key"),
  recipientPath: join(keyDir, "sutra-recipient.txt"),
});
const loader = new CredentialLoader({ secretStore: store, keyDir: oauthDir });

let cred;
try {
  cred = await loader.load(toolkit);
} catch (e) {
  console.error(`✘ verify-connection: ${e?.message ?? e}`);
  console.error(`  If no credential exists yet: sutra connect ${toolkit}`);
  process.exit(1);
}

console.log(`── Verifying ${toolkit} ──────────────────────────────────`);
console.log(`  cred type:  ${cred.type}`);
console.log(`  cred dir:   ${oauthDir}/${toolkit}.{age,json}`);

try {
  switch (toolkit) {
    case "slack":
      await verifySlack(cred);
      break;
    case "gmail":
      await verifyGmail(cred);
      break;
    default:
      console.error(`✘ no verifier for toolkit '${toolkit}'`);
      process.exit(1);
  }
} catch (e) {
  console.error(`✘ verification failed: ${e.message}`);
  process.exit(1);
}

// ── Slack: POST https://slack.com/api/auth.test ─────────────────────────────
async function verifySlack(cred) {
  if (cred.type !== "slack-bot") {
    throw new Error(`expected type='slack-bot', got '${cred.type}'`);
  }
  const r = await fetch("https://slack.com/api/auth.test", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${cred.token}`,
      "Content-Type": "application/json",
    },
    body: "{}",
  });
  const json = await r.json();
  if (!json.ok) {
    throw new Error(`slack auth.test ok=false: ${json.error || "unknown"}`);
  }
  console.log(`✔ Slack OK`);
  console.log(`  team:    ${json.team}`);
  console.log(`  user:    ${json.user}`);
  console.log(`  bot_id:  ${json.bot_id || "(no bot_id)"}`);
  console.log(`  url:     ${json.url}`);
}

// ── Gmail: GET https://gmail.googleapis.com/gmail/v1/users/me/profile ───────
async function verifyGmail(cred) {
  if (cred.type !== "gmail-oauth") {
    throw new Error(`expected type='gmail-oauth', got '${cred.type}'`);
  }
  let { accessToken, expiresAt, refreshToken, clientId, clientSecret } = cred;

  // Pre-emptive refresh if token expired or close to it (60s skew)
  if (Date.now() > expiresAt - 60_000) {
    console.log(`  (access token near/past expiry — refreshing)`);
    const refreshed = await refreshGmail({ refreshToken, clientId, clientSecret });
    accessToken = refreshed.access_token;
    // (For verify-only, we don't write back to disk — connect.sh / runtime do that.)
    console.log(`  ✔ refresh OK (new expires_in=${refreshed.expires_in}s)`);
  }

  const r = await fetch(
    "https://gmail.googleapis.com/gmail/v1/users/me/profile",
    { headers: { Authorization: `Bearer ${accessToken}` } },
  );
  if (r.status === 401) {
    // One reactive retry after refresh, in case our skew check missed.
    console.log(`  (401 — attempting refresh + retry)`);
    const refreshed = await refreshGmail({ refreshToken, clientId, clientSecret });
    const r2 = await fetch(
      "https://gmail.googleapis.com/gmail/v1/users/me/profile",
      { headers: { Authorization: `Bearer ${refreshed.access_token}` } },
    );
    if (r2.status !== 200) {
      throw new Error(`Gmail /profile ${r2.status} after refresh`);
    }
    const j = await r2.json();
    console.log(`✔ Gmail OK (after refresh)`);
    console.log(`  emailAddress:  ${j.emailAddress}`);
    console.log(`  messagesTotal: ${j.messagesTotal}`);
    return;
  }
  if (r.status !== 200) {
    throw new Error(`Gmail /profile ${r.status}`);
  }
  const j = await r.json();
  console.log(`✔ Gmail OK`);
  console.log(`  emailAddress:  ${j.emailAddress}`);
  console.log(`  messagesTotal: ${j.messagesTotal}`);
  console.log(`  threadsTotal:  ${j.threadsTotal}`);
}

async function refreshGmail({ refreshToken, clientId, clientSecret }) {
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    client_id: clientId,
    client_secret: clientSecret,
    refresh_token: refreshToken,
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
  return r.json();
}
