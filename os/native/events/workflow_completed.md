---
part-id: workflow_completed
bucket: events
template: L9-event-spec
parity-source: §3.2 row #3
parity-source-sha256: 8a25aa2cf81f0e9ad0783cde9e92ae885cdac994e3b5dbae759c1cc9dcb20be1
status: DRAFT v1
authored: 2026-05-09
---

# workflow_completed

## Purpose

Signals that an Execution has entered the terminal `success` state (per §3.2 row #3). One of the three terminal events allowed for any Workflow Execution per I-14 (the other two: `workflow_failed`, `approval_requested` transitioning to `awaiting_approval`).

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "workflow_completed",
  "source": "/native/runtime/lite-executor",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "execution_id": "<uuid>",
    "results_ref": "<DataRef pointer to results artifact>",
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #3: `execution_id`, `results_ref`. Per §2.6 ExecutionResult invariants, `ExecutionResult.failure_reason` is null on the producing Execution (I-4).

## Emitter

LiteExecutor (exclusive emitter). Fires after the final step's `step_completed` (#6) returns successfully AND `postcondition_check` (#11) passes for all Workflow postconditions (per ADR-012 typed predicates).

## Consumers

- AUDIT surface — persists to DecisionProvenance JSONL per ADR-013.
- B9 Closed-Loop Artifact — `results_ref` enters the artifact catalog for downstream lineage.
- Cadence scheduler — closes the firing window for cadence-triggered Executions (per ADR-017).
- Telemetry sink (§5.6) — per-tenant success-count for fleet analytics.
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface (always persists), B9-artifact-registration.

## Ordering invariants

- Exactly one terminal event per `execution_id` per I-14; if `workflow_completed` is emitted, neither `workflow_failed` nor `workflow_rollback_*` may follow for the same `execution_id`.
- Always emitted AFTER the final `step_completed` (#6) AND `postcondition_check` (#11) for the Workflow.
- Causal predecessor: `workflow_started` (#2) for the same `execution_id`.

## Replayability

- **Idempotent on replay**: emission is informational — the terminal state already exists in the Execution JSONL row.
- **Audit-critical**: required for replayable Execution reconstruction. Missing `workflow_completed` against an Execution row in `success` indicates audit loss (operator HITL required).
- **Fail-closed on emission failure** (per HS-4): emission failure across all 3 channels fires HS-4; governance hooks BLOCK; no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #3.
- NATIVE-ENGINE.md §2.6 ExecutionResult.
- NATIVE-ENGINE.md §4 I-14 (terminal-event set), I-4 (failure_reason invariant).
- ADR-011 — failure_policy enum.
- ADR-012 — typed preconditions/postconditions.
- ADR-013 — 3-channel audit durability.
- ../primitives/execution-result.md
- ../primitives/engine-event.md
- ../hardstops/HS-4-audit-unwritable.md
