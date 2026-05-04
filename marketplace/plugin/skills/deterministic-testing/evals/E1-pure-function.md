# Eval E1 — Pure Function (parser, golden + property)

## Input

> Generate I/O determinism test scaffolding for `parseURL(s: string): URLParts`. Subject: a URL parser that accepts a URL string and returns `{scheme, host, port, path, query, fragment}`. Existing infra: Jest in TypeScript, `tests/` directory. Invariants the team knows must hold: round-trip equality (`parseURL(formatURL(x)) == x`), and parsing should never throw on malformed input (it should return null fields, not exception).

## Required assertions (output MUST contain)

| # | Assertion | Where to check |
|---|---|---|
| 1 | At least 5 golden fixtures spread across happy / edge / failure (e.g., simple URL, URL with port, URL with query, malformed URL, empty string) | tests/fixtures/parseURL/ |
| 2 | Golden file test runner iterates fixtures and asserts `parseURL(input) == expected` | tests/parseURL.golden.test.ts |
| 3 | At least one property-based test asserting round-trip: `parseURL(formatURL(x)) == x` | tests/parseURL.property.test.ts |
| 4 | (Optional, only if user prompt named such an invariant) Property-based test asserting an invariant the user explicitly mentioned (e.g., no-throw on arbitrary input) — NOT required if user gave only the round-trip invariant | tests/parseURL.property.test.ts |
| 5 | FIXTURES.md present, documents what each fixture is for and rotation cadence | tests/fixtures/parseURL/FIXTURES.md |
| 6 | Snapshot tests SKIPPED (or noted as N/A) — output is small structured object, golden suffices | output |
| 7 | Contract tests SKIPPED (or noted as N/A) — pure function, no API boundary | output |
| 8 | Open questions section present with any caveats or assumptions made | output |

Pass = ≥6/8 assertions hit.

## Anti-assertions (output MUST NOT contain)

- Property test that always passes (vacuous) — verify by examining the assertion
- Tests that mock the parser internals (defeats the I/O determinism purpose)
- Fixture-less tests (inline expected values in test bodies) — golden discipline requires fixtures
- A single fixture (no spread) — minimum 3-fixture composition
- Tests that depend on time / random / environment without injection

## Baseline comparison

Without the skill, Claude typically:
- Inlines 1-3 expected values in the test body instead of using fixtures
- Writes 0 property-based tests
- Skips FIXTURES.md
- Doesn't enumerate happy + edge + failure modes

Skill should win on assertions 1, 3, 4, 5 vs baseline.
