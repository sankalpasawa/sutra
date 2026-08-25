# 8 · Delivery

Covers deliverables **24 (testing), 26 (deployment), 27 (production security checklist), 28 (troubleshooting)**, plus project structure, desktop UX, and the implementation sequence for deliverable 25.

---

## 8.1 Project structure

```
connector-service/                     (ships inside the desktop bundle today,
├── api/                                deploys standalone tomorrow — same code)
│   ├── routes/{connectors,oauth,tools,approvals,stream}.py
│   ├── dto.py                         request/response models — NEVER a Credential
│   └── errors.py                      the one error envelope + user_action mapping
├── auth/
│   ├── operator.py                    Sutra identity — no provider knowledge
│   └── local_caller.py                per-launch bearer, Origin allow-list
├── oauth/
│   ├── transaction.py                 FSM, state, single-use redemption
│   ├── strategies/device.py           local (F3/F4)
│   └── strategies/web_pkce.py         hosted (F1/F2)
├── connectors/
│   ├── core/{service,lifecycle,models}.py     provider-agnostic
│   ├── provider/{factory,protocol,config}.py
│   └── github/                        ← the ONLY package that knows GitHub exists
│       ├── provider.py  client.py  identity.py
│       ├── repositories.py  organizations.py
│       ├── capabilities.py  operations.py  errors.py
├── credentials/
│   ├── store.py                       the port
│   ├── keychain.py  dpapi.py  libsecret.py   local adapters
│   └── kms_envelope.py                hosted adapter
├── capabilities/{model,resolver,policy}.py
├── approvals/{grant,gate}.py
├── tools/{registry,schemas,gateway}.py
├── audit/{sink,chain,events}.py
├── security/{untrusted,taint,redaction}.py
├── ratelimit/{budget,breaker,retry}.py
├── cache/{store,keys}.py
├── database/{migrations,repositories}.py
└── observability/{metrics,tracing}.py

desktop/
├── connectors/                        connector list, connect flow, manage, disconnect
├── github/                            repo & org pickers  (renders only; no API knowledge)
├── agent/                             session binding, tool-result rendering
├── permissions/                       approval cards, capability settings
├── ui/                                shared components
└── security/                          caller token handling, CSP, contextIsolation
```

**Enforced in CI, not by convention:**
1. No import of `connectors.github` outside `connectors/provider/factory.py`.
2. The literal `github` appears above `connectors/github/` only as a provider-id string.
3. No query in `database/repositories/` lacking an `operator_id` predicate.
4. `Credential` is unreachable from any module under `api/`.

---

## 8.2 Desktop UX

```
Settings ─► Connections ─► GitHub ─► Connect ─► [device code card] ─► browser ─► Connected
```

```
┌──────────────────────────────────────────────────┐   ┌──────────────────────────────────────┐
│ Connections                                      │   │ Connect GitHub                       │
│                                                  │   │                                      │
│ GitHub                                           │   │ 1. Your code:   WDJB-MJHT     [copy] │
│ ● Connected as octocat            personal       │   │ 2. Open github.com/login/device      │
│   12 repositories · 3 organizations              │   │ 3. Enter the code                    │
│   [Manage]  [Disconnect]                         │   │                                      │
│                                                  │   │ Waiting…  expires in 14:32           │
│ GitHub                                           │   │                    [Open browser]    │
│ ▲ Reconnect needed — acme-corp requires SAML     │   │                    [Cancel]          │
│   [Authorise for acme-corp]  [Disconnect]        │   └──────────────────────────────────────┘
│                                                  │
│ Slack        ○ Not connected        [Connect]    │
└──────────────────────────────────────────────────┘
```

Error and reauth states follow `02 §2.1`: the message names the **specific** cause and offers the action that fixes *that* cause. Four rules the UI must not break:

1. Never show a raw provider error string. Switch on `user_action`.
2. Never show a connector UUID to a human. Show `@login` + label + avatar.
3. Never say "revoked on GitHub" when we only deleted our local copy (`02 §2.6`).
4. Always show which connector an action will use, when more than one exists.

---

## 8.3 Testing

### Unit

