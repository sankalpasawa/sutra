# Eval E2 — PostgreSQL → DynamoDB (live-state, regulated)

## Input

> Plan the migration from PostgreSQL to DynamoDB. Subject: our payment service (handles charges, refunds, subscriptions) currently on PostgreSQL with 50M rows of transaction data and 7-year retention requirement. Team: 4 engineers. Downtime tolerance: zero (financial system). Drop-dead deadline: 9 months (PostgreSQL license renewal cliff). Constraints: PCI-DSS compliance; data parity audit before cutover.

## Required assertions (output MUST contain — STRUCTURAL only)

| # | Assertion | Where to check |
|---|---|---|
| 1 | All 9 sections emitted | grep section headings |
| 2 | Pattern selection includes branch-by-abstraction OR parallel-run OR hybrid (rationale references zero-downtime + audit-driven correctness) | section 2 |
| 3 | Phase plan has a parallel-run phase before any cutover phase | section 3 |
| 4 | Each phase has rollback (non-"fix forward") | section 3 |
| 5 | Risk register includes at least one of: hidden coupling, dual-write consistency, schema evolution / data parity, distributed-monolith — per skill contract MUST | section 4 |
| 6 | Parallel-run observability includes data parity verification (any specific mechanism: row count comparison, hash, audit-log diff) | section 5 |
| 7 | Decommission gate addresses 7-year retention constraint (cannot delete PG until DynamoDB has 7 years OR PG preserved as read-only archive) | section 6 |
| 8 | Decommission gate has all 4 operational elements (named approver + evidence + window + final-deletion phase) | section 6 |
| 9 | Cost projection acknowledges parallel-run cost spike (dual-write doubles writes during overlap period) | section 7 |
| 10 | Open questions section flags any unresolved DynamoDB-vs-PG semantic mismatches (transactions, query patterns, secondary indexes) | section 9 |

Pass = ≥8/10 assertions hit.

## Anti-assertions (output MUST NOT contain)

- Single big-bang cutover phase (zero-downtime + financial system forbids)
- Decommission criteria that ignores 7-year retention
- Cost projection that assumes DynamoDB cheaper without showing parallel-run spike
- Skip of data parity audit (PCI-DSS + audit-driven correctness require)

## Baseline comparison

Without the skill, Claude typically:
- Misses per-phase rollback
- Vague decommission criteria
- Doesn't address parallel-run cost spike
- Misses 7-year retention forcing function

Skill should win on assertions 4, 6, 7, 8, 9 vs baseline.
