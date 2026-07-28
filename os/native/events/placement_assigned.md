---
part-id: placement_assigned
bucket: events
template: L9-event-spec
parity-source: net-new (ADR-028); post-cutover canon, not from pre-cutover monolith
status: DRAFT v1
authored: 2026-07-27
---

# placement_assigned

## Purpose

Signals that a unit of work has been stamped with an authority address — one Domain, one Charter — before executing. This is the event that makes placement coverage measurable: counting `placement_assigned` against work units executed answers "is every piece of work addressed?" (ADR-028 Decision 1, I-P1).

Emitted for every placement path: matched, minted, floor-held, and backfilled. Also emitted for superseding rows (post-close corrections and restructure re-pointing), distinguished by the `supersedes` field.

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "placement_assigned",
  "source": "/native/runtime/placement-resolver",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "placement_id": "PL-<hash>",
    "work_ref": { "kind": "commit", "id": "80c112c" },
    "domain_ref": "<stable-domain-id>",
    "domain_path": "D3.D2.D7",
    "charter_id": "C-<hash>",
    "origin": "matched | minted | backfilled",
    "phase": "pre-flight | post-close",
    "confidence": 0.82,
    "created": { "domains": ["<stable-id>"], "charters": ["C-<hash>"] },
    "supersedes": "PL-<hash> | null",
    "floor_held": false,
    "tenant_id": "T-<hash>",
    "agent_identity": "claude | codex | operator",
    "ts_ms": 1785145485000
  }
}
```

Required payload fields: `placement_id`, `work_ref`, `domain_ref`, `charter_id`, `origin`, `phase`, `tenant_id`.

`domain_path` is included for human readability of the audit stream only. It is the derived display path at emission time and MUST NOT be treated as a stable key — consumers key on `domain_ref` (I-P8).

`floor_held: true` marks a placement that stopped at an ancestor rather than minting a child, because classifier confidence fell below the floor (I-P9). These are the rows B20's consolidation and MECE report care about most.

## Emitter

The placement resolver, invoked by B19 (new work), B21 (backfill on touch), and B22 (bulk discovery scan). Exclusive emitter — no other component stamps addresses.

Emission is synchronous with the placement write and precedes the first mutating action of the work unit. A failure to emit is a durability failure and routes to HS-4; it is not fail-open.

## Consumers

- **AUDIT surface** — persists per ADR-013.
- **B20 restructure** — reads the stream to compute per-node Placement counts, sibling evidence overlap, and the MECE report.
- **Coverage metrics** — placement coverage, mint rate, floor-held fraction, backfill coverage.
- **C2 Charter + Domain Browser** — reverse lookup ("what work lives under this Domain?").
- **Telemetry sink** (§5.6).

## Ordering invariants

- Emitted BEFORE the first mutating action of the work unit it addresses (I-P1). A `placement_assigned` arriving after a mutation for the same `work_ref` is an ordering violation.
- When `created.domains` or `created.charters` is non-empty, the corresponding `domain_minted` events are causal predecessors — the node exists before the address citing it is emitted.
- A superseding event (`supersedes` non-null) is a causal successor of the event that assigned the superseded row.
- Not bound to an Execution lifecycle; a Placement addresses work units of several kinds, only one of which is an Execution.

## Replayability

- **Idempotent on replay**: the durable record is the Placement row at `~/.sutra-native/user-kit/placements/PL-<hash>.json` plus the `CURRENT.jsonl` pointer. Replaying the event does not re-stamp.
- **Audit-critical**: required to reconstruct which work was addressed where, and when the address changed.
- **Fail-closed on emission failure** (HS-4): no fail-open.
- Content-addressed `placement_id` means a genuinely identical placement replays to the same id — duplicate emission is detectable, not silently doubled.

## References

- ADR-028 — mandatory work placement.
- `../primitives/placement.md` — I-P1, I-P5, I-P8, I-P9.
- `../blocks/B19-work-placement.md` · `../blocks/B21-backfill-on-touch.md` · `../blocks/B22-domain-discovery-scan.md` — the three emitting paths.
- `../blocks/B20-domain-restructure.md` — primary consumer.
- `./domain_minted.md` — causal predecessor when nodes are created.
- ADR-013 — 3-channel audit durability.
- `../hardstops/HS-4-audit-unwritable.md`.
