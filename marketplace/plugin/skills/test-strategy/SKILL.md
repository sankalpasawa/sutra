---
name: test-strategy
description: Designs a test strategy document (TEST-STRATEGY.md) for a function, module, system, or AI prompt before any tests are written. Produces test pyramid breakdown with rationale, fixture choices, mock-vs-real boundary declaration, coverage targets matched to risk profile, AI eval-pack design when AI is in the loop, and CI gate placement. Fires when the user asks for a test plan, test strategy, test pyramid, eval-pack design, or fixture strategy BEFORE implementation — not when the user wants tests generated, run, or debugged. Skip when the user asks "write tests for X" (that is generation, not strategy), "run the tests" (that is execution), "why is this test failing" (that is debugging), or "how do I mock Y" (that is implementation help). Output is one strategy document; downstream skills handle generation, execution, and debugging.
allowed-tools: Read, Write, Bash
---

# Test Strategy — design the test plan before writing tests

This skill produces a single `TEST-STRATEGY.md` for a piece of work. It does NOT generate test files, run tests, or debug failures. Composition pointers live in the "Composition" section near the end.

## Skill card

- **WHAT**: design the test strategy document for one piece of work — pyramid breakdown, fixture choices, boundaries, coverage targets, AI eval-pack design when applicable, CI gate placement.
- **WHY**: tests written without a strategy concentrate in the wrong layer and miss the failure modes that actually matter; this skill forces an explicit, recorded decision before code is written.
- **EXPECT**: a `TEST-STRATEGY.md` file in the working directory covering 8 sections (7 main + 1 anti-patterns); ~150-300 lines depending on scope.
- **ASKS**: 3-5 high-leverage questions about risk profile, existing infra, and what failure modes matter most. Skips questions whose answers are implied by inputs.

`allowed-tools` rationale: `Read` for inspecting existing tests and infra, `Write` for the artifact, `Bash` narrowly for repo inspection (`ls`, `find`, `grep` for test config files).

## When to use

| Trigger | Use this skill? |
|---|---|
| "Design the test strategy for the new payment module" | Yes |
| "What's our test plan for this LLM classifier?" | Yes |
| "How should I test this CLI?" | Yes |
| "Write the unit tests for `parseURL`" | No — use `core:deterministic-testing` or gstack `gsd-add-tests` |
| "Run the tests" | No — use gstack `qa` or your existing test runner |
| "Why is this test failing?" | No — use `gstack investigate` or `superpowers:systematic-debugging` |

## Inputs

| Input | Required? | Default if missing |
|---|---|---|
| Subject — what's being tested (function / module / system / AI prompt) | Yes | Ask |
| Risk profile — data integrity / user-facing / internal-only / safety-critical | Yes | Ask; default `internal-only` if user defers |
| Existing test infra — frameworks, CI, coverage tools | If discoverable | Inspect repo (look for `package.json`, `pytest.ini`, `Cargo.toml`, `.github/workflows/`); fall back to "language defaults" |
| Failure modes the user is most worried about | Strongly preferred | Ask 1 question if not provided |
| Performance / latency requirements (if relevant) | Optional | Skip section if unspecified |

## Output: `TEST-STRATEGY.md` template

Always emit these 8 sections in this order (7 main + 1 anti-patterns):

```
1. Subject + risk profile (1 paragraph)
2. Test pyramid breakdown (% per layer + rationale)
3. Fixture strategy (fakes / mocks / stubs / real, with mapping)
4. Mock-vs-real boundary (declared explicitly with reason)
5. Coverage targets (line / branch / mutation; rationale per target)
6. AI eval-pack design — write a one-line "no AI in loop; this section does not apply" if the subject contains no model call; otherwise emit the full eval-pack spec
7. CI gates (which tests block merge / nightly / on-demand)
8. Anti-patterns to avoid for this specific work
```

Section 6 is ALWAYS present — either as the placeholder line or as the full design. Never omit. ASCII boxes for any decision blocks (no unicode box-drawing).

