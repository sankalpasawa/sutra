# Eval E3 — LLM Prompt Template (schema-shape, not exact text)

## Input

> Generate I/O determinism test scaffolding for the `classifyTicket` LLM prompt template. Subject: a prompt that takes a customer support ticket (subject + body) and returns JSON `{category: string, confidence: float, reasoning: string}` from Claude Haiku. Existing infra: pytest, no LLM eval framework yet, no fixtures yet. The output is non-deterministic (LLM) but must conform to a fixed JSON schema and the category field must be one of 12 known categories.

## Required assertions (output MUST contain)

| # | Assertion | Where to check |
|---|---|---|
| 1 | At least 5 input fixtures spread across categories (e.g., billing-question, technical-bug, account-access, feature-request, ambiguous-edge-case) | tests/fixtures/classifyTicket/ |
| 2 | Tests assert OUTPUT SHAPE via JSON Schema (not exact text — LLM output is non-deterministic by design) | tests/classifyTicket.schema.test.py |
| 3 | Tests assert `category` field value is in the 12-category enumeration (structural constraint, not exact match) | tests/classifyTicket.schema.test.py |
| 4 | Tests assert `confidence` is a float in [0.0, 1.0] (bounded property invariant) | tests/classifyTicket.property.test.py |
| 5 | Tests assert `reasoning` is non-empty string (not text-equality) | tests/classifyTicket.schema.test.py |
| 6 | NO test asserts exact text equality on the LLM output (anti-pattern explicitly avoided) | output |
| 7 | FIXTURES.md notes that LLM outputs are non-deterministic and rotation cadence accounts for prompt updates triggering eval re-run | tests/fixtures/classifyTicket/FIXTURES.md |
| 8 | Fixture set explicitly includes an "ambiguous-edge-case" input where the correct category is debatable (forces the test to handle uncertainty) | tests/fixtures/classifyTicket/ |
| 9 | Open questions section acknowledges that LLM-output testing has inherent variability (any acknowledgement is sufficient — specific mitigation strategies like reruns or statistical pass-rate are NOT required by this skill's contract) | output |

Pass = ≥7/9 assertions hit.

## Anti-assertions (output MUST NOT contain)

- Exact-text equality assertions on `reasoning` field (LLM-specific anti-pattern)
- Mocking the LLM call inside the eval (defeats the purpose of LLM eval)
- Tests that pass even when the LLM returns garbage (insufficiently constraining)
- Single happy-path fixture (must spread across categories)
- Property test asserting exact float equality on `confidence` (LLM-specific brittleness)

## Baseline comparison

Without the skill, Claude typically:
- Writes string-equality assertions on the LLM output (always fails or always passes — both broken)
- Mocks the LLM with a hardcoded response (defeats the purpose)
- Doesn't enforce JSON schema constraint
- Misses the "category must be in the 12-enum" constraint

Skill should win on assertions 2, 3, 4, 6 vs baseline. This is the eval where the LLM-aware fixture discipline shows the most lift over generic test-generation.
