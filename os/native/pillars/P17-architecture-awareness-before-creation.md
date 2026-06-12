---
part-id: P17
bucket: pillars
template: L1-pov
parity-source: FOUNDER-DIRECTIONS.md §D12 + dispatcher-pretool.sh Checks 3-4 + architecture-awareness.sh
parity-source-sha256: eee87b8a678cb0f80eb1e80df466fa3d03c851f213484305816d31c94c228d3e
status: DRAFT v1
authored: 2026-06-12
---

# P17: Architecture awareness before creation

## Pillar statement

> Before any CREATE-class action, survey the architecture registry: what exists, what connects, what changes downstream. Per FOUNDER-DIRECTIONS.md D12 (founder verbatim): *"When you add something, how do you think about the existing architecture?"* — implication: "Before creating anything, read SYSTEM-MAP.md + HIERARCHY.md. Check what exists, what connects, what changes downstream." In Native, the map source is the registry/ontology rather than SYSTEM-MAP.md; the invariant is unchanged.

## What this rules in

- The two-check shape, ported verbatim from production: **(a)** a new-file consultation reminder — any Write creating a file at a non-existent, non-whitelisted path triggers a PreToolUse warning to consult the architecture map ("Was SYSTEM-MAP.md consulted? Does this fit existing architecture?"); **(b)** an unknown-directory detector — a new file landing in a directory not listed in the map is flagged as a new-path event.
- SOFT enforcement: warn, never block (exit 0) — production proved this sufficient; the value is the forced survey, not the gate.
- Composition with D55 Restructure-on-Add: D12's survey IS Step 1 of D55's four steps (Survey → Re-organize → Simplify → Surface), generalized fleet-wide via `structure-first-reminder.sh`. P17 names the distinct upstream invariant: read the map BEFORE creating, with a map-membership detector — D55 coverage alone does not carry the detector.
- Protocol lineage kept honest: PROTO-001 "Structure Before Creation" is RETIRED in PROTOCOLS.md; its substance survives in these checks. Retired protocols whose substance lives on must say where.

## What this rules out

- Creating files, parts, or directories without consulting the architecture registry first.
- New paths landing outside known structure silently — every map-unknown directory is an event, not a default.
- Hardening this to a block: production kept it SOFT deliberately; converting to HARD requires founder direction plus evidence the warning is being ignored at cost.
- Treating D55's Survey step as a substitute for the map-membership detector (they compose; neither subsumes the other).

## Falsification test

**If a CREATE-class action lands a file in a directory unknown to the architecture registry and no new-path event/warning is emitted → P17 broken.** (Falsification test newly authored from the production behavior contract — no §10.3 row exists; P17 is a post-cutover gap-fill.)

## Doctrine inheritance (from L0)

P17 is not in the §10.4 doctrine-tension table (authored post-cutover as a canon gap-fill); no tension is logged. Inheritance via L0 generally — Customer Focus First (`./P0-customer-focus-first.md`); strongest alignment is with the Simple and Scalable tests: surveying before creating is what keeps the structure one coherent shape as it grows.

(If a tension exists in practice but is not in §10.4, this is a gap to surface via future ADR rather than invent inline.)

## References

- holding/FOUNDER-DIRECTIONS.md §D12 — doctrine + founder verbatim (production evidence).
- holding/DIRECTION-ENFORCEMENT.md row D12 (production evidence).
- holding/hooks/dispatcher-pretool.sh — Check 3 architecture awareness + Check 4 new-path detector (production evidence).
- holding/hooks/architecture-awareness.sh — standalone L2 copy with build-layer header (production evidence).
- holding/SYSTEM-MAP.md + holding/HIERARCHY.md — the production map sources this pillar generalizes to Native's registry/ontology.
- sutra/layer2-operating-system/PROTOCOLS.md — PROTO-001 RETIRED row (substance survives in the two checks).
- holding/FOUNDER-DIRECTIONS.md §D55 + sutra/marketplace/plugin/hooks/structure-first-reminder.sh — Restructure-on-Add; P17's survey is its Step 1, fleet-generalized.
- `./P0-customer-focus-first.md` — doctrine parent.
- Parity-source deviation: canon GAP — content does not exist in NATIVE-ENGINE.md; parity-source anchors point at the production source docs per MIGRATION-PLAN §9 limitation #2.
