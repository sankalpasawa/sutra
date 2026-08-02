---
part-id: artifact_registered
bucket: events
template: L9-event-spec
parity-source: §3.2 row #9
parity-source-sha256: ae7c16c55535d312631dc0cdb21e3b029fd999c0ff603d82ad24e38face9bee7
status: DRAFT v1
authored: 2026-05-09
---

# artifact_registered

## Purpose

Signals that a new Asset/DataRef has been registered in the catalog (per §3.2 row #9). Carries `lineage_parent_id` linking to the producing step or upstream artifact — the closed-loop attribution mechanism for B9 (per §12.13 extension relationship: B9 extends existing Asset/DataRef primitives, does NOT introduce a new primitive).

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "artifact_registered",
  "source": "/native/runtime/artifact-catalog",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "artifact_id": "<asset-or-dataref-id>",
    "lineage_parent_id": "<execution-id | step-id | null>",
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #9: `artifact_id`, `lineage_parent_id`. `lineage_parent_id` may be null for externally-imported artifacts (no upstream Native producer).

## Emitter

Artifact catalog component of B9 (Closed-Loop Artifact). Exact emitter binding not enumerated in canon §3.2; runtime implementation choice — likely emitter: LiteExecutor invokes the catalog after `step_completed` (#6) carries a non-null `output_ref`, OR catalog auto-registers on Asset/DataRef instantiation.

## Consumers

- AUDIT surface — persists per ADR-013.
- B9 Closed-Loop Artifact — the catalog itself maintains lineage edges.
- Telemetry sink (§5.6) — artifact count per tenant per Workflow.
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, B9 catalog index.

## Ordering invariants

- When emitted following `step_completed` (#6) with non-null `output_ref`: causally follows that `step_completed` for the same `execution_id`.
- `lineage_parent_id`, when non-null, MUST reference an `execution_id` or `step_id` already audited (no forward references).

## Replayability

- **Idempotent on replay**: artifact registration is keyed by `artifact_id`; replay collides on duplicate IDs and is a no-op.
- **Audit-critical**: required for B9 lineage reconstruction.
- **Fail-closed on emission failure** (per HS-4): no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #9.
- NATIVE-ENGINE.md §3.5 Authoritative state (DataRef.authoritative_status per ADR-008).
- NATIVE-ENGINE.md §12.13 — B9 Asset/DataRef extension relationship (per F5 rule: B9 extends, does not promote).
- ADR-008 — Authoritative-vs-advisory DataRef.
- ADR-013 — 3-channel audit durability.
- ../primitives/data-ref.md
- ../hardstops/HS-4-audit-unwritable.md
