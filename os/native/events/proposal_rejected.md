---
part-id: proposal_rejected
bucket: events
template: L9-event-spec
parity-source: §3.2 row #14
parity-source-sha256: 6d3f0ccf03a1e3370eafb64bf25128cddfbeec03f49be85cfaf1d75572445d81
status: DRAFT v1
authored: 2026-05-09
---

# proposal_rejected

## Purpose

Signals that the founder rejected a proposed Workflow (per §3.2 row #14). The proposal is closed; no Workflow is materialized. Records the rejection reason for emergence-detector learning.

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "proposal_rejected",
  "source": "/native/runtime/approval-parser",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "proposal_id": "<P-hash>",
    "reason": "<sanitized reason string>",
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #14: `proposal_id`, `reason`.

## Emitter

Approval parser. Fires when founder rejects a proposal — exact utterance form for rejection not enumerated in canon §3.4 (lists `approve P-<id>`, `approve E-<id>`, `reject E-<id> <reason>` but not an explicit `reject P-<id> <reason>` form; rejection utterance form is a runtime implementation choice, likely paralleling the Execution rejection grammar).

## Consumers

- AUDIT surface — persists per ADR-013.
- Pattern detector (EMERGE surface) — updates the detector model: rejected pattern hash is recorded; future k-threshold counts may suppress this pattern.
- Telemetry sink (§5.6) — proposal-rejection count.
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, pattern detector.

## Ordering invariants

- Always preceded by `pattern_proposed` (#12) for the same `proposal_id`.
- Mutually exclusive with `proposal_approved` (#13) for the same `proposal_id`.

## Replayability

- **Idempotent on replay**: informational; the durable record is the rejected-proposal entry.
- **Audit-critical**: required for emergence-detector learning correctness.
- **Fail-closed on emission failure** (per HS-4): no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #14.
- NATIVE-ENGINE.md §3.4 Approval utterances.
- ADR-010 — pattern emergence detection.
- ADR-013 — 3-channel audit durability.
- ../events/pattern_proposed.md
- ../events/proposal_approved.md
- ../hardstops/HS-4-audit-unwritable.md
