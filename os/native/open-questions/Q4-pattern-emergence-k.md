---
part-id: Q4
bucket: open-questions
template: research-log
parity-source: §14.10 Q4
parity-source-sha256: bea0309fd1cf2e969be7c9fe64f748a341f8c50e3f1f44926224aa751fcfa1a4
status: ANSWERED
answered: 2026-05-09
authored: 2026-05-09
---

# Q4: Pattern emergence threshold k — default value

## Question

Verbatim per §14.10 row Q4 (post-2026-05-09 ratification): the row records the resolved answer in place of an open prompt. The original question shape was: what is the default k (number of recurring observations) before Native proposes a pattern as a candidate Workflow for founder approval — per D45 organic emergence?

## Why it matters

k sets the sensitivity of the emergence pipeline. k too low → noisy proposals, founder approval fatigue, false positives. k too high → emergence pipeline rarely fires, Native fails the "learns from me" promise. Per-tenant configurability protects against one-size-fits-all failure but requires usage data first.

## Default if unanswered

n/a — answer is recorded in canon row directly; no fallback default applies once ratified.

## Answer

**k = 4** as v1 default for pattern emergence proposal threshold. Per-tenant configurable in v2 once real usage data lands per D45 organic emergence. k=4 balances recall (catches genuine patterns within a working week) vs precision (filters out two-occurrence coincidences and triplets that may not yet be habit). Founder retains approval gate per Q5; emergence is proposal, not auto-registration.

## Sources informing the answer

- Founder voice 2026-05-09 (this session) — ratification statement captured in §14.10 row Q4.
- Founder direction D45 (2026-05-03) — T0/T2 organic emergence pipeline; ratifies Native's emergence layer.
- Canon `NATIVE-ENGINE.md` §14.5 G3 — registration approval gate downstream of emergence proposal.
- Canon `NATIVE-ENGINE.md` §3.2 — `pattern_detected` / `workflow_proposed` event types feed this threshold.
- Memory `project_d45_ratification` — D45 ratifies organic emergence at T0/T2; v1.2.1 host-LLM wire closes P1.2.

## References

- `NATIVE-ENGINE.md` §14.10 row Q4
- `NATIVE-ENGINE.md` §14.5 G3
- `holding/FOUNDER-DIRECTIONS.md` §D45
- `Q5-approval-scope.md` (sibling — approval gate post-emergence)
- `../events/` (pattern_detected / workflow_proposed downstream)
