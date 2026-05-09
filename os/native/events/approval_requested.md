---
part-id: approval_requested
bucket: events
template: L9-event-spec
parity-source: §3.2 row #15
parity-source-sha256: a50ed113970f2c96c1a92b38e82e66df47bde75c22e081ad27e08b7a31e4fc21
status: DRAFT v1
authored: 2026-05-09
---

# approval_requested

## Purpose

Signals that a step with `requires_approval=true` has been reached (per §3.2 row #15 + ADR-009). The Execution transitions to `awaiting_approval`; a persisted ledger row at `user-kit/pending-approvals/E-<id>.json` records the pending state (per I-15). Per I-14, this event participates as one of three terminal events when the Execution remains in `awaiting_approval`.

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "approval_requested",
  "source": "/native/runtime/lite-executor",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "execution_id": "<uuid>",
    "step_index": 0,
    "prompt_summary": "<sanitized summary>",
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #15: `execution_id`, `step_index`, `prompt_summary`.

## Emitter

LiteExecutor (exclusive emitter) per ADR-009. Fires when the next step to dispatch has `requires_approval=true` AND the persisted ledger row at `user-kit/pending-approvals/E-<id>.json` is written (per I-15 fail-closed on missing ledger row).

## Consumers

- AUDIT surface — persists per ADR-013.
- Founder approval channel — surfaces the prompt for `approve E-<id>` / `reject E-<id> <reason>` utterance per §3.4.
- LiteExecutor itself — Execution enters `awaiting_approval` state; further step dispatch is paused pending the approval utterance.
- Telemetry sink (§5.6) — pending-approval count per tenant.
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, founder approval surface.

## Ordering invariants

- Preceded by `step_started` (#5) is NOT required — `approval_requested` fires BEFORE the gated step's `step_started` (gating semantic per ADR-009).
- Causal predecessor of `approval_granted` (#16) or `approval_denied` (#17) for the same `execution_id`.
- May also be a terminal event for the Execution per I-14 (if approval never arrives and the Execution remains in `awaiting_approval`).
- `approval_already_handled` (#18) may fire as an idempotent re-fire when an approval utterance re-arrives after resolution.

## Replayability

- **Idempotent on replay**: informational; the durable record is the pending-approval ledger row at `user-kit/pending-approvals/E-<id>.json` (I-15).
- **Audit-critical**: required to reconstruct the gate.
- **Fail-closed on emission failure** (per HS-4): no fail-open. If ledger row write fails, the Execution does NOT proceed (per I-15 invariant).

## References

- NATIVE-ENGINE.md §3.2 row #15.
- NATIVE-ENGINE.md §4 I-14 (terminal-event set), I-15 (pending-approval ledger).
- NATIVE-ENGINE.md §3.4 Approval utterances.
- ADR-009 — requires_approval semantics + ledger.
- ADR-013 — 3-channel audit durability.
- ../primitives/workflow-step.md
- ../events/approval_granted.md
- ../events/approval_denied.md
- ../events/approval_already_handled.md
- ../hardstops/HS-4-audit-unwritable.md
