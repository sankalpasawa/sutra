---
part-id: step_completed
bucket: events
template: L9-event-spec
parity-source: §3.2 row #6
parity-source-sha256: 08b87ec37ecad6ce06bc6d6332caeb7c4bcae33ca5478479cdc036a392569eb8
status: DRAFT v1
authored: 2026-05-09
---

# step_completed

## Purpose

Signals that a step has returned successfully (per §3.2 row #6). The step's effector (skill / action / host_llm) returned without error and within `timeout_ms`.

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "step_completed",
  "source": "/native/runtime/lite-executor",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "execution_id": "<uuid>",
    "step_index": 0,
    "output_ref": "<DataRef pointer or null>",
    "duration_ms": 1234,
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #6: `step_index`, `output_ref`, `duration_ms`. `output_ref` is null when the step returns no artifact (read-only or telemetry-only steps).

## Emitter

LiteExecutor (exclusive emitter). Fires after step effector returns success AND the per-step timeout watchdog (§6.7) is cleared.

## Consumers

- AUDIT surface — persists per ADR-013.
- B9 Closed-Loop Artifact — if `output_ref !== null`, downstream `artifact_registered` (#9) fires with `lineage_parent_id` referencing the prior `step_completed` chain.
- Telemetry sink (§5.6) — per-step latency.
- LiteExecutor itself — sequences next `step_started` (#5) for `step_index+1`, or `postcondition_check` (#11) if step was final.
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, executor sequencer, B9-artifact-registration.

## Ordering invariants

- Always preceded by `step_started` (#5) for the same `execution_id + step_index`.
- For each `step_index`, exactly one terminal step event per Execution run: `step_completed` OR `step_paused` (#7) OR a failure-routed event (per §6.5 on_failure machinery).
- Causal predecessor of either the next `step_started` (#5) (step_index+1) OR `postcondition_check` (#11) (for final step).

## Replayability

- **Idempotent on replay**: informational.
- **Audit-critical**: step lineage requires `step_completed` for B9 closed-loop artifact attribution.
- **Fail-closed on emission failure** (per HS-4): no fail-open semantic.

## References

- NATIVE-ENGINE.md §3.2 row #6.
- NATIVE-ENGINE.md §2.4 WorkflowStep.
- NATIVE-ENGINE.md §6.5 on_failure machinery.
- NATIVE-ENGINE.md §6.7 per-step timeout.
- ADR-011 — failure_policy enum.
- ADR-013 — 3-channel audit durability.
- ../primitives/workflow-step.md
- ../events/artifact_registered.md
- ../hardstops/HS-4-audit-unwritable.md
