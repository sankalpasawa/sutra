---
name: deterministic-testing
description: Generates I/O determinism test scaffolding (golden file tests, snapshot tests, property-based tests, contract tests, snapshot drift detector) for a function, API, skill, or pipeline. Produces test files + fixture files in the user's existing test infrastructure, plus a fixture-rotation policy. Fires when the user asks to write golden-file tests, snapshot tests, property-based tests, contract tests, fixture-based tests, or wants drift detection on a function's outputs. Skip when the user asks for a TEST STRATEGY (use core:test-strategy first), wants TDD workflow (use superpowers:test-driven-development), is debugging an existing test (use gstack investigate), or wants tests RUN (use gstack qa). This skill is the IMPLEMENTATION layer for I/O determinism testing — the strategy comes from core:test-strategy.
allowed-tools: Read, Write, Bash
---

# Deterministic Testing — generate I/O determinism test scaffolding

This skill writes test files + fixture files for I/O determinism: golden-file pairs, snapshots, property-based invariants, contract tests, and a snapshot drift detector. It does NOT design the test strategy (use `core:test-strategy` for that) or run the tests (use the test runner already in the repo).

## Skill card

- **WHAT**: generate I/O determinism test scaffolding for a function / API / skill / pipeline — golden file pairs, snapshots, property-based invariants, contract tests, snapshot drift detector, fixture-rotation policy.
- **WHY**: I/O determinism is a leverage point — once a function's input/output behavior is locked behind golden + property + contract tests, refactoring becomes safe and regressions become loud. Without it, every refactor is a gamble.
- **EXPECT**: a set of test files + fixture files in the project's existing test layout, conforming to the project's test framework. Plus a `FIXTURES.md` that documents the fixture-rotation policy.
- **ASKS**: 3-5 questions about subject signature, existing test infra, fixture format, and which invariants matter (skip questions whose answers are implied by inputs).

`allowed-tools` rationale: `Read` for inspecting the subject + existing test layout, `Write` for test files + fixture files + FIXTURES.md, `Bash` narrowly for running test discovery commands (`find tests/`, `cat package.json`, etc.) to detect the project's test framework.

## When to use

| Trigger | Use this skill? |
|---|---|
| "Write golden-file tests for `parseURL`" | Yes |
| "Add property-based tests for the date parser" | Yes |
| "Set up snapshot tests for the HTTP API responses" | Yes |
| "Add contract tests for the consumer-driven boundary" | Yes |
| "What's the test strategy for this module?" | No — use `core:test-strategy` first |
| "Run the tests" | No — use gstack `qa` or your existing test runner |
| "Why did this snapshot test fail?" | No — use gstack `investigate` or `superpowers:systematic-debugging` |
| "Write unit tests for this class" (no I/O focus) | No — use gstack `gsd-add-tests` or `superpowers:test-driven-development` |

## Inputs

| Input | Required? | Default if missing |
|---|---|---|
| Subject — function / API / skill / pipeline reference (file path + function name OR endpoint URL OR skill name) | Yes | Ask |
| I/O contract — signature, expected behavior, side effects | Strongly preferred | Ask 1 question; default to inspecting the subject's source if accessible |
| Test framework already in repo | If discoverable | Inspect `package.json` / `pytest.ini` / `Cargo.toml` / `go.mod`; default to language-stdlib runner |
| Fixture format preference | Optional | Default to JSON for structured data, plain text for line-oriented |
| Invariants the user knows must hold | Strongly preferred | Ask 1 question if subject is non-trivial (e.g., parser → "round-trip equality?") |

## Output: test files + fixture files + FIXTURES.md

Produce these in this order:

```
1. Golden file fixtures: tests/fixtures/<subject>/E1-happy-path.{json,txt}, E2-edge-case, E3-failure-mode (>=5 fixtures total when subject scope warrants; >=3 minimum)
2. Golden file test runner: tests/<subject>.golden.test.* — iterates fixtures, asserts subject(input) == expected
3. Snapshot tests: tests/<subject>.snapshot.test.* — for outputs too large to inline as goldens (e.g., HTML, JSON trees)
4. Property-based tests: tests/<subject>.property.test.* — invariants that must hold for all inputs (>=1 invariant per subject minimum)
5. Contract tests: tests/<subject>.contract.test.* — for API boundaries; consumer-driven where applicable
6. Snapshot drift detector: scripts/check-snapshot-drift.sh OR equivalent — flags when snapshots change, surfaces diff
7. FIXTURES.md: documents fixture-update procedure (when to refresh vs preserve), rotation cadence, and the meaning of each fixture
8. Open questions + noted limitations: what the scaffolding leaves uncovered (always emit, even if empty)
```

Sections 1-7 are conditional on applicability (e.g., contract tests don't apply to a pure function; snapshot tests don't apply to scalar return values). Section 8 is ALWAYS present — even "no open questions" is a valid entry.

## Fixture decision matrix

