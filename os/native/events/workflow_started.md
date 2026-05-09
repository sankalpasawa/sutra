---
part-id: workflow_started
bucket: events
template: L9-event-spec
parity-source: §3.2 row #2
parity-source-sha256: 45bb51ce2f1a95f7483f527ee8380b4a14c75cba2c70966b9ebbb4256715b497
status: DRAFT v1
authored: 2026-05-09
---

# workflow_started

## Purpose

Signals that a Workflow's Execution has entered the `running` state. Fired by LiteExecutor after the Workflow's `preconditions` (per ADR-012) clear and before step[0] dispatches.

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "workflow_started",
  "source": "/native/runtime/lite-executor",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "execution_id": "<uuid>",
    "workflow_id": "<W-hash>",
    "trigger_event_id": "<event-id or null>",
    "tenant_id": "<tenant-id>",
    "agent_identity": "<claude | codex | operator>",
    "preconditions_cleared": ["<predicate-id>", ...],
    "ts_ms": 1778336529000
  }
}
```

Required fields:
- `type`, `id`, `time`, `data.execution_id`, `data.workflow_id` (always present).
- `data.trigger_event_id` (null only when Workflow started manually via `run` CLI subcommand).
- `data.tenant_id` (always present — multi-tenant invariant per I-8).

## Emitter

LiteExecutor (single emitter — exclusive owner). Fires after:
1. Workflow `id` resolved via SkillEngine.
2. `preconditions` evaluated and cleared (per ADR-012 typed predicates).
3. Tenant context bound; `tenant_context_id` non-null when `custody_owner !== null` (per I-8 fail-closed).
4. Execution row inserted to executions JSONL with `state='running'`.

## Consumers

- **AUDIT surface**: persists to `.enforcement/native-execution-events.jsonl` (3-channel durability per ADR-013).
- **B9 Closed-Loop Artifact**: lineage_parent_id resolution for downstream step-emitted Artifacts.
- **Pattern detector (EMERGE surface)**: counts workflow_started by Workflow id for k=4 emergence detection (per ADR-010).
- **Cadence scheduler**: marks cadence-triggered Workflows as having fired (per ADR-017).
- **Telemetry sink (§5.6)**: per-tenant Execution count for fleet analytics.
- **Tenant isolation engine**: tagged with `tenant_id` for cross-tenant audit.

## Ordering invariants

- Always emitted BEFORE first `step_started` (#5) for the same `execution_id`.
- Always emitted AFTER `routing_decision` (#1) that matched the Workflow.
- Always emitted AFTER `precondition_check` (#10) clearing the Workflow's preconditions.
- Causal predecessor of `workflow_completed` (#3), `workflow_failed` (#4), or `workflow_rollback_started` (#19) for the same `execution_id` (exactly one terminal event per execution_id; ADR-011).

## Replayability

- **Idempotent on replay**: emission is informational only — no side effects on replay (state already in Execution JSONL row).
- **Audit-critical**: required for replayable Execution reconstruction. If `workflow_started` is missing from audit log but Execution JSONL row exists, the row is considered orphaned (operator HITL required).
- **No retry semantics**: if emission fails (all 3 channels per HS-4), Execution still proceeds; failure beacon emitted via stderr; audit consistency restored on next successful emit.

## References

- NATIVE-ENGINE.md §3.2 row #2 (canonical event catalog entry).
- NATIVE-ENGINE.md §3.1 EngineEvent type signature.
- NATIVE-ENGINE.md §2.7 EngineEvent primitive (`sutra/os/native/primitives/engine-event.md`).
- ADR-013 — 3-channel audit durability + fsync semantics.
- ADR-011 — failure_policy enum (rollback/escalate/pause/abort/continue).
- ADR-012 — typed preconditions/postconditions (Predicate Non-Compliance pattern).
- HS-4 — DecisionProvenance log unwritable hardstop.
