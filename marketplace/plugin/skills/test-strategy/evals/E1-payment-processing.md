# Eval E1 — Payment Processing Module (stateful service, safety-critical)

## Input

> Design the test strategy for a new payment processing module. Subject: a Node.js service that accepts charge requests, calls Stripe, persists transaction rows in PostgreSQL, and emits webhook notifications. Risk profile: safety-critical (handles money). Existing infra: Jest + supertest, PostgreSQL test container, Stripe test-mode key. Failure modes the team is most worried about: double-charging on retry, schema drift breaking webhooks, idempotency key collisions.

## Required assertions (output MUST contain)

| # | Assertion | Where to check |
|---|---|---|
| 1 | All 7 main sections + anti-pattern section emitted (8 total) | grep section headings |
| 2 | Risk profile correctly classified as `safety-critical` | section 1 |
| 3 | Pyramid skews unit + integration heavy (NOT E2E-heavy); state pyramid matches "Stateful service" heuristic (~40/45/10 +/- 10pts) | section 2 |
| 4 | Real PostgreSQL declared (test container), Stripe declared as MOCK with recorded fixtures + nightly contract verification | section 3 + section 4 |
| 5 | Mock-vs-real boundary block present and explicit, with each side (real / mocked) and a stated reason for the boundary choice | section 4 |
| 6 | Coverage targets set ABOVE language defaults to match safety-critical risk; mutation testing recommended for at least the idempotency code path | section 5 |
| 7 | AI eval-pack section is present with a not-applicable placeholder (non-AI subject) — section is NOT silently omitted | section 6 |
| 8 | CI gates: unit + integration block merge; nightly Stripe contract test specified | section 7 |
| 9 | Anti-patterns named for THIS subject: ≥3 of {idempotency-key collisions go untested, mocking PostgreSQL because tests "feel slow", real Stripe calls in unit loop, no schema-migration test, missing webhook delivery test} | section 8 |
| 10 | Idempotency, double-charge, OR webhook-delivery appears in failure-mode framing | sections 1, 8 |

Pass = ≥8/10 assertions hit.

## Anti-assertions (output MUST NOT contain)

- "Mock the database for speed" without a measured wall-time justification
- A pyramid that puts E2E above 25% (this is service code, not a CLI)
- AI eval-pack content (no AI here)
- Coverage targets at language defaults (80% line) — should be safety-critical (95%)
- Generic anti-patterns ("write more tests", "test edge cases") — must be subject-specific

## Baseline comparison

Without the skill, Claude typically:
- Lists generic test types
- Picks 80% coverage target by default
- Doesn't draw an explicit mock-vs-real boundary
- Doesn't cite a pyramid heuristic
- Doesn't name idempotency-key collision as an anti-pattern unless prompted

Skill should win on assertions 3, 4, 5, 6, 9 vs baseline.
