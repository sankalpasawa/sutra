---
part-id: approval_denied
bucket: events
template: L9-event-spec
parity-source: §3.2 row #17
parity-source-sha256: e28d7e28e742125e1fa42a4735d8d695510312eab2f62bd346f4b2ae7c6c87ed
status: DRAFT v1
authored: 2026-05-09
---

# approval_denied

## Purpose

Signals that founder utterance `reject E-<id> <reason>` (per §3.4) has been parsed (per §3.2 row #17). The Execution does NOT resume; its lifecycle proceeds to a terminal state via the Workflow's `failure_policy` (per §6.5 + ADR-011).

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "approval_denied",
  "source": "/native/runtime/approval-parser",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "execution_id": "<uuid>",
    "reason": "<sanitized reason string>",
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #17: `execution_id`, `reason`.

## Emitter

Approval parser (exclusive emitter — §3.4 utterance parsing).

## Consumers

- AUDIT surface — persists per ADR-013.
- LiteExecutor — routes the denied Execution per Workflow `failure_policy` (rollback / escalate / pause / abort / continue per ADR-011 5-set); the specific routing on denial vs. routine step failure is not separately enumerated in canon — runtime implementation choice; likely routes via `failure_policy='abort'` semantic to `workflow_failed` (#4).
- Pending-approval ledger writer — clears `user-kit/pending-approvals/E-<id>.json`.
- Telemetry sink (§5.6).
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, executor, ledger writer.

## Ordering invariants

- Always preceded by `approval_requested` (#15) for the same `execution_id`.
- Mutually exclusive with `approval_granted` (#16) for the same `execution_id`.
- Causal predecessor of a terminal event for the Execution per I-14 (typically `workflow_failed` #4; `workflow_escalated` #24 or `workflow_rollback_started` #19 also possible per `failure_policy`).

## Replayability

- **Idempotent on replay**: re-fire emits `approval_already_handled` (#18).
- **Audit-critical**: required to reconstruct denial reason.
- **Fail-closed on emission failure** (per HS-4): no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #17.
- NATIVE-ENGINE.md §3.4 Approval utterances (`reject E-<id> <reason>`).
- NATIVE-ENGINE.md §6.5 on_failure machinery.
- ADR-009 — requires_approval semantics.
- ADR-011 — failure_policy enum.
- ADR-013 — 3-channel audit durability.
- ../events/approval_requested.md
- ../events/approval_already_handled.md
- ../hardstops/HS-4-audit-unwritable.md
