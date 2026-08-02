---
part-id: Q7
bucket: open-questions
template: research-log
parity-source: §14.10 Q7
parity-source-sha256: e81ec94144847af7008a1626b67de30d9fef591b3af34ea6ad27796d838da0ff
status: ANSWERED
answered: 2026-05-09
authored: 2026-05-09
---

# Q7: v1 → v2 transition trigger

## Question

Verbatim per §14.10 row Q7 (post-2026-05-09 ratification): the row records the resolved answer in place of an open prompt. The original question shape was: what triggers the v1 → v2 transition — time-based (e.g., 90 days), signal-based (cohort-green / blocker-on-upgrade), or hybrid?

## Why it matters

Wrong trigger causes premature scaling (v2 ships before v1 PMF) or stalled cycles (v1 lingers past its useful life). D41 revert moved the T4-first cohort pivot; the v2 trigger has to align with that cohort's signal-shape rather than calendar time.

## Default if unanswered

n/a — answer is recorded in canon row directly; no fallback default applies once ratified.

## Answer

**Signal-based v1 → v2 trigger** per D41 revert: **≥3 T4 clients green for 14d post-onboard OR ≥1 T2 portfolio co blocked on Native upgrade**. Time-based is deferred (premature without signal). The signal is observable, dispute-free, and ties v2 investment directly to demonstrated v1 demand.

## Sources informing the answer

- Founder voice 2026-05-09 (this session) — ratification statement captured in §14.10 row Q7.
- Founder direction D41 (2026-04-30) — T4-first cohort pivot.
- Canon `NATIVE-ENGINE.md` §11.4 — cohort retention target ≥80% at 14d post-onboard (aligned signal window).
- Memory `project_d45_ratification` — emergence + v1.2.1 host-LLM wire closes P1.2 (v1 wedge completeness).
- Cross-link Q1 founder-portfolio persona — T2 + T4 cohorts ARE the founder-portfolio wedge.

## References

- `NATIVE-ENGINE.md` §14.10 row Q7
- `NATIVE-ENGINE.md` §11.4 cohort retention
- `holding/FOUNDER-DIRECTIONS.md` §D41
- `Q1-persona.md` (sibling — persona defines cohort)
- `../metrics/north-star-ohs-per-week.md` (sibling — N* is the signal substrate)
