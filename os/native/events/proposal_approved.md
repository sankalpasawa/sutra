---
part-id: proposal_approved
bucket: events
template: L9-event-spec
parity-source: §3.2 row #13
parity-source-sha256: 4bfaff6fdddec68fc2113b192d7b7730591aa4374fde200e9ab0166a5d7216d8
status: DRAFT v1
authored: 2026-05-09
---

# proposal_approved

## Purpose

Signals that the founder approved a proposed Workflow (per §3.2 row #13). Parsed from founder utterance `approve P-<id>` per §3.4. Materializes the proposal into a Workflow registered in the user-kit.

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "proposal_approved",
  "source": "/native/runtime/approval-parser",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "proposal_id": "<P-hash>",
    "workflow_id": "<W-hash>",
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #13: `proposal_id`, `workflow_id`.

## Emitter

Approval parser (exclusive emitter — per §3.4 utterance parsing). Fires when founder utterance `approve P-<id>` is parsed and the proposal is materialized into a Workflow.

## Consumers

- AUDIT surface — persists per ADR-013.
- SkillEngine — registers the new Workflow per §3.1 `SkillEngine.resolve`.
- Pattern detector (EMERGE surface) — closes the loop for `pattern_hash`.
- Telemetry sink (§5.6) — proposal-acceptance count.
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, SkillEngine, pattern detector.

## Ordering invariants

- Always preceded by `pattern_proposed` (#12) for the same `proposal_id`.
- Mutually exclusive with `proposal_rejected` (#14) for the same `proposal_id`.

## Replayability

- **Idempotent on replay**: workflow registration is keyed by `workflow_id`; replay is a no-op if Workflow already exists.
- **Audit-critical**: required to reconstruct emergence-to-Workflow attribution.
- **Fail-closed on emission failure** (per HS-4): no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #13.
- NATIVE-ENGINE.md §3.4 Approval utterances (`approve P-<id>`).
- NATIVE-ENGINE.md §3.1 Engine API (SkillEngine.resolve).
- ADR-010 — pattern emergence detection.
- ADR-013 — 3-channel audit durability.
- ../events/pattern_proposed.md
- ../primitives/workflow.md
- ../hardstops/HS-4-audit-unwritable.md
