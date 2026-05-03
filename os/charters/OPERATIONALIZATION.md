# Charter: Operationalization

**Objective**: Every shipped artifact operates in production — measured, monitored, iterated, retired on signal — not just deployed and forgotten.
**DRI**: Sutra-OS
**Contributors**: Engineering, Operations, Analytics
**Status**: ACTIVE (v2 — rewritten 2026-04-20 post-Codex round-1 + founder decisions)
**Applies to**: Sutra (self) first. Propagation to DayFlow + Billu queued (depends on upgrade-clients.sh charter-aware extension — shared dep with Tokens).
**Created**: 2026-04-20 (v1) → rewritten 2026-04-20 (v2)
**Review cadence**: Every 6 hours for first 72h, then daily; scored bi-weekly
**Source direction**: holding/FOUNDER-DIRECTIONS.md D30 (2026-04-20)
**Cadence note**: All windows in this charter calibrated in hours, not days, per founder 2026-04-20 — Asawa moves per-hour. 6h check cadence; 24h minimum observation window.
**Design doc**: holding/research/2026-04-20-operationalization-charter-v2-redesign.md

---

## 1. Why this charter exists

Sutra lifecycle terminates at EXECUTE → MEASURE → LEARN. Artifacts get designed, implemented, sometimes measured — but adoption, monitoring, escalation, and decommissioning get left for the next founder prompt.

Founder D30 (2026-04-20): "Whatever things we build for Sutra, Asawa, client companies — plan, design, ship, and AFTER shipping, work on operationalizing it. Can't wait for humans to operationalize — create the operational plan and execute it."

This charter inserts a **7th lifecycle phase — OPERATIONALIZE** — between MEASURE and LEARN. Every new artifact ships with a 6-section operationalization plan, enforced at git boundary.

---

## 2. Six-Section Operationalization Template

Every enforced artifact carries this inline section:

~~~markdown
## Operationalization

### 1. Measurement mechanism
What metric proves this works in prod?

### 2. Adoption mechanism
How does this reach every intended consumer?

### 3. Monitoring / escalation
Who watches, at what cadence, with what threshold triggers action?

### 4. Iteration trigger
Under what observed condition does this get revised, deprecated, or expanded?

### 5. DRI
Named role (not "author default").

### 6. Decommission criteria
Under what signal does this artifact retire?
~~~

1-3 lines per section minimum. V1 = presence gate only (quality lint deferred to V3 per founder 2026-04-20).

---

## 3. KPIs (denominator-safe)

| Metric | Formula | Null handling | Target (Q2) | Warn | Breach |
|---|---|---|---|---|---|
| New-artifact compliance | count(new_artifacts_with_ops) / count(new_artifacts) rolling 6h, denom>=2 | denom<2 → insufficient-data | 100% | <95% | <80% |
| Grandfather-revoked compliance | count(revoked_with_ops) / count(revocations) rolling 24h, denom>=2 | denom<2 → insufficient-data | 100% | <90% | <70% |
| Block-to-add time | median(commit_ts_ops_added − commit_ts_first_block) per artifact | null if no block | <=4h | >24h | >72h |
| Active artifact churn | count(retired_in_q) / count(active_at_q_start) | active=0 → N/A | 5-15% | 0% | >40% |
| Registry freshness (risk-tiered) | count(active where next_review < today - 2q) / count(active) | tier-relative | <10% | >=25% | >=50% |

---

## 4. OKRs — Q2 2026

```
OBJECTIVE: Every shipped artifact operates in prod — measured, monitored, iterated.

  KR1: Lifecycle extended (ESTIMATION-ENGINE + PROTO-000 6th criterion
       + state/system.yaml) shipped 2026-04-20 — Score: 1.0 (shipped V1)
  KR2: Hook HARD at 4 trigger points (PostToolUse + pre-commit + pre-push + CI)
       shipped 2026-04-20 — Score: 1.0 (shipped V1)
  KR3: New-artifact compliance = 100% for 14 consecutive days
       by 2026-05-05 — Score: 0.0
  KR4: Propagated to >=2 downstream companies via charter-aware
       upgrade-clients.sh (shared dep with Tokens KR4) by 2026-06-30 — Score: 0.0
```

---

## 5. Enforcement Spec

### 5.1 Enforced paths (Tier A + Tier B per founder)

