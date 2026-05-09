---
part-id: approval_already_handled
bucket: events
template: L9-event-spec
parity-source: §3.2 row #18
parity-source-sha256: 4268cb76c97967dd36967e146dbd3fe6c96c36e9838a373b25727269fee8d083
status: DRAFT v1
authored: 2026-05-09
---

# approval_already_handled

## Purpose

Signals an idempotent re-fire on an approval that has already been resolved (per §3.2 row #18). Prevents double-resume / double-deny when an approval utterance is repeated for an Execution whose `awaiting_approval` state has already been cleared.

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "approval_already_handled",
  "source": "/native/runtime/approval-parser",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "execution_id": "<uuid>",
    "prior_outcome": "granted | denied",
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #18: `execution_id`, `prior_outcome`. `prior_outcome` is one of `granted` (per #16) or `denied` (per #17).

## Emitter

Approval parser (exclusive emitter). Fires when an approval utterance arrives for an `execution_id` whose pending-approval ledger row (`user-kit/pending-approvals/E-<id>.json`) is already cleared (per I-15).

## Consumers

- AUDIT surface — persists per ADR-013.
- Telemetry sink (§5.6) — idempotency-replay count (signal for upstream UX issues — e.g., founder confusion about approval state).
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface (always persists), UX-feedback telemetry.

## Ordering invariants

- Always follows EITHER `approval_granted` (#16) OR `approval_denied` (#17) for the same `execution_id` — the resolving event must precede this idempotent re-fire.
- Does NOT itself change the Execution state.

## Replayability

- **Idempotent on replay**: the entire purpose of this event is to capture replay/duplicate-utterance attempts as audit rows.
- **Audit-only**: no state-machine effect; purely informational.
- **Fail-closed on emission failure** (per HS-4): no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #18.
- NATIVE-ENGINE.md §3.4 Approval utterances.
- NATIVE-ENGINE.md §4 I-15 (pending-approval ledger).
- ADR-009 — requires_approval semantics + idempotency.
- ADR-013 — 3-channel audit durability.
- ../events/approval_granted.md
- ../events/approval_denied.md
- ../hardstops/HS-4-audit-unwritable.md
