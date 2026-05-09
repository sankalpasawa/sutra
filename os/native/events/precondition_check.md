---
part-id: precondition_check
bucket: events
template: L9-event-spec
parity-source: §3.2 row #10
parity-source-sha256: 92572534840aab12bd9e26f8e1819d776326d072530792aefa31671d549135e0
status: DRAFT v1
authored: 2026-05-09
---

# precondition_check

## Purpose

Signals that a Workflow's `preconditions` were evaluated (per §3.2 row #10 + ADR-012 typed predicates). Emitted once per predicate in `Workflow.preconditions`, before Execution may enter `running` (gates `workflow_started` #2).

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "precondition_check",
  "source": "/native/runtime/lite-executor",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "wf_id": "<W-hash>",
    "predicate_id": "<predicate-id>",
    "result": true,
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #10: `wf_id`, `predicate_id`, `result`. `result` is boolean.

## Emitter

LiteExecutor (exclusive emitter) per ADR-012. Fires before `workflow_started` (#2) — exactly once per predicate in `Workflow.preconditions`.

## Consumers

- AUDIT surface — persists per ADR-013.
- LiteExecutor — gating signal: ALL predicates must return `result=true` before `workflow_started` (#2) fires.
- Telemetry sink (§5.6) — predicate-evaluation count.
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, executor gate.

## Ordering invariants

- Always emitted AFTER `routing_decision` (#1) for the same `wf_id`.
- Always emitted BEFORE `workflow_started` (#2) for the same Execution.
- If any predicate returns `result=false`, Execution does NOT enter `running`; `workflow_failed` (#4) fires with `failure_reason` referencing the failed predicate id.

## Replayability

- **Idempotent on replay**: predicate evaluation is deterministic over the input bindings; replay produces identical result.
- **Audit-critical**: required to reconstruct gate decisions for replay.
- **Fail-closed on emission failure** (per HS-4): no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #10.
- NATIVE-ENGINE.md §2.3 Workflow (preconditions field).
- ADR-012 — typed preconditions/postconditions (Predicate Non-Compliance pattern).
- ADR-013 — 3-channel audit durability.
- ../primitives/workflow.md
- ../hardstops/HS-4-audit-unwritable.md
