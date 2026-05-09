---
part-id: step_paused
bucket: events
template: L9-event-spec
parity-source: §3.2 row #7
parity-source-sha256: 4b71636e75872ac2e4388d4ef0f40aaa4224e2e30eb3c0e52e6025bdbe7dc1b1
status: DRAFT v1
authored: 2026-05-09
---

# step_paused

## Purpose

Signals that `failure_policy='pause'` triggered at a step (per §3.2 row #7 + §6.5). The step did not complete; the Execution is suspended and a queue entry persists for resumption on signal.

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "step_paused",
  "source": "/native/runtime/lite-executor",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "execution_id": "<uuid>",
    "step_index": 0,
    "pause_reason": "<sanitized reason string>",
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #7: `step_index`, `pause_reason`.

## Emitter

LiteExecutor (exclusive emitter). Fires when `step.on_failure='pause'` triggers AND a queue entry is persisted for later resume (per §6.5 pause policy: "Emit `step_paused`; persist queue entry; resume on signal").

## Consumers

- AUDIT surface — persists per ADR-013.
- Resume signal handler — watches for resume utterance / re-dispatch; signal-name not specified in canon §3.2 (runtime implementation choice).
- Telemetry sink (§5.6) — per-tenant paused-execution count.
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, resume queue.

## Ordering invariants

- Always preceded by `step_started` (#5) for the same `execution_id + step_index`.
- Non-terminal for the Execution: the Execution may still produce a terminal event (`workflow_completed`, `workflow_failed`, or `workflow_rollback_*`) after resume.
- `step_paused` for a given `step_index` may be followed (on resume) by either `step_completed` (#6) or a re-fire of `step_started` (#5) per implementation; canon does not specify resume semantics here.

## Replayability

- **Idempotent on replay**: informational; queue entry is the durable signal source, not the event.
- **Audit-critical**: required to identify Executions stuck in pause state.
- **Fail-closed on emission failure** (per HS-4): no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #7.
- NATIVE-ENGINE.md §6.5 on_failure machinery (pause policy).
- ADR-011 — failure_policy enum.
- ADR-013 — 3-channel audit durability.
- ../primitives/workflow-step.md
- ../hardstops/HS-4-audit-unwritable.md
