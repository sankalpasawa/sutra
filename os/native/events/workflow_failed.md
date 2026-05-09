---
part-id: workflow_failed
bucket: events
template: L9-event-spec
parity-source: §3.2 row #4
parity-source-sha256: 6996477b28942a477df4289a3fec2eb1a7a331b9cd5198fbda475d1407642b99
status: DRAFT v1
authored: 2026-05-09
---

# workflow_failed

## Purpose

Signals that an Execution has entered the terminal `failed` state (per §3.2 row #4). One of three terminal events allowed per I-14. Fired when `step.on_failure='abort'` triggers OR a non-recoverable step error halts the Workflow before any rollback path opens (per §6.5).

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "workflow_failed",
  "source": "/native/runtime/lite-executor",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "execution_id": "<uuid>",
    "failure_reason": "<sanitized reason string>",
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #4: `execution_id`, `failure_reason`. Per I-4, `ExecutionResult.failure_reason` is non-null when state ∉ {success, declared_gap} — `workflow_failed` enforces that invariant in the audit trail.

## Emitter

LiteExecutor (exclusive emitter). Fires when:
1. A step throws non-recoverable error AND `step.on_failure='abort'` (per ADR-011 5-set: rollback/escalate/pause/abort/continue), OR
2. Pre-step terminal_check predicate (T1-T6) fails after Workflow.preconditions cleared, OR
3. Per-step timeout exceeded with `on_failure='abort'` (per §6.7).

## Consumers

- AUDIT surface — persists to DecisionProvenance JSONL per ADR-013.
- Telemetry sink (§5.6) — per-tenant failure-count.
- L4-COMMITMENT engine — checks if failure missed a Charter obligation; emits `commitment_broken` (#25) if so (per I-16, ADR-012).
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface (always persists), commitment evaluation.

## Ordering invariants

- Exactly one terminal event per `execution_id` per I-14; mutually exclusive with `workflow_completed` (#3), `workflow_rollback_*` (#22, #23), and `approval_requested`-terminal (#15 transitioning to `awaiting_approval`) for the same `execution_id`.
- Always preceded by `workflow_started` (#2) for the same `execution_id`.
- May be followed by `commitment_broken` (#25) per ADR-012 if Charter obligation missed.

## Replayability

- **Idempotent on replay**: informational only.
- **Audit-critical**: required for terminal-state reconstruction; orphaned Execution rows in `failed` state without `workflow_failed` event indicate audit loss.
- **Fail-closed on emission failure** (per HS-4): emission failure fires HS-4; no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #4.
- NATIVE-ENGINE.md §4 I-14 (terminal-event set), I-4 (failure_reason invariant), I-16 (commitment resolution).
- NATIVE-ENGINE.md §6.5 on_failure machinery.
- NATIVE-ENGINE.md §6.7 per-step timeout.
- ADR-011 — failure_policy enum.
- ADR-013 — 3-channel audit durability.
- ../primitives/execution-result.md
- ../events/commitment_broken.md
- ../hardstops/HS-4-audit-unwritable.md
