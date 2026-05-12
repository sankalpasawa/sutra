# ADR-019 — Design ↔ Product ↔ Tech Bridge (cross-layer traceability)

## Status

PROPOSED 2026-05-13 (R8 tech-parts execute phase). Pending R9 codex + deepseek review.

Companion to PRD §1.5 "Tech-parts cross-cut overlay" (the operator-facing summary) and [ADR-018 agentic-systems-pattern](ADR-018-agentic-systems-pattern.md) (the agentic doctrine).

## Context

Native has three layers of artifacts:

| Layer | Where | Audience |
|---|---|---|
| **Design** (doctrine + pillars + open questions) | canon `pillars/`, `open-questions/`, `doc-layers/L1-philosophy.md` | Founder / design / architecture reviewers |
| **Product** (operator-facing capability surfaces) | PRD body `holding/website/native/product-prd-native-v1.html` | Operator / product / GTM |
| **Tech** (primitives + events + surfaces + hardstops + blocks + ADRs) | canon `primitives/`, `events/`, `surfaces/`, `hardstops/`, `blocks/`, `decisions/` | Engineering / Sutra team |

Each layer evolves at its own cadence. **Drift between layers** is the principal risk:
- A pillar (Design) gets refined but PRD capability surface (Product) isn't updated → operator-promised behavior mismatches the design intent
- A primitive (Tech) gets a new field but no PRD capability bullet acknowledges it → operators don't know they can use it
- A capability bullet in PRD body (Product) drifts from canon spec (Tech) → engineering builds to spec, operator reads PRD, contracts diverge

ADR-019 is the **traceability bridge** — a single living matrix that maps every Design decision → its Product manifestation → its Tech implementation files. Engineers consult it during change-impact analysis (per PRD §C.6 FQ3). Architects consult it during cross-layer coherence reviews. Operators do NOT read it (not their audience per A.2.2 zero-terminal).

## Decision

Adopt this living bridge matrix as the cross-layer traceability artifact. Rows = the 4 tech-parts categories (per PRD §1.5). Columns = Design layer / Product layer / Tech layer. Each cell points to canonical files.

### Bridge matrix

| Tech-parts category | Design layer (canon pillars/) | Product layer (PRD body) | Tech layer (canon primitives/events/etc.) |
|---|---|---|---|
| **Domain Models** | [P5 MECE domains](../native/pillars/P5-mece-domains.md) — "mutually exclusive AND collectively exhaustive per user"; [P10 typed-config every layer](../native/pillars/P10-typed-config-every-layer.md) — "Domain typed-config: principles + guidelines + decisions" | PRD §1.5 row 1 — "operator-visible accountability model"; per-product capability bullets in §2.B per pillar (CoS) | [primitives/domain.md](../native/primitives/domain.md) + [primitives/charter.md](../native/primitives/charter.md) + [primitives/workflow.md](../native/primitives/workflow.md) + [primitives/decision-provenance.md](../native/primitives/decision-provenance.md) + [blocks/B10-typed-config.md](../native/blocks/B10-typed-config.md) |
| **Hooks** | [P2 pre/post LLM validation](../native/pillars/P2-pre-post-llm-validation.md) — "every LLM call has pre-declared expected output + post-call check (testing-framework analog)" | PRD §1.5 row 2 — "safeguard + escalation behavior"; surfaces in §2.B B3 + §4.5 Test-before-conclude | [hardstops/HS-1..HS-8](../native/hardstops/) (8 hardstop files) + [events/](../native/events/) catalog (26 events) + [ADR-011 on-failure-policy-five-set](ADR-011-on-failure-policy-five-set.md) + [ADR-012 pnc-typed-parser-over-prose](ADR-012-pnc-typed-parser-over-prose.md) |
| **Governance Machinery** | [P13 multi-human-org-Native](../native/pillars/P13-multi-human-org-native.md) — "each human has own Native; org-shared artifacts addressable" (tenant-isolation governance); [P14 outcomes drive design](../native/pillars/P14-outcomes-drive-design.md) — "governance + security + agentic infra serve outcomes" (governance is infra in service of outcomes, not standalone product surface) | PRD §1.5 row 3 — "authority + audit + intervention contract"; §D.6 Authority Model overlay; §2.B B5.c audit | [primitives/approval.md](../native/primitives/approval.md) + [primitives/tenant.md](../native/primitives/tenant.md) + [ADR-006 tenant-isolation](ADR-006-tenant-isolation-domain-field.md) + [ADR-007 decision-provenance](ADR-007-decision-provenance-schema.md) + [ADR-009 approval-gate](ADR-009-approval-gate-primitive.md) + [ADR-013 telemetry-sink](ADR-013-telemetry-sink-fsync-jsonl.md) |
| **Agentic-Systems Pattern** | [P4 product-pov-before-tech-pov](../native/pillars/P4-product-pov-before-tech-pov.md); [P12 deterministic-surface-stochastic-core](../native/pillars/P12-deterministic-surface-stochastic-core.md) | PRD §1.5 row 4 — "operator-in-loop on consequential decisions"; §2.B B3a THINK / B3b DO / B3c PRESENT | [ADR-018 agentic-systems-pattern](ADR-018-agentic-systems-pattern.md) + [surfaces/route.md](../native/surfaces/route.md) + [surfaces/run.md](../native/surfaces/run.md) + [surfaces/gate.md](../native/surfaces/gate.md) |

