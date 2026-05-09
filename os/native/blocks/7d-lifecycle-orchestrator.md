---
part-id: 7d
bucket: blocks
template: L8-feature-spec
parity-source: §12.6 row 7d + §14.15.2 rank 3 + §10.2 P8 + §12.3 row 7
parity-source-sha256: ad8cc0f44d6046048139e1716a8c412b75996ddd29043867efed12678a44ec71
status: DRAFT v1
authored: 2026-05-09
---

# 7d: Lifecycle Orchestrator

## 1-line summary

Sutra's 8-phase task lifecycle (OBJECTIVE → OBSERVE → SHAPE → PLAN → EXECUTE → MEASURE → OPERATIONALIZE → LEARN per D30a) becomes Native's first-class Execution-state phases — picked work runs through analysis → decision → build → operationalize → auto-run as one orchestrated arc.

## Scope (in / out)

**In scope**:
- Run picked work through the Sutra 8-phase lifecycle (D30a OBJECTIVE / OBSERVE / SHAPE / PLAN / EXECUTE / MEASURE / OPERATIONALIZE / LEARN per §12.6 row 7d).
- ExecutionResult gains `lifecycle_phase` enum surface (per Q16 default 2026-05-09 — Sutra's 8-phase becomes Native canon).
- Once a piece of work reaches OPERATIONALIZE, it transitions to autonomous-on-trigger (gated v1 per Q13 — founder approval each cycle).
- Operationalized work re-fires via existing cadence scheduler (§6.4 / ADR-017); no new scheduler invented (per F2).

**Out of scope (v1)**:
- Fully autonomous auto-run (Q13 defers to v2+ once trust signal lands — ≥30d clean cadence per cycle).
- Cross-Workflow lifecycle composition (one lifecycle = one Workflow chain v1; multi-Workflow projects deferred to Project primitive per §12.3 row 1).
- Phase-skipping (lifecycle is sequential v1; out-of-order phases not specified in canon → gap per F2; future ADR may codify).

## User outcome

> "I pick work + it runs analysis → decide → build → operationalize → auto-run" (per §14.15.2 rank 3).

The operator picks a piece of work and Native carries it through the full lifecycle without dropping context between phases. Once operationalized, the work runs autonomously (gated per cycle v1; trust-graduated v2+). This is the "magic" outcome flagged at §14.15.2 rank 3.

## UX flow (narrative; terminal + audit log)

1. Operator picks a piece of work (utterance or explicit Workflow trigger).
2. Lifecycle orchestrator initializes ExecutionResult with `lifecycle_phase=OBJECTIVE`.
3. Phase OBJECTIVE captures intent (per B1 Intent Layer) → emits artifact → transitions to OBSERVE.
4. Phase OBSERVE gathers context (per 7a context-structuring) → emits artifact → transitions to SHAPE.
5. Phase SHAPE decomposes (per B2 Decomposition Layer) → emits artifact → transitions to PLAN.
6. Phase PLAN constructs the problem (per B11 PromptBuilder) → emits artifact → transitions to EXECUTE.
7. Phase EXECUTE runs the Workflow steps (host-LLM dispatch per §5.1) → emits per-step artifacts → transitions to MEASURE.
8. Phase MEASURE evaluates pre/post predicates (per B7) → emits result → transitions to OPERATIONALIZE if green.
9. Phase OPERATIONALIZE registers the Workflow for cadence-fire (§6.4 / ADR-017); founder approval per Q13.
10. Phase LEARN closes the loop (per B19 Learning Loop in r7) → captures systemic learnings → emits final Artifact.
11. Once operationalized, Workflow re-fires per `TriggerSpec` (§2.5) on its cadence; each fire gets a fresh ExecutionResult while sharing parent lifecycle lineage via `parent_exec_id`.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Operator picks work via utterance OR explicit trigger | classifier routes → matched Workflow | ExecutionResult created with `lifecycle_phase=OBJECTIVE` and existing ExecutionResult terminal states (canon §4 I-5) remain unchanged |
| 2 | Lifecycle in phase N | phase N succeeds (artifact emitted, post-check passes) | transition to phase N+1; lifecycle_phase enum advances; `step_completed` (§3.2 #6) emitted at phase boundary |
| 3 | Lifecycle in phase N | phase N fails (predicate fails OR step errors) | routed through canon `on_failure` machinery per §6.5; lifecycle does NOT auto-skip to next phase (no canon authorization for skip per F2/F4) |
| 4 | Lifecycle reaches OPERATIONALIZE | Workflow has valid `TriggerSpec` per §2.5 | registered with CadenceScheduler per §6.4 / ADR-017; gated v1 by per-cycle founder approval per Q13 |
| 5 | Operationalized Workflow re-fires | trigger matches | new ExecutionResult spawned with `parent_exec_id` chain back to lifecycle root; canon terminal-state invariants (§4 I-5) preserved |

## Data model

Per §12.6 row 7d + Q16: ExecutionResult primitive (§2.6 / `../primitives/execution-result.md`) EXTENDS with `lifecycle_phase` enum field (D30a 8-phase). This is field-level extension; no new §2 primitive materialized (per F5).

Conceptual extension (per Q16 default 2026-05-09, founder-ratified):

```
ExecutionResult (extended) = {
  ...existing §2.6 fields,
  lifecycle_phase: 'OBJECTIVE' | 'OBSERVE' | 'SHAPE' | 'PLAN' | 'EXECUTE' | 'MEASURE' | 'OPERATIONALIZE' | 'LEARN'
}
```

Cross-refs:
- `../primitives/execution-result.md` (host)
- `../primitives/workflow.md` (lifecycle is a Workflow chain)
- `../primitives/trigger.md` (re-fire after OPERATIONALIZE)
- `../primitives/engine-event.md` (per-phase events)

## Edge cases

- **Lifecycle in OPERATIONALIZE phase but trigger never fires** → ExecutionResult sits in OPERATIONALIZE indefinitely; per-cycle approval gate per Q13 does not auto-revoke. Operator may manually advance to LEARN.
- **Lifecycle interrupted mid-phase** (process crash) → recovery per §6.8 canon (no new recovery semantics invented per F3).
- **Phase-N artifact persistence fails** → HS-4 audit-unwritable fires per canon §6.9 (cross-ref `../hardstops/HS-4-audit-unwritable.md`).
- **Operator wants to RE-RUN a single phase** → not specified in canon (gap per F2; future ADR may codify replay-from-phase semantics).
- **Two lifecycles racing to operationalize the same Workflow** → B13 ConcurrencyCoordinator handles (cross-ref `B13-multi-runtime-concurrency.md`).

## Telemetry

Events emitted by 7d (all from canon §3.2 catalog — no new event types invented per F3):
- `workflow_started` (#2) — at OBJECTIVE phase start.
- `step_started` (#5) / `step_completed` (#6) — per phase boundary.
- `artifact_registered` (#9) — per phase artifact.
- `workflow_completed` (#3) — at LEARN phase exit.
- `workflow_failed` (#4) — on lifecycle abort.

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Operator-Hours-Saved (N*) — lifecycle orchestrator is the primary OHS lever (auto-running operationalized work is direct hours saved).
- Founder weekly active sessions (canon §14.9 lagging) — lifecycle reduces context-switch friction.

## Dependencies

- **Primitives**: `execution-result`, `workflow`, `step`, `trigger`, `engine-event`, `decision-provenance`.
- **Events**: `workflow_started`, `step_started`, `step_completed`, `artifact_registered`, `workflow_completed`, `workflow_failed`.
- **Surfaces**: `run` (executes phases), `gate` (per-cycle approval per Q13), `audit` (persists per-phase events), `emerge` (LEARN phase may propose new Workflow per ADR-010).
- **Hardstops**: HS-1 (reflexive-check on mutating Sutra mid-lifecycle), HS-4 (audit log unwritable).
- **Blocks (downstream)**: B1 (OBJECTIVE phase consumes B1 Intent), B2 (SHAPE phase consumes B2 Decomposition), 7a (OBSERVE consumes 7a Context Structuring), B11 (PLAN consumes B11 PromptBuilder), B7 (MEASURE consumes B7 pre/post), B19 (LEARN consumes B19 Learning Loop).
- **Pillars**: P8 (Lifecycle is the unit of value), P14 (Outcomes drive design).
- **ADRs**: ADR-017 (cadence scheduler — used by OPERATIONALIZE), ADR-009 (approval gate — used per Q13).

## References

- NATIVE-ENGINE.md §12.6 row 7d (founder voice round 2 — autonomous mode + Sutra-lifecycle integration).
- NATIVE-ENGINE.md §14.15.2 rank 3 (outcome-first ordering — 7d = "lifecycle orchestrator").
- NATIVE-ENGINE.md §10.2 P8 (Lifecycle is the unit of value).
- NATIVE-ENGINE.md §12.3 row 7 (capability-7 → lifecycle orchestrator gap).
- NATIVE-ENGINE.md §6.4 cadence scheduling + ADR-017.
- NATIVE-ENGINE.md §6.5 on_failure (canon fail-mode 7d uses).
- D30a (Sutra 8-phase TASK-LIFECYCLE) — referenced by §12.6.
- Q13 (§12.4) — gated v1 per-cycle approval; autonomous v2+ once trust signal.
- Q16 (§12.7) — Sutra 8-phase becomes Native canon as ExecutionResult.lifecycle_phase.
