---
name: architect
description: Designs and writes a structured ARCHITECTURE.md for a system that does not yet have one, OR for a system whose architecture is implicit and scattered across the codebase. Produces C4 model (System Context + Container, optional Component for high-leverage parts only), ADRs (Status / Context / Decision / Consequences), STRIDE threat model with top risks, scaling axes (load / data / team / geography), and a Sutra D38 Build-Layer table (which components ship in plugin L0, which stage as L1, which are instance-only L2). Fires when the user asks to design an architecture, write an architecture document, document the system, produce ADRs, perform a threat model, or sketch a system before implementation. Skip when the user wants the architecture REVIEWED (use gstack plan-eng-review), MIGRATED to a new shape (use core:incremental-architect), or wants implementation code (this skill produces a document, not code).
allowed-tools: Read, Write, Bash
---

# Architect — write the architecture document

This skill produces a single `ARCHITECTURE.md` for one system. It does NOT write implementation code, run code, or migrate an existing architecture (composition pointers near the end).

## Skill card

- **WHAT**: design and author the architecture document for one system — C4 (Context + Container, optional Component), ADRs, STRIDE threat model, scaling axes, Sutra D38 Build-Layer table.
- **WHY**: implicit / scattered architecture creates re-litigation cost, onboarding friction, and security blind spots; an explicit, recorded architecture turns "what is this thing?" from a 30-min archaeology dig into a 5-min read.
- **EXPECT**: a single `ARCHITECTURE.md` file in the working directory covering 8 sections; ~300-600 lines depending on system scope.
- **ASKS**: 3-5 high-leverage questions (purpose, scale, constraints, current pain, success criteria); skip questions whose answers are implied by inputs.

`allowed-tools` rationale: `Read` for inspecting existing code to ground the C4 in observed structure (no fabrication), `Write` for the artifact, `Bash` narrowly for repo inspection (`ls`, `find`, `tree`, dependency manifests).

## When to use

| Trigger | Use this skill? |
|---|---|
| "Design the architecture for the new payments service" | Yes |
| "Write an architecture doc for this codebase" | Yes |
| "I need ADRs for the database choice" | Yes |
| "Threat-model this system" | Yes (this skill includes STRIDE) |
| "Review my architecture proposal" | No — use gstack `plan-eng-review` |
| "Migrate from monolith to microservices" | No — use `core:incremental-architect` (W4) |
| "Implement the user service" | No — this skill is design only; use gstack `gsd-execute-phase` for implementation |
| "Add a test strategy" | No — use `core:test-strategy` |

## Inputs

| Input | Required? | Default if missing |
|---|---|---|
| System name + one-paragraph purpose | Yes | Ask |
| Scale targets (users / requests / data volume / latency) | Strongly preferred | Ask 1 question if not provided |
| Constraints (regulatory, language / runtime, team size, deadline) | Optional | Note as "unspecified" in §6 of output |
| Existing code locations (if architecting an existing implicit system) | Optional | If absent, treat as greenfield |
| Risk profile (consumer / B2B / safety-critical / regulated) | Strongly preferred | Default `B2B` if user defers |

## Output: `ARCHITECTURE.md` template

Always emit these 9 sections in this order. Never omit; use a placeholder line if a section does not apply.

```
1. Purpose + scale + constraints (1-2 paragraphs)
2. C4 Level 1 — System Context (text + ASCII boxes; users / external systems / our system)
3. C4 Level 2 — Container (text + ASCII boxes; runtimes, data stores, queues, our containers)
4. C4 Level 3 — Component (only for the 1-3 highest-leverage containers; placeholder line for the rest)
5. ADRs — one per major decision (Status / Context / Decision / Consequences). Number however many are warranted; do not pad to a target count.
6. STRIDE threat model (Spoofing / Tampering / Repudiation / Info disclosure / DoS / Elevation) with top 5-10 risks
7. Scaling axes — load, data, team, geography (each addressed; "n/a today, watch for X" is a valid entry)
8. Sutra D38 Build-Layer table — for each component: L0 (plugin / fleet) | L1 (staging with promotion deadline) | L2 (instance-only with reason)
9. Open questions + noted limitations — what this document leaves unresolved, what assumptions need validation, and what the architect could not see from the inputs
```

