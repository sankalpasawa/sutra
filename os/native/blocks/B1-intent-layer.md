---
part-id: B1
bucket: blocks
template: L8-feature-spec
parity-source: §12.9 row B1 + §12.8 founder voice round 3 + §10.2 P2
parity-source-sha256: bf8a0a945e4ae693b687f512e852044aa2e74ea3ccff72dd3599480e2938e56b
status: DRAFT v1
authored: 2026-05-09
---

# B1: Intent Layer

## 1-line summary

Capture user intent (high-level "what user wants") and specifics (detailed sub-tasks); pre-LLM declare expected output schema, post-LLM check actual, measure — the testing-framework analog at the intent layer.

## Scope (in / out)

**In scope (v1)**:
- NEW primitive per §12.9 row B1: `Intent { high_level, specifics, expected_output_schema, post_check }`.
- v1 stub validates schema; full logic fills later per P3 (all blocks as stubs).
- Pairs with B7 pre/post validation — B7 is the per-LLM-step gate; B1 is the per-INTENT gate that frames the whole Workflow.

**Out of scope (v1)**:
- Auto-derivation of `specifics` from `high_level` — not specified in canon (gap per F2).
- Intent classification accuracy targets — canon-silent (gap per F2).
- Multi-intent composition (one utterance carries multiple intents) — not v1; founder may slice manually.

## User outcome

Operator's intents are captured + verified end-to-end; nothing about what was asked is implicit. Founder voice round 3: "intents are captured then specifics are captured and then those are measured. Those are checked once the output is there."

## UX flow (narrative; terminal + audit log)

1. Operator utterance arrives via H-Sutra.
2. Classifier extracts `high_level` intent (verbatim founder voice — high-level "what user wants").
3. Decomposer (B2) extracts `specifics` (detailed sub-tasks).
4. Intent primitive instantiated with both + `expected_output_schema` (Workflow-author-declared).
5. Workflow fires; on completion `post_check` evaluates output against intent schema.
6. Pass → Workflow completes; Fail → routes via canon `on_failure` per §6.5.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Operator utterance arrives | classifier routes per ADR-015 | Intent instantiated with `high_level` captured verbatim |
| 2 | Workflow author declares `expected_output_schema` | Workflow registered | schema captured at Workflow registration (W-hash content-addressed per §14.13.2) |
| 3 | Workflow completes | `post_check` evaluates | pass → `workflow_completed` (§3.2 #3); fail → canon `on_failure` per §6.5 (no fail-mode invention per F3) |
| 4 | Specifics missing | check fires | `clarification_needed` predicate trips per B2; flows back to operator before continuing |

## Data model

NEW primitive per §12.9 row B1. Per F5, canon authorizes new primitive here ("NEW primitive: `Intent { high_level, specifics, expected_output_schema, post_check }`"). Shape declared in v1; §2 sub-section addition deferred.

```
Intent = {
  high_level
  specifics
  expected_output_schema
  post_check
}
```

Cross-refs:
- `../primitives/workflow.md` (Intent attaches to Workflow root)
- `../primitives/engine-event.md` (Intent state changes emit events)

## Edge cases

- **No `expected_output_schema`** → Workflow rejected at registration (B7 acceptance #1 cascades).
- **Specifics empty after decomposition** → defaults to ecosystem-contextualize per B2 + §12.9 row B2.
- **`post_check` fails on a value** → routes per canon `on_failure`; DecisionProvenance row per ADR-007.
- **Multi-intent utterance** → not v1; canon-silent (gap per F2).

## Telemetry

Events (canon-existing):
- `routing_decision` (§3.2 #1) — when Intent routed to Workflow.
- `precondition_check` (#11) / `postcondition_check` (#12) — at intent boundary.
- `workflow_started` (#2) / `workflow_completed` (#3) / `workflow_failed` (#4).

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Pattern-detection precision — well-captured intents = sharper pattern emergence per §14.9.

## Dependencies

- **Primitives**: `workflow`, `engine-event`, `decision-provenance`.
- **Events**: `routing_decision`, `precondition_check`, `postcondition_check`, `workflow_started`, `workflow_completed`, `workflow_failed`.
- **Surfaces**: `route`, `run`, `audit`.
- **Hardstops**: HS-4 (audit-unwritable).
- **Blocks**: B2 (Decomposition consumes Intent.high_level → specifics), B7 (per-LLM-step gating; complementary), B11 (PromptBuilder embeds Intent in prompt).
- **Pillars**: P2 (Pre/post LLM-node validation), P11 (Constrained problem construction).

## References

- NATIVE-ENGINE.md §12.9 row B1 (founder voice round 3).
- NATIVE-ENGINE.md §10.2 P2 (Pre/post validation).
- ADR-015 (H-Sutra event classification).
