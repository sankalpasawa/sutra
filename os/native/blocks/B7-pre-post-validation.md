---
part-id: B7
bucket: blocks
template: L8-feature-spec
parity-source: §12.9 row B7 + §14.15.2 rank 2 + §10.2 P2 + §12.13 (extension note)
parity-source-sha256: c3a0f8e1160cab5c55e583b9b08444aa90c053b936a40abd2e2c979dd0ffe04b
status: DRAFT v1
authored: 2026-05-09
---

# B7: Pre/Post LLM-Node Validation

## 1-line summary

Every LLM-bearing step pre-declares an expected output schema and post-checks the actual output against that schema before the step is allowed to complete — testing-framework discipline applied to every LLM call so nothing about the deterministic surface is left to chance.

## Scope (in / out)

**In scope**:
- Every WorkflowStep where `action='invoke_host_llm'` carries a mandatory `expected_output_schema` (pre) and `output_check_predicate` (post) per §12.9 row B7.
- Pre-validation runs before the LLM is invoked (asserts the prompt context + intent specifics are well-formed).
- Post-validation runs against the LLM response (asserts the response matches the declared schema + predicate).
- Validation failure routes through existing `on_failure` 5-set per §6.5 (canon-default; no new failure-policy invented here).
- Captures pre/post-validation outcomes as typed EngineEvents — see Telemetry.

**Out of scope (v1)**:
- Validation of stochastic content quality (LLM reasoning quality is by canon §12.14 P12 explicitly left stochastic; only deterministic shape + predicate are validated here).
- Coverage gate enforcement (test-coverage discipline lives at §14.16.8 / Phase D codex review, NOT in this block).
- Skipping validation for "cheap calls" — Q22 default v1 = every LLM-bearing step validated; fast-path opt-out deferred per Q22.

## User outcome

> "Every LLM call is checked; nothing left to chance" (per §14.15.2 rank 2).

The operator trusts that each LLM-bearing step has a pre-declared expected output and is checked after the fact — the testing-framework analog founder asked for in r3 ("we ensure there's end to end testing of everything so that nothing is left to chance only the reasoning part is left"). Trust is the unlock that gates founder dogfood quality (rank-2 rationale, §14.15.2).

## UX flow (narrative; terminal + audit log)

