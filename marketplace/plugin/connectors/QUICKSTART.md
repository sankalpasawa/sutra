# Sutra Connectors — Quickstart

**Status:** v0 shipped (codex ADVISORY, 117 tests passing). Module on disk; OAuth + real Composio install are founder-action.

---

## What this is

A Sutra-governed bridge to Slack, Gmail, GitHub, Linear, and any other Composio-supported service. **You** keep the brain (audit, depth-gating, tier-scoped permissions, fleet policy). Composio carries the auth + execution.

```
Your tier (T1-T4)  →  Sutra L1 (this module — rules)
                  →  Composio (auth + tool execution)
                  →  External system (Slack/Gmail/etc.)
```

All external calls are logged to `.enforcement/connector-audit.jsonl` with depth, tier, capability, outcome, and a hash of the (redacted) args.

---

## Founder action items — first-time setup

**One-time, ~10 minutes.**

### 1. Update plugin (after push lands)

```bash
claude plugin marketplace update sutra
claude plugin update core@sutra
```

This pulls the new connectors module into your `~/.claude/plugins/cache/sutra/core/<latest>/`.

### 2. Install Composio runtime deps

```bash
cd ~/.claude/plugins/cache/sutra/core/$(ls -1 ~/.claude/plugins/cache/sutra/core/ | sort -V | tail -1)/connectors
npm install
```

(This pulls vitest, yaml, typescript — dev deps. The Composio runtime client itself lands when we wire the real adapter — see `lib/composio-adapter.ts` — currently the module ships with the interface defined and a mock-friendly boundary, so tests run without the Composio package. Founder action 4 below pastes a token; the adapter wraps whatever Composio client you supply.)

### 3. Connect Slack

Register a Slack OAuth app → get a bot token (`xoxb-...`).

```bash
sutra connect slack
```

Paste the token when prompted. Lands at `~/.sutra-connectors/oauth/slack.token` (chmod 600).

### 4. Connect Gmail

Either path:

**Path A — Composio Cloud (easiest):**
1. Sign in at https://composio.dev → create an account API key
2. Connect Gmail through Composio's OAuth flow (they handle the Google OAuth dance)
3. Get the connection ID

**Path B — self-host Composio (per CHARTER TODO-003):**
1. Install Composio backend (Node + Postgres + Redis)
2. Register your own Google OAuth app
3. Connect Gmail through your local Composio instance

Then:

```bash
sutra connect gmail
```

Paste the Composio connection ID + API key.

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
6. Composio executes the post
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
2. Run `npm test tests/unit/shipped-manifests.test.ts` — should auto-validate the new manifest
3. Optionally add tier-specific scenarios to `tests/integration/v0-scenarios.test.ts`
4. `sutra connect <name>` to register OAuth

The Composio toolkit name in the manifest's `composioToolkit` field maps to https://composio.dev/toolkits/<toolkit>.

---

## Charter TODOs (deferred — revisit triggers in CHARTER.md)

- **TODO-001** — Re-evaluate Nango for SOC2/HIPAA-sensitive paths (6-month checkpoint 2026-10-30)
- **TODO-002** — OAuth app ownership: Asawa-managed vs per-client
- **TODO-003** — Composio self-host topology
- **TODO-004** — `tierOverrides` implement-or-remove
- **TODO-005** — `findCapabilityDecl` resolver order — prefer specific globs over generic

---

## Files to know

- `lib/index.ts` — `ConnectorRouter` (top-level orchestrator)
- `lib/policy.ts` — depth-aware permission + approval gate
- `lib/audit.ts` — append-only sink with redaction-by-construction
- `manifests/*.yaml` — per-connector capability + tier + redaction
- `CHARTER.md` — governance contract (5 LOAD-BEARING boundaries; do not delegate)
- `holding/research/2026-04-30-sutra-connectors-foundational-design.md` — spec
- `holding/research/2026-04-30-connectors-LLD.md` — frozen interfaces
- `.enforcement/codex-reviews/2026-04-30-connectors-master.md` — codex verdict (ADVISORY)

---

## Test it

```bash
cd ~/.claude/plugins/cache/sutra/core/$(ls -1 ~/.claude/plugins/cache/sutra/core/ | sort -V | tail -1)/connectors
npm test
```

Expected: **117 tests passing.**

Smoke-test the CLI without committing anything:

```bash
SUTRA_CONNECTORS_DRY_RUN=1 sutra connect slack
SUTRA_CONNECTORS_DRY_RUN=1 sutra connect gmail
```

Should print the connector summary + dry-run note for each.