| Subject type | Primary technique | Fixture format |
|---|---|---|
| Pure function (parser / formatter / math) | Golden + property | JSON or text fixture pairs |
| Stateful function with side effects | Golden + before/after state snapshot | JSON state dump |
| HTTP API (own) | Snapshot of response shape + contract | JSON response |
| HTTP API (third-party) | Recorded fixtures (mock at SDK level) | JSON / VCR cassette |
| Database query | Golden output for a fixed seed dataset | SQL seed + JSON expected rows |
| LLM prompt template | Fixture set of input prompts + golden output SCHEMA (assert SHAPE not exact text — prompts are non-deterministic) | JSON for input, JSON Schema for expected output shape |
| CLI tool | Golden stdin → stdout pair, exit code assertion | Plain text or JSON |
| Stream / pipeline | Golden input chunks → golden output chunks | Newline-delimited JSON or chunked text |

## Property-based invariants — common patterns

Every subject deserves at least one property invariant. Common patterns:

| Pattern | Invariant |
|---|---|
| Parser / serializer | `parse(serialize(x)) == x` (round-trip) |
| Comparator | Reflexive (`compare(x, x) == 0`), antisymmetric, transitive |
| Idempotent operation | `f(f(x)) == f(x)` |
| Commutative operation | `f(x, y) == f(y, x)` |
| Identity element | `f(x, identity) == x` |
| Bounded function | `min <= f(x) <= max` for all valid x |
| Schema-conforming output | `validate(f(x), schema) == true` for all valid x |
| Length / cardinality | `length(f(x)) == g(length(x))` for some known g |

Pick at least one. If none apply, ask the user "what must always be true about this function's output, regardless of input?" — that question often surfaces the invariant.

## Snapshot drift discipline

Snapshots are a power tool with a sharp edge: they lock in current behavior, but they can become brittle (failing on cosmetic changes) or stale (locking in current bugs as expected behavior).

Three rules:
1. **Snapshots assert SHAPE, not exact text** when the subject's output has cosmetic variability. Use JSON Schema, regex, or structured comparison rather than string equality.
2. **The drift detector surfaces the diff for review** — never auto-update snapshots silently. A passing snapshot test should mean "the output is unchanged"; a failing one is a deliberate review event, not a flake.
3. **Document why each snapshot exists.** A snapshot whose purpose isn't recorded becomes hard to update correctly when the underlying behavior intentionally changes.

## FIXTURES.md template

```
# Fixtures for <subject>

## Layout
- `E1-<name>.json` — happy path (most common input)
- `E2-<name>.json` — edge case (boundary condition)
- `E3-<name>.json` — failure mode (intentionally invalid input)
- (additional E4+ as needed)

## When to refresh
- Subject's contract intentionally changed: update affected fixtures + document in CHANGELOG
- Subject's bug is fixed and a fixture was locking in the bug: update fixture + reference the fix commit

## When to preserve
- Refactoring with no behavior change: fixtures should pass unchanged
- Performance optimization: fixtures should pass unchanged

## Rotation cadence
- Review fixture set every 90 days OR after any major subject contract change
- Add new fixtures when bugs are discovered (regression-protection)
```

## Process (internal — not user-visible)

Six-step authoring loop: read I/O contract → pick fixture format from matrix → generate ≥5 representative input cases (happy / edge / failure spread) → identify ≥1 property invariant from the patterns table → wire into existing test runner → write FIXTURES.md.

## Composition with other Sutra + ecosystem skills

| When you need... | Use... |
|---|---|
| Test STRATEGY (pyramid, fixture choice, boundaries) | `core:test-strategy` first — this skill implements the strategy |
| TDD workflow (red-green-refactor) | `superpowers:test-driven-development` |
| Tests generated from existing code (general, not I/O-focused) | gstack `gsd-add-tests` |
| QA execution + bug-fix loop | gstack `qa` |
| Why did this test fail? | gstack `investigate` or `superpowers:systematic-debugging` |
| Architecture-aware test boundaries | `core:architect` (W2) for the system architecture, then this skill for the I/O tests at each boundary |

## Failure modes to watch (this skill itself)

- Brittle snapshots that fail on cosmetic whitespace or timestamps — assert SHAPE not exact text when output has variability
- Property tests that always pass (vacuous) — verify the property actually constrains the output by mutation-testing it
- Contract tests that lock in current bugs as expected behavior — when scaffolding contract tests, note any current outputs that look wrong
- Fixture sets without happy + edge + failure spread — minimum 3-fixture composition
- Snapshot files committed without the FIXTURES.md explaining why each exists — orphan snapshots become impossible to maintain
- LLM prompt template tests that assert exact text output — prompts are non-deterministic; assert schema/shape instead

## Eval pack

Three evals shipped in `evals/` next to this SKILL.md.

## Self-score (optional telemetry, never a side effect)

The validation framework can be applied as telemetry. If `holding/research/skill-adoption-log.jsonl` is writable AND telemetry is not opted out (`SUTRA_TELEMETRY=0` or `~/.sutra-telemetry-disabled`), one row may be appended:

```json
{"date": "YYYY-MM-DD", "skill": "core:deterministic-testing", "career_track": 5, "mode": "Generative+Procedural", "subject": "<what was scaffolded>", "fixture_count": N, "property_invariants": N, "techniques_used": ["golden", "property", "contract"]}
```

If the sink is unwritable or telemetry is opted out — silently skip. Never let telemetry side effects fail the user's primary task.

## Build-Layer

L0 (PLUGIN-RUNTIME, fleet). Per Sutra D38 — this skill ships in the marketplace plugin and reaches all clients via plugin update.
