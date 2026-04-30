# CONNECTORS — Sutra Governance Charter

*Version: v0.1.0 · Adopted: 2026-04-30 · Status: ACTIVE · Owner: CEO of Sutra*

Internal governance charter for the Sutra Connectors module — peer to PERMISSIONS and PRIVACY. Lives in-tree with the module at `sutra/marketplace/plugin/connectors/CHARTER.md` (per build-plan codex review: charter ships WITH the module so every install carries the scope rules that bind it).

**Source spec:** `holding/research/2026-04-30-sutra-connectors-foundational-design.md` (APPROVED).
**LLD:** `holding/research/2026-04-30-connectors-LLD.md` (FROZEN — interfaces are contract).
**Codex consult:** `.enforcement/codex-reviews/2026-04-30-sutra-connectors-design.md` (DIRECTIVE-ID 1777490023, VERDICT: ADVISORY).

---

## 1. Scope statement — what Connectors IS and what it ISN'T

### Connectors IS

A Sutra-owned three-layer architecture for invoking external services (Slack, GitHub, Gmail, Linear, etc.) under tier-scoped capability policy with append-only audit. The three layers, per foundational spec §2:

| Layer | Who builds | What it does |
|-------|------------|--------------|
| **L1: Sutra** | We build | Rules: who can do what, audit, approval gates, fleet policy |
| **L2: Composio** | We plug | Auth + tool catalog + execution (MIT, self-hosted) |
| **L3: MCP** | We use | Wire protocol — already exists in Claude Code |

The module path is `sutra/marketplace/plugin/connectors/` and is D38 build-layer L0 (PLUGIN-RUNTIME — ships to every client). Public API is the `ConnectorRouter.call(ctx)` orchestrator from LLD §2.9.

### Connectors IS NOT

- **Not a planning surface.** Connectors do not invoke `Composio.plan()`, `Composio.discover()`, `Composio.workbench`, `session-memory`, or any Composio surface beyond `authenticate` + `executeTool` + `isAuthenticated` (LLD §2.7).
- **Not a substitute for permission gates.** Existing PERMISSIONS hooks govern the local Bash/Write/Edit surface; Connectors govern *external* service calls. Different threat models, different gates.
- **Not an MCP-shaped internal model.** MCP is a wire protocol used at L3 only. Sutra's internal types (LLD §2.1) are MCP-agnostic.
- **Not a multi-vendor abstraction layer in v0.** v0 supports two integration patterns — Composio adapter AND first-party direct backends — both legitimate. A SECOND EXTERNAL VENDOR (e.g. Activepieces) still triggers charter amendment + codex review per PROTO-019.
- **Not unaudited.** Every external call produces an `AuditEvent` in `.enforcement/connector-audit.jsonl` (LLD §2.5). No silent calls.

---

## 2. Boundary discipline — the 5 LOAD-BEARING rules

These five rules from foundational spec §5 are the architectural promise. Each rule is enforced by mechanism (not honor system) where possible, and by codex review on every PR touching `connectors/` where mechanism is partial.

```
┌─ RULE 1 ────────────────────────────────────────────────────┐
│ Sutra L1 owns policy + audit + capability gating. L1        │
│ dispatches to integration adapters (Composio for catalog    │
│ connectors, first-party direct backends for high-traffic    │
│ services like Slack/Gmail). Adapters NEVER call back into   │
│ Sutra.                                                      │
└──────────────────────────────────────────────────────────────┘
```

**Mechanism**: `ComposioAdapter` (LLD §2.7) is the only egress; no Composio webhook receiver, no callback URL registered, no Composio-to-Sutra IPC. Any future "let Composio notify us" pattern requires charter amendment.

**Why**: keeps Sutra's policy + audit on the single hot path. If Composio could re-enter, we'd need a second policy/audit pipe and an authentication boundary between them — drift accelerates.

```
┌─ RULE 2 ────────────────────────────────────────────────────┐
│ Composio's planning/discovery features are NOT used.        │
│ Only auth + execution.                                      │
└──────────────────────────────────────────────────────────────┘
```

**Mechanism**: `ComposioClient` interface (LLD §2.7) exposes only `authenticate`, `executeTool`, `isAuthenticated`. `ComposioAdapter` throws `ForbiddenComposioApiError` if planning/discovery surface is touched. Guard tests in `tests/unit/composio-adapter.test.ts` verify this invariant.

**Why**: Composio's planning layer would dilute Sutra L1 — the Sutra LLM-visible tool surface must be Sutra-curated, not Composio-discovered.

