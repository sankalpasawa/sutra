<!-- MIRROR (read-only distribution copy). Canonical: sutra/os/decisions/ADR-012-pnc-typed-parser-over-prose.md. -->
# ADR-012 — PNC Predicates: Typed Parser, Not Trusted Prose

## Status
Accepted 2026-05-07 (formalized as part of Native formalization v1.0). Charter contract: see `sutra/os/engines/NATIVE-ENGINE.md` §2.3 (`Workflow.preconditions/postconditions/failure_policy`), §3.2 events 10/11/25; invariants I-5; F-10.

## Context
Workflows declare **PNC** — Preconditions, postconditions, and Charter commitments / on-failure conditions. Two shapes were live during v1.0:

- **English prose fields** ("workflow runs only when the founder has approved the daily pulse") — readable but not machine-checkable; cannot be evaluated at runtime.
- **Typed predicate** (e.g. `match-all`, `match-any`, structured comparisons against execution context) — parsed at primitive-mint, evaluated at runtime.

V2 architecture spec §3 HARD requirement (`holding/research/2026-04-28-v2-architecture-spec.md`) declared prose-only PNC a HARD reject. Gap-audit (D4 §3 F-10) plus 13-case run report (`holding/research/2026-05-04-native-use-case-runs.md` N1) showed prose PNC declared at primitive-mint but never eval-checked at runtime — silent guarantee failure.

The `commitment_broken` event (event 25 in catalog) is a sub-consequence: when `failure_policy='continue'` advances past a step that violated a Charter obligation, the engine needs a typed reference to the obligation id — only possible if PNC is typed.

### Alternatives considered
- English prose PNC fields — rejected per V2 §3 HARD + F-10 violation; not machine-checkable.
- LLM-eval of prose at runtime (host-llm reads the prose + decides) — rejected because non-deterministic + non-replayable + opens injection surface.
- Hybrid (typed core + prose annotation) — accepted as documentation, but only the typed core is load-bearing; prose annotation is `advisory` per ADR-008.

## Decision
Native engine MUST parse `Workflow.preconditions`, `Workflow.postconditions`, `Workflow.failure_policy`, and `step.on_failure` as typed machine-checkable predicates — not free prose.

- Parser surface: `match-all` / `match-any` / cron / typed comparison against execution context (Tenant, Domain, Charter obligation id, prior EngineEvent).
- Evaluated at runtime: `precondition_check` (event 10) and `postcondition_check` (event 11) emit per evaluation.
- `commitment_broken` (event 25) references a Charter obligation id resolvable in the registry (I-16).
- F-10 forbids English-only routing/gating positions at terminal_check (HARD reject at primitive-mint).

## Consequences

| Kind | Effect |
|---|---|
| + | PNC is enforced at runtime, not just declared — closes V2 §3 HARD requirement |
| + | `commitment_broken` carries a typed obligation id — replayable + cross-referenceable |
| + | Injection surface closed — no LLM eval of prose; predicates are static |
| − | Author must learn predicate syntax — prose annotation stays as advisory documentation |
| − | Migration: legacy prose-PNC Workflows must be rewritten or marked `legacy_advisory` |
| 0 | OS-5 `commitment_broken` semantics under `continue` (per-step vs terminal-only) is a follow-up |
