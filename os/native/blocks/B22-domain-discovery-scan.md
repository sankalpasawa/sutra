---
part-id: B22
bucket: blocks
template: L8-feature-spec
parity-source: net-new (ADR-028); post-cutover canon, not from pre-cutover monolith
status: DRAFT v1
authored: 2026-07-27
---

# B22: Domain Discovery Scan (one-time bulk addressing)

## 1-line summary

One deliberate run per client that walks the existing corpus, derives the Domain tree from what is actually there, mints Charters for each domain, and addresses every unaddressed work unit — closing the infinite tail that lazy backfill leaves behind.

## Scope (in / out)

**In scope (v1)**:
- Enumerate the corpus for one tenant: directory structure, file classes, commit history, existing artifacts.
- Derive a candidate Domain tree from that evidence, one level at a time, deepest-confident-level first.
- Mint Domains and Charter stubs for the derived tree (Charter obligations remain empty with a stated reason — ADR-028 Decision 5).
- Stamp `origin='backfilled'` Placements for every enumerated work unit.
- Produce a **coverage report**: units enumerated, addressed, floor-held, and the resulting tree shape.
- Run idempotently — a second run over an unchanged corpus mints nothing new.

**Out of scope (v1)**:
- Running automatically. B22 is a deliberate operator action, once per client (ADR-028 Decision 4).
- Authoring Charter obligations or success metrics for the derived Charters.
- Semantic/embedding classification — v1 derives from structural and historical evidence; F1 semantic retrieval is v2+.
- Cross-tenant scanning — one tenant per run (I-13).

## User outcome

> "I ran it once per client. Afterwards every existing thing had a home, and the tree matched what was actually in the repo rather than what I imagined was in it."

Founder direction 2026-07-27: *"For all the clients, we can do one run, one-level scan of the entire domain structure and create charters and the objectives accordingly. That can be one-time feature."*

## The "one-level" contract

The founder's phrasing — *one-level scan* — is the operative constraint, and it is a good one. B22 does **not** attempt to derive the whole tree to arbitrary depth in a single pass. It derives **one level at a time**, and stops descending where evidence stops being decisive.

| Pass | Derives | Stops when |
|---|---|---|
| 1 | Top-level Domains under root | structural evidence at that level is exhausted |
| 2 | Children of each level-1 Domain | evidence for a child is below the confidence floor |
| n | …continues while evidence remains decisive | any level where the floor is not met |

Everything below the stopping point is **floor-held**: placed at the deepest confident ancestor (I-P9) rather than speculatively partitioned. Depth then grows organically as B19 and B21 address real work. This is why the scan produces a shallow, honest tree rather than a deep, invented one — a deep guessed tree is worse than a shallow true one, because MECE violations compound with depth.

## Objectives → Charter fields (explicit mapping)

The founder asked for "charters and the objectives accordingly". Objectives map onto existing Charter fields; no new concept is introduced:

| Founder's word | Charter field | Auto-derived? |
|---|---|---|
| what this area is for | `purpose` | **yes** — descriptive, inferred from evidence |
| its name | `title` | **yes** |
| what's in / out | `scope_in`, `scope_out` | **yes** — from the enumerated corpus |
| its promises | `obligations` | **no** — left empty with a stated reason (I-2 satisfied) |
| its targets | `success_metrics` | **no** — left empty |

The split is deliberate: descriptive fields state what *is* and can be observed; `obligations` and `success_metrics` state what is *promised* and cannot be observed. Deriving the second kind would fabricate commitments the operator never made — the same reasoning as ADR-028 Decision 5.

## UX flow (narrative)

1. Operator invokes the scan for a tenant.
2. B22 enumerates the corpus and reports its size before doing anything — units found, rough shape, estimated run cost.
3. Operator confirms.
4. Level-by-level derivation runs, stopping each branch where evidence falls below the floor.
5. Domains and Charter stubs mint (atomic per I-P10).
6. Every enumerated unit gets a `backfilled` Placement — matched, or floor-held at the deepest confident ancestor.
7. Coverage report renders: the derived tree, per-node counts, floor-held count, and the MECE report from B20.
8. Operator reviews. Corrections route to B20; B22 itself never asks for ratification of individual nodes.

## Acceptance criteria (Given / When / Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | A corpus of 10,000 units, empty Domain tree | scan runs | every unit carries a `backfilled` Placement; zero units unaddressed; coverage report shows a denominator for the first time |
| 2 | Structural evidence is decisive to 2 levels and ambiguous below | scan runs | tree derived to 2 levels; deeper units floor-held at level 2; **no speculative level-3 nodes minted** |
| 3 | Scan run twice with no corpus change | second run | idempotent — zero new Domains, zero new Charters, zero new Placements |
| 4 | Scan run after B21 already backfilled 200 units lazily | scan runs | those 200 keep their existing Placements; only the remaining unaddressed units are stamped |
| 5 | Derived Charters inspected | after scan | each has non-empty `title`, `purpose`, `scope_in`/`scope_out`; each has `obligations: []` plus a stated reason; none fabricates a promise |
| 6 | Two tenants share a machine | scan run for tenant A | tenant B's corpus untouched; no cross-tenant Domain created (I-13) |
| 7 | Scan interrupted midway | operator interrupts | already-stamped Placements persist; rerun resumes and completes; no duplicates (idempotence, I-P10) |
| 8 | Derived tree checked against P5 | after scan | B20's MECE report runs automatically and reports violations, if any, as part of the coverage report |

## Data model

No new primitive. Produces `../primitives/domain.md`, `../primitives/charter.md`, and `../primitives/placement.md` rows.

Coverage report shape:

```
units_enumerated, units_addressed, units_floor_held,
domains_minted, charters_minted, max_depth_derived,
mece_violations (from B20)
```

`units_enumerated` is the denominator B21 lacks — after a B22 run, legacy coverage becomes a real percentage rather than an absolute count.

## Edge cases

- **Corpus too large for one run** → chunked by subtree; each chunk idempotent, so partial completion is safe and resumable.
- **A corpus with no discernible structure** (flat directory of 5,000 files) → derivation stops at level 1; everything floor-holds at root's children. Honest and shallow beats invented and deep.
- **Existing hand-built Domains present** → treated as authoritative; the scan derives around them and never auto-merges an operator-touched node (B20's PROPOSE tier).
- **Scan derives a node that duplicates an operator's node** → surfaced in B20's PROPOSE tier, not auto-merged, because the operator's node is touched.

## Telemetry

Events: `domain_minted` (per node), `placement_assigned` (per unit, `origin=backfilled`), `policy_decision`.

Metrics:
- **Corpus coverage** — `units_addressed / units_enumerated`. The number that only exists after this scan.
- **Derived depth** — how deep evidence supported partitioning. Shallow is not failure; it is the honest reading of a flat corpus.
- **Floor-held fraction** — share of units placed at an ancestor rather than a precise node. Falls over time as B19/B21 address real work.

## Dependencies

- **Primitives**: `placement`, `domain`, `charter`, `tenant`.
- **Blocks**: B19 (shared resolution contract), B21 (complementary lazy path), B20 (MECE report + consolidation of what B22 mints).
- **Pillars**: P5 (MECE), P17 (architecture awareness before creation).
- **Hardstops**: HS-3, HS-4.
- **ADRs**: ADR-028 Decision 4.

## References

- ADR-028 — legacy addressing strategy.
- B21 (`./B21-backfill-on-touch.md`) — the lazy complement.
- B20 (`./B20-domain-restructure.md`) — MECE report consumed by the coverage report.
- Founder direction 2026-07-27 ("one run, one-level scan … create charters and the objectives accordingly").
