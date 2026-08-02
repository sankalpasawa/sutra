---
part-id: routing_decision
bucket: events
template: L9-event-spec
parity-source: §3.2 row #1
parity-source-sha256: 0deeccc31d016bd70212de65e66ebc8b503c0ccc4bbd942cfdce3fbb19580de1
status: DRAFT v1
authored: 2026-05-09
---

# routing_decision

## Purpose

Signals that the Router has selected (or rejected) a Workflow for an HSutraEvent (per §3.2 row #1). Emitted unconditionally for every HSutraEvent that reaches the Router — including no-match outcomes — so that every founder turn has a corresponding routing audit trail (per §5.3 H-Sutra event bus contract and ADR-015 agent_identity emission requirements).

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "routing_decision",
  "source": "/native/runtime/router",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "execution_id": null,
    "matched_workflow_id": "<W-hash or null>",
    "predicate_id": "<predicate-id or null>",
    "score": 0.0,
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required fields per §3.2 row #1 + §2.7 EngineEvent: `event_type`, `ts_ms`, `agent_identity`, `payload`. Required payload fields: `matched_workflow_id`, `predicate_id`, `score`. `execution_id` is null at routing time (no Execution exists yet — per §2.7 `execution_id: string | null`).

## Emitter

`Router.route(evt)` (sync, live path) and `Router.routeAsync(evt)` (latent — §8 OS-8). Both signatures from §3.1 Engine API. Router is the exclusive emitter of `routing_decision`.

## Consumers

- AUDIT surface — always persists, per §5.6 telemetry sink + ADR-013 3-channel durability (3-channel append + fsync).
- LiteExecutor — when `matched_workflow_id !== null`, consumes the decision and prepares Execution (precedes `workflow_started` #2).
- Pattern detector (EMERGE surface) — counts no-match events for k≥4 emergence detection (per ADR-010, §3.2 row #12 references).
- Consumer set not enumerated in canon §3.2; additional consumers are runtime implementation choice.

## Ordering invariants

- First event for any HSutraEvent that reaches the Router; no preceding event for the same event chain.
- When `matched_workflow_id !== null`: causal predecessor of `precondition_check` (#10) and `workflow_started` (#2) for the resulting Execution.
- When `matched_workflow_id === null`: terminal event for the HSutraEvent — no further events flow.

## Replayability

- **Idempotent on replay**: emission is informational; Router decisions are pure functions over the HSutraEvent + Workflow registry state at decision time.
- **Audit-critical**: every founder turn classified by H-Sutra must produce a `routing_decision` row; gaps indicate Router skip and require operator HITL.
- **Fail-closed on emission failure** (per canon HS-4): if append to DecisionProvenance JSONL fails across all 3 durability channels, HS-4 fires — governance hooks BLOCK; stderr beacon emits last-resort observability. No fail-open semantic.

## References

- NATIVE-ENGINE.md §3.2 row #1 (canonical event catalog entry).
- NATIVE-ENGINE.md §3.1 EngineEvent API (`Router.route`, `Router.routeAsync`).
- NATIVE-ENGINE.md §2.7 EngineEvent primitive.
- NATIVE-ENGINE.md §5.3 H-Sutra event bus.
- NATIVE-ENGINE.md §5.6 telemetry sink.
- ADR-013 — 3-channel audit durability + fsync semantics.
- ADR-015 — agent_identity chain emission.
- ../primitives/engine-event.md
- ../surfaces/route.md
- ../hardstops/HS-4-audit-unwritable.md