## Pyramid heuristics by domain

Use as starting point; adapt to risk profile.

| Subject domain | Unit | Integration | E2E | Property / Eval | Notes |
|---|---:|---:|---:|---:|---|
| Pure compute (parsers, formatters, math) | 70% | 15% | 5% | 10% | Property-based shines here |
| Stateful service (CRUD, business logic) | 40% | 45% | 10% | 5% | Integration carries the load |
| API / HTTP boundary | 30% | 50% | 15% | 5% | Contract tests on the boundary |
| CLI tool | 20% | 30% | 50% | — | Golden-file E2E dominates |
| LLM-powered classifier / generator | 15% | 20% | 5% | 60% (eval pack) | Unit tests cover glue code (parsing, routing, fallback, guardrails); eval pack carries model-quality |
| RAG / agent / multi-step LLM | 10% | 20% | 10% | 60% (eval pack + trace eval) | Glue code unit tested; eval pack + trace evaluation carry semantic quality |
| Data pipeline / ETL | 25% | 50% | 15% | 10% | Fixture data + golden output diff dominate |
| Infrastructure (terraform, k8s) | 20% | 50% | 25% (live env) | 5% | Policy/plan validation + integration; chaos optional, not default |

Heuristics are starting points. State the deviation reason if you depart.

## Fixture decision matrix

| Boundary | Default fixture | When to deviate |
|---|---|---|
| Database (own data) | Real (test container) | Reduce scope, parallelize, or shard before considering fakes; fake only for narrow logic seams that don't depend on DB semantics |
| Database (third-party / managed service like Firestore, DynamoDB) | Stub at SDK level for unit; recorded fixtures for integration | Use real in nightly contract verification job to catch SDK / service behavior drift |
| HTTP API (own) | Real (test server) | Use mock when target server has rate limits or cost |
| HTTP API (third-party) | Mock with recorded fixtures | Use real ONLY in nightly contract verification job |
| LLM API | Real for eval pack; mock for unit | Eval pack against real always; unit tests should NOT call LLM |
| File system | Real (tmpdir) | Mock only when testing fs-error paths |
| Time / clock | Inject fake clock | Real only for performance benchmarks |
| Random | Inject seed | Real only for distribution tests |

## Mock-vs-real boundary discipline

State the boundary explicitly, with the reason. Examples:

```
+--- BOUNDARY ----------------------------------------------------+
| Real:    application code, our DB (test container), file system |
| Mock:    Stripe API, SendGrid API, S3, DynamoDB                 |
| Reason:  third-party APIs are rate-limited and cost money;      |
|          schema-locked contract tests run nightly to catch      |
|          provider drift                                         |
+----------------------------------------------------------------+
```

Anti-patterns to call out:
- Mocking the database "for speed" without first measuring real-DB test wall-time
- Mocking your own modules (defeats the purpose; refactor instead)
- Real third-party calls inside the unit test loop (flaky, slow, expensive)

## Coverage targets

Pick targets per risk profile, not language defaults:

| Risk profile | Line | Branch | Mutation | Rationale |
|---|---:|---:|---:|---|
| Safety-critical (medical, financial, infra) | 95% | 90% | 60% | Cost of bug >> cost of test |
| User-facing (web app, mobile) | 80% | 70% | — | Mutation expensive; prioritize branch |
| Internal tooling | 60% | 50% | — | Coverage informs, doesn't block |
| Throwaway / spike | 30% | — | — | Just enough to refactor confidently |

Mutation testing (Stryker, mutmut, PIT) optional but valuable for safety-critical paths — declare which subset gets mutation coverage; never run on whole codebase (too slow).

## AI eval-pack design (only if AI in loop)

Required when subject is an LLM prompt, RAG pipeline, agent, or any system whose output depends on a model call.

