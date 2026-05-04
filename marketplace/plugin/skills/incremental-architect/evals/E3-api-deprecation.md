# Eval E3 — Deprecated API Decommission

## Input

> Plan the decommission of our v1 REST API. Subject: 200 external customers currently use v1; we shipped v2 12 months ago and 60% of customers have migrated voluntarily. v1 maintenance is consuming significant engineering time. Team: 3 engineers. Downtime tolerance: window OK during low-traffic hours. No hard deadline but desire to fully decommission within 12 months. Constraints: enterprise contracts have 6-month deprecation notice clause.

## Required assertions (output MUST contain — STRUCTURAL only)

| # | Assertion | Where to check |
|---|---|---|
| 1 | All 9 sections emitted | grep section headings |
| 2 | Pattern selection is strangler-with-sunset OR hybrid (rationale references customer migration tracking) | section 2 |
| 3 | Phase plan has ≥3 phases; first phase is announcement / tracking infrastructure (NOT shutting off v1 immediately) | section 3 |
| 4 | Each phase has rollback (non-"fix forward"; e.g., extend deprecation timeline) | section 3 |
| 5 | Risk register includes ≥1 of: hidden coupling on v1, customer churn, missed migrations, v1-only-feature dependency, contract violation | section 4 |
| 6 | Parallel-run period (v1+v2 both live) has observability for tracking customer migration progress | section 5 |
| 7 | Decommission gate has all 4 operational elements (named approver + evidence + window + final-deletion phase) | section 6 |
| 8 | Decommission gate respects 6-month enterprise contract notice clause | section 6 |
| 9 | Communication plan addresses enterprise account management for the notice clause | section 8 |
| 10 | Open questions flag any uncertainty around v1-only customers (those who can't or won't migrate) | section 9 |

Pass = ≥8/10 assertions hit.

## Anti-assertions (output MUST NOT contain)

- Hard cutoff date that violates 6-month notice clause for enterprise customers
- Phase plan that starts with "shut off v1" (must start with announcement + tracking)
- Decommission gate missing any of the 4 operational elements

## Baseline comparison

Without the skill, Claude typically:
- Proposes single deprecation date without phased warning
- Ignores enterprise contract clauses
- Misses migration-tracking infrastructure
- Vague decommission criteria

Skill should win on assertions 4, 6, 7, 8, 9 vs baseline.
