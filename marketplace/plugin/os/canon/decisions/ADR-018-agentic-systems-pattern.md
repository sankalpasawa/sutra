<!-- MIRROR (read-only distribution copy). Canonical: sutra/os/decisions/ADR-018-agentic-systems-pattern.md. -->
# ADR-018 — Agentic-Systems Pattern (operator-in-loop + deterministic guardrails)

## Status

PROPOSED 2026-05-13 (R8 tech-parts execute phase). Pending R9 codex + deepseek review. Anchored by canon pillars [P4 product-pov-before-tech-pov](../native/pillars/P4-product-pov-before-tech-pov.md) + [P12 deterministic-surface-stochastic-core](../native/pillars/P12-deterministic-surface-stochastic-core.md).

Surface in PRD body: `holding/website/native/product-prd-native-v1.html` §1.5 row "Agentic-Systems Pattern".

## Context

Native is an agentic platform. CoS (and future Layer-B products: Senior Expert, Project Manager) execute multi-step workflows autonomously — but the operator is the principal of every Charter. The product POV must dominate the engine POV (P4); the operator-facing surface must be deterministic even when the internal reasoning is stochastic (P12).

Two failure modes the agentic pattern must prevent:

1. **Autonomous on consequential decisions** — system takes an irreversible / costly / cross-tenant / external-effect action without operator gate. Breaks Authority Model (D.6).
2. **Operator-in-loop on routine work** — system over-asks; operator drowns in approval requests for low-stakes auto-executable paths. Breaks CX Bar (D.7) and operator-first lens (D.8).

The pattern resolves the tradeoff: deterministic gating at consequential decision points, autonomy on known paths.

## Decision

Adopt the **operator-in-loop + deterministic-guardrails** agentic pattern with three contracts:

### Contract 1 — Autonomy classification

Every action point in Native is classified at design time as one of three classes:

| Class | Trigger | Default behavior |
|---|---|---|
| **AUTO** | Path is known + within Charter scope + reversible + below $-threshold + within-tenant | Execute without asking; audit-log only |
| **GATE** | Path is consequential per Authority Model (D.6) 6-dimension check | Stop + surface decision to operator + wait for ratification |
| **ESCALATE** | Path is novel / high-stakes / cross-tenant / failure-recovery / above $-threshold | Stop + surface decision + provide 3-angle THINK output (per B3a) + require explicit operator approval |

Classification is per-action-type, not per-instance. Charter-set policies can shift specific actions between classes (e.g., operator pre-authorizes "send to chair" as AUTO after 30d trust window).

### Contract 2 — Deterministic surface invariant (P12 anchor)

Operator-facing output of any agentic step must be deterministic-shape:
- Same operator input + same Charter context + same prior B5 state → same output schema (not same content, same shape)
- Stochastic LLM reasoning sits INSIDE the deterministic envelope
- Pre-Node Check (PNC) validates input schema before LLM call (typed parser, ADR-012)
- Post-Node Check validates LLM output schema before delivery (rejected back to retry if non-conforming)

Failures of this invariant fire [HS-1 reflexive-check](../native/hardstops/HS-1-reflexive-check.md).

### Contract 3 — Cascade depth budget

Cascading recursion (HOW Engine §3.1 Cascading dimension) is bounded:
- Per-Charter complexity budget (operator-set; default 3 levels for T0-T2, 5 for T3)
- Each cascade level consumes budget
- Budget-exhaustion triggers ESCALATE (operator must extend budget or accept incomplete output)
- Audit row captures cascade depth + budget remaining

This prevents agentic infinite-loops where the system spawns sub-agents indefinitely.

## Consequences

### Required canon work

- **No new code** — pattern is implemented through existing primitives (Authority Gate / Charter / DecisionProvenance / B3a/b/c routing).
- ADR-018 codifies what was implicit; future block specs (B*.md) cite this ADR for their gate/auto classification.

### What operators see (PRD body §1.5)

- AUTO actions: no interruption; visible in B5.c audit replay.
- GATE actions: surfaced as decision moment with 1-2 sentence framing; operator picks among proposed paths.
- ESCALATE actions: surfaced with B3a THINK output (3-angle brainstorm); operator confirms direction; system then executes auto.

### What this is NOT

- Not a new agent-loop architecture — Native primitives already implement the loop.
- Not a permission model — Authority Model (D.6) covers that.
- Not a planning engine — HOW Methodology (§3) covers that.
- This ADR is the doctrine that says: **here's how autonomous decisions get routed in agentic Native.**

### Falsification tests

Inherited from anchor pillars (per P4 + P12 falsification suites in canon):

| # | Falsifier | Anchor |
|---|---|---|
| 1 | Operator must approve every consequential action by Authority Model definition | P4 |
| 2 | Same input + same context → same output schema, always | P12 |
| 3 | Cascade depth never exceeds Charter budget | this ADR (Contract 3) |
| 4 | AUTO actions produce DecisionProvenance rows; GATE actions produce DecisionProvenance + Approval rows | ADR-007 + ADR-009 |
| 5 | ESCALATE actions surface B3a THINK output before requesting approval | this ADR (Contract 1) |

## Open questions

These join PRD §C.6 (forward open questions):

- **OQ-018-1**: How are AUTO ↔ GATE ↔ ESCALATE classifications learned vs hardcoded? Auto-learning from operator overrides risks drift; hardcoded risks operator friction. Likely answer: hardcoded default + operator-overridable per-action with audit.
- **OQ-018-2**: When does AUTO promotion from GATE happen (operator pre-authorizes after seeing N successful gated executions)? What N? What signal?
- **OQ-018-3**: How does the cascade-depth budget compose across sub-Charters in T3 (e.g., a T3 Charter spawns child T3)? Sum budgets, or each fresh?

These will be resolved in subsequent ADRs as patterns mature in v1 dogfooding.

## References

- [P4 product-pov-before-tech-pov](../native/pillars/P4-product-pov-before-tech-pov.md) — operator product POV dominates engine POV
- [P12 deterministic-surface-stochastic-core](../native/pillars/P12-deterministic-surface-stochastic-core.md) — operator sees deterministic envelope around stochastic reasoning
- [ADR-007 decision-provenance-schema](ADR-007-decision-provenance-schema.md) — every decision has a row
- [ADR-009 approval-gate-primitive](ADR-009-approval-gate-primitive.md) — Approval primitive for GATE/ESCALATE
- [ADR-012 pnc-typed-parser-over-prose](ADR-012-pnc-typed-parser-over-prose.md) — Pre/Post-Node Check schemas
- [HS-1 reflexive-check](../native/hardstops/HS-1-reflexive-check.md) — fires on deterministic-surface violations
- PRD §1.5 row "Agentic-Systems Pattern" — operator-facing capability surface
- PRD §C.6 FQ1 + FQ3 — forward open questions on HOW + change-impact analysis
- R8 codex consult ADVISORY 2026-05-13 — recommended this pattern be a doctrine ADR anchored by P4 + P12
- R8 deepseek consult PROCEED 2026-05-13 — confirmed split between PRD operator-surface and canon doctrine

## Authoring

claude-drafted via R8 tech-parts execute phase under directive 1778610507 follow-up. R9 codex + deepseek review pending.
