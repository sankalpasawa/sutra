# Eval E1 — Monolith → Microservices (live-state transition)

## Input

> Plan the migration from our monolith to microservices. Subject: a Rails monolith handling user-facing web app + admin panel + background jobs + scheduled reports. Team: 6 engineers. Downtime tolerance: zero (B2B SaaS with paying customers). No hard deadline (aspirational 18 months). Constraints: must continue shipping features during migration; SOC2 audit in 6 months requires audit log continuity.

## Required assertions (output MUST contain — STRUCTURAL only, per skill contract)

| # | Assertion | Where to check |
|---|---|---|
| 1 | All 9 main sections emitted | grep section headings |
| 2 | Pattern selection is one of (strangler / branch / parallel / decompose / hybrid) with rationale paragraph that references at least one of the input constraints (zero-downtime, 18-month, SOC2, 6 engineers) | section 2 |
| 3 | Phase plan has ≥3 phases with first phase being a small reversible step (NOT "extract first service immediately") | section 3 |
| 4 | Each phase has a populated rollback plan that is NOT the literal text "fix forward" | section 3 |
| 5 | Risk register has ≥5 entries; at least one references hidden-coupling OR dual-write OR schema-evolution OR distributed-monolith trap (per skill contract) | section 4 |
| 6 | Parallel-run observability section names specific metrics (any concrete metrics; not "we'll watch logs") | section 5 |
| 7 | Decommission gate has named approver + evidence artifact + observation window + a final-deletion phase blocked on gate (operational enforcement, all 4 elements present) | section 6 |
| 8 | Cost projection breaks down by phase (per-phase engineer-hours OR per-phase weeks; not vague total) | section 7 |
| 9 | Communication plan addresses the SOC2-audit-in-6-months constraint | section 8 |
| 10 | Open questions section non-empty (acknowledges what's not resolvable from inputs alone) | section 9 |

Pass = ≥8/10 assertions hit.

## Anti-assertions (output MUST NOT contain)

- A phase whose rollback plan is "fix forward" (literal anti-pattern)
- Decommission criteria that lacks ANY of: named approver / evidence artifact / observation window / final-deletion phase
- Plan that ignores zero-downtime constraint (e.g., proposes a maintenance window)

## Baseline comparison

Without the skill, Claude typically:
- Misses per-phase rollback discipline
- Vague decommission criteria
- Risk register thin or absent
- Doesn't operationalize the gate (no named approver)

Skill should win on assertions 4, 5, 6, 7 vs baseline.
