# Sutra Connectors — Quickstart

**Status:** v0 shipped — Path C (direct provider integration, no Composio). 146 tests passing.

---

## What this is

A Sutra-governed bridge to Slack, Gmail, and (later) GitHub, Linear, etc. **You** keep the brain (audit, depth-gating, tier-scoped permissions, fleet policy). Each provider is wrapped by a thin direct-API backend in `lib/backends/` — no third-party broker, no SaaS dependency at runtime.

```
Tier (T1-T4) → Sutra L1 (rules)
             → Direct backend (slack-direct.ts, gmail-direct.ts)
             → Provider API (slack.com/api, gmail.googleapis.com)
```

All external calls log to `.enforcement/connector-audit.jsonl` with depth, tier, capability, outcome, and a hash of the (redacted) args.

---

## Founder action items — first-time setup

### 1. Update plugin (after push lands)

```bash
claude plugin marketplace update sutra
claude plugin update core@sutra
```

This refreshes `~/.claude/plugins/cache/sutra/core/<latest>/`. Your shell `sutra` function auto-points at the latest cached version.

### 2. Connect Slack — paste a bot token (~2 minutes)

```bash
sutra connect slack
```

The CLI walks you through:
1. Open https://api.slack.com/apps → "Create New App" → "From scratch"
2. Pick your workspace, add scopes: `channels:history`, `channels:read`, `chat:write`, `users:read`
3. Install to workspace, copy the Bot User OAuth Token (`xoxb-...`)
4. Paste it into the prompt

Saves to `~/.sutra-connectors/oauth/slack.json` (chmod 600).

**Verify it works:**

```bash
sutra connect-test slack
```

Expected output:
```
✔ Slack OK
  team:    YourWorkspace
  user:    your-bot-name
  bot_id:  B0123ABCDEF
  url:     https://yourworkspace.slack.com/
```

### 3. Connect Gmail — OAuth 2.0 flow (~10 minutes one-time)

```bash
sutra connect gmail
```

The CLI walks you through Google Cloud Console setup. Summary:
1. https://console.cloud.google.com — create / pick a project
2. Enable Gmail API
3. Create OAuth client ID (type: Desktop app)
4. Add your Gmail to OAuth consent screen test users
5. Use https://developers.google.com/oauthplayground to do the auth dance and get an `access_token` + `refresh_token`
6. Paste 5 values into the prompt: `client_id`, `client_secret`, `access_token`, `refresh_token`, `expires_in`

Saves to `~/.sutra-connectors/oauth/gmail.json` (chmod 600).

**Verify it works:**

```bash
sutra connect-test gmail
```

Expected output:
```
✔ Gmail OK
  emailAddress:  you@gmail.com
  messagesTotal: 12345
  threadsTotal:  6789
```

If your access token has expired, `connect-test` automatically refreshes using the refresh_token before checking — same logic that runs at every real call.

---

## Tier model (which channels/labels you can touch)

| Tier | Who | Slack | Gmail |
|------|-----|-------|-------|
| **T1** | Asawa (you) | full read + post | full read + send + label-modify |
| **T2** | Owned cos (DayFlow, Billu, Paisa, etc.) | own scoped channels (e.g. `#dayflow-eng`) read + approval-gated post | read all + send-with-approval + own labels (`dayflow-*`) |
| **T3** | Project clients (Testlify, Dharmik) | own scoped channels read only (`#testlify-*`, `#dharmik-*`) | own labels read only |
| **T4** | External fleet | `#public-*` only — Asawa-internal blocked | none by default; opt-in per-tenant via fleet policy |

---

## What gets audited

Every external call writes a JSONL line to `.enforcement/connector-audit.jsonl`:

```json
{"ts":1777501234,"clientId":"asawa-holding","tier":"T1","depth":3,
 "capability":"gmail:list-messages:*","outcome":"allowed",
 "sessionId":"<id>","redactedArgsHash":"<sha256>"}
```

Filter:

```bash
jq -r 'select(.tier=="T2") | "\(.ts) \(.clientId) \(.capability) \(.outcome)"' \
  .enforcement/connector-audit.jsonl
```

---

## Approval flow (what happens when you post a customer-facing message)

1. Code calls `router.call({tier:'T2', capability:'slack:post-message:#public-launch', depth:5, …})`
2. Policy returns `verdict='require-approval'` + mints a single-use token bound to (clientId, sessionId, capability)
3. Caller surfaces a BLUEPRINT box with the message preview
4. You approve → caller re-invokes `router.call({…, approvalToken:<token>})`
5. Policy verifies binding match (no replay across sessions/clients/capabilities) + 5-min TTL + single-use
6. Backend executes the post (Slack chat.postMessage)
7. Audit logs `outcome='approved-after-gate'` with the token id