| Area | Cases |
|---|---|
| OAuth state | 256-bit entropy · stored hashed · single-use (second redemption updates 0 rows) · expiry enforced on the clock as well as the status · operator binding |
| PKCE | S256 only · `plain` rejected · verifier↔challenge round-trip · verifier destroyed on completion |
| Transaction FSM | every legal transition; **every illegal transition raises** |
| Connector lifecycle | all state transitions; `EXPIRED` is not a state; reconnect preserves the row id |
| CredentialStore | save/get/delete/rotate per adapter · delete is irreversible · `repr()` never leaks · not JSON-serialisable |
| Capability resolver | intersection of three layers · most-specific-wins · most-restrictive-on-tie · unknown capability = DENY (fail closed) |
| Error classification | all 8 rows of `03 §3.2`; the four 403 branches of `07 §7.1` |
| Approval grants | hash binding · single-use · expiry · every reuse variant in `04 §4.4` |
| Audit chain | verify passes on a good chain, fails on any single altered row |

### Integration

```
Desktop → Connector Service → GitHub (recorded fixtures + one live nightly)
  connect → identity → installations → repositories → read file → disconnect
```
Fixtures are recorded from real responses with tokens scrubbed at record time. One nightly job runs the full path against a real test GitHub App — because fixtures cannot catch GitHub changing behaviour, and that is what pinning the API version and testing live are jointly for.

### Security tests (these are the suite that must never be allowed to rot)

| Test | Asserts |
|---|---|
| Token leakage | no token-shaped string in any log, response, metric label, error, or crash dump |
| State replay | a second redemption of one `state` fails |
| Transaction hijack | operator B cannot complete operator A's transaction |
| Connector id manipulation | operator B gets **404**, not 403, for A's connector |
| Cross-user tool call | agent session bound to A cannot touch B's connector |
| Cross-connector | session on the personal connector cannot reach a work-only repo |
| Cross-repository | a write outside the resource scope is DENY |
| Privilege escalation | no tool grants/queries/escalates permission; DENY has no retry path |
| Approval reuse | all six reuse variants rejected |
| Prompt injection | 20+ payloads across README / issue / PR body / commit message / `AGENTS.md` / `CLAUDE.md`; assert **no** unapproved write occurs |
| Taint escalation | after any untrusted read, an AUTO write becomes ASK_USER |
| Malicious tool args | URLs in `repository`, `../` traversal, 10 MB strings, unknown fields — all rejected |
| Cursor tampering | an altered cursor is rejected, never dereferenced |
| Blind 403 retry | a permission 403 produces exactly one request |

### Agent tests

Read a repo · create a branch · create a commit · create a PR · **attempt an unauthorized operation (must be denied and audited)** · **attempt a destructive operation (must require approval, and must not execute on denial)**. The last two are the tests that prove the platform, and they must fail the build when broken.

---

## 8.4 Development vs production

Two separate GitHub Apps, always:

| | Development | Production |
|---|---|---|
| App | `Sutra (dev)` | `Sutra` |
| Client id | dev | prod |
| Client secret | dev, hosted dev only | prod, in the secrets manager only |
| Private key | dev | prod, KMS-held, never on a laptop |
| Callback | `https://dev-api.sutra.…/oauth/github/callback` | `https://api.sutra.…/oauth/github/callback` |
| Test data | a throwaway org | real users |

`.env.development` / `.env.test` / `.env.production` hold **names of secrets**, never values. Values come from the OS keychain (dev) or the secrets manager (prod). `.gitignore` covers `.env*` except `.env.example`; a pre-commit secret scanner is mandatory, not advisory. Production credentials never appear on a developer machine — if they must be rotated, that is done in the console, not locally.

---

## 8.5 Deployment

**Local (v1)** — the service is a child process of the Electron main process, bound to 127.0.0.1 only, never `0.0.0.0`. Port is ephemeral and handed to the renderer with the launch token; a fixed port is a squattable port. SQLite in WAL mode, 0600, under Application Support. The app is signed and notarised; the Keychain ACL depends on that signature, so an unsigned build cannot silently read a signed build's credentials.

**Hosted (v2)**

```
Desktop ──► API Gateway (TLS, WAF, per-operator rate limit)
                 │
                 ▼
      Connector Service — stateless, N replicas, HPA
                 ├── PostgreSQL (primary + replica, PITR, RLS on operator_id)
                 ├── Redis (transactions, budgets, cache — never credentials)
                 ├── KMS (multi-region CMK, service role holds Decrypt alone)
                 └── GitHub API (published egress IPs for org allow-lists)
```