```
┌─ RULE 3 ────────────────────────────────────────────────────┐
│ Sutra owns the tool surface visible to the LLM.             │
│ Sutra curates which Composio tools become Sutra             │
│ capabilities.                                               │
└──────────────────────────────────────────────────────────────┘
```

**Mechanism**: `ConnectorManifest.capabilities` (LLD §2.2) is the LLM-visible surface. The manifest references `composioToolkit`, but only declared `CapabilityDecl` entries are reachable. Adding a new capability is a charter-touched action: the manifest must list it, the tier map must include it, the redact paths must cover it.

**Why**: drift defense. Composio's catalog is 1000+ toolkits; if "any tool Composio has" became reachable, the LLM-visible surface could expand silently. Manifest-curated keeps it explicit.

```
┌─ RULE 4 ────────────────────────────────────────────────────┐
│ Sutra audit log is source of truth, NOT Composio's.         │
└──────────────────────────────────────────────────────────────┘
```

**Mechanism**: `AuditSink` (LLD §2.5) writes `.enforcement/connector-audit.jsonl` append-only with redaction-by-construction. Composio's logs are advisory only and never queried as authoritative. Fleet policy queries operate on Sutra's log.

**Why**: Composio is MIT and self-hosted but not a compliance product (foundational spec §1). Audit fidelity is Sutra's responsibility. If Composio rotates, breaks, or changes log schema, our governance doesn't degrade.

```
┌─ RULE 5 ────────────────────────────────────────────────────┐
│ CHARTER scope-pins L1; charter amendment required to        │
│ extend L1 into Composio territory.                          │
└──────────────────────────────────────────────────────────────┘
```

**Mechanism**: this charter, plus codex review on every PR under `connectors/`. PR description must call out boundary impact when L1 surface area changes (new lib file, new public API, new Composio API touched). Reviewer rejects if charter §2 amendment is missing.

**Why**: discipline drift is the named #1 risk in foundational spec §10. The trade we accepted for picking Composio over Nango was discipline cost; this rule is the discipline.

---

## 3. Charter TODOs (intentional deferrals — survive verbatim from spec §9)

Each TODO is a first-class entry. Trigger conditions are ANY-OF unless stated. Action when triggered is mandatory; deferral past trigger requires charter amendment with documented reason.

### TODO-CONNECTORS-001 — Revisit Nango for security/compliance

**Why deferred:** picked Composio for time. Nango ships SOC 2 Type II / GDPR / HIPAA / white-label auth out of the box; Composio's posture in those categories is verified only as a permissive MIT codebase, not as a compliance product.

**Trigger conditions to revisit (any one):**
- First connector requiring SOC 2 / HIPAA / GDPR attestation
- First T3 client or T4 fleet user with enterprise security requirements
- Discovery of Composio gaps in token-handling, multi-tenant isolation, or audit fidelity
- **6-month checkpoint: 2026-10-30** regardless of triggers

**Action when triggered:**
- Codex consult on Composio's specific security posture for the use case
- Evaluate hybrid topology: Composio for catalog, Nango for OAuth-heavy sensitive paths
- Compare attestation/certification surface (SOC 2 / HIPAA / GDPR / pen-test results)
- Write addendum to this charter with decision + rationale

**Why this matters:** Nango's security/compliance is genuinely stronger out of the box (Replit/Ramp/Mercor production usage attests). Composio's MIT openness means we *can* harden, but it's not delivered hardened. We accepted this trade for speed; we owe ourselves an honest re-look.

### TODO-CONNECTORS-002 — Revisit OAuth app ownership model

**Why deferred:** Asawa-managed OAuth apps vs per-client own apps is a UX/limit decision, not a foundation decision.

**Trigger:** first install at scale + first OAuth-rate-limit hit (e.g., Slack ~1000 installs free tier).

**Action when triggered:**
- Audit current OAuth app utilization and rate-limit headroom
- Decide Asawa-managed-fleet-OAuth vs per-client-own-app vs hybrid
- Update `connect.sh` flow + manifest tier policy if model changes
- Charter amendment if the choice affects T3/T4 access boundaries

### TODO-CONNECTORS-003 — Revisit Composio self-host topology

**Why deferred:** local-per-client vs Asawa-hosted backend affects T4 fleet UX. v0 = local. Long-term may need centralized.

**Trigger:** first T4 user with self-host friction (e.g., cannot run Postgres+Redis locally, or wants zero-config install).

