---
part-id: policy_decision
bucket: events
template: L9-event-spec
parity-source: §3.2 row #8
parity-source-sha256: c25c864d2e628913c234133fb5bb95763d69e7ae8c52f797acbc5fb050f431e8
status: DRAFT v1
authored: 2026-05-09
---

# policy_decision

## Purpose

Signals that PolicyDispatcher emitted a deny/allow/pause/escalate decision for a scope (per §3.2 row #8). Carries `policy_id` and `policy_version` (per I-9 + F-8 — every governance hook emits DecisionProvenance with policy versioning).

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "policy_decision",
  "source": "/native/runtime/policy-dispatcher",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "policy_id": "<policy-id>",
    "policy_version": "<semver>",
    "scope": "WORKFLOW | STEP | HOOK | TENANT | CUTOVER",
    "outcome": "allow | deny | pause | escalate",
    "reason": "<sanitized reason>",
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #8: `policy_id`, `policy_version`, `outcome`. `scope` follows §2.9 DecisionProvenance enum; `outcome` follows §2.9 enum {`allow`, `deny`, `pause`, `escalate`}. `reason` is sanitized (no colons / newlines per §2.9).

## Emitter

PolicyDispatcher.evaluate (exclusive emitter — §3.1 Engine API). Every consequential policy evaluation emits one `policy_decision` event AND one DecisionProvenance row (the latter is the durable trace; the event surfaces in the EngineEvent stream).

## Consumers

- AUDIT surface — persists per ADR-013 (DecisionProvenance JSONL is the canonical surface; EngineEvent stream is a parallel surface).
- LiteExecutor — when `outcome='deny'` or `outcome='pause'`, halts step dispatch.
- Telemetry sink (§5.6) — per-policy decision counts.
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, executor, escalation router.

## Ordering invariants

- May be emitted at any point in an Execution lifecycle; not bound to a specific predecessor event.
- When `scope='WORKFLOW'` with `outcome='deny'`: must precede `workflow_failed` (#4) for the affected Execution.
- When `scope='STEP'` with `outcome='pause'`: must precede `step_paused` (#7) for the affected step.

## Replayability

- **Idempotent on replay**: informational; the durable record is DecisionProvenance (§2.9), not this event.
- **Audit-critical**: pairs with DecisionProvenance per I-7 + I-9 (every governance hook emits DecisionProvenance carrying `policy_id` AND `policy_version`).
- **Fail-closed on emission failure** (per HS-4): emission failure fires HS-4; governance hooks BLOCK; no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #8.
- NATIVE-ENGINE.md §2.9 DecisionProvenance.
- NATIVE-ENGINE.md §3.1 Engine API (PolicyDispatcher.evaluate).
- NATIVE-ENGINE.md §4 I-7 (DecisionProvenance per consequential decision), I-9 (policy_id + policy_version), I-17.
- ADR-007 — DecisionProvenance schema.
- ADR-013 — 3-channel audit durability.
- ../primitives/decision-provenance.md
- ../hardstops/HS-4-audit-unwritable.md
