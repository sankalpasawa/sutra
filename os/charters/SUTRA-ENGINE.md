# Charter: Sutra Engine — Native Architecture

**Status**: PROMOTED + ACTIVE (canonical here; promoted from `holding/research/2026-04-28-sutra-engine-charter.md` on 2026-05-04 per TD-11)
**Date promoted**: 2026-05-04 | **Drafted**: 2026-04-28
**Owner Domain**: D1 Sutra-OS
**Source spec**: `holding/research/2026-04-28-v2-architecture-spec.md` (V2.4 internal version anchor; user-facing name: Native Architecture)
**Full source archive**: `holding/research/2026-04-28-sutra-engine-charter.md` (31KB, complete history)
**Active execution plan**: `holding/plans/native-resume-2026-05-04.md` (codex-revised v2)

---

## Core Objective

**Build and ship Native — the deployable plugin clients install — based on the Native Architecture (internal V2.x spec).** Every activity in this charter serves that ship.

Native plugin is the product. The Native Architecture (versioned internally V2.0 → V2.4 with amendments A1-A12) is the foundation. Architecture changes are valid only when they unblock or improve the client deployment.

## Purpose

Build and ship Native plugin (`sutra/marketplace/native/`) as a Claude Code plugin clients install via `/plugin install native@sutra`. Coexists with Core plugin (existing fleet) without breaking it.

## Scope (in)
- Native Architecture spec evolution (V2.x amendments per spec §13 game plan)
- Native plugin build (v1.0.0 → v1.x.y series)
- Future plugins built on Native Architecture
- Codex+Claude convergence reviews at every architectural change
- Tier-staged rollout (T0 → T2 → T3 → T4 per D41/PROTO-021)

## Scope (out)
- Core plugin maintenance (existing PROTO-021 governs)
- Sutra Marketplace operations (separate concern)
- Client-specific customization layers (per-client charter)

## Obligations (machine-checkable)
1. Ship Native v1.0.0 with all 4 primitives + 6 laws + 5 schemas + 8 edges + Workflow Engine + Skill Engine implemented and tested
2. Maintain backward-compat per spec §12 (no breaking changes within V2.x internal version)
3. Codex review at every layer change (Layer 1 xhigh / Layer 2 high / Layer 3 medium per PROTO-019)
4. Test before ship: contract test per primitive; integration test per engine; E2E test per workflow
5. Test after ship: canary deployment; observe production behavior; rollback gate
6. 6-section ops block on every artifact this charter ships (per OPERATIONALIZATION charter)
7. Spec version bump on every amendment with version history entry in spec §14

## Invariants (machine-checkable)
1. 4 primitives stable: DOMAIN, CHARTER, WORKFLOW, EXECUTION (any change = breaking = V3.0)
2. 6 laws stable: L1-L6 (any change = breaking = V3.0)
3. Fractal property holds: Sutra Engine itself is an engine; engines compose into engines
4. Patterns (Engine, Skill, Protocol, etc.) remain dial-values, not primitives
5. Native plugin self-contained: does not depend on Core plugin internals
6. Core plugin keeps working unmodified throughout V2.x evolution

## Success metrics
- V2.x spec lock cadence: ≥1 amendment cycle per quarter with codex+claude convergence
- Native v1.0 lands with all 4 primitives implemented + 6 laws enforced + ≥80% test coverage + Asawa dogfood
- Native usage adoption: ≥1 portfolio company on Native within 90d of v1.0 ship
- Architecture stress-test: every quarter, codex audit V2.x against live Asawa/Sutra use cases

## Authority
- Founder-only for breaking changes (V2.x → V3.0)
- Sutra-OS team for additive amendments (V2.x → V2.x+1)
- Codex+Claude convergence for component decisions per locked process

## Termination
- Active until: superseded by V3.0 OR Native plugin reaches end-of-life OR Native Architecture deprecated
- Decommission criteria: 6 consecutive months with zero amendments AND no active build work AND no fleet adoption growth

## Status (current state — 2026-05-04)

| Phase | Status |
|---|---|
| Native v1.0 (M1-M12) | ✅ DONE — engine v1.0.0 GA + v1.0.1 patch |
| Native v1.1.0 (productization) | ✅ SHIPPED — runtime-active engine; `/plugin install native@sutra` working |
| Native v1.2 (organic-emergence v1) | ✅ SHIPPED — pattern-detect → propose → approve → register loop live |
| Phase B (governance v2 follow-ups) | ✅ DONE 2026-05-04 — close-loop V0 + ops follow-ups + D45-candidate skills |
| Active execution | W1 of `holding/plans/native-resume-2026-05-04.md` (codex-revised v2) |

## Reference

For full historical context (Architecture Method, 5-step design process, 6 disciplines, all 19 founder-directive TDs, NPD productization tier, Bucket B 6 picks, 9 stack decisions Q1-Q9, complete charter history): see source archive `holding/research/2026-04-28-sutra-engine-charter.md`.

For the canonical architecture spec: `holding/research/2026-04-28-v2-architecture-spec.md` (filename anchored to internal V2 version; content describes Native Architecture).