**Action when triggered:**
- Evaluate centralized Composio host operated by Asawa (cost + ops + privacy implications)
- Audit data flows under centralized model against PRIVACY charter tier rules
- Decide; if topology changes, charter amendment + PRIVACY charter cross-reference

---

## 4. Capability model

Reference: LLD §2.3 (`capability.ts`) and foundational spec §4.

A **Capability** is a string in the form `<connector>:<action>:<resource>?` — e.g. `slack:read-channel:#dayflow-eng`. Capabilities are declared by manifests (LLD §2.2 `CapabilityDecl`) and granted by tier (LLD §2.2 `tierAccess`).

| Concept | Source | Notes |
|---|---|---|
| `Capability` (string) | `types.ts` | Format `<connector>:<action>:<resource>?`; declarative, no enum |
| `CapabilityDecl` | `manifest.ts` | id, action (read/write/admin), resourcePattern, minDepth, approvalRequired, costEstimate |
| `tierGrants(tier, capability, manifest)` | `capability.ts` | Returns `granted` + reason: tier-allowed / tier-denied / pattern-mismatch / depth-floor / unknown-capability |
| `isOverbroadCapability(capability)` | `capability.ts` | Rejects e.g. `slack:*` — no wildcard grants |
| `evaluatePolicy(ctx, manifest, fleetPolicy)` | `policy.ts` | Combines capability + depth + fleet checks; returns `PolicyDecision` |

**Approval gate**: capabilities with `approvalRequired: true` raise `ApprovalRequiredError` carrying `FounderApprovalRequest` (LLD §2.1). Caller renders BLUEPRINT-style box; founder ack issues a single-use approval token consumed via `policy.consumeApproval(token)`.

**No wildcard capabilities.** `isOverbroadCapability` rejects manifests declaring `slack:*` or similar. Concrete resource patterns only.

---

## 5. Tier-scoped access

Connectors honor Asawa D34 tier taxonomy and align with PERMISSIONS charter §4. The `tierAccess` map in each manifest is authoritative; the table below is the policy frame manifests must satisfy.

| Tier | Identity | Default Connector access | Approval gate | Notes |
|---|---|---|---|---|
| **T1 Asawa-internal** | `asawa-holding` and Asawa-owned modules | All declared capabilities, including admin actions | Approval required only for capabilities with `approvalRequired: true` (e.g. write to public-facing channels at D5) | Highest trust; founder is operator |
| **T2 Owned portfolio** | DayFlow, Billu, Paisa, PPR, Maze | Read + scoped-write per manifest; admin actions denied by default | Approval required for cross-tenant or external-visible writes | Per spec §7 v0 scenarios — DayFlow reads `#dayflow-eng`, posts to `#public-launch` only after founder approval |
| **T3 Projects** | Testlify, Dharmik (client owns IP) | Project-scoped only — must declare client-owned resource patterns; Asawa internal resources denied | Approval required on every write | v0 scenario 4: Testlify reading Asawa `#ops` is blocked (T3 + no capability) |
| **T4 External fleet** | External Sutra plugin users | License-bound subset; capabilities default-OFF unless explicitly licensed in manifest tierAccess | Approval required on every write; opt-in per PRIVACY charter T4 stance | Default is the most restrictive; per PRIVACY charter, T4 is opt-in for telemetry — same posture for connector access |

**Stale-policy gate**: `FleetPolicyCache.isStale()` (LLD §2.6) returns true when policy age exceeds `staleAfterMs`. `evaluatePolicy` MUST reject calls when policy is stale (LLD §4 — `StalePolicyError`). This protects T4 from running on indefinitely-cached policy after a freeze push.

**Freeze rules**: Asawa pushes `FreezeRule` entries (LLD §2.6) with `capabilityPattern`, `tierScope`, optional `until`, and `reason`. A matching freeze blocks the call; freeze.id is logged in audit. v0 scenario 6: Asawa pushes "freeze external Slack" → all T2 clients block within 1 turn.

---

## 6. Audit invariants

Reference: LLD §2.5 (`audit.ts`), §4 (failure modes).

### Append-only

`.enforcement/connector-audit.jsonl` is append-only. No truncation, no rewrite, no in-place edit. Retention is governed by PRIVACY charter (default 30d, configurable via `SUTRA_RETENTION_DAYS`); rotation is by file-roll with new filename, not in-place mutation.

### Redaction-by-construction

