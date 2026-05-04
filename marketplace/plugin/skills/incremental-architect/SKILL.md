---
name: incremental-architect
description: Migration planning skill — authors a MIGRATION-PLAN.md for evolving a live production system toward a new shape with a compatibility period. Output covers pattern selection (strangler fig / branch by abstraction / parallel-run / decompose-then-recompose / hybrid), phased plan with rollback per phase, risk register including hidden-coupling/dual-write/schema-evolution risks, parallel-run observability, decommission gate (named approver + evidence artifact + observation window + final-deletion phase), and engineer-hour / calendar-week / runtime-cost projection. Fires ONLY when the change involves live-state transition, compatibility period, phased cutover, or retirement of an existing production path. Skip for routine library upgrades (use upgrade tooling), feature-flag cleanup (use the flag system's lifecycle), vendor swaps without state migration (use core:architect for the new shape), or product retirement without infrastructure decommission. Skip when the user wants to AUTHOR a NEW architecture from scratch (use core:architect), wants the migration EXECUTED (this skill plans; execution is downstream), or wants a code review of an existing migration plan (use gstack plan-eng-review). The output is a plan document, NOT migration code.
allowed-tools: Read, Write, Bash
---

# Incremental Architect — migration planning

This skill produces a single `MIGRATION-PLAN.md` for evolving an existing production system. It does NOT write migration code, run the migration, or author a net-new architecture (use `core:architect` for the to-state).

## Skill card

- **WHAT**: author a migration plan document — pattern selection, phase plan with rollback per phase, risk register, parallel-run observability, decommission gate (operationally enforced), cost projection.
- **WHY**: most "incremental" migrations are big-bang migrations in disguise; many lack rollback; many never decommission the old path. An explicit migration plan with these forcing functions stops the common failure modes before code is written.
- **EXPECT**: a single `MIGRATION-PLAN.md` covering 9 sections; ~250-450 lines depending on scope.
- **ASKS**: 4-6 high-leverage questions (current architecture, migration goal, downtime tolerance, team size, deadline, regulatory constraints); skip questions whose answers are implied by inputs.

`allowed-tools` rationale: `Read` for inspecting the existing architecture, `Write` for the artifact, `Bash` narrowly for repo inspection.

## When to use

| Trigger | Use this skill? |
|---|---|
| "Plan the migration from monolith to microservices" | Yes |
| "Replace PostgreSQL with DynamoDB while keeping the system live" | Yes |
| "Decommission the deprecated v1 API gradually" | Yes |
| "Strangler fig pattern for our legacy system" | Yes |
| "Move from REST to GraphQL incrementally" | Yes (but compose with `core:architect` first if target architecture isn't defined enough to phase) |
| "Upgrade Rails from 6 to 7" | No — use Rails upgrade tooling; this skill is for live-state transitions |
| "Clean up a stale feature flag" | No — use the flag system's lifecycle |
| "Swap from SendGrid to Postmark for email" | No — vendor swap without state migration; use `core:architect` for the new shape |
| "Design the architecture for a new service" | No — use `core:architect` (W2) |
| "Implement the migration" | No — this skill plans; execution is downstream |
| "Review my migration plan" | No — use gstack `plan-eng-review` |

## Inputs

| Input | Required? | Default if missing |
|---|---|---|
| Current architecture (ARCHITECTURE.md OR codebase reference OR brief description) | Yes | Ask |
| Migration goal (what we're moving toward and why) | Yes | Ask |
| Downtime tolerance (zero / window / best-effort) | Strongly preferred | Ask 1 question |
| Team size | Strongly preferred | Default 3 if user defers |
| Deadline | Optional | Note as "no hard deadline" if absent |
| Regulatory / compliance constraints | Optional | Note as "no constraints declared" if absent |
| To-state architecture defined? | Decision branch | If NO: route to `core:architect` first; if YES: proceed |

## Output: `MIGRATION-PLAN.md` template

Always emit these 9 sections in this order. Never omit; placeholder line if section truly does not apply.

```
1. Migration goal + constraints (1-2 paragraphs: from-state, to-state, why now)
2. Pattern selection — strangler fig | branch by abstraction | parallel run | decompose-then-recompose | hybrid; with rationale
3. Phase plan — N phases (typically 3-7), each with: scope, build-layer (L0/L1/L2 per Sutra D38), entry criteria, exit criteria, rollback plan
4. Risk register — top 5-10 risks INCLUDING hidden-coupling, dual-write consistency, schema evolution; mitigation per phase
5. Parallel-run period — duration target + observability requirements (specific metrics that confirm parity)
6. Decommission gate — operational enforcement: named approver + evidence artifact + observation window default + a final "delete old path" phase blocked on gate completion
7. Cost projection — engineer-hours per phase, calendar weeks total, runtime cost delta during parallel-run (acknowledge dual-write spike)
8. Communication plan — who needs to know what at each phase
9. Open questions + noted limitations
```

Section 9 is ALWAYS present. ASCII boxes only.

## Pre-planning checklist (before writing the plan)

Per Fowler / Newman / Adzic on real-world migration traps, the planner MUST first surface:

| # | Check | Why |
|---|---|---|
| 1 | Dependency / coupling map of the old path | Reveals seams; reveals hidden shared-state that breaks decomposition |
| 2 | Data ownership boundaries | Prevents distributed-monolith outcome (multiple services writing to one shared DB) |
| 3 | Dual-write consistency strategy (if parallel-run involves writing to both old and new stores) | Without explicit strategy, dual-write becomes silent corruption |
| 4 | Schema evolution path (additive vs breaking; backfill strategy) | Schema migration is the single most common cause of "incremental" migrations turning into outages |
| 5 | Thinnest possible slice that proves end-to-end (Adzic) | Phasing without a thin-slice proof of concept is structural decomposition without delivery validation |

If any of items 1-3 surface a hard blocker (e.g., shared DB with no clear ownership), the plan MUST flag it as a P0 risk in section 4 + propose a pre-migration step to resolve it.

## Pattern selection heuristics

| Pattern | Best for | Avoid when |
|---|---|---|
| **Strangler fig** | Replacing a legacy system component-by-component while it stays live | The legacy system has no clean component boundaries (monolithic state) |
| **Branch by abstraction** | Replacing an internal dependency where consumer code can't tolerate interface churn | Replacing user-facing or external-API surface (use parallel-run instead) |
| **Parallel run** | Verifying a new implementation produces identical outputs to the old one before cutover | Outputs are inherently non-deterministic |
| **Decompose-then-recompose** | Breaking a monolith into modules first (within), then extracting | Time pressure (slowest pattern; high upfront cost) |
| **Hybrid** | Real migrations usually combine 2-3 of the above | Single-pattern descriptions are simpler — pick hybrid only when one pattern truly doesn't cover scope |

Anti-pattern: declaring "incremental" but planning a hard cutover phase with no rollback. If a phase's rollback is "fix forward," it's a big-bang migration in disguise.

## Phase plan template

```
### Phase N: <name>
- Scope: <what changes; what doesn't>
- Build-Layer: L0 | L1 | L2 (per Sutra D38)
- Entry criteria
- Exit criteria
- Duration target
- Rollback plan: <specific steps; not "fix forward">
- Observability: <metrics that confirm phase health>
```

Smallest reversible step first. The first phase typically sets up infrastructure (routing layer, abstraction, parallel-run plumbing) — not data migration.

## Risk register template

| # | Risk | Affects phase | Likelihood | Impact | Mitigation |
|---|---|---|---:|---:|---|

≥5 risks. MUST include at least one of: hidden coupling discovered during seam-finding, dual-write consistency failure, schema migration breaking, distributed-monolith trap (services sharing a DB).

## Decommission gate — operational enforcement

The plan MUST specify all four:

```
DECOMMISSION GATE
  Named approver: <role + person>
  Evidence artifact: <e.g., parity audit report stored at /artifacts/...>
  Observation window: <default 4 weeks; longer for regulated systems>
  Final-deletion phase: <Phase N+1 explicitly blocked until gate passes>
```

A plan with prose-only criteria but no named approver, no evidence artifact, and no terminal-phase block is decommission theater. The old path will live forever.

## Process (internal — not user-visible)

Author the plan in this order: pre-planning checklist (5 items above) → classify migration domain → pick pattern → phase smallest-reversible-step-first → author rollback per phase → write decommission gate operationally → tally cost projection. User-visible MIGRATION-PLAN.md uses domain language; pattern brand names appear because they're load-bearing pedagogy.

## Composition with other Sutra + ecosystem skills

| When you need... | Use... |
|---|---|
| Author the migration plan | This skill (`core:incremental-architect`) |
| Author the to-state architecture (if not yet defined) | `core:architect` (W2) FIRST, then return here |
| Test strategy for the migrated system | `core:test-strategy` (W1) |
| I/O determinism tests for parity verification during parallel-run | `core:deterministic-testing` (W3) |
| Review the migration plan | gstack `plan-eng-review` |
| Execute the migration phase by phase | gstack `gsd-execute-phase` |
| Codex second-opinion | `core:codex-sutra` consult mode |

## Failure modes to watch (this skill itself)

- Big-bang disguised as incremental — at least one phase that has no rollback is the smell
- Missing decommission gate (named approver + evidence + window + final-deletion phase) — leads to permanent parallel-run
- Risk register missing hidden-coupling / dual-write / schema-evolution entries
- Distributed-monolith trap — services extracted without data ownership boundary, all sharing the same DB
- Parallel-run period without observability — "we'll watch logs" is not parity verification
- Cost projection vague ("a few weeks") — must be phase-by-phase
- Communication plan absent for vendor / compliance / customer-facing migrations

## Eval pack

Three evals shipped in `evals/` next to this SKILL.md.

## Self-score (optional telemetry, never a side effect)

If `holding/research/skill-adoption-log.jsonl` is writable AND telemetry not opted out — one row may be appended:

```json
{"date": "YYYY-MM-DD", "skill": "core:incremental-architect", "career_track": 5, "mode": "Decisional+Generative", "subject": "<migration goal>", "pattern": "<strangler|branch|parallel|decompose|hybrid>", "phase_count": N, "risk_count": N, "decommission_gate_operational": true|false}
```

If sink unwritable or opted out — silently skip.

## Build-Layer

L0 (PLUGIN-RUNTIME, fleet). Per Sutra D38 — this skill ships in the marketplace plugin and reaches all clients via plugin update.
