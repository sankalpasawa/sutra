---
part-id: postcondition_check
bucket: events
template: L9-event-spec
parity-source: §3.2 row #11
parity-source-sha256: f4389cd5c9365dffedb13751e8de7c85c59e81e39ad4f8b1d370f15ac153b09c
status: DRAFT v1
authored: 2026-05-09
---

# postcondition_check

## Purpose

Signals that a Workflow's `postconditions` were evaluated (per §3.2 row #11 + ADR-012). Emitted once per predicate in `Workflow.postconditions`, after the final step's `step_completed` (#6) and before terminal `workflow_completed` (#3).

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "postcondition_check",
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

Required payload fields per §3.2 row #11: `wf_id`, `predicate_id`, `result`.

## Emitter

LiteExecutor (exclusive emitter) per ADR-012. Fires after the final step's `step_completed` (#6).

## Consumers

- AUDIT surface — persists per ADR-013.
- LiteExecutor — gating signal: ALL predicates must return `result=true` before `workflow_completed` (#3) fires.
- Telemetry sink (§5.6) — postcondition-evaluation count.
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, executor terminal-state gate.

## Ordering invariants

- Always preceded by final `step_completed` (#6) for the Execution.
- Causal predecessor of `workflow_completed` (#3) when ALL predicates pass.
- If any predicate returns `result=false`, the Workflow's `failure_policy` engages (§6.5): `workflow_failed` (#4), `workflow_escalated` (#24), `workflow_rollback_started` (#19), `step_paused` (#7), or `abort` per ADR-011 5-set.

## Replayability

- **Idempotent on replay**: predicate evaluation is deterministic.
- **Audit-critical**: required to reconstruct exit-gate decisions.
- **Fail-closed on emission failure** (per HS-4): no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #11.
- NATIVE-ENGINE.md §2.3 Workflow (postconditions field).
- NATIVE-ENGINE.md §6.5 on_failure machinery.
- ADR-011 — failure_policy enum.
- ADR-012 — typed preconditions/postconditions.
- ADR-013 — 3-channel audit durability.
- ../primitives/workflow.md
- ../hardstops/HS-4-audit-unwritable.md
