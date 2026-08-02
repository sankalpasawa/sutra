# ADR-008 — Authoritative-vs-Advisory State on Every DataRef

## Status
Accepted 2026-05-07 (formalized as part of Native formalization v1.0). Charter contract: see `sutra/os/engines/NATIVE-ENGINE.md` §2.4 (`WorkflowStep.inputs`), §3.5; ADR-007 schema reference.

## Context
Sutra has two parallel state surfaces: **markdown** (charters, founder-directions, plans — human-authored, append-prone) and **code** (JSON registry, hook output, execution rows — machine-emitted, deterministic). Conflicts occur — e.g. a charter declares an obligation but the code registry has no matching ID; or the founder updates `FOUNDER-DIRECTIONS.md` but the executable policy still references the prior version.

Two ad-hoc precedence rules existed:
1. "Code always wins" — naive but breaks when markdown captures a NEW direction not yet wired.
2. "PROTO-021 markdown-source-of-truth" — privileges human-authored charters but breaks when the code is the live runtime contract.

Gap-audit `PS-9 / Q7 UNMET` (`holding/research/2026-04-29-native-gap-audit.md`) and V2 architecture spec §3 HARD requirement (`holding/research/2026-04-28-v2-architecture-spec.md`) both flagged: implicit precedence is fragile; conflicts must be resolvable at lookup time, not by convention.

### Alternatives considered
- Implicit "code wins" everywhere — rejected because newly-captured directions (markdown) have no representation in code yet but must be load-bearing.
- Implicit "markdown wins" everywhere — rejected because runtime decisions (Execution rows, hook outputs) are the live contract and must override stale markdown.
- Single-source-of-truth migration (collapse one into the other) — rejected because both surfaces serve different audiences (founder reads markdown; daemon reads code).

## Decision
Native engine MUST require every `DataRef` to carry an explicit `authoritative_status ∈ {authoritative, advisory}` field.

- Readers honor `authoritative` over `advisory` at lookup time (declarative precedence; no convention).
- Workflow `inputs[]` and Workflow `outputs[]` (DataRef arrays) tag each entry — enforced at primitive-mint via ajv schema validation.
- DecisionProvenance.data_refs[] carries the same field — every audit row records which version of which surface was load-bearing.
- Drift detection: weekly cadence (see `sutra/os/engines/NATIVE-ENGINE.md` §6.4) reports authoritative-vs-advisory diff for each known artifact pair.

## Consequences

| Kind | Effect |
|---|---|
| + | Conflicts resolved at lookup, not by convention — the field IS the rule |
| + | Audit replay knows which surface drove each decision (markdown vs code per row) |
| + | Drift becomes a measurable signal (weekly report) instead of a "we forgot to update X" surprise |
| − | Every DataRef author must set the field — no implicit default; ajv rejects on omission |
| − | Migration cost: existing DataRefs need backfill or marked legacy |
| 0 | First non-additive use case (e.g. authoritative downgrade on conflict) may need policy upgrade |