`AuditSink.append` redacts BEFORE serialization. Redact paths come from `ConnectorManifest.redactPaths` (LLD §2.2). Args are hashed (`redactedArgsHash`: SHA-256 of redacted args) and stored, not raw args. Codex [P1] "redaction by construction" is satisfied: secrets cannot reach disk by accident.

This is the same fail-closed posture as PRIVACY charter §"Failure Modes" — sanitization error = skip write, never raw-write because scrub broke.

### Required fields present

Every `AuditEvent` (LLD §2.5) carries: `ts`, `clientId`, `tier`, `depth`, `capability`, `outcome`, `sessionId`, `redactedArgsHash`. Optional: `reason`, `approvalToken`, `errorClass`. Compile-time + runtime checks enforce presence.

### /tmp fallback + stderr beacon

If primary write fails (disk full, permission, file lock contention), `AuditSink` writes the event to `/tmp` with a process-unique filename AND emits a stderr beacon with the event id. The beacon is the loud failure signal — silent audit-loss is not allowed.

This is the codex-required failure path from LLD §4 row "Audit write failure". A future audit-reconciliation tool merges /tmp fallbacks back into the canonical log on next session start.

### Audit on every outcome

Outcomes audited: `allowed`, `blocked`, `approved-after-gate`, `error`. Blocked-then-approved produces TWO audit rows (the block first, then the approve), so the approval ledger is reconstructible without diffing.

---

## 7. Fleet policy

Reference: LLD §2.6 (`fleet-policy.ts`), spec §7 v0 scenario 6.

### Push direction

Asawa-holding pushes; clients pull. `FleetPolicySource` is the abstraction (LLD §2.6); v0 implementation is decided in plan-phase (foundational spec §11 Q4: git config? gh issue trigger? push notification?). The mechanism is interchangeable; the contract is not.

### Stale-detection

`FleetPolicyCache(staleAfterMs)` exposes `isStale()`. `staleAfterMs` defaults are tier-shaped (T1 longest, T4 shortest — exact values set in plan-phase). When stale, policy.evaluate rejects until refresh succeeds. Stale-failure is loud (StalePolicyError → audit row + caller-visible `outcome='blocked'`).

### Freeze

A `FreezeRule` is push-active immediately. The cache `watch()` callback fires on change; in-flight calls receive the new policy on next call boundary, not mid-call (LLD §3 dataflow — policy is evaluated in step 2, single read per call).

### Tier overrides — DEFERRED to v1.x (TODO-CONNECTORS-004)

