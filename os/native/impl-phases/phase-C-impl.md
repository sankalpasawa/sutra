---
part-id: phase-C
bucket: impl-phases
template: L12-roadmap-entry
parity-source: §14.15.1 phase C box
parity-source-sha256: 01cdca2a0ead0e21e86ac5d569273658e75a2f7ee8d389123c7ae26ea15e50d5
status: DRAFT v1
authored: 2026-05-09
---

# Phase C: Per-Block Implementation

## Gate (entry criteria)
Phase B top-5 outcome blocks authored (B9, B7, 7d, B5, B18 per §14.15.2). Feature specs locked enough that TDD can begin without contradicting canon.

## Scope (what gets done)
- Implement per-block runtime in `sutra/marketplace/native/` (plugin runtime).
- Extensions to existing primitives land in `sutra/marketplace/native/src/`. (Per §14.15.1 phase-C box "Where" row.)
- TDD per `superpowers:test-driven-development`. (Per §14.15.1 phase-C box "Format" row.)
- Codex consult before edit per D40 G2. (Per §14.15.1 phase-C box "Format" row.)
- Cadence: per-block; can parallelize via subagent dispatch. (Per §14.15.1 phase-C box "Cadence" row.)

## Duration (target wall-clock)
NOT specified in canon. Runtime implementation pace; per-block with concurrent subagent dispatch allowed.

## DRI
Claude codes; codex reviews. (Per §14.15.1 phase-C box "Owner" row.)

## Acceptance (exit criteria)
Block functional + tests pass + codex PASS. (Per §14.15.1 phase-C box "Gate" row.)

## Dependencies (on other phases / blocks)
- Phase B (top-5 outcome-block feature specs) must be complete for those blocks.
- Phase D (codex review) runs concurrently per-PR — Phase C exit requires Phase D codex PASS, so they interlock per block.
- Block-level dependencies on canon primitives + events (e.g., B9 depends on canon Artifact / DataRef extension per F5 fidelity rule).

## Rollback
Per-block commit + per-PR codex verdict file at `.enforcement/codex-reviews/`; rollback = `git revert <PR-merge-sha>` on the block PR. Failing codex verdict (less than ADVISORY) blocks merge ⇒ no rollback needed pre-merge.

## References
- NATIVE-ENGINE.md §14.15.1 phase-C box
- ../decisions/ADR-NNN (per-block ADRs as they land)
- `sutra/marketplace/native/` (plugin runtime home)
- `superpowers:test-driven-development` skill
- D40 G2 (codex-consult-before-edit gate)
- `core:codex-sutra` skill (review mode)