| Concern | Design |
|---|---|
| Horizontal scaling | Stateless; all state in Postgres/Redis. Refresh uses `SELECT … FOR UPDATE` so N replicas cannot race one refresh token. |
| Backups | Nightly + PITR. Backups contain ciphertext and wrapped DEKs only — safe to hold, useless without live KMS. |
| Disaster recovery | Documented restore drill, run quarterly. **A lost CMK = total connector loss and universal re-auth**; this is written down rather than discovered. |
| Secret rotation | Client secret rotated with an overlap window; CMK rotation rewraps DEKs in the background; per-launch tokens rotate every launch. |
| Migration local→hosted | Re-auth, never credential export (ADR-034). |

---

## 8.6 Implementation sequence

| Phase | Ships | Status |
|-------|-------|--------|
| **P1** | schema + migrations, `ConnectorService`, `CredentialStore`+Keychain, device-flow `AuthStrategy`, `/authorize` + poll, identity, connector row | ✅ **shipped 2.111.0** — verified against a live connection to the then-collaborator's GitHub account (identifier removed per D69) |
| **P2** | `GitHubClient` (pinned version, Link pagination, error classification), installations, repos, orgs, `validate`, reauth, disconnect | ✅ **shipped 2.111.0** — ⚠️ **unproven against real repositories**: the GitHub App is authorized but not installed, so `/user/installations` returns `total_count: 0` and only the empty-state path has run live |
| **P3** | capability model, resolver, policy table, capability API | ✅ **shipped 2.112.0** — settings resolved from the five real paths; 11 panel endpoints; Connectors screen |
| **P4** | tool registry + gateway, READ tools, untrusted envelope, taint tracking, audit chain wiring | ⬜ next |
| **P5** | approval grants + gate + desktop cards, WRITE tools, idempotency | ⬜ |
| **P6** | rate budgets, breaker, retry classification, cache, metrics, alerts | ⬜ |
| **P7** | the full security suite of `8.3` in CI as a merge gate | ⬜ |

P7 is not last because it is least important. It is last because it asserts the
properties P1–P6 build, and it must be a merge gate from the day it exists.

### What P1–P3 do NOT yet give you

Stated plainly so the phase ticks above are not read as more than they are:

| Not built | Consequence today |
|---|---|
| Tool gateway (P4) | **Nothing invokes a capability.** The permission engine answers "would this be allowed"; no code path asks it on behalf of an agent. |
| Untrusted envelope + taint tracking (P4) | Repository content is not yet wrapped or taint-tracked, because nothing reads it into an agent. |
| Approval grants (P5) | `ASK` is a decision the engine returns; no card renders it and no grant is minted. |
| Rate budgets, breaker (P6) | GitHub's limits are classified correctly but not yet enforced on our side. |
| `web_pkce` strategy | Hosted-only. The port exists; the implementation does not. |
| Remote revocation on disconnect | Needs a `client_secret` local mode is never issued. Reported honestly rather than claimed. |

## 8.7 Troubleshooting

| Symptom | Likely cause | Check | Fix |
|---|---|---|---|
| Device code never completes | user never entered it, or entered it on a different GitHub account | transaction status; `expires_at` | restart the flow; confirm which account is signed in |
| `authorization_pending` forever | user authorised a *different* App (dev vs prod) | which client id the transaction used | use the matching build |
| Connected, but zero repositories | App installed on the personal account only, or `repository_selection: selected` with none chosen | `/user/installations` → `repository_selection` | "Add repositories" deep link |
| Repo visible on github.com, absent in Sutra | App not installed on its owner | installations vs `/user/orgs` diff | install on that org |
| 403 with no rate headers | App permission missing, or org third-party restriction | response body; installation `permissions` | request the permission, or ask the org owner to approve |
| 403 that comes and goes | secondary rate limit | `retry-after` present? | honour it — do not lower the interval |
| 404 on a repo the user can open | private and outside the installation | installation repo list | add it; **do not** report "not found" to the user |
| Works personally, fails at work | SAML SSO not authorised for that org | `X-GitHub-SSO` header | "Authorise for <org>" link |
| Reconnect does not clear the error | the App was uninstalled, or the user was removed from the org | `status_reason` | reinstall / restore membership — reconnect cannot fix either |
| Agent says it lacks permission it should have | capability grant is resource-scoped narrower than the repo | `connector_capabilities` rows for that resource | widen the grant in Manage |
| Every write asks for approval unexpectedly | taint escalation after an untrusted read (working as designed) | `untrusted_content_read` for the session | expected; the card shows the taint warning |
| Two connectors, wrong account used | session bound to the other connector | session record | new session with the right connector — never switch mid-session |
| Tokens vanish after an app update | build signature changed → Keychain ACL no longer matches | signing identity of both builds | re-auth; ensure release builds share a signing identity |

