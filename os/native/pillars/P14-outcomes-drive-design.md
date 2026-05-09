---
part-id: P14
bucket: pillars
template: L1-pov
parity-source: §10.2 row P14 + §10.3 row P14 + §14.15.2 outcome-first ordering
parity-source-sha256: 3f518bf4eb5eec37e542c499320f9d087118a856f3942e653eecbdb1af063c5e
status: DRAFT v1
authored: 2026-05-09
---

# P14: Outcomes drive design

## Pillar statement

> Governance, security, and agentic frameworks are infrastructure. The customer-facing surface is OUTCOMES. Native is designed backward from what the operator gets — measurable hours saved, decisions captured, work auto-running — not forward from technical primitives. Every block, every primitive, every event must trace to an operator-observable outcome OR explicitly justify itself as infrastructure supporting an outcome-bearing block.

Per founder direction 2026-05-09: *"I want to ensure this proper governance, security, and all the agentic frameworks which we have used are there. But these are kind of the outcomes which I need from a product point of view."*

## What this rules in

- Build sequencing by **outcome value**, not by infra dependency order (per §14.15.2 — Top-5 v1 blocks ordered by founder-outcome).
- Every block has a 1-line user outcome statement (B9 = "anything I produce is logged + reused"; B7 = "every LLM call is checked"; etc.).
- Metrics anchored on operator outcome (N* = Operator-Hours-Saved per Week — measures operator time recovered, not system throughput).
- Infrastructure work (e.g., audit logs, tenant isolation, governance hooks) is JUSTIFIED by which outcome-bearing block it enables, not by intrinsic technical interest.
- Phase B in §14.15.1 Implementation Kickoff Framework — feature specs ordered by outcome (top-5 first), other 13 blocks ship as stubs per P3.

## What this rules out

- Building primitives because they're elegant or canonical without traceability to an outcome.
- "Infrastructure for infrastructure's sake" — runtime substrate that doesn't support a customer-facing block.
- Build sequencing by infra-dependency topology (e.g., "build primitives first, then events, then blocks") instead of outcome value.
- Marketing infra as the value prop (e.g., framing Native as "the most rigorous agent framework" instead of "your portfolio doesn't lose decisions").

## Falsification test

**If Native ships without a measurable operator-outcome → P14 broken.**

Specifically (from §10.3):
- Native runtime exists but Operator-Hours-Saved is unmeasurable or zero → broken.
- A block ships without a `## User outcome` section in its part file → broken (per L8 template enforcement via `native-author-part` skill).
- Build cycle prioritizes infra polish over an outcome-block that founder-requested → broken.

## Doctrine inheritance (from L0)

Customer Focus First (Founding Doctrine Principle 0) is the parent of P14. Principle 0: *"Every output serves the person reading it. If the customer needs explanation to understand, fix it. Supersedes all other principles."*

P14 specializes this for Native specifically: the customer here is the operator (founder + manager-IC). The PRODUCT surface is outcomes; the INFRASTRUCTURE surface (governance / security / frameworks) is invisible-by-default. This resolves the latent tension between rigor (Sutra discipline) and usability (Customer Focus) — rigor is the WHY behind the experience, not the experience itself.

Per §10.4 doctrine-tension resolution: no direct conflict with the 5 Doctrine tests (Dynamic / Flexible / Scalable / Simple / Nuanced) — P14 reinforces all five by keeping the customer surface clean.

## References

- NATIVE-ENGINE.md §10.2 row P14 — "Outcomes drive design | governance/security = infra; outcomes = customer surface".
- NATIVE-ENGINE.md §10.3 row P14 — falsification test.
- NATIVE-ENGINE.md §10.4 — doctrine inheritance + tension resolution.
- NATIVE-ENGINE.md §14.15.2 — outcome-first ordering of v1.x build sequence (top-5 outcome blocks).
- NATIVE-ENGINE.md §14.15.4 — explicit "governance/security/agentic-framework infra (already present)" — infra exists but is not the product.
- Founder direction 2026-05-09 (verbatim above).
- Founding Doctrine Principle 0 — Customer Focus First.
