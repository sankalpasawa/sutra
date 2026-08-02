---
part-id: step_started
bucket: events
template: L9-event-spec
parity-source: §3.2 row #5
parity-source-sha256: 4ef195ab1aab916635bac5801a00d08f70f5f29b042c76d3ed358f3974b776ff
status: DRAFT v1
authored: 2026-05-09
---

# step_started

## Purpose

Signals that LiteExecutor dispatched step[i] of an Execution (per §3.2 row #5). Fired before any step effector (skill / action / host_llm invocation) runs.

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "step_started",
  "source": "/native/runtime/lite-executor",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "execution_id": "<uuid>",
    "step_index": 0,
    "host": "<claude | codex | null>",
    "timeout_ms": 60000,
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #5: `step_index`, `host?`, `timeout_ms`. `host` may be null for non-`invoke_host_llm` actions (per §5.1 host-llm effector boundary).

## Emitter

LiteExecutor (exclusive emitter). Fires per ADR-011 / I-3 per WorkflowStep dispatch, after the step's `skill_ref` XOR `action` resolves and before any effector subprocess spawns or skill invocation runs.

## Consumers

- AUDIT surface — persists per ADR-013.
- Per-step timeout watchdog (§6.7) — starts timer keyed to `execution_id + step_index`.
- Telemetry sink (§5.6) — step-level latency baseline.
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, timeout watchdog.

## Ordering invariants

- Always emitted AFTER `workflow_started` (#2) for the same `execution_id`.
- Causal predecessor of `step_completed` (#6) OR `step_paused` (#7) OR `step_compensated` (#20) OR `step_compensation_failed` (#21) for the same `step_index`.
- For each `step_index`, at most one `step_started` per Execution run (compensation runs are separate ordering).

## Replayability

- **Idempotent on replay**: informational.
- **Audit-critical**: required to reconstruct step-level lineage. Missing `step_started` for a step with `step_completed` indicates audit loss.
- **Fail-closed on emission failure** (per HS-4): emission failure across 3 channels fires HS-4; no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #5.
- NATIVE-ENGINE.md §2.4 WorkflowStep.
- NATIVE-ENGINE.md §4 I-3 (skill_ref XOR action).
- NATIVE-ENGINE.md §5.1 host-llm effector boundary.
- NATIVE-ENGINE.md §6.7 per-step timeout.
- ADR-005 — host-llm contract.
- ADR-011 — failure_policy enum.
- ADR-013 — 3-channel audit durability.
- ../primitives/workflow-step.md
- ../hardstops/HS-4-audit-unwritable.md
