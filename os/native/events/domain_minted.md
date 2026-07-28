---
part-id: domain_minted
bucket: events
template: L9-event-spec
parity-source: net-new (ADR-028); post-cutover canon, not from pre-cutover monolith
status: DRAFT v1
authored: 2026-07-27
---

# domain_minted

## Purpose

Signals that the system created a Domain — or a Charter stub to inhabit one — without asking the operator. This is the audit record of Native exercising the taxonomy authority granted by ADR-028 Decision 1.

It is deliberately a *notification*, not a *proposal*. Its sibling `pattern_proposed` (ADR-010) asks the founder to approve a Workflow at k≥4; `domain_minted` asks nothing and waits for nothing. The distinction is the whole authority model: Workflows are proposed because they are reusable commitments, Domains are minted because they are addresses.

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "domain_minted",
  "source": "/native/runtime/placement-resolver",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "kind": "domain | charter",
    "ref": "<stable-domain-id> | C-<hash>",
    "name": "Canon / part-files",
    "domain_path": "D3.D2.D7",
    "parent_ref": "<stable-domain-id> | null",
    "trigger": "B19 | B21 | B22",
    "confidence": 0.82,
    "evidence": ["<path or term that drove the decision>"],
    "race_adopted": false,
    "obligations_empty_reason": "<string> | null",
    "tenant_id": "T-<hash>",
    "agent_identity": "claude | codex | operator",
    "ts_ms": 1785145485000
  }
}
```

Required payload fields: `kind`, `ref`, `name`, `parent_ref`, `trigger`, `tenant_id`.

`evidence` carries what drove the decision — the paths or terms the classifier matched on. Without it the operator cannot audit why a node appeared, and B20 cannot compute sibling overlap. It is the field that makes system authority reviewable after the fact rather than opaque.

`race_adopted: true` marks the loser of an atomic check-then-insert race: this session wanted to mint, found a concurrent session had already minted an equivalent node, and adopted that node's `ref` instead of creating a duplicate sibling (I-P10). The event still emits — the intent to mint is itself audit-relevant.

`obligations_empty_reason` is required and non-null when `kind='charter'`. It records the stated reason that satisfies Charter invariant I-2 for a stub with no obligations, and it exists so that "the system did not fabricate promises" is verifiable rather than merely claimed (ADR-028 Decision 5).

## Emitter

The placement resolver, on the mint path only. Triggered from B19 (new work), B21 (backfill on touch), or B22 (bulk discovery scan); the `trigger` field records which.

Not emitted on the matched path, and not emitted on the floor-held path — floor-holding exists precisely to avoid minting (I-P9). A rising `domain_minted` rate against a flat work rate is the leading indicator that the classifier is producing noise.

## Consumers

- **AUDIT surface** — persists per ADR-013.
- **B20 consolidation** — reads `evidence`, `confidence`, and `trigger` to decide AUTO-tier eligibility. Only nodes minted here (never operator-created ones) are eligible for automatic merging.
- **MECE report** — sibling overlap is computed from the evidence signatures recorded here.
- **Coverage metrics** — mint rate, race-adoption rate, per-trigger attribution.
- **C2 Charter + Domain Browser** — renders provenance ("this node was created automatically, from this evidence").

## Ordering invariants

- Causal predecessor of the `placement_assigned` event that cites the minted `ref` — the node exists before any address points at it.
- When a Domain and its Charter stub are both created for one placement, the `kind='domain'` event precedes the `kind='charter'` event: a Charter lives in exactly one Domain, so the Domain must exist first.
- `parent_ref` MUST resolve to an already-existing Domain at emission time, except at root creation where it is null.
- Concurrent mints under the same parent serialise through the atomic check-then-insert; exactly one wins and any losers emit with `race_adopted: true` (I-P10).

## Replayability

- **Idempotent on replay**: the durable record is the Domain or Charter row in the user-kit registry. Replay does not create a second node.
- **Audit-critical**: this is the only record of *why* the tree has the shape it has. Without it, system authority is unauditable and B20's AUTO tier has no eligibility signal.
- **Fail-closed on emission failure** (HS-4).

## References

- ADR-028 — Decision 1 (system authority), Decision 5 (no fabricated obligations).
- `../primitives/placement.md` — I-P4 (MECE-preserving mint), I-P9 (floor), I-P10 (atomic mint).
- `../primitives/domain.md` · `../primitives/charter.md` — the minted primitives.
- `../blocks/B20-domain-restructure.md` — AUTO-tier eligibility depends on this event.
- `./placement_assigned.md` — causal successor.
- `./pattern_proposed.md` — the contrasting propose-and-wait path for Workflows (ADR-010).
- ADR-013 — audit durability. `../hardstops/HS-4-audit-unwritable.md`.
