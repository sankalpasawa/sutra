---
part-id: step_compensated
bucket: events
template: L9-event-spec
parity-source: §3.2 row #20
parity-source-sha256: c909aac40cc58b0e171917418b863a0ee7c07167241886a9bb5b54ee095a40f2
status: DRAFT v1
authored: 2026-05-09
---

# step_compensated

## Purpose

Signals that a single step's compensation completed successfully (per §3.2 row #20). Emitted within a `workflow_rollback_started` (#19) sequence, in reverse step order.

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "step_compensated",
  "source": "/native/runtime/lite-executor",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "execution_id": "<uuid>",
    "step_index": 0,
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #20: `step_index`.

## Emitter

LiteExecutor compensator (exclusive emitter). Fires per successfully-compensated step during rollback. Exact compensation effector binding (what "compensation" means for a given step) is governed by the WorkflowStep contract (§2.4) — runtime implementation choice; canon §3.2 does not enumerate compensation forms.

## Consumers

- AUDIT surface — persists per ADR-013.
- LiteExecutor compensator — sequences the next reverse-step compensation OR transitions to terminal `workflow_rollback_complete` (#22).
- Telemetry sink (§5.6).
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, executor sequencer.

## Ordering invariants

- Always preceded by `workflow_rollback_started` (#19) for the same `execution_id`.
- Within a rollback sequence: emitted in REVERSE step order (last-executed step compensated first).
- Causal predecessor of either the next `step_compensated` (#20) (next-reverse step) OR `workflow_rollback_complete` (#22) (final reverse step).

## Replayability

- **Idempotent on replay**: compensation effectors must themselves be idempotent for replay safety; the event itself is informational.
- **Audit-critical**: required to reconstruct partial-rollback state.
- **Fail-closed on emission failure** (per HS-4): no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #20.
- NATIVE-ENGINE.md §2.4 WorkflowStep.
- NATIVE-ENGINE.md §6.5 on_failure machinery (rollback policy).
- ADR-011 — failure_policy enum.
- ADR-013 — 3-channel audit durability.
- ../events/workflow_rollback_started.md
- ../events/step_compensation_failed.md
- ../hardstops/HS-4-audit-unwritable.md
