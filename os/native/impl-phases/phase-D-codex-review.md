---
part-id: phase-D
bucket: impl-phases
template: L12-roadmap-entry
parity-source: §14.15.1 phase D box
parity-source-sha256: 336b815c191f788678f4c9bfe1ed0fa762a6dd47befeffcfde37e0e4d2de0319
status: DRAFT v1
authored: 2026-05-09
---

# Phase D: Codex Review on Diff

## Gate (entry criteria)
Phase C produced a PR diff for a block (or block extension). PROTO-019 directive gate active per canon.

## Scope (what gets done)
- Per-PR diff review via `core:codex-sutra` skill review mode. (Per §14.15.1 phase-D box "Where" row.)
- Verdict file written at `.enforcement/codex-reviews/<date>-<slug>.md` with DIRECTIVE-ID + CODEX-VERDICT fields. (Per §14.15.1 phase-D box "Format" row.)
- Cadence: per-PR; PROTO-019 directive gate. (Per §14.15.1 phase-D box "Cadence" row.)

## Duration (target wall-clock)
NOT specified in canon. Per-PR; bounded by codex CLI 15-min hard cap (per `core:codex-sutra` skill).

## DRI
Claude dispatches; codex returns. (Per §14.15.1 phase-D box "Owner" row.)

## Acceptance (exit criteria)
CODEX-VERDICT >= ADVISORY (PASS preferred). (Per §14.15.1 phase-D box "Gate" row.)

## Dependencies (on other phases / blocks)
- Phase C produces the diff that Phase D reviews.
- Blocks Phase E: a PR cannot ship unless Phase D verdict gate passes.
- PROTO-019 directive (codex-review-on-diff gate) must be active per canon.

## Rollback
A failing codex verdict prevents merge ⇒ no rollback needed; PR returns to Phase C for fix. Verdict files at `.enforcement/codex-reviews/` are append-only audit records; not rolled back.

## References
- NATIVE-ENGINE.md §14.15.1 phase-D box
- `core:codex-sutra` skill (review mode)
- PROTO-019 directive (codex-review-on-diff gate)
- `.enforcement/codex-reviews/` (verdict file home)