**Status (2026-04-30, codex iter-11 P2 #5):** the `tierOverrides` field on `FleetPolicy` is documented in LLD §2.6 but **not implemented** in v0. `evaluatePolicy` does not consult it; setting a value has no effect on tier access. The field is kept optional on the type for backward-compat with existing fixtures and is deprecated in `types.ts`.

**Why deferred:** v0 ships a single source of truth for tier access — `ConnectorManifest.tierAccess`. Adding a runtime override layer increases surface area without a v0 use case. A real v1.x driver (e.g., per-customer license-bound additions) will pull this back as TODO-CONNECTORS-004 with a real test matrix.

**v1 design intent (when implemented):** overrides are SUBTRACTIVE OR within-manifest only — they MUST NOT widen access beyond what `tierAccess` already declares. This preserves rule 3 (Sutra owns the LLM-visible surface).

### TODO-CONNECTORS-004 — Implement tierOverrides

**Why deferred:** v0 had no concrete driver for fleet-level tier overrides; sole demand was "documented in LLD." Removing instead of implementing keeps the v0 surface honest.

**Trigger conditions to revisit (any one):**
- First customer asking for per-license capability subset (e.g., T4 customer with limited #public-* + #their-org channel)
- First need to dynamically REVOKE a tier-granted capability without re-shipping the manifest
- Fleet policy roll-out cadence outpaces manifest update cadence

**Action when triggered:**
- Codex consult on subtractive-only semantics + drift defense
- Implement in `policy.ts` with explicit allow-only-narrowing test matrix
- Lift `@deprecated` from `FleetPolicy.tierOverrides` in `types.ts`
- Charter amendment to update §7 prose

### TODO-CONNECTORS-005 — Browser-control connector for OAuth bootstrap (co-work)

**Why deferred:** every OAuth bootstrap step (creating a Slack app, getting a Gmail token via the OAuth playground, etc.) is human-only by OAuth design — Claude cannot click "Allow" on a consent screen because it has no logged-in browser session. Today the founder does this once per provider (3-10 min each). Path B (self-host Composio) eliminates this for most providers but adds Postgres + Redis runtime.

**Why this charter row exists:** founder direction 2026-04-30 — long-term goal is Claude-and-founder co-working with proper consent boundaries, where Claude can drive the founder's authenticated browser session for OAuth dances, then operate against the resulting tokens. Sometimes the only way to provision an OAuth app for an obscure SaaS is to click through their UI; a browser connector lets Claude do that step instead of the founder.

**Trigger conditions to revisit (any one):**
- Onboarding the 3rd direct-OAuth connector (i.e., 2 already used the manual click-through; founder time on bootstrap is now non-trivial)
- OR the founder's existing direct-OAuth providers exceed ~10 (token rotation / reauth becomes tedious)
- OR a Sutra client (T2/T3) needs OAuth bootstrap on their machine and we want it self-service

**Action when triggered:**
- Codex consult on browser-connector security model
- Build `lib/backends/browser-direct.ts` using Playwright with `userDataDir` pointing at the founder's existing Chrome profile (so Claude inherits real logins, doesn't need credentials in-band)
- Storage of "what the connector is allowed to do" — must integrate with PERMISSIONS charter (every browser action subject to depth + tier + approval gate, like every other connector)
- Hardening: deny-list of destructive UI patterns ("Delete account", "Revoke all sessions", etc.) backed by codex review of the click-script
- Audit trail: every navigation + click logged to `.enforcement/connector-audit.jsonl` like any other connector call
- v0 scope: read-only flows (creating apps, copying tokens). Mutations (sending DMs, modifying account settings) require depth ≥4 + approval token, same model as other backends.

**What it explicitly is NOT:**
- A keylogger or general remote-control surface — it operates inside Sutra's policy/audit boundary, every action governed
- A way to bypass MFA/2FA — the founder still does any TOTP/security-key step at session start; Claude operates inside the authenticated session
- A substitute for OAuth — it AUTOMATES the OAuth dance; the consent step is still the founder's authentication, just with Claude driving the click sequence per founder's instruction

**Required charter clarifications before build:**
- Which Chrome profile (default vs dedicated `~/.sutra-connectors/chrome-profile/`)
- Default depth floor for any browser action (proposed: 3; UI mutations: 5 + approval)
- Per-domain allow-list (api.slack.com, accounts.google.com, etc. — refuse navigation outside)
- Screenshot retention + redaction for audit (PRIVACY charter alignment)

### Push cadence

No fixed cadence in v0. Asawa pushes when policy needs to change. Clients refresh on session start and on `watch()` notification. The 6-month TODO-CONNECTORS-001 checkpoint may revisit cadence if a compliance-driven model is needed.

---

## 8. Amendment process — what requires re-charter

A charter amendment is required (PR with `[charter]` tag, codex review, founder approval) for any of:

| Change | Required because |
|---|---|
| Extending L1 surface into Composio territory (e.g., adding a new method to `ComposioClient` beyond `authenticate`/`executeTool`/`isAuthenticated`) | Boundary rule 2 + 5 |
| Widening `ComposioAdapter`'s forbidden-API list inversion (e.g., allowing `Composio.plan()` for any reason) | Boundary rule 2 |
| Adding a second L2 vendor (e.g., Nango as a sibling to Composio) | Foundational decision per spec §1; would also resolve TODO-CONNECTORS-001 |
| Removing or weakening any of the 5 boundary rules in §2 | They are LOAD-BEARING by name |
| Changing audit invariants in §6 (append-only, redaction-by-construction, fallback) | Audit fidelity is rule 4 |
| Tier policy changes in §5 that widen access (e.g., T4 default-on for any capability) | Crosses PRIVACY charter T4 stance |
| Self-host topology change (resolves TODO-CONNECTORS-003) | Touches client install model + PRIVACY data flows |
| OAuth ownership model change (resolves TODO-CONNECTORS-002) | Touches multi-tenant + rate-limit boundaries |
| Adding a new MCP-shaped internal type (would break "MCP is a wire, not a schema" — spec §6) | Architectural shape decision |

A change is **NOT** a charter amendment when it:

- Adds a new connector manifest under existing rules (e.g., `manifests/github.yaml` following the slack reference shape)
- Adds capabilities to an existing manifest within the manifest's pattern shape (subject to PR review against rule 3)
- Tunes `staleAfterMs` or freeze cadence within tier defaults
- Adds new audit-event fields that are pure additions (codified in PRIVACY charter as "must update allowlist + sheet + charter in same commit" — same rule applies here for the audit-fields surface)

Codex review is required on every PR touching `connectors/` regardless of amendment status (foundational spec §10 mitigation for "discipline drift").

---

## 9. References

| Artifact | Path |
|---|---|
| Foundational design spec | `holding/research/2026-04-30-sutra-connectors-foundational-design.md` |
| Low-Level Design (frozen interfaces) | `holding/research/2026-04-30-connectors-LLD.md` |
| High-Level Design + diagrams | `sutra/marketplace/plugin/connectors/HLD.md` (iter 2) |
| Test plan | `sutra/marketplace/plugin/connectors/TEST-PLAN.md` (iter 2) |
| Codex consult verdict (design) | `.enforcement/codex-reviews/2026-04-30-sutra-connectors-design.md` (DIRECTIVE-ID 1777490023, ADVISORY) |
| Codex consult (build plan) | `.enforcement/codex-reviews/2026-04-30-connectors-build-plan.md` |
| Peer charter — PERMISSIONS | `sutra/os/charters/PERMISSIONS.md` |
| Peer charter — PRIVACY | `sutra/os/charters/PRIVACY.md` |
| Module README | `sutra/marketplace/plugin/connectors/README.md` (iter 6) |
| In-tree spec copy | `sutra/marketplace/plugin/connectors/SPEC.md` |

---

*This charter governs the Connectors module. Amendments follow §8. Quarterly audit by CEO of Sutra; 6-month TODO-CONNECTORS-001 checkpoint at 2026-10-30 (mandatory).*

---

## 10. License posture (M2 step 5 honesty)

The Connectors module pulls in five OSS dependencies plus one system binary. License posture is an explicit clause in the charter so future contributors know what's acceptable to swap in or replace.

| Dep | Kind | License | Status | Why we picked it |
|---|---|---|---|---|
| **Composio** | L2 adapter (npm) | MIT | shipped (optional, behind ComposioAdapter) | Self-hosted, MIT, broadest catalog. Per §1, Composio is a plug — no callbacks, no planning surface. |
| **age** | system binary | BSD-3-Clause | shipped (system dep, install via brew/apt/pacman/scoop) | Single small binary, well-audited symmetric encryption. Used by `lib/secret-store-age.ts` for credential at-rest encryption (M1.7). |
| **cockatiel** | npm dep (Microsoft) | MIT | shipped (Mode B retry policy) | Battle-tested retry + circuit-breaker. Used by `ConnectorRouter` Mode B (M1.6). |
| **nanoid** | npm dep | MIT | shipped (idempotency_key + event_id generation) | Tiny (~130B), zero deps, URL-safe IDs. Used by `call.mjs` + Mode B Router (M1.3). |
| **yaml** | npm dep | ISC | shipped (manifest parser) | Standard YAML 1.2 parser. Used by `lib/manifest.ts`. Moved to runtime `dependencies` in M2 step 1. |

### Considered but NOT shipped

| Dep | License | Why we did not ship |
|---|---|---|
| **Infisical** | MIT-core / commercial-enterprise | Considered for credential management before age was selected. age won on simplicity (single binary, no server) and license clarity (pure BSD vs split-license). |
| **Activepieces** | MIT-core / commercial | Considered as a second L2 vendor alongside Composio. Per §1 rule 4 ("Not a multi-vendor abstraction layer in v0"), adding a second vendor triggers charter amendment + codex review. Not shipped in v2.10.x. |

### Posture rule

Any new runtime dependency added to `connectors/package.json` MUST be:
1. Listed in this section with kind, license, status, and rationale.
2. Reviewed for license compatibility with the plugin's MIT umbrella (no GPL, no AGPL, no SSPL).
3. Justified against an in-tree alternative — if Sutra could write 50 lines of code instead of taking the dep, prefer the in-tree code.

License-tracking note: this charter is the source of truth. `package.json` is the runtime artifact. If they drift, the charter wins and `package.json` must be reconciled.

---

## Changelog
- v0.3.0 (2026-05-01): §10 added — explicit license posture for shipped + considered OSS deps (M2 step 5).
- v0.2.0 (2026-04-30): Sync to shipped runtime — direct backends recognized as legitimate alongside Composio. Multi-vendor expansion still triggers amendment.

TRIAGE: depth=5 class=correct
ESTIMATE: tokens=~25k files=1 time=3min category=charter
ACTUAL: tokens=~28k files=1 time=3min
OS TRACE: subagent > read-spec+peer-charters > write-CONNECTORS-charter > done
