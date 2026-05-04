# Eval E2 — HTTP API (snapshot + contract)

## Input

> Generate I/O determinism test scaffolding for the `POST /api/charges` endpoint. Subject: a TypeScript Express handler that accepts `{amount, currency, customer_id, idempotency_key}` and returns `{charge_id, status, created_at}` after persisting to PostgreSQL. Existing infra: Jest + supertest, recorded fixtures in `tests/fixtures/http/`. The endpoint has both an internal contract (our DB schema) and an external contract (consumer apps depend on the response shape).

## Required assertions (output MUST contain)

| # | Assertion | Where to check |
|---|---|---|
| 1 | At least 5 fixture cases spread across happy + idempotency-key-replay + invalid-currency + missing-customer + amount-validation-failure. Fixtures may be golden (full body), normalized (with timestamp / id stripped), or fixture+matcher pairs — any of these patterns satisfies the assertion as long as the case is covered | tests/fixtures/charges/ |
| 2 | Snapshot test for the response shape uses JSON SCHEMA assertion (not exact text) — handles `created_at` timestamp variability | tests/charges.snapshot.test.ts |
| 3 | Contract test for the consumer boundary (response shape must include charge_id, status, created_at fields) | tests/charges.contract.test.ts |
| 4 | Property-based test asserting idempotency: same idempotency_key returns same charge_id | tests/charges.property.test.ts |
| 5 | Snapshot drift detector script or equivalent that surfaces diffs for review (no auto-update) | scripts/check-snapshot-drift.sh OR equivalent |
| 6 | FIXTURES.md documents which fixtures are happy / edge / failure and the refresh procedure | tests/fixtures/charges/FIXTURES.md |
| 7 | At least one fixture explicitly tests an FAILURE response code (e.g., 400, 422) | tests/fixtures/charges/ |
| 8 | Open questions section calls out anything the scaffolding doesn't cover (e.g., concurrency, transaction rollback) | output |

Pass = ≥6/8 assertions hit.

## Anti-assertions (output MUST NOT contain)

- Snapshot tests that assert exact text including the timestamp (would fail every run — brittle)
- Contract tests that lock in current bugs as expected behavior without flagging them
- Tests that hit a real Stripe / payment processor (should be mocked at SDK boundary)
- Single happy-path fixture only (no spread)
- Property test that always passes (verify the idempotency assertion actually constrains output)

## Baseline comparison

Without the skill, Claude typically:
- Writes exact-text snapshot assertions (brittle; fail on timestamp)
- Doesn't separate contract test from snapshot test
- Misses idempotency property invariant
- Skips drift detector entirely

Skill should win on assertions 2, 3, 4, 5 vs baseline. Brittle-snapshot avoidance is the core discipline being tested here.