### How to use this bridge

**Reading a Layer-B product PRD section** (e.g., CoS pillars): bridge tells engineering where the canon spec lives for any operator-promised capability. Find the row matching the capability, follow the Tech column.

**Implementing a canon spec change**: bridge tells which design pillar(s) the change must remain consistent with (Design column) + which operator-facing capability surface needs updating (Product column).

**Change-impact analysis** (PRD §C.6 FQ3): when changing a canon primitive, scan the Tech column for matches → resulting Design pillar(s) constrain valid changes → resulting Product capability(ies) may need PRD body updates. This is the cascade-impact analysis substrate (until the full cascade-impact engine ships per FQ3).

**Coherence reviews**: scan every row to verify all 3 layers tell the same story. A row where Design and Product don't agree, or Product and Tech don't agree, signals drift requiring resolution.

## Consequences

### Required maintenance discipline

- Every NEW Design pillar gets a bridge row appended (or extends existing row's Design column).
- Every NEW Product capability gets cross-referenced in the bridge.
- Every NEW Tech file gets a Tech-column citation.
- ADR-019 update is part of the canon-write protocol — when authoring a new ADR / primitive / block / event, check whether bridge needs updating.

### What this is NOT

- Not a gate (no PR requires reading or updating it)
- Not a contract (the contracts live in each layer's canon)
- Not exhaustive (only the 4 tech-parts categories from §1.5; other concerns like Authority / CX Bar live in §1.3 cross-cutting concerns + §D.6/D.7 overlays)
- Not auto-generated (manually maintained; coherence audit run quarterly per future cadence)

### Anti-patterns guarded

1. **Bridge becomes documentation primary source** — the bridge POINTS; the canon HOLDS. If someone reads only the bridge and stops, they're missing actual spec content. Bridge is a router, not a destination.
2. **Bridge becomes a gate** — if a PR review requires "is bridge updated?", maintenance cost dominates value. Maintain in batches (e.g., quarterly canon-coherence sweep) instead.
3. **Operator-facing leakage** — the bridge is engineer-facing; PRD body never embeds the matrix. PRD §1.5 has the operator-visible summary table; this ADR has the engineering-facing version.

## Open questions

These compose with PRD §C.6 forward open questions:

- **OQ-019-1**: Maintenance cadence — quarterly sweep vs per-PR check vs auto-generated from canon header metadata. Per-PR is heavy; quarterly is lossy; auto-generation requires header schema discipline first.
- **OQ-019-2**: Should the bridge expand to cover non-tech-parts cross-cuts (Authority Model, CX Bar, Operator-First Lens, Charter Model, Method Selection)? Risk: turns into a 50-row mega-table; loses focused value. Defer until evidence demands.
- **OQ-019-3**: Tooling — should there be a `scripts/bridge-coherence-audit.sh` that scans all 3 layers for drift? Plausible; queued.

## References

- PRD §1.5 "Tech-parts cross-cut overlay" — operator-facing summary table
- [ADR-018 agentic-systems-pattern](ADR-018-agentic-systems-pattern.md) — companion doctrine for row 4 of the bridge
- All canon pillar files referenced in the Design column
- All canon primitive / hardstop / event / surface files referenced in the Tech column
- R8 codex consult 2026-05-13 — recommended "two-layer bridge: compact reader-facing in PRD + real bridge spec in canon"
- R8 deepseek consult 2026-05-13 — recommended bridge ADR with 3-sentence pointer from PRD

## Authoring

claude-drafted via R8 tech-parts execute phase under directive 1778610507 follow-up. R9 codex + deepseek review pending. Maintained-by: any contributor when adding canon files; reviewed during canon-coherence sweeps.
