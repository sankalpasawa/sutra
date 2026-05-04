# Eval E2 — LLM-Powered Support Ticket Classifier (AI in loop)

## Input

> Design the test strategy for an LLM-powered support ticket classifier. Subject: a Python service that takes a customer support ticket (subject + body) and routes it to one of 12 categories (billing, technical, account, etc.) using Claude Haiku. Risk profile: user-facing (mis-routing delays response). Existing infra: pytest, no eval framework yet, no fixtures yet. Failure modes the team is most worried about: ambiguous tickets, drift after model upgrade, prompt regression on edge cases.

## Required assertions (output MUST contain)

| # | Assertion | Where to check |
|---|---|---|
| 1 | All 8 main sections emitted | grep section headings |
| 2 | Risk profile correctly classified as `user-facing` | section 1 |
| 3 | Pyramid heavily skews to eval pack (≥50%); unit tests minimal (<20%); state pyramid matches "LLM-powered classifier" heuristic | section 2 |
| 4 | Fixture strategy declares: real LLM in eval pack, NO LLM in unit tests (mock at SDK level for unit) | section 3 |
| 5 | AI eval-pack section IS emitted with: ≥3 evals minimum, baseline comparison required, more than one model included in evaluation, structural + LLM-judge combined scoring, drift-detection cadence stated, fixture-rotation policy stated | section 6 |
| 6 | CI gates specify: nightly eval pack run + on-AI-touched-PRs (NOT block-merge for cost reasons) | section 7 |
| 7 | Anti-patterns named for THIS subject: ≥3 of {single eval generalizes, LLM-judge only with no structural floor, same model judges itself, "100% accuracy" reward hacking, mocking LLM in eval pack defeats purpose, no baseline = can't prove value, prompt-string unit test is vacuous} | section 8 |
| 8 | Coverage targets section explicitly says line/branch coverage doesn't apply meaningfully to the prompt itself; applies to glue code only | section 5 |
| 9 | Drift after model upgrade is named as a failure mode + evals re-run on upgrade declared | sections 1, 6 |
| 10 | Mock-vs-real boundary distinguishes prompt+model (real in eval pack, mock in unit) vs glue code (always real) | section 4 |

Pass = ≥8/10 assertions hit.

## Anti-assertions (output MUST NOT contain)

- Pyramid that puts unit tests above 30% (LLM-classifier domain)
- "Test that the prompt contains the word 'classify'" or similar string-matching unit tests
- Coverage targets at safety-critical levels (95%) — this is user-facing, not safety-critical
- Eval count of 1 or 2 — Anthropic standard is ≥3
- Self-judge pattern (Haiku judges Haiku) without flagging the bias
- Mock LLM in eval pack — defeats purpose

## Baseline comparison

Without the skill, Claude typically:
- Treats the LLM as if it were normal code (suggests unit tests on the prompt string)
- Doesn't propose a baseline-comparison
- Picks one eval scenario or none
- Doesn't address drift / rotation cadence
- Doesn't distinguish prompt+model from glue code in mock-vs-real boundary

Skill should win on assertions 3, 4, 5, 7, 8, 10 vs baseline — this is the eval where the skill demonstrates the most lift.
