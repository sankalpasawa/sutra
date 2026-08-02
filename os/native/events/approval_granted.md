---
part-id: approval_granted
bucket: events
template: L9-event-spec
parity-source: §3.2 row #16
parity-source-sha256: b2451684e208c4c5b3fa59f7badd410fd003eac38b38a57fd043f5bf46698cb6
status: DRAFT v1
authored: 2026-05-09
---

# approval_granted

## Purpose

Signals that founder utterance `approve E-<id>` (per §3.4) has been parsed (per §3.2 row #16). Resumes the Execution from `awaiting_approval`; LiteExecutor proceeds with the gated step's `step_started` (#5) via `NativeEngine.resumeApproved(execId)` (§3.1).

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "approval_granted",
  "source": "/native/runtime/approval-parser",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "execution_id": "<uuid>",
    "approver_id": "<agent-identity>",
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #16: `execution_id`, `approver_id`.

## Emitter

Approval parser (exclusive emitter — §3.4 utterance parsing).

## Consumers

- AUDIT surface — persists per ADR-013.
- LiteExecutor / NativeEngine.resumeApproved — clears `awaiting_approval`; dispatches the gated `step_started` (#5).
- Pending-approval ledger writer — clears `user-kit/pending-approvals/E-<id>.json` (per I-15).
- Telemetry sink (§5.6) — approval-throughput count.
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, executor resumer, ledger writer.

## Ordering invariants

- Always preceded by `approval_requested` (#15) for the same `execution_id`.
- Mutually exclusive with `approval_denied` (#17) for the same `execution_id`.
- Causal predecessor of the gated step's `step_started` (#5) on resume.

## Replayability

- **Idempotent on replay**: re-fire of an already-granted approval emits `approval_already_handled` (#18) instead.
- **Audit-critical**: required to reconstruct approver identity per ADR-015 agent_identity chain.
- **Fail-closed on emission failure** (per HS-4): no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #16.
- NATIVE-ENGINE.md §3.1 Engine API (`NativeEngine.resumeApproved`).
- NATIVE-ENGINE.md §3.4 Approval utterances.
- NATIVE-ENGINE.md §4 I-15 (pending-approval ledger).
- ADR-009 — requires_approval semantics.
- ADR-013 — 3-channel audit durability.
- ADR-015 — agent_identity chain.
- ../events/approval_requested.md
- ../events/approval_already_handled.md
- ../hardstops/HS-4-audit-unwritable.md
