---
part-id: P5
bucket: pillars
template: L1-pov
parity-source: §10.2 row P5 + §10.3 row P5
parity-source-sha256: 383f541b32d27e11c04465856a8c4f5b5e82d003ece9e9706d419f57304dd5ab
status: DRAFT v1
authored: 2026-05-09
---

# P5: MECE domains

## Pillar statement

> Native domains are mutually exclusive AND collectively exhaustive per user. Per §10.2 row P5: "mutually exclusive, collectively exhaustive per user." Every operator concern fits into exactly one domain (mutual exclusion) and every operator concern fits into some domain (collective exhaustion). Domain overlap is a defect; uncovered concerns are also defects.

## What this rules in

- Per-operator domain taxonomy is checked for MECE before any block consumes it (cross-ref to `../primitives/domain.md`, file authored in Phase 5).
- Every operator-surfaced concern has a unique domain home.
- Domain taxonomy can be re-partitioned over time, but must remain MECE at every cut.

## What this rules out

- Domains that overlap (one concern fits two domains → not mutually exclusive).
- Concerns that fit no domain (orphan concerns → not collectively exhaustive).
- "Catch-all" or "misc" domains used as a dumping ground (defeats MECE — collective exhaustion must be by deliberate partition, not by an Other bucket; NOT specified explicitly in canon — this is one operationalization).

## Falsification test

**If a domain overlaps another domain OR an operator concern fits no domain → P5 broken; not MECE.** (Exact text from §10.3 row P5.)

## Doctrine inheritance (from L0)

Per canon §10.4 doctrine-tension resolution table: P5 has NO direct conflict with the 5 Doctrine tests (Customer Focus First · Dynamic · Flexible · Scalable · Simple · Nuanced) recorded in §10.4. The table only enumerates tensions for P3 (vs Simple), P11 (vs Customer Focus), and P13 (vs Scalable). For P5, no tension is logged; inheritance is via L0 generally (Customer Focus First applies as parent of all pillars).

(If a tension exists in practice but is not in §10.4, this is a gap to surface via future ADR rather than invent inline.)

## References

- NATIVE-ENGINE.md §10.2 row P5 — pillar statement.
- NATIVE-ENGINE.md §10.3 row P5 — falsification test.
- NATIVE-ENGINE.md §10.4 — doctrine inheritance table (P5 not listed; no documented tension).
- `../primitives/domain.md` — Domain primitive (typed-config for MECE partition; authored in Phase 5).
- `./P10-typed-config-every-layer.md` — Domain config is one instance of P10.
