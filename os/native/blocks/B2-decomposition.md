---
part-id: B2
bucket: blocks
template: L8-feature-spec
parity-source: §12.9 row B2 + §12.8 founder voice round 3
parity-source-sha256: f2aac063652912af7d2f4c8ffb9921310c4dc97616f925c29659439b7022c135
status: DRAFT v1
authored: 2026-05-09
---

# B2: Decomposition Layer

## 1-line summary

Full decomposition of user request — splits intent into sub-intents, branches into clarification sub-routine when needed, otherwise context-resolves via the Native ecosystem.

## Scope (in / out)

**In scope (v1)**:
- NEW Decomposition Engine per §12.9 row B2 — splits Intent.high_level into sub-intents.
- Clarification-needed predicate (when ambiguity ≥ threshold; specific threshold NOT specified in canon — gap per F2; runtime implementation choice).
- Default = no clarity ⇒ ecosystem-contextualize (Native ecosystem fills the gap via context retrieval per 7a / Q19).

**Out of scope (v1)**:
- Auto-learning of decomposition patterns — not specified in canon (gap per F2; future ADR may codify).
- Multi-pass decomposition (decompose, partial-execute, re-decompose) — single-pass v1.
- Decomposition across Tenants — Tenant-scoped only per §6.2.

## User outcome

Operator says one thing, Native breaks it into the right sub-tasks — asks for clarification when truly needed, otherwise just resolves it. Founder voice round 3: "first we can do an entire decomposition. If some clarity is needed, Native will get that clarity ... sometimes we don't need clarity, so that has to be contextualized".

## UX flow (narrative; terminal + audit log)

1. Intent primitive (B1) arrives with `high_level` populated.
2. B2 splits into sub-intents (specific algorithm NOT specified in canon — gap per F2).
3. Clarification-needed predicate evaluates ambiguity.
4. Ambiguity ≥ threshold → emit clarification request to operator (canon-silent on exact surface — gap per F2; runtime implementation choice).
5. Ambiguity < threshold → ecosystem-contextualize via 7a context retrieval; sub-intents proceed to PLAN phase (per 7d lifecycle).
6. Sub-intents become individual WorkflowStep entries per §2.4 (canon primitive).

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Intent.high_level populated | B2 fires | sub-intents emitted; Intent.specifics populated (per B1 schema) |
| 2 | Ambiguity ≥ threshold | clarification predicate evaluates | clarification request emitted; Workflow pauses awaiting operator response |
| 3 | Ambiguity < threshold | predicate evaluates | ecosystem-contextualize via 7a; sub-intents proceed to next phase per 7d lifecycle |
| 4 | Clarification response arrives | classifier routes | sub-intents updated; Workflow resumes from clarification pause |

## Data model

Per §12.9 row B2: NEW Decomposition Engine; partial use of canon `Workflow.preconditions` (typed PNC predicates per ADR-012 + §4 F-10). Per F5, canon authorizes NEW Decomposition Engine.

```
Decomposition = {
  parent_intent_id
  sub_intents[]
  clarification_needed: boolean
}
```

Cross-refs:
- `../primitives/workflow.md` (sub-intents become WorkflowStep entries)
- `../primitives/step.md` (per-sub-intent step)
- `../primitives/engine-event.md` (decomposition state)

## Edge cases

- **Empty sub-intents** (decomposition yields nothing) → fallback semantic NOT specified in canon (gap per F2).
- **Operator never responds to clarification** → §6.7 per-step-timeout applies.
- **Sub-intents partially ambiguous** → mixed-state handling NOT specified in canon (gap per F2; future ADR may codify).
- **Decomposition produces sub-intent that violates scope_out per 7b** → routed via TenantIsolation per §6.2; HS-3 fires.

## Telemetry

Events (canon-existing only):
- `routing_decision` (§3.2 #1) — for decomposition routing.
- `precondition_check` (#11) — clarification-needed predicate evaluation.
- `step_paused` — when clarification pause fires.

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Pattern-detection precision — accurate decomposition raises pattern proposal precision.
- Approval-gate latency — well-decomposed steps reduce per-step approval friction.

## Dependencies

- **Primitives**: `workflow`, `step`, `engine-event`.
- **Events**: `routing_decision`, `precondition_check`, `step_paused`.
- **Surfaces**: `route`, `run`, `gate` (clarification pause uses approval substrate).
- **Hardstops**: HS-3 (tenant-boundary on out-of-scope sub-intent), HS-4 (audit-unwritable).
- **Blocks**: B1 (Intent input), 7a (ecosystem-contextualize path), B11 (PromptBuilder consumes sub-intent set), 7d (lifecycle SHAPE phase consumes B2 output).
- **Pillars**: P11 (Constrained problem construction), P5 (MECE domains).
- **ADRs**: ADR-012 (PNC typed predicates), ADR-015 (H-Sutra classification — clarification routing).

## References

- NATIVE-ENGINE.md §12.9 row B2 (founder voice round 3).
- NATIVE-ENGINE.md §4 F-10 (PNC parser).
- ADR-012 (PNC typed predicates).
