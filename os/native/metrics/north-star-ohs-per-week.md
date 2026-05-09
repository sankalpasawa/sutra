---
part-id: north-star-ohs-per-week
bucket: metrics
template: L11-okr
parity-source: §11.2 + §11.3 + §11.4 + §14.9
parity-source-sha256: c5946e8d70925ad5aaa1bdf5a5a752cb445b4f29cfcc23375ae3ecf9f1d0280e
status: DRAFT v1
authored: 2026-05-09
---

# Operator-Hours-Saved per Week (OHS/wk)

## Definition

Hours per week the operator NO LONGER thinks about, because Native handled them — audit-derived from auto-run lifecycle phases + operator weekly confirmation. (NATIVE-ENGINE.md §11.2)

**Why this metric**: Captures unit-of-value (time); measurable; leading indicator of retention; aligns with §14.3 JTBD outcomes #1+#2 (minimize time + variance); works at any scale.

## Measurement

Two-channel measurement per §11.2:

- **(a) Audit-derived**: auto-run lifecycle Executions × completion-time × non-trivial gate.
- **(b) Operator self-report**: weekly survey "did Native save you time this week?".

Cadence: weekly aggregation; per-operator + per-tenant roll-up.

## Targets

| Horizon | Target | Rationale |
|---|---|---|
| v1 baseline | 0 OHS/wk | pre-Native — no operator hours saved yet (§11.2) |
| v1 14d post-install | ≥3 OHS/wk per operator | early adoption signal — minimum viable value (§11.2) |
| v3 mature product | ≥20 OHS/wk per operator | sustained value at product maturity (§11.2) |

## Leading inputs

Indicators that move N* (per §11.3 + §14.9):

- Workflows successfully auto-run after operationalization (count/wk per operator).
- Pattern proposals approved by operator (count/wk; precision ≥75%).
- Cross-company decisions replayable from audit log (% complete; ≥99% — DecisionProvenance log completeness 100% of consequential decisions logged per §14.9).
- Operator weekly active sessions (trend up over 12-week window).
- Time-to-first-Execution on fresh install (≤30 min, per I-11 in §4).

## What "winning" looks like

5-year picture (per §11.4):

| Metric | 5-yr target |
|---|---|
| T4 fleet operators running Native daily | ≥1000 |
| Operator retention at 90d post-install | ≥80% |
| Portfolio companies (T2 owned) operating ENTIRELY through Native | ≥5 |
| Paying T3 / enterprise clients on outcome-based pricing | ≥1 |
| Native shipping as canonical Sutra plugin extension; T4 self-onboards | YES |

(Targets illustrative for direction; founder reviews + tunes at quarterly OKR cycle per §17.)

## References

- NATIVE-ENGINE.md §11.2 (N* definition + targets + measurement)
- NATIVE-ENGINE.md §11.3 (leading inputs)
- NATIVE-ENGINE.md §11.4 (5-year winning picture)
- NATIVE-ENGINE.md §14.9 (input/output success metrics anchored on L2)
- NATIVE-ENGINE.md §11.1 (5-year vision paragraph informing this N*)
- NATIVE-ENGINE.md §11.5 + D41 (v1 → v2 expansion trigger)
- NATIVE-ENGINE.md §4 I-11 (time-to-first-Execution invariant)
- NATIVE-ENGINE.md §14.3 (JTBD outcomes #1+#2)
