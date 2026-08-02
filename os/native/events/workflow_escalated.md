---
part-id: workflow_escalated
bucket: events
template: L9-event-spec
parity-source: §3.2 row #24
parity-source-sha256: 2798c68392775473f7f05bdf49586a6ef38c93a0b36d61e3c65f7ca42e7ba4bf
status: DRAFT v1
authored: 2026-05-09
---

# workflow_escalated

## Purpose

Signals that `failure_policy='escalate'` was triggered for an Execution (per §3.2 row #24 + §6.5 + ADR-011). The Execution is routed to a founder channel for operator HITL; no further automated step dispatch proceeds until the escalation is resolved.

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "workflow_escalated",
  "source": "/native/runtime/lite-executor",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "execution_id": "<uuid>",
    "channel": "<founder-channel-id>",
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #24: `execution_id`, `channel`. The `channel` value space (e.g., slack/email/in-session) is not enumerated in canon §3.2 — runtime implementation choice.

## Emitter

LiteExecutor (exclusive emitter). Fires when a step fails AND `step.on_failure='escalate'` (per ADR-011 5-set: rollback/escalate/pause/abort/continue).

## Consumers

- AUDIT surface — persists per ADR-013.
- Founder notification channel — receives the escalation per `channel` field.
- LiteExecutor — Execution awaits founder HITL; further automated dispatch suspended.
- Telemetry sink (§5.6) — escalation count (alerting signal).
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, founder notification channel, executor.

## Ordering invariants

- Always preceded by `workflow_started` (#2) for the same `execution_id`.
- The Execution's lifecycle resolves via founder HITL signal (resume utterance form not enumerated in canon §3.4 for escalation; runtime implementation choice).

## Replayability

- **Idempotent on replay**: informational; the durable record is the Execution row in `awaiting_escalation` (or equivalent state per implementation).
- **Audit-critical**: required for founder HITL trail.
- **Fail-closed on emission failure** (per HS-4): no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #24.
- NATIVE-ENGINE.md §6.5 on_failure machinery (escalate policy).
- ADR-011 — failure_policy enum.
- ADR-013 — 3-channel audit durability.
- ../primitives/workflow.md
- ../hardstops/HS-4-audit-unwritable.md
