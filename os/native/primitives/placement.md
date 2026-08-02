---
part-id: Placement
bucket: primitives
template: L9-primitive-spec
parity-source: net-new (ADR-028); post-cutover canon, not from pre-cutover monolith
status: DRAFT v1
authored: 2026-07-27
peer-review: deepseek consult 2026-07-27 CHANGES-REQUIRED (4xP1, 3xP2) — all folded; see ADR-028 §Peer review
---

# Placement

## Purpose

The Placement primitive is the **address stamped on every unit of work before that work executes**. It answers two questions with one durable row: *where does this work live* (Domain) and *what vehicle is it running under* (Charter).

Before Placement, canon bound Workflows to Domains only at registration time (B3), and only through a field that did not exist on the Workflow primitive. Work executed outside a registered Workflow — an operator utterance handled inline, an ad-hoc edit, a commit — had no authority address at all. Placement closes that hole: **no work unit executes without an address, and the address is always resolvable because the system mints what is missing rather than blocking the operator** (ADR-028).

Placement is the join row between the MECE Domain tree (P5, B3) and the operator's actual activity. It is what makes "all documentation and everything is mapped up properly" mechanically true rather than aspirational.

## Identity is separate from position (peer-review P1, folded)

The Domain `id` (`D3.D2.D7`) **encodes tree position**. Re-parenting a branch therefore changes that node's id and every descendant id. If a Placement were keyed on the positional path, one MOVE would invalidate every Placement beneath the moved subtree and — under content-addressing — force a new row for each. That is unbounded write amplification.

Canon therefore splits the two:

| Concept | Field | Mutable? | Used for |
|---|---|---|---|
| **Identity** | `domain_ref` — stable id, assigned once at Domain mint, never changes | never | the stored key; what Placement points at; what content-addressing hashes |
| **Position** | `domain_path` — dotted D-pattern (`D3.D2.D7`) | changes on MOVE/MERGE | **display only**; the printed tree; human reference |

`domain_path` is **derived at read time** from the Domain registry by walking `parent_id`. It is stored on the row as a denormalised convenience for cheap rendering, but it is **excluded from the canonical form** used to compute `id`. A restructure that changes an ancestor's position therefore does NOT invalidate a single Placement row.

## Type signature (TypeScript-style)

```typescript
type Placement = {
  id: string;                  // PL-hash — sha256 of canonical form (see below)
  work_ref: {
    kind: 'utterance' | 'execution' | 'step' | 'artifact' | 'commit' | 'file';
    id: string;                // stable ref to the work unit
  };
  domain_ref: string;          // STABLE domain id — the key; never changes
  charter_id: string;          // C-hash; NEVER null (I-P6)
  origin: 'matched' | 'minted' | 'backfilled';
  confidence: number;          // 0.0-1.0 — classifier confidence at stamp time
  created: {
    domains: string[];         // domain_refs minted to satisfy this placement
    charters: string[];        // Charter ids minted to satisfy this placement
  };
  supersedes: string | null;   // prior PL-hash this row replaces; null for first placement
  phase: 'pre-flight' | 'post-close';   // when this row was stamped (I-P9)
  tenant_id: string;           // T-hash; required (ADR-006, I-13 inheritance)
  ts_ms: number;               // stamp time, unix ms

  // ---- derived, NOT part of canonical form ----
  domain_path?: string;        // 'D3.D2.D7' — display only, recomputed on read
  domain_depth?: number;       // segment count - 1; display only
};
```

**Canonical form** for content-addressing: `{charter_id, confidence, created, domain_ref, origin, phase, supersedes, tenant_id, ts_ms, work_ref}` — keys sorted alphabetically, no whitespace, UTF-8. `domain_path` and `domain_depth` are excluded. SHA256 of that canonical form = `PL-<hex>`.

## Invariants (must hold)

- **I-P1 (mandatory before work)**: no work unit executes without a resolvable Placement. The check fires BEFORE the first mutating action of the unit (ADR-028 Decision 2).
- **I-P2 (resolvable)**: at write time, `domain_ref` MUST resolve to a Domain in the registry AND `charter_id` MUST resolve to a Charter. A row citing an unresolvable id is a HARD reject.
- **I-P3 (never-stops)**: Placement resolution has NO exit that halts operator work on account of a missing Domain or Charter. If nothing matches, the mint path (B19) runs and resolution continues. The only halt is registry-unwritable, routing to HS-4 — a durability failure, not a taxonomy failure.
- **I-P4 (MECE-preserving mint)**: an auto-minted Domain MUST be created as a **child of the deepest matching existing ancestor**, MUST NOT overlap an existing sibling, and MUST NOT be a catch-all bucket (P5 forbids both).
- **I-P5 (append-only, single current)**: rows are never mutated. Re-placement mints a new row with `supersedes` set to the prior row's id. Exactly one row per `work_ref` is **current** — the one no other row supersedes. Superseded rows are retained, not deleted.
- **I-P6 (charter non-null)**: every Placement cites a Charter. If the resolved Domain hosts none, B19 mints a Charter whose `obligations` is explicitly empty with a stated reason — satisfying Charter invariant I-2 without fabricating commitments (ADR-028 Decision 5).
- **I-P7 (system authority)**: Domain and Charter mint decisions are system-made. The operator is NOT gated, NOT asked, NOT required to ratify. Operator correction routes through B20 (ADR-028 Decision 1).
- **I-P8 (position is not identity)**: `domain_ref` is the key and is immutable. `domain_path` is derived and excluded from the canonical form. A restructure that changes positions MUST NOT invalidate or re-mint any Placement row (peer-review P1).
- **I-P9 (confidence floor)**: below the configured floor, the classifier MUST NOT mint a new child Domain. It places the work in the deepest matching **existing** ancestor and emits a low-confidence event. This prevents semantic-garbage nodes without reintroducing an operator gate (peer-review P2).
- **I-P10 (atomic mint)**: Domain minting under a given parent MUST be an atomic check-then-insert. Two concurrent sessions encountering the same unmatched work MUST NOT produce duplicate siblings; the loser of the race adopts the winner's `domain_ref` (peer-review P1).

