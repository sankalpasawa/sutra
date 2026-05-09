---
part-id: workflow_rollback_started
bucket: events
template: L9-event-spec
parity-source: §3.2 row #19
parity-source-sha256: 15fbacd1b0e3d93d63072cbdae987122da84b9eff91d63a6ebb2529ec50a6e24
status: DRAFT v1
authored: 2026-05-09
---

# workflow_rollback_started

## Purpose

Signals that `failure_policy='rollback'` was initiated for an Execution (per §3.2 row #19 + §6.5 + ADR-011). Steps will be compensated in reverse order. Per I-14 this is NOT a terminal event — the Execution proceeds to either `workflow_rollback_complete` (#22) or `workflow_rollback_partial` (#23) as the terminal.

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "workflow_rollback_started",
  "source": "/native/runtime/lite-executor",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "execution_id": "<uuid>",
    "snapshot_ref": "<DataRef to pre-execution snapshot>",
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #19: `execution_id`, `snapshot_ref`.

## Emitter

LiteExecutor (exclusive emitter). Fires when:
1. A step fails AND `step.on_failure='rollback'` (per ADR-011 5-set), OR
2. `postcondition_check` (#11) returns false AND Workflow `failure_policy='rollback'`.

## Consumers

- AUDIT surface — persists per ADR-013.
- LiteExecutor compensator — sequences `step_compensated` (#20) / `step_compensation_failed` (#21) events in reverse step order.
- Telemetry sink (§5.6) — rollback-event count.
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, executor compensator.

## Ordering invariants

- Always preceded by `workflow_started` (#2) for the same `execution_id`.
- Per I-14, NOT a terminal event — the Execution terminates via either `workflow_rollback_complete` (#22) or `workflow_rollback_partial` (#23).
- Causal predecessor of zero-or-more `step_compensated` (#20) / `step_compensation_failed` (#21) events.

## Replayability

- **Idempotent on replay**: informational; the `snapshot_ref` is the durable source of truth for rollback target state.
- **Audit-critical**: required to reconstruct rollback initiation point.
- **Fail-closed on emission failure** (per HS-4): no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #19.
- NATIVE-ENGINE.md §4 I-14 (terminal-event set — rollback-started is NOT terminal).
- NATIVE-ENGINE.md §6.5 on_failure machinery (rollback policy).
- ADR-011 — failure_policy enum.
- ADR-013 — 3-channel audit durability.
- ../events/step_compensated.md
- ../events/step_compensation_failed.md
- ../events/workflow_rollback_complete.md
- ../events/workflow_rollback_partial.md
- ../hardstops/HS-4-audit-unwritable.md