---

## 8.8 Production readiness checklist

```
(marked as of 2.112.0 — P1-P3. Unticked items are P4-P7 or hosted-only.)

OAuth
[ ] Authorization Code flow implemented (hosted strategy)
[x] Device flow implemented (local strategy)                       ← v1 path
[ ] PKCE implemented, S256 only, `plain` unreachable
[x] State: 256-bit, hashed at rest, single-use via rowcount, ≤10 min, operator-bound
[x] OAuth transactions expire and are swept
[x] Authorization codes single-use (GitHub-enforced + our claim check)
[x] Client secret never in the desktop binary, repo, log, or renderer
[ ] Redirect URI exact-match, one registered value (hosted)

Credentials
[x] Encrypted at rest — Keychain (local) / KMS envelope with AAD (hosted)
[x] Never in logs, responses, metric labels, traces, or crash dumps
[ ] CI test greps every sink for token-shaped strings
[x] Credential type not serialisable; repr/str/format redacted
[x] Rotation on every refresh; old credential destroyed
[x] No credential export path exists anywhere in the codebase

Identity & lifecycle
[x] Connector identity separate from application identity
[x] GitHub numeric user id is the stable provider identity; login is display-only
[x] UNIQUE(operator_id, provider, provider_account_id) present and tested
[x] Multiple GitHub accounts: connect, switch, isolate, no overwrite
[x] Full lifecycle implemented incl. specific REAUTH reasons
[x] Reauthorize preserves the connector row; account mismatch is rejected
[x] Disconnect deletes credentials before attempting remote revocation
[x] Disconnect UI states honestly whether GitHub authorization was revoked

Authorization
[ ] Repository permissions enforced; 404 never rendered as "does not exist"
[ ] Organization restrictions handled: SSO, third-party approval, EMU, suspended, selected-repos
[x] Capabilities enforced outside the LLM, re-resolved per call, never cached
[x] Unknown capability fails closed
[x] Destructive operations require human approval; repo/org deletion not implemented at all
[ ] Approval grants bound to an operation hash, single-use, ≤5 min, re-verified at dispatch
[x] Cross-user connector access prevented (operator predicate + 404 + RLS)
[ ] Cross-connector and cross-repository access prevented
[x] connector_id never appears in a tool schema

Agent safety
[ ] All provider content wrapped as untrusted; no filename confers trust
[ ] Taint tracking escalates writes to ASK_USER after any untrusted read
[ ] Injection classifiers are telemetry only, never an authz input
[ ] Tool args strictly schema-validated; additionalProperties false; no URLs in identifiers
[x] Cursors opaque and signed; never dereferenced

Operations
[ ] 403 classified four ways; permission 403 never retried
[ ] Budgets below GitHub's; concurrency under 100; content-creating under 80/min
[ ] retry-after honoured exactly; circuit breaker per connector
[ ] File contents cached only at an immutable SHA
[ ] Cache keys always include connector_id
[x] Audit rows for every meaningful action, hash-chained, append-only, secret-free
[ ] Chain verification scheduled; failure is P1
[ ] Metrics, alerts and request-id tracing in place; no PII in labels

Build & release
[x] Development and production GitHub Apps fully separated
[ ] .env holds secret names, not values; pre-commit secret scanning enforced
[ ] Desktop packages signed and notarised (Keychain ACL depends on it)
[ ] Renderer: contextIsolation on, nodeIntegration off, strict CSP
[ ] Service binds 127.0.0.1 only, ephemeral port, per-launch bearer token
[ ] Security test suite is a merge gate
[ ] E2E suite green against a real test GitHub App
[ ] Production monitoring and alerting live before the first external user
```