Section 9 is ALWAYS present — even on greenfield blank-slate cases, "no open questions; all inputs were sufficient" is itself a valid (and rare) entry. The point is to never claim more visibility than the inputs warrant. ASCII boxes only (no unicode box-drawing). Tables for any decision matrix with ≥3 rows.

## C4 depth choice

Always emit L1 + L2. L3 only when:

| Container | Emit L3? |
|---|---|
| Has non-obvious internal complexity (e.g., custom routing, plugin system, state machine) | Yes |
| Holds the system's distinctive IP | Yes |
| Standard CRUD / glue / well-known framework usage | No (placeholder line) |
| External system you don't own | Never |

Rule of thumb: 1-3 L3 sections per architecture document. More than 3 is usually over-decomposition.

## ADR template

Each ADR follows this shape:

```
### ADR-NNN: <decision title>
- Status: PROPOSED | ACCEPTED | DEPRECATED | SUPERSEDED-BY-ADR-XXX
- Context: <why this decision is needed; constraints; alternatives considered>
- Decision: <what we chose; one sentence>
- Consequences: <what becomes easier; what becomes harder; what's locked in>
```

Number ADRs in the order they're decided, not in order of importance. ADR-001 is whichever came first chronologically.

Anti-pattern: ADR theater. Every ADR must have a real Consequences section — at least one item under "harder" or "locked in." If an ADR's Consequences section reads "all upside, no downside," the decision wasn't a real choice.

## STRIDE threat model

Quick reference for the threat-model section:

| Letter | Threat | Common mitigations |
|---|---|---|
| **S**poofing | Identity forgery | Authn (OAuth/SAML/mTLS), API keys with rotation |
| **T**ampering | Data modification in flight or at rest | TLS, signed payloads, integrity checks |
| **R**epudiation | "I didn't do that" | Audit logs, append-only ledgers, signed actions |
| **I**nfo disclosure | Confidentiality breach | Encryption at rest + in flight, RBAC, least privilege |
| **D**oS | Availability attack | Rate limiting, circuit breakers, autoscaling, degraded modes |
| **E**levation | Privilege escalation | Least privilege, separation of duties, sandbox / capability model |

Output should list top 5-10 risks specific to THIS system (not generic STRIDE). Each risk: which letter, how it'd manifest here, the mitigation declared in the architecture.

## Sutra D38 Build-Layer table (the distinctive value-add)

This is what makes Sutra's architect skill different from a generic C4 generator. For every component identified in C4 L2, declare its build-layer:

| Layer | When to use | Example |
|---|---|---|
| **L0 — Plugin / fleet** | Generic, ships to all clients (T2 + T3 + T4 fleet) | Authentication library, common UI primitives, governance hooks |
| **L1 — Staging (with promotion deadline)** | Built for one project but expected to generalize | New analytics pipeline shipped first to one client, promote to L0 by date X |
| **L2 — Instance-only (with reason)** | Genuinely client-specific, will not generalize | Custom Salesforce integration unique to one client's CRM |

Every L1 entry MUST declare PROMOTE_TO + PROMOTE_BY + OWNER + ACCEPTANCE. Every L2 entry MUST declare WHY_NOT_L0_KIND + WHY_NOT_L0_REASON. If the architecture declares ALL components L0, the document MUST include a one-line justification ("everything generalizes because X") — silent all-L0 risks build-layer cosplay.

### D38 enforcement-path mapping (existing-codebase mode)

When architecting an existing codebase, also map components to the D38 enforcement categories that `holding/hooks/build-layer-check.sh` recognizes. This is what the runtime hook checks at edit time:

| Enforcement category | Path patterns | Build-layer constraint |
|---|---|---|
| **D38 PLUGIN-RUNTIME** | `sutra/marketplace/plugin/{hooks,scripts,skills,commands,bin}/**` | LAYER must be L0 (HARD; hook exits 2 on violation) |
| **D38 SHARED-RUNTIME** | `sutra/hooks/**` | LAYER must be L0 (HARD) |
| **D38 HOLDING-IMPL** | `holding/{hooks,scripts,skills,commands,bin}/**` | Marker required; L0 forbidden (lying); L1 needs PROMOTE_TO + PROMOTE_BY + OWNER + ACCEPTANCE non-NONE; L2 needs WHY_NOT_L0_KIND=instance-only + non-empty WHY_NOT_L0_REASON |
| **LEGACY-HARD** | `holding/departments/**`, `holding/evolution/**`, `holding/FOUNDER-DIRECTIONS.md`, `sutra/os/charters/**` | Marker present (any content) = pass |
| **SOFT** | Anywhere else not whitelisted | Advisory only |

