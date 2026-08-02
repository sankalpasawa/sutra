---
part-id: P10
bucket: pillars
template: L1-pov
parity-source: §10.2 row P10 + §10.3 row P10
parity-source-sha256: 5d81d98c0eeab11ce6e7aeb9a602f3687902df6b3c64bcc822cc399132bae457
status: DRAFT v1
authored: 2026-05-09
---

# P10: Typed config at every layer

## Pillar statement

> Configuration in Native is typed and explicit at every architectural layer. Per §10.2 row P10: "Domain principles+guidelines+decisions; Charter instructions+guidelines+constraints." Domain config and Charter config each have a defined schema with named slots — config is not inferred from code, not scattered across files, and not implicit. Every Native primitive declares its config schema up front.

## What this rules in

- Domain typed-config: principles + guidelines + decisions (three named slots).
- Charter typed-config: instructions + guidelines + constraints (three named slots).
- Every Native primitive that has configuration declares the schema explicitly.
- Per cross-ref to `../primitives/charter.md` and `../primitives/domain.md` (authored in Phase 5) — these primitives carry the canonical typed-config shape.

## What this rules out

- Native primitive config that is implicit (per §10.3 P10 falsification, part 1).
- Config inferred from code (must be a declared schema, not back-derived) (per §10.3 P10 falsification, part 2).
- Config scattered across files outside the Domain or Charter typed-config schema (per §10.3 P10 falsification, part 3).

## Falsification test

**If a Native primitive's config is implicit / inferred-from-code / scattered-across-files (not Domain or Charter typed-config schema) → P10 broken; not typed-at-every-layer.** (Exact text from §10.3 row P10.)

## Doctrine inheritance (from L0)

Per canon §10.4 doctrine-tension resolution table: P10 has NO direct conflict with the 5 Doctrine tests (Customer Focus First · Dynamic · Flexible · Scalable · Simple · Nuanced) recorded in §10.4. The table only enumerates tensions for P3 (vs Simple), P11 (vs Customer Focus), and P13 (vs Scalable). For P10, no tension is logged; inheritance is via L0 generally (Customer Focus First applies as parent of all pillars).

(If a tension exists in practice but is not in §10.4, this is a gap to surface via future ADR rather than invent inline.)

## References

- NATIVE-ENGINE.md §10.2 row P10 — pillar statement.
- NATIVE-ENGINE.md §10.3 row P10 — falsification test.
- NATIVE-ENGINE.md §10.4 — doctrine inheritance table (P10 not listed; no documented tension).
- `../primitives/domain.md` — Domain typed-config (Phase 5).
- `../primitives/charter.md` — Charter typed-config (Phase 5).