1. Founder fires Workflow W containing step S where `action='invoke_host_llm'`.
2. PromptBuilder (B11) composes prompt from Domain config + Charter config + relevant Artifacts + step inputs + Intent specifics (per §12.14 P11).
3. Native emits `precondition_check` EngineEvent (event in §3.2) — asserts `expected_output_schema` is declared and the prompt context is well-formed.
4. host-LLM dispatch fires (per §5.1); LLM returns response.
5. Native emits `postcondition_check` EngineEvent — asserts response matches declared schema + predicate.
6. Pass → step completes → `step_completed` emitted (§3.2 #6) → Artifact registered per B9.
7. Fail → routes through canon `on_failure` machinery (§6.5); no new fail-mode invented.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Workflow step has `action='invoke_host_llm'` AND `expected_output_schema` is null | step is loaded | step rejected at load-time; ExecutionResult terminal state = `failed` (canon-default per §6.5 / §4 I-5; not a new state) |
| 2 | Step has both `expected_output_schema` + `output_check_predicate` declared | step fires | `precondition_check` event emitted before LLM call; `postcondition_check` event emitted after LLM response |
| 3 | LLM response matches declared schema + predicate passes | post-check evaluates | `step_completed` emitted (§3.2 #6); response registered as Artifact per B9 |
| 4 | LLM response fails schema OR predicate | post-check evaluates | step failure routed through canon `on_failure` 5-set per §6.5; behavior follows configured policy (NOT specified in canon; runtime implementation choice per F2; future ADR may codify per-block default) |
| 5 | Step `action != 'invoke_host_llm'` (e.g., `host_action`) | step fires | B7 pre/post check does NOT fire (B7 scope is LLM-bearing steps; per §12.9 + §12.14 P12 only LLM reasoning is the stochastic surface this guards) |

## Data model

Per F5 + §12.9 row B7: B7 EXTENDS existing `step.outputs` validation (already partial per §2.4) — adds two MANDATORY fields to the existing WorkflowStep primitive when `action='invoke_host_llm'`:

- `expected_output_schema` — typed JSON schema (PNC-aligned per §4 F-10 + ADR-012). Declared at Workflow author time.
- `output_check_predicate` — typed predicate (PNC parser). Evaluated post-LLM-response.

These fields are NOT a new §2 primitive. They extend the existing `WorkflowStep` primitive (`../primitives/step.md`). Per F5, no new primitive materialized unless v2+ canon authorizes.

Cross-refs:
- `../primitives/step.md` (host primitive)
- `../primitives/workflow.md` (parent)
- `../primitives/engine-event.md` (event substrate)

## Edge cases

- **LLM returns valid JSON but predicate fails on a value** → routes via `on_failure` per §6.5; predicate failure-reason logged to DecisionProvenance per ADR-007 + §2.9.
- **LLM returns malformed JSON** → schema-validator failure; same `on_failure` route.
- **Schema declared but predicate omitted** → schema-only validation is allowed (predicate is optional belt-and-suspenders; canon does NOT require predicate, only schema is mandatory per §12.9 row B7). Specific predicate-optional-vs-required policy NOT specified in canon (gap per F2; future ADR may codify).
- **Race: concurrent step fires same Workflow** → coordination handled at B13 (ConcurrencyCoordinator); B7 is per-step-per-execution scoped, no cross-step state.
- **Schema evolution mid-Workflow** → schema is captured at Workflow registration (W-hash content-addressed per §14.13.2); change requires new Workflow version.

## Telemetry

Events emitted by B7 (all from canon §3.2 catalog):
- `precondition_check` (#11 per §3.2) — pre-LLM-invocation gate.
- `postcondition_check` (#12 per §3.2) — post-LLM-response gate.
- `step_completed` (#6) — when both gates pass.

Failure side: failure events routed via canon `on_failure` 5-set per §6.5 (no new failure-event invented here).

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Pattern-detection precision input (canon §14.9 leading metric "Pattern-detection precision (founder approval rate of proposed Workflows) ≥75%") — pre/post gating raises proposal quality.
- Pre/post gate pass-rate (NOT specified in canon as a tracked metric; runtime implementation choice per F2; future ADR may codify a per-block leading indicator).

## Dependencies

- **Primitives** (cross-refs `../primitives/*.md`): `step`, `workflow`, `engine-event`, `decision-provenance`, `execution-result`.
- **Events** (cross-refs `../events/*.md`): `precondition_check`, `postcondition_check`, `step_completed`, `step_started`.
- **Surfaces** (cross-refs `../surfaces/*.md`): `run` (B7 fires inside RUN surface), `audit` (persists pre/post events).
- **Hardstops that fire here** (cross-refs `../hardstops/HS-*.md`): HS-4 (audit log unwritable; if pre/post events fail to persist, fail-closed per canon §6.9.4).
- **Pillars**: P2 (pre/post validation), P12 (deterministic surface around stochastic core).
- **ADRs**: ADR-012 (PNC typed predicates — the parser B7 uses), ADR-007 (DecisionProvenance schema), ADR-005 (host-LLM dispatch boundary).

## References

- NATIVE-ENGINE.md §12.9 row B7 (founder voice round 3 + reverse-engineered architecture).
- NATIVE-ENGINE.md §14.15.2 rank 2 (outcome-first ordering — B7 = "every LLM call is checked").
- NATIVE-ENGINE.md §10.2 P2 (pre/post intent-specifics validation per LLM node).
- NATIVE-ENGINE.md §12.14 P12 (deterministic surface around stochastic core — B7's philosophical anchor).
- NATIVE-ENGINE.md §3.2 events #11 `precondition_check`, #12 `postcondition_check`, #6 `step_completed`.
- NATIVE-ENGINE.md §6.5 on_failure machinery (canon fail-mode B7 uses; no fail-open invention per F3).
- Q22 (§12.15) — every-LLM-bearing-step gate v1; opt-out v2.