## Lifecycle (created → terminal states)

1. **Resolve**: a work unit is about to execute. The classifier gathers evidence (utterance terms, target paths, artifacts referenced, adjacent Placements) and searches the Domain registry for the deepest matching node.
2. **Match** (`origin='matched'`): a Domain matched and hosts at least one Charter. `created` is empty. Cheapest path.
3. **Mint** (`origin='minted'`): nothing matched above the confidence floor. B19 mints a Domain under the deepest matching ancestor via atomic check-then-insert (I-P10), mints a Charter stub if needed (I-P6), records both in `created`.
4. **Floor-hold** (`origin='matched'`, low confidence): below the floor per I-P9 — no child minted; work placed in the nearest existing ancestor; low-confidence event emitted for B20's attention.
5. **Backfill** (`origin='backfilled'`): pre-existing work addressed retroactively by B21 (on touch) or B22 (bulk scan). Same schema; the origin tag keeps migration coverage measurable.
6. **Stamped** (`phase='pre-flight'`): row persisted; `placement_assigned` emitted; the PLACEMENT block renders; work proceeds.
7. **Post-close correction** (`phase='post-close'`): when the completed work's evidence diverges from the pre-flight stamp, a superseding row is minted with `supersedes` set. The pre-flight row remains for audit (peer-review P2).
8. **Superseded**: any row later replaced by a restructure re-placement or a post-close correction. Retained; never deleted.

Note on I-14 mapping: Placement is not an Execution. I-14's terminal-event set binds Workflow Executions only and does NOT apply here.

## Serialization + retention

User-kit registry at `~/.sutra-native/user-kit/placements/PL-<hash>.json`.

```jsonl
{"id":"PL-<hash>","work_ref":{"kind":"commit","id":"80c112c"},"domain_ref":"<stable-id>","charter_id":"C-<hash>","origin":"minted","confidence":0.82,"created":{"domains":["<stable-id>"],"charters":["C-<hash>"]},"supersedes":null,"phase":"pre-flight","tenant_id":"T-<hash>","ts_ms":1785145485000}
```

`CURRENT.jsonl` maps `work_ref` → current `PL-hash` (the single-current pointer of I-P5), so "where does this work live" is one lookup, not a scan.

**Retention / compaction** (peer-review P1): superseded rows are retained in full for the configured audit window, then compacted — the current row plus the most recent N superseded rows stay hot; older ones archive to cold storage. Nothing is deleted (archive-never-delete). Because I-P8 removes restructure-driven re-minting, the steady-state growth rate is one row per work unit plus occasional corrections — not one row per work unit per restructure.

## Rendering contract (the printed block)

Two shapes, selected by whether anything was created.

**Expanded** — when `created` is non-empty. Full ancestor chain with names:

```
+-- PLACEMENT --------------------------------------------------+
| D0              Asawa Inc.                                    |
|  |__ D3         Sutra OS                                      |
|      |__ D3.D2      Native                                    |
|          |__ D3.D2.D7   Canon / part-files       [NEW]        |
|                                                               |
| CHARTER  "Native Canon Integrity"                [NEW]        |
|   Promises: every Native fact lives in one part-file          |
|   In:  part-files, ADRs, engine index                         |
|   Out: website renders, holding research                      |
|                                                               |
| CREATED THIS TURN: 1 domain, 1 charter                        |
+---------------------------------------------------------------+
```

**Compact** — when matched and nothing created:

```
PLACEMENT: D0 > D3 Sutra OS > D3.D2 Native > D3.D2.D7 Canon | "Native Canon Integrity"
```

The rendered path is the derived `domain_path`, recomputed from the registry at print time — so the display always reflects the current tree shape even though the stored key never moved. ASCII-only per D-UX-1.

## Cross-primitive references

- **Domain** (`./domain.md`): `domain_ref` addresses a Domain by its stable id. Placement is why Domain gains a stable-id field, a system-mint path, and atomic mint semantics.
- **Charter** (`./charter.md`): `charter_id` cites the running vehicle. Charter gains `title` + home Domain so the render is readable.
- **Workflow** (`./workflow.md`): a Workflow Execution is one `work_ref.kind`. Workflow gains the `domain_id` field B3 always assumed.
- **Tenant** (`./tenant.md`): `tenant_id` scopes every row; cross-tenant placement is forbidden (HS-3).
- **DecisionProvenance** (`./decision-provenance.md`): the match-vs-mint decision is consequential and emits a provenance row per I-7.

## References

- ADR-028 — mandatory work placement; system authority; never-blocks; peer-review fold.
- B19 (`../blocks/B19-work-placement.md`) — produces Placements.
- B20 (`../blocks/B20-domain-restructure.md`) — operator correction + consolidation.
- B21 (`../blocks/B21-backfill-on-touch.md`) · B22 (`../blocks/B22-domain-discovery-scan.md`) — legacy addressing.
- B3 (`../blocks/B3-domain-hierarchy-mece.md`) · P5 (`../pillars/P5-mece-domains.md`) — the MECE constraint.
- `../events/placement_assigned.md` · `../events/domain_minted.md`.
- HS-3 (tenant boundary) · HS-4 (audit unwritable).
- deepseek consult 2026-07-27 — `.enforcement/deepseek-reviews/gate-log.jsonl`.
