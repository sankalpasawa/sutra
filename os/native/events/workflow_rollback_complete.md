---
part-id: workflow_rollback_complete
bucket: events
template: L9-event-spec
parity-source: §3.2 row #22
parity-source-sha256: 7d14f51cbdd142a37ddd7ddfcd412746d63644e4394383f3ab848705fb54cfb1
status: DRAFT v1
authored: 2026-05-09
---

# workflow_rollback_complete

## Purpose

Signals that all steps were compensated and the Execution was restored to the rollback target state (per §3.2 row #22 + §6.5). One of the terminal events per the §6.5 rollback policy ("terminal `workflow_rollback_complete` or `_partial`"). Per I-14, terminal events are `workflow_completed` / `workflow_failed` / `approval_requested`-terminal — note: §6.5 names `workflow_rollback_complete` as a rollback-terminal but I-14 does NOT include it in the enumerated terminal set; this is a known canon ambiguity (runtime implementation choice in classifying I-14 strictly vs. recognizing §6.5 as the operative semantic).

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "workflow_rollback_complete",
  "source": "/native/runtime/lite-executor",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "execution_id": "<uuid>",
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #22: `execution_id`.

## Emitter

LiteExecutor compensator (exclusive emitter). Fires when ALL steps with `step_started` (#5) audit history have a corresponding `step_compensated` (#20) event, AND zero `step_compensation_failed` (#21) events exist for the Execution.

## Consumers

- AUDIT surface — persists per ADR-013.
- Telemetry sink (§5.6) — successful-rollback count.
- B9 Closed-Loop Artifact — purges or marks-rolled-back any artifacts produced by the compensated Execution (binding details runtime-specific; canon §3.2 does not enumerate).
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, B9 catalog.

## Ordering invariants

- Always preceded by `workflow_rollback_started` (#19) for the same `execution_id`.
- Mutually exclusive with `workflow_rollback_partial` (#23) for the same `execution_id`.
- All `step_compensated` (#20) events for the Execution precede this event.

## Replayability

- **Idempotent on replay**: informational; the Execution's restored state is the durable record.
- **Audit-critical**: required to confirm rollback finality.
- **Fail-closed on emission failure** (per HS-4): no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #22.
- NATIVE-ENGINE.md §4 I-14 (terminal-event set — known canon ambiguity re: rollback terminals).
- NATIVE-ENGINE.md §6.5 on_failure machinery (rollback policy).
- ADR-011 — failure_policy enum.
- ADR-013 — 3-channel audit durability.
- ../events/workflow_rollback_started.md
- ../events/step_compensated.md
- ../events/workflow_rollback_partial.md
- ../hardstops/HS-4-audit-unwritable.md