**Tier A** (always enforced):
- sutra/os/charters/*.md
- sutra/**/protocols/PROTO-*.md
- sutra/**/d-engines/*.md, sutra/**/engines/*.md
- holding/departments/*/CHARTER.md
- sutra/os/SUTRA-CONFIG.md, */os/SUTRA-CONFIG.md

**Tier B** (extended):
- holding/hooks/*.sh, sutra/package/hooks/*.sh
- sutra/layer4-practice-skills/**/*.md
- sutra/package/bin/*.sh, sutra/package/bin/*.mjs
- .claude/commands/*.md
- holding/departments/*/*.sh

Editable registry: sutra/state/system.yaml.operationalization.enforced_paths.

### 5.2 Exempt paths
- holding/research/*.md, TODO/BACKLOG/CHANGELOG/MEMORY, .claude/, .enforcement/, .analytics/, *.log, *.jsonl, holding/checkpoints/*

### 5.3 Four trigger points

| Point | Location | Speed | Authority |
|---|---|---|---|
| Early feedback | PostToolUse on Edit/Write | instant | warn only |
| Pre-commit | .git/hooks/pre-commit | <1s | BLOCK commit |
| Pre-push | .git/hooks/pre-push | <2s | BLOCK push |
| CI merge gate | .github/workflows/operationalization-check.yml | ~60s | BLOCK merge |

### 5.4 Grandfathering (git-history)

- Cutover commit SHA stored in sutra/state/system.yaml.operationalization.cutover_commit
- Files existing at cutover → exempt until semantic change
- Semantic change: new file OR diff >=5 lines OR heading change OR table row change
- Pure typo/whitespace → not semantic
- Pure rename → not semantic; grandfathering transfers to new path

### 5.5 No override

Per founder 2026-04-20: no env-var override. No OPS_PLAN_ACK. Only escape is reverting the hook (visible in git blame).

---

## 6. Roadmap — V1 shipped 2026-04-20; V2 ongoing

| # | Action | Wave | Status |
|---|---|---|---|
| 1 | holding/OPERATIONALIZATION-STANDARD.md | V1 | DONE |
| 2 | holding/hooks/operationalization-check.sh | V1 | DONE |
| 3 | holding/hooks/tests/test-operationalization-check.sh | V1 | DONE |
| 4 | .git/hooks/pre-commit + pre-push wrappers | V1 | DONE |
| 5 | .github/workflows/operationalization-check.yml | V1 (flipped per founder Q2) | DONE |
| 6 | sutra/state/system.yaml operationalization block + cutover_commit | V1 | DONE |
| 7 | PROTOCOLS.md — add 6th criterion OPERATIONALIZED to PROTO-000 | V1 (flipped per founder Q5) | DONE |
| 8 | ESTIMATION-ENGINE.md — add OPERATIONALIZE phase (both paths) | V1 (flipped per founder Q5) | DONE |
| 9 | Self-test: TOKENS.md gets ops section | V1 | DONE |
| 10 | 24-hour compliance window (4 × 6h cycles); heuristic revision if FP>10% | V2 | TODO |
| 11 | Charter-aware upgrade-clients.sh extension (shared w/ Tokens) | V2 | TODO |
| 12 | Propagate to DayFlow + Billu | V2 | TODO |
| 13 | Q2 review | — | TODO |
| 14 | **Reclassify charter → engine** per founder direction 2026-04-28: "operationalize is not a charter, but a higher abstraction layer that sits at any place." Move to `sutra/os/engines/OPERATIONALIZATION-ENGINE.md` (peer to BLUEPRINT-ENGINE / ESTIMATION-ENGINE). Tier 2 + Tier 3 framing per 2026-04-28 conversation. | V3 | TODO |
| 15 | **Default-strict scope inversion** per founder direction 2026-04-28: invert §5.1 from include-list of enforced paths to exempt-list (current §5.2 stays; everything else becomes a member of the artifact-class taxonomy by default). Closes the scope-mismatch failure mode that let `holding/scripts/sync-feedback-from-gh.sh` ship without an ops block on 2026-04-28. | V3 | TODO |
| 16 | **CLAUDE.md mandatory-block entry** for OPERATIONALIZATION alongside cascade-check / build-layer / blueprint, so contributors see the trigger at session start instead of post-hoc. Currently the charter's "enforced at git boundary" framing is invisible to in-session writes. | V3 | TODO |
| 17 | **Registry-coverage telemetry**: Analytics dept emits "% of `*.sh` paths edited that triggered the hook" so registry holes surface before they bite (the 2026-04-28 sync-feedback case had hook hits = 0 over 8 days; nobody noticed). | V3 | TODO |

Deferred to V3: quality lint, system-emits-typed-data, active registry quarterly kill, items 14-17 above (charter→engine reclassification + scope-default-strict + CLAUDE.md trigger + registry-coverage telemetry).

---

## 7. Active Artifact Registry

sutra/state/system.yaml.operationalization.active_artifacts — list of {path, cutover_sha, dri, tier, next_review_date, status}. Populated as artifacts get ops sections.

Quarterly: Sutra-OS scans next_review_date past-due entries, escalates to DRI. Two unresolved quarters → kill review → retired.

---

## 8. Practice Contributions

| Unit | Role | Responsibilities |
|---|---|---|
| Sutra-OS | DRI | Charter, STANDARD, engine edits, PROTO-000 extension, schema, scoring |
| Engineering | Contrib | Hook, 4-point trigger wiring, tests, upgrade-clients.sh extension |
| Operations | Contrib | Run-state monitoring, escalation, decommission |
| Analytics | Contrib | KPI collection, Pulse, 14-day audit |

---

## 9. Cross-charter links

| Link | Direction |
|---|---|
| Tokens | Each cut gets ops plan. Shared upgrade-clients.sh dep. |
| Speed | Each cut gets ops plan. |
| Artifact Structure Standard | Will require Operationalization section when shipped. |
| PROTO-000 | 6th criterion OPERATIONALIZED — this charter wires it. |
| Big Rock 2 | OPERATIONALIZE adds estimation dimension. |
| CLIENT-REGISTRY | V2 propagation tier-gated. |

---

## 10. Guardrails (forward-only, git-history)

Per founder 2026-04-20: no retroactive work. Existing artifacts (TOKENS, SPEED, PROTO-000..018, ESTIMATION-ENGINE pre-cutover) operate under old contract until a semantic change triggers revocation.

---

## 11. Operationalization (charter's own ops plan — D30 dogfood)

### 1. Measurement mechanism
New-artifact compliance % + grandfather-revoked compliance % from §3. Source: .analytics/ops-enforcement.jsonl aggregated weekly.

### 2. Adoption mechanism
Hook deploys to Sutra self first (roadmap #9 self-test on TOKENS). Propagation to DayFlow + Billu via upgrade-clients.sh extension (V2 #11).

### 3. Monitoring / escalation
Sutra-OS reviews compliance % every 6 hours (daily fallback). Warn <95% → investigate. Breach <80% → revert + rework. Block-to-add time p50 >24h → rework heuristics.

### 4. Iteration trigger
FP block rate >10% after 24 hours → adjust semantic-change heuristic. Zero blocks in 72 hours → investigate coverage gap.

### 5. DRI
Sutra-OS (Sankalp through Q2 2026; reassigned at first quarterly review).

### 6. Decommission criteria
(a) Reflexive author habit for 30 consecutive days (compliance >=95%, FP<2%) → hook → SOFT sensor, merge into PROTO-000 6th criterion; or (b) codex/founder review concludes net-negative → revert + retire.

---

## 12. Standing Instructions Abstraction (D30b — 2026-04-27)

### 12.1 Why this section exists

The 6-section ops contract (§2) names the WHAT — "monitor monthly, alert on breach, retire on signal X." It does not run anything. This section names the runtime primitive that turns those contracts into executable orders.

Founder direction (2026-04-27, this charter): *"Some standing instructions which run at some frequency, which get triggered either by time or by some deviation in metrics having happened, or they depend on some other things. How do we think about this holistically and fit this as an abstraction level in Sutra?"*

Founder constraint (2026-04-27, feedback memory `feedback_no_operational_capacity`): no new departments, no human rituals, no manual KPI tracking. The abstraction must self-run.

### 12.2 Definition

A **Standing Instruction (SI)** is a registered, automated action that fires on a defined trigger. SIs replace the need for human ritual review. They are the operational layer that runs the contracts charters declare.

### 12.3 Three trigger types (one runtime)

| Type | Fires when | Production example today | Runtime today |
|---|---|---|---|
| **cadence** | A clock condition is met (every Nh / daily at HH:MM / Nx per day) | `os.sutra.analytics-collect` (8x daily); `com.asawa.observability` (every 3h) | ✅ launchd |
| **threshold** | A metric crosses a defined breach point | None — runtime missing as standalone | ⚠️ implemented as cadence + metric check |
| **dependency** | A watched signal changes (file write, log append, state transition) | `com.asawa.escape-hatch` (WatchPaths on `.claude/active-role`) | ✅ launchd `WatchPaths` |

**Architectural simplification**: one runtime serves all three trigger types. Cadence is native launchd. Threshold collapses to cadence + a metric-breach gate inside the script. Dependency uses launchd `WatchPaths` (file watch, native). No new daemon needed for V1.

### 12.4 Registry

All SIs are registered in `sutra/state/system.yaml#standing_instructions`. **No SI exists outside the registry.** The registry is the single source of truth answering "what is this OS doing for us?"

Charters reference SIs by `id` from their §3 (Monitoring/escalation) section. The registry validates against the existing `sutra/state/validate.mjs` schema (extended to cover the new top-level key).

### 12.5 Engine

Location: `holding/hooks/standing-instructions/`
- `engine.sh` — dispatcher. Reads registry, generates plists, loads them.
- `lib/cadence.sh` — cadence runner helper.
- `lib/threshold.sh` — threshold runner helper (cadence + metric breach check).
- `lib/dependency.sh` — dependency runner helper (uses launchd `WatchPaths`).
- `plists/` — generated launchd plists, one per SI.

Failure handling: every SI invocation appends a row to `.enforcement/standing-instructions.log`. P0-tagged failures (declared per-SI) trigger founder notification via the existing notification channel.

### 12.6 Lifecycle

```
charter declares SI need (§3 Monitoring/escalation)
    │
    ▼
SI registered in sutra/state/system.yaml#standing_instructions
    │
    ▼
engine.sh compiles registry → installs/updates plists in ~/Library/LaunchAgents/
    │
    ▼
plist fires on schedule/watch → script runs → output to declared sink
    │
    ▼
failures land in .enforcement/standing-instructions.log
    │
    ▼
SI retires via §6 of owner charter's ops contract → registry status: retired → engine unloads plist
```

### 12.7 Registry schema (minimal)

```yaml
standing_instructions:
  - id: <slug>                          # unique, kebab-case
    owner_charter: <path>                # source charter (e.g. sutra/os/charters/PRIVACY.md)
    description: <one-line>
    trigger:
      type: cadence | threshold | dependency
      spec:                              # type-specific:
        # cadence: { every: "3h" } OR { calendar: ["09:17", "21:00"] }
        # threshold: { cadence: "5m", metric: <path>, op: ">"|"<", value: <n> }
        # dependency: { watch_paths: [<paths>] }
    command: <bash invocation>           # full command, run from repo root
    output_sink: <path> | 'founder-notify' | 'pulse'
    on_failure: <log path>               # default .enforcement/standing-instructions.log
    severity: P0 | P1 | P2               # P0 = founder-notify on failure
    status: active | paused | retired
    plist: <generated path>              # written by engine, not by hand
    created: <YYYY-MM-DD>
    last_fire: <unix-ts | null>          # written by engine
```

### 12.8 V1 scope (what ships with this section)

- Architecture spec (this section)
- Registry schema added to `sutra/state/system.yaml`
- Engine skeleton in `holding/hooks/standing-instructions/`
- 4 pre-existing plists registered (observability, observability-daily, analytics-collect, escape-hatch)
- 1 new instance live: **ops-compliance-rollup** (cadence, every 6h) — closes §11.3 dormant requirement

### 12.9 V2 (deferred)

- Threshold runtime as event-driven daemon (not cadence-poll). V1 ships SOFT (cadence + metric check). Promote when V1 data shows polling latency matters.
- Dependency runtime via fswatch/inotify (current launchd `WatchPaths` is adequate for file changes; insufficient for log-append signals on a single rotating file).
- Cross-company propagation via charter-aware `upgrade-clients.sh` (same dep as Tokens KR4).
- Plugin promotion (move from `holding/hooks/` to `sutra/marketplace/plugin/runtime/`) when stable on Sutra-self.

### 12.10 Operationalization (this section's own ops plan)

| Section | Spec |
|---|---|
| Measurement | Count of SIs in registry; count of failures in `.enforcement/standing-instructions.log` rolling 7d; per-SI last_fire freshness vs spec |
| Adoption | Each new charter §3 entry must register SI in registry within same commit (review-enforced, not hook-enforced V1) |
| Monitoring | 7d failure count >0 → land in `/asawa` pulse; P0 failure → founder-notify same hour |
| Iteration | If V1 cadence-poll threshold latency >5min consistently → promote threshold to event-driven daemon |
| DRI | CEO of Sutra (charter); engine maintenance shared with Engineering on hook bugs |
| Decommission | Standing Instructions abstraction retires only if (a) Sutra discontinues automation surface, or (b) replaced by a more general workflow primitive |

### 12.11 Follow-up TODOs (parked 2026-04-28; pick up next)

Captured by founder direction 2026-04-28 ("Add these as to-dos to the charter. We'll pick it up next."). Three items, ordered by effort:

| # | Effort | Action | Trigger to unpark | Acceptance |
|---|---|---|---|---|
| **T1** | ~30s | Activate the new live SI: `bash holding/hooks/standing-instructions/engine.sh install ops-compliance-rollup`. Plist already generated; this `launchctl load`s it so it fires every 6h going forward. | Founder explicit "install it" OR resumed work on this charter. | `launchctl list \| grep sutra.si.ops-compliance-rollup` returns the plist; first 6h fire produces a fresh `.analytics/ops-compliance-latest.json`. |
| **T2** | ~5 min | Add the next live SI. Two candidates already named in the charter: (a) **privacy-secrets-p0** (threshold trigger — fires when `.enforcement/proto-004-blocks.jsonl` post-cutover count > 0; severity P0; sink `founder-notify`); or (b) **speed-rca-trigger** (dependency trigger — fires when `holding/LATENCY-LOG.jsonl` reaches 50 task entries; sink `holding/research/<date>-speed-rca.md`). Either one exercises a non-cadence trigger type and proves the abstraction beyond the cadence path. | Founder picks the second SI to instantiate, OR a real KR1/SPEED-W2 signal needs surfacing. | Registry entry added, `engine.sh compile` produces a plist, plist plutil-clean. For threshold variant: runner script reads metric file and exits 0 (no fire) when below breach. |
| **T3** | ~30 days | **L0 plugin promotion**: move engine + lib + runners from `holding/hooks/standing-instructions/` → `sutra/marketplace/plugin/runtime/standing-instructions/` so fleet inherits. Holding L1 copy retained for 30d stability window then retired. Mirrors the cascade-check.sh promotion pattern (which retired its holding copy 30d after L0 ship). | 30d clean operation on Sutra-self with zero engine bugs in `.enforcement/standing-instructions.log`. Earliest unpark: 2026-05-28. | Plugin path live; charter §13 updated; holding/hooks/standing-instructions/ retains a redirect comment; tier-2/3 clients see the engine on next plugin update. |

These three items fully complete the V1 → V2 transition for Standing Instructions. Beyond T3, V2 work begins (event-driven threshold daemon, fswatch dependency runtime, charter-aware `upgrade-clients.sh` extension).

## 13. Related files

- Design doc: holding/research/2026-04-20-operationalization-charter-v2-redesign.md
- Standard: holding/OPERATIONALIZATION-STANDARD.md
- Hook: holding/hooks/operationalization-check.sh
- Test: holding/hooks/tests/test-operationalization-check.sh
- Git wrappers: .git/hooks/pre-commit, .git/hooks/pre-push
- CI: .github/workflows/operationalization-check.yml
- State: sutra/state/system.yaml.operationalization, sutra/state/system.yaml.standing_instructions
- Standing instructions engine: holding/hooks/standing-instructions/engine.sh
- Lifecycle: sutra/os/engines/ESTIMATION-ENGINE.md (OPERATIONALIZE phase)
- PROTO-000 extension: sutra/layer2-operating-system/PROTOCOLS.md (6th criterion)
- Sister charters: sutra/os/charters/TOKENS.md, sutra/os/charters/SPEED.md
- Codex round-1: .enforcement/codex-reviews/gate-log.jsonl session 019daada-ffd0-7602-a12a-99208ff8baa1
- D30b feedback memory: feedback_no_operational_capacity.md (founder constraint)
