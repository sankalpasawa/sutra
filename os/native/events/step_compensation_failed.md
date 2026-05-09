---
part-id: step_compensation_failed
bucket: events
template: L9-event-spec
parity-source: §3.2 row #21
parity-source-sha256: 703144088af367204c02b6c9baf62f6ccab259e763b55331822c903bb3f6dfd7
status: DRAFT v1
authored: 2026-05-09
---

# step_compensation_failed

## Purpose

Signals that a step's compensation itself failed during rollback (per §3.2 row #21). Records the un-compensated step; the Execution proceeds to terminal `workflow_rollback_partial` (#23) when one or more steps cannot be compensated.

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "step_compensation_failed",
  "source": "/native/runtime/lite-executor",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "execution_id": "<uuid>",
    "step_index": 0,
    "reason": "<sanitized reason string>",
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #21: `step_index`, `reason`.

## Emitter

LiteExecutor compensator (exclusive emitter). Fires when a compensation effector raises an error OR exceeds its timeout.

## Consumers

- AUDIT surface — persists per ADR-013.
- LiteExecutor compensator — drives the rollback toward terminal `workflow_rollback_partial` (#23) carrying the un-compensable step list.
- Telemetry sink (§5.6) — compensation-failure count (operator HITL signal).
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, executor compensator, operator HITL surface.

## Ordering invariants

- Always preceded by `workflow_rollback_started` (#19) for the same `execution_id`.
- Causal predecessor of `workflow_rollback_partial` (#23) for the Execution (one or more `step_compensation_failed` events implies the partial-terminal outcome).

## Replayability

- **Idempotent on replay**: informational; the un-compensable step list at terminal #23 is the durable record.
- **Audit-critical**: required for operator HITL diagnosis of un-compensable state.
- **Fail-closed on emission failure** (per HS-4): no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #21.
- NATIVE-ENGINE.md §6.5 on_failure machinery (rollback policy).
- ADR-011 — failure_policy enum.
- ADR-013 — 3-channel audit durability.
- ../events/workflow_rollback_started.md
- ../events/step_compensated.md
- ../events/workflow_rollback_partial.md
- ../hardstops/HS-4-audit-unwritable.md
