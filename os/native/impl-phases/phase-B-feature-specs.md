---
part-id: phase-B
bucket: impl-phases
template: L12-roadmap-entry
parity-source: §14.15.1 phase B box
parity-source-sha256: 13cbd65373b71e654636b357d53c79ef7c07e03a34e1145563798d9fca192b4e
status: DRAFT v1
authored: 2026-05-09
---

# Phase B: §16 Feature Specs Per Block

## Gate (entry criteria)
Phase A's §16 section reached DRAFT skeleton (one sub-section stub per block); founder-owned layers L1/L2/L4 ratified so outcome ordering (per P14) is stable; Q39 top-5 outcome ranking confirmed (per §14.15.2). NOT specified in canon as an exact gate predicate beyond "after Phase A founder-owned layers DRAFT v1"; runtime implementation choice.

## Scope (what gets done)
- Author per-block feature specs as sub-sections of NATIVE-ENGINE.md §16, one sub-section per block.
- Block set: B1-B18 + 7a-7e + F1 (per canon §16 enumeration).
- Per L8 standard: name + 1-line summary + scope-in/out + UX flow + acceptance + data model + edges + telemetry. (Per §14.15.1 phase-B box "Format" row.)
- Cadence: 1-2 features / turn. (Per §14.15.1 phase-B box "Cadence" row.)

## Duration (target wall-clock)
NOT specified in canon. Runtime implementation pace at 1-2 features / turn × ~24 blocks ⇒ multi-week.

## DRI
Claude drafts; founder reviews. (Per §14.15.1 phase-B box "Owner" row.)

## Acceptance (exit criteria)
Top-5 outcome blocks (per Q39) authored before Phase C starts. (Per §14.15.1 phase-B box "Gate" row.)

Top-5 per §14.15.2: B9 Closed-Loop Artifact, B7 Pre/Post Validation, 7d Lifecycle Orchestrator, B5 Explanation Surface, B18 Person Formation.

Other 13 blocks (B1-B4 · B6 · B8 · 7a-7c · 7e · B10-B13 · B14-B17) ship as STUBS in v1 per P3; fill incrementally based on founder feedback signal. (Per §14.15.2 trailing paragraph.)

## Dependencies (on other phases / blocks)
- Phase A (founder-owned layers DRAFT v1) must complete first.
- Q39 (top-5 outcome ranking) must be answered.
- Block specs cross-reference Native primitives + events + hardstops (see ../primitives/, ../events/, ../hardstops/).

## Rollback
Per-block sub-section commit; `git revert` per block. STUB-state fallback for any block whose feature-spec turns out to disagree with canon hardstops or invariants (founder direction).

## References
- NATIVE-ENGINE.md §14.15.1 phase-B box
- NATIVE-ENGINE.md §14.15.2 (outcome-first ordering + top-5)
- NATIVE-ENGINE.md §16 (per-block feature-spec home)
- ../blocks/B9-closed-loop-artifact.md, ../blocks/B7-pre-post-validation.md, ../blocks/7d-lifecycle-orchestrator.md, ../blocks/B5-explanation-surface.md, ../blocks/B18-person-formation.md (top-5 outcome blocks)
- ../open-questions/Q39 (outcome-ranking question; if formalized in `../open-questions/`)
