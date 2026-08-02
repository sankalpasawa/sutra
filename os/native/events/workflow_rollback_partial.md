---
part-id: workflow_rollback_partial
bucket: events
template: L9-event-spec
parity-source: §3.2 row #23
parity-source-sha256: f6ba48474bb3a00b26939fec53005e19f7a3b46e1dffaf5150a4b4ef53f63b4d
status: DRAFT v1
authored: 2026-05-09
---

# workflow_rollback_partial

## Purpose

Signals that some steps could not be compensated and the Execution is in a partial post-rollback state (per §3.2 row #23 + §6.5). Carries the list of un-compensated step indexes for operator HITL recovery. Per §6.5 this is one of the rollback-terminal events; I-14 strict reading lists only `workflow_completed` / `workflow_failed` / `approval_requested` as terminal — known canon ambiguity.

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "workflow_rollback_partial",
  "source": "/native/runtime/lite-executor",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "execution_id": "<uuid>",
    "uncompensated_steps": [0, 2],
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #23: `execution_id`, `uncompensated_steps[]`.

## Emitter

LiteExecutor compensator (exclusive emitter). Fires when one or more `step_compensation_failed` (#21) events exist AND the compensator has exhausted the reverse step list.

## Consumers

- AUDIT surface — persists per ADR-013.
- Operator HITL surface — surfaces the un-compensable steps for manual recovery.
- Telemetry sink (§5.6) — partial-rollback count (alerting signal).
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, operator HITL surface, alerting.

## Ordering invariants

- Always preceded by `workflow_rollback_started` (#19) for the same `execution_id`.
- At least one `step_compensation_failed` (#21) precedes this event for the same `execution_id`.
- Mutually exclusive with `workflow_rollback_complete` (#22) for the same `execution_id`.

## Replayability

- **Idempotent on replay**: informational; the `uncompensated_steps[]` list at this event is the durable record for HITL.
- **Audit-critical**: required for operator recovery of un-compensable state.
- **Fail-closed on emission failure** (per HS-4): no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #23.
- NATIVE-ENGINE.md §4 I-14 (terminal-event set — known canon ambiguity).
- NATIVE-ENGINE.md §6.5 on_failure machinery (rollback policy).
- ADR-011 — failure_policy enum.
- ADR-013 — 3-channel audit durability.
- ../events/workflow_rollback_started.md
- ../events/step_compensation_failed.md
- ../events/workflow_rollback_complete.md
- ../hardstops/HS-4-audit-unwritable.md
