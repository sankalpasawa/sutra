---
part-id: phase-A
bucket: impl-phases
template: L12-roadmap-entry
parity-source: §14.15.1 phase A box
parity-source-sha256: 7c1fd604cddc02e99e09f1284adf41c82a90812336081788b6215b02034f643a
status: ACTIVE
authored: 2026-05-09
---

# Phase A: Complete the PRD Docs

## Gate (entry criteria)
Native canon decomposition active (this Phase 10 of `sutra/os/native/MIGRATION-PLAN.md`). Founder available to ratify STRAW drafts per layer. NATIVE-ENGINE.md §10 / §11 / §13 / §15 / §16 / §17 / §18 / §19 currently DRAFT or empty (per §14.15.1 phase-A box).

## Scope (what gets done)
- Complete NATIVE-ENGINE.md §10 (pillars), §11 (north-star metric), §13 (TBD), §15 (TBD), §16 (feature specs — handed to Phase B), §17, §18, §19.
- Founder-owned layers per `holding/PRODUCT-DOC-STANDARD.md`: L1 (Philosophy), L2 (Strategy), L3 (Roadmap shape), L4 (Customer), L11 (Metrics / OKR), L14 (Vision) each reach DRAFT v1.
- Multi-turn drafting cadence; 1-3 sections / turn.

## Duration (target wall-clock)
Multi-turn over multi-week founder cycle. NOT specified in canon as a wall-clock estimate; runtime implementation pace. Stage B (§14 PRD + §12 Mission landed) was the in-flight checkpoint as of canon authoring (2026-05-09).

## DRI
Claude drafts STRAW; founder ratifies. (Per §14.15.1 phase-A box "Owner" row.)

## Acceptance (exit criteria)
Every founder-owned layer (L1 / L2 / L3 / L4 / L11 / L14) reaches DRAFT v1 with founder review. (Per §14.15.1 phase-A box "Gate" row.)

## Dependencies (on other phases / blocks)
None upstream. Phase A unblocks Phase B (which depends on §16 being drafted before per-block feature-spec authoring).

## Rollback
Each layer's DRAFT v1 is a markdown commit; rollback = `git revert <sha>` on the offending section commit. Founder ratification is a forward-only signal (cf. canon hardstops); rolling back a ratified layer requires explicit new direction.

## References
- NATIVE-ENGINE.md §14.15.1 phase-A box
- NATIVE-ENGINE.md §10 / §11 / §13 / §15 / §16 / §17 / §18 / §19 (target sections)
- `holding/PRODUCT-DOC-STANDARD.md` (L0-L14 spec)
- ../doc-layers/L1-philosophy.md, ../doc-layers/L11-metrics.md (founder-owned doc-layer instances)