---

## Fleet policy (push a freeze without redeploying)

Asawa-side, push a fleet policy update that all clients pick up:

```yaml
freezes:
  - id: q3-merge-freeze
    capabilityPattern: 'slack:post-message:*'
    tierScope: ['T2']
    until: 1780000000   # unix ts
    reason: "Q3 merge freeze — no T2 customer-facing posts"
```

Next call from any T2 client returns `outcome='blocked' reason='active-freeze:q3-merge-freeze'`. No code change needed; cache picks it up via `source.watch()`.

The push mechanism (git? gh issue? push notification?) is **CHARTER TODO-002** — not yet wired.

---

## Adding a new connector

1. Add manifest `manifests/<name>.yaml` (follow `slack.yaml` / `gmail.yaml` shape)
2. Write a backend at `lib/backends/<name>-direct.ts` implementing the `ComposioClient` interface (3 methods: authenticate / executeTool / isAuthenticated)
3. Add a case to `scripts/connect.sh` for the credential collection flow (or rely on the generic opaque-token fallback)
4. Add a verifier branch to `scripts/verify-connection.mjs` for `sutra connect-test <name>`
5. Run `npm test` — `shipped-manifests.test.ts` auto-validates the new manifest

Templates:
- `lib/backends/slack-direct.ts` — simplest case (single bot token, ~150 LOC)
- `lib/backends/gmail-direct.ts` — full OAuth 2.0 with refresh-token handling, ~300 LOC

Both ship with paired test files in `tests/unit/` (mocked fetch).

---

## Charter TODOs (deferred — revisit triggers in CHARTER.md)

- **TODO-001** — Re-evaluate Nango for SOC2/HIPAA-sensitive paths (6-month checkpoint 2026-10-30)
- **TODO-002** — Fleet-policy push mechanism (git? gh issue? push notification?)
- **TODO-003** — `tierOverrides` implement-or-remove
- **TODO-004** — Resolver-order specificity in `findCapabilityDecl`
- **TODO-005** — Wire ConnectorRouter to load credentials from disk (`lib/oauth-store.ts` ?) so callers don't have to manually instantiate the backend

---

## Files to know

- `lib/index.ts` — `ConnectorRouter` (top-level orchestrator)
- `lib/policy.ts` — depth-aware permission + approval gate
- `lib/audit.ts` — append-only sink with redaction-by-construction
- `lib/backends/slack-direct.ts` — Slack Web API wrapper
- `lib/backends/gmail-direct.ts` — Gmail API + OAuth 2.0 refresh
- `manifests/*.yaml` — per-connector capability + tier + redaction
- `scripts/connect.sh` — `sutra connect <toolkit>`
- `scripts/verify-connection.mjs` — `sutra connect-test <toolkit>`
- `CHARTER.md` — governance contract (5 LOAD-BEARING boundaries; do not delegate)

---

## Test it locally (dry-run, no creds needed)

```bash
cd ~/.claude/plugins/cache/sutra/core/$(ls -1 ~/.claude/plugins/cache/sutra/core/ | sort -V | tail -1)/connectors
npm install
npm test
```

Expected: **146 tests passing** across 11 files (unit + integration + CLI).

Smoke-test the CLI without committing anything:

```bash
SUTRA_CONNECTORS_DRY_RUN=1 sutra connect slack
SUTRA_CONNECTORS_DRY_RUN=1 sutra connect gmail
```

---

## What's NOT done yet (deliberate v0 scope)

- **`ConnectorRouter` doesn't auto-load creds from disk** — the test harness builds its own backend. For a real CLI tool that invokes a Slack/Gmail call, we need a tiny `lib/oauth-store.ts` that reads `~/.sutra-connectors/oauth/<name>.json` and instantiates the right backend. **TODO-005.** Maybe ~30 LoC + a CLI verb like `sutra call <toolkit> <tool> --arg ...`.
- **Production deployment** — for the connectors module to actually be invoked from a Sutra session (e.g. when an LLM agent decides to read Slack), we need to expose `ConnectorRouter` to the agent runtime. Currently it's a library; not yet wired into a Claude Code skill or the assistant loop. Separate work.

These are intentional v0 deferrals. The pieces that ship today: governance contracts (frozen), backends (tested), CLI registration + verification (works against live Slack/Gmail today).