Greenfield architectures (no existing codebase) skip the enforcement-path mapping and just declare L0/L1/L2 per component. Existing-codebase architectures MUST include the enforcement-path mapping for at least the components that already live in `sutra/` or `holding/` paths.

## Scaling axes

For each axis, state the current target and the watch threshold:

| Axis | Format |
|---|---|
| Load (req/s, concurrent users) | "Today: X. Watch: re-architect at 10X." |
| Data (rows, bytes, growth rate) | "Today: X. Watch: shard at 5X." |
| Team (engineers touching this) | "Today: 2. Watch: split when 5+ engineers contend on one service." |
| Geography (regions, latency budgets) | "Today: us-east only. Watch: multi-region if a customer signs from EU." |

"n/a today, watch for X" is a valid entry. The point is to record the trigger condition.

## Process (internal — not user-visible)

Author in this order: gather inputs → draft Section 1 → sketch C4 L1+L2 → identify ≥1 ADR-worthy decision → fill ADRs → walk STRIDE → declare scaling axes → assign build-layers → self-check (every C4 container has a deployment story; every ADR has consequences; threat model has system-specific entries; build-layer table covers every L2 container).

Methodology brand names (e.g., "C4 model" by Simon Brown, "ADR" by Michael Nygard, "STRIDE" by Microsoft) appear in the user-facing output where they're load-bearing pedagogy. Internal reasoning patterns (Polya, design-thinking) stay internal.

## Composition with other Sutra + ecosystem skills

| When you need... | Use... |
|---|---|
| Author the architecture | This skill (`core:architect`) |
| Review an existing architecture proposal | gstack `plan-eng-review` |
| Migrate / evolve an existing architecture | `core:incremental-architect` (W4) |
| Test strategy that respects this architecture | `core:test-strategy` |
| Implementation plan derived from this architecture | gstack `gsd-plan-phase` |
| Code generation for the implementation | gstack `gsd-execute-phase` |
| Codex second-opinion on the architecture | `core:codex-sutra` consult mode |

## Failure modes to watch (this skill itself)

- Plausible-but-generic architecture (every system gets the same answer) — ground every ADR in this system's specific constraints
- ADR theater (decisions without real Consequences) — if all consequences are upside, the decision wasn't a choice
- Diagram divergence (C4 levels disagree with each other) — C4 L2 must show every container that L1 mentions; L3 must drill into a container shown in L2
- Fabricated files (when grounding in existing code) — if the user provided a code location, every C4 reference must trace to a real path; never invent files
- Build-layer cosplay (everything declared L0 because it's "the default") — at least one component should typically need L1 or L2 with real reasons; if the whole system is L0, double-check it really generalizes

## Eval pack

Three evals shipped in `evals/` next to this SKILL.md. Each is a fixture pair (input prompt + expected structural assertions on the output). See `evals/README.md` for runner.

## Self-score (optional telemetry, never a side effect)

The Sutra validation framework can be applied to this skill's outputs as telemetry — but **the append is OPTIONAL and conditional on a writable telemetry sink**. If `holding/research/skill-adoption-log.jsonl` is writable AND the user has not opted out (`SUTRA_TELEMETRY=0` or `~/.sutra-telemetry-disabled`), one row may be appended:

```json
{"date": "YYYY-MM-DD", "skill": "core:architect", "career_track": 5, "mode": "Generative", "subject": "<system name>", "sections_emitted": 9, "adr_count": N, "l3_containers": N, "build_layer_l1_l2_count": N}
```

If the sink is unwritable, in a constrained environment (T4 fleet machine without `holding/research/` path), or telemetry is opted out — **silently skip the append**. Never let telemetry side effects fail the user's primary task. The architecture document is the deliverable; the JSONL row is metrics garnish.

## Build-Layer

L0 (PLUGIN-RUNTIME, fleet). Per Sutra D38 — this skill ships in the marketplace plugin and reaches all clients via plugin update.