| Element | Spec |
|---|---|
| Eval count | ≥ 3 (Anthropic standard); 10-30 better |
| Baseline | Run subject WITHOUT the prompt under test, compare scores |
| Models tested | At minimum the production model; ideally one weaker (Haiku) and one stronger (Opus) |
| Scoring | Structural assertions (output shape, required fields) + LLM-judge (correctness, taste) — combine both |
| Drift detection | Re-run weekly; alert on >5% score drop |
| Fixture rotation | Rotate evals every 90 days OR after model upgrade — prevents memorization |

Anti-patterns:
- Single eval ("it works on my example") — does not generalize
- LLM-judge only (no structural floor) — judge bias
- Same model judging itself
- Eval rubrics that pass "contains stages" while missing "adds decision quality"

## CI gate placement

| Test class | Gate | Justification |
|---|---|---|
| Unit | Block merge | Fast (<1s/test); flake budget = 0 |
| Integration | Block merge | Slow (1-30s/test); flake budget < 0.1% |
| E2E (happy path) | Block merge | Slow (30s-5min); flake budget < 1% |
| E2E (full matrix) | Nightly | Too slow for PR loop |
| AI eval pack | Nightly + on AI-touched PRs | Cost; baseline comparison required |
| Mutation | On-demand | Slow; informs hardening priority |
| Chaos / failure injection | Nightly | Disruptive; needs isolated env |

## Anti-patterns to call out for the user's specific work

After authoring sections 1-6, list 3-5 anti-patterns this user is at risk of based on the subject + risk profile. Example output for "LLM-powered support classifier":

- "100% accuracy on the eval pack" — reward hacking; rotate evals
- Unit-testing the prompt string ("prompt contains the word 'classify'") — vacuous
- Mocking the LLM in the eval pack — defeats the purpose
- No baseline comparison — can't prove the prompt added value
- One-size-fits-all coverage target across model + glue code — they have different risk profiles

## Process (internal — not user-visible)

Five-step authoring loop: classify failure modes (Section 1 + Section 8) → inspect what's known about the subject → choose pyramid shape and fixtures (Sections 2-3) → declare boundaries, targets, gates (Sections 4-7) → declare drift detection / cadence (Section 7). User-visible TEST-STRATEGY.md uses domain language only — methodology brand names stay internal.

## Composition with other Sutra + ecosystem skills

| When you need... | Use... |
|---|---|
| The strategy doc itself | This skill (`core:test-strategy`) |
| I/O determinism scaffolding (golden / snapshot / property / contract) | `core:deterministic-testing` |
| Tests generated from existing code | gstack `gsd-add-tests` |
| TDD workflow (red-green-refactor) | `superpowers:test-driven-development` |
| QA execution + bug-fix loop | gstack `qa` |
| Plan review (architecture + tests) | gstack `plan-eng-review` |
| Architecture-aware test boundaries (D38 build-layer) | this skill + `core:architect` (W2) |

## Failure modes to watch (this skill itself)

- Strategy doc that's universal across all projects (one-size-fits-all pyramid) — ground every section in the specific subject
- AI eval-pack design that's a generic checklist instead of ≥3 named eval scenarios
- Coverage targets at language defaults (80% line) regardless of risk profile
- "We'll mock the database" without a measured reason
- Boundary declaration absent — tests drift toward whatever is convenient

## Eval pack

Three evals shipped in `evals/` next to this SKILL.md. Each is a fixture pair (input prompt + expected structural assertions on the output). See `evals/README.md` for runner.

## Self-score (telemetry, not gate)

After authoring a TEST-STRATEGY.md, append one row to `holding/research/skill-adoption-log.jsonl`:

```json
{"date": "YYYY-MM-DD", "skill": "core:test-strategy", "career_track": 5, "mode": "Decisional+Generative", "subject": "<what was strategized>", "sections_emitted": 8, "ai_eval_pack_designed": true|false}
```

Telemetry only. Used to calibrate framework v2.

## Build-Layer

L0 (PLUGIN-RUNTIME, fleet). Per Sutra D38 — this skill ships in the marketplace plugin and reaches all clients via plugin update.
