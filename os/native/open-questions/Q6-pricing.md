---
part-id: Q6
bucket: open-questions
template: research-log
parity-source: §14.10 Q6
parity-source-sha256: 87f9cc4def03325c1993cdec0cc0b67833490cb94efaf2d58e06a2e8a044b844
status: ANSWERED
answered: 2026-05-09
authored: 2026-05-09
---

# Q6: Pricing unit — per-Tenant subscription vs outcome-based

## Question

Verbatim per §14.10 row Q6 (post-2026-05-09 ratification): the row records the resolved answer in place of an open prompt. The original question shape was: is v1 priced per-Tenant subscription (flat-rate per company), or outcome-based (Sierra-style pay-per-OHS-saved)?

## Why it matters

Pricing unit changes everything downstream — measurement infra needed, sales cycle length, churn semantics, contract shape. Per-Tenant is simplest and ships day-1 without measurement maturity. Outcome-based requires N* (OHS/wk) measurement to be trustworthy + auditable + non-gameable — a tall pre-PMF order.

## Default if unanswered

n/a — answer is recorded in canon row directly; no fallback default applies once ratified.

## Answer

**Per-Tenant subscription v1** (simplest revenue model; flat-rate per-company). Outcome-based pricing is a v2+ experiment once N* (OHS/wk) measurement proves trustworthy and Sierra-style pricing maturity allows. Per-Tenant ships against the Tenant primitive (§2) Native already has; outcome-based ships only when the metric is dispute-free.

## Sources informing the answer

- Founder voice 2026-05-09 (this session) — ratification statement captured in §14.10 row Q6.
- Canon `NATIVE-ENGINE.md` §11.2 — N* (OHS/wk) metric definition; pre-PMF baseline.
- Canon `NATIVE-ENGINE.md` §2 Tenant primitive — billing unit aligns with isolation boundary.
- A3 external landscape (2026-05-08) — Sierra outcome-pricing model captured; deferred as v2+ aspirational target.
- Memory `project_sutra_vision_apr2026` — two business models (CoS subscription + System-of-CoS outcome); v1 ships the simpler model first.

## References

- `NATIVE-ENGINE.md` §14.10 row Q6
- `NATIVE-ENGINE.md` §11.2 north-star OHS metric
- `NATIVE-ENGINE.md` §2 Tenant primitive
- `../metrics/north-star-ohs-per-week.md` (sibling — N* metric powers v2 outcome pricing)
- `../primitives/` (Tenant primitive — billing unit)
