# Sutra — Sutra Config (self-hosted, tier 3 platform)

tier: 3                       # Platform — Sutra runs Sutra
enforcement_level: 3          # Skill + hook + memory
depth_default: 3              # Most Sutra work is thorough; governance work D5
depth_range: [1, 5]           # Full range — Sutra does surface through exhaustive
coverage: on                  # Platform must dogfood its own coverage engine
model_profile: quality

## Hooks
- enforce-boundaries.sh       # restrict sutra session to sutra/ + */feedback-from-sutra/
- cascade-warning.sh          # warn on edits with downstream implications
- policy-coverage-gate.sh     # PROTO-017: block policy-file edits missing coverage
- codex-review-gate.sh        # PROTO-019: ecosystem-wide AI code review (request/verify)

## Model routing
- Governance decisions: claude-opus-4-6
- Protocol drafting: claude-opus-4-6
- Documentation sync: claude-haiku-4-5-20251001

## Enabled Methods (D31, 2026-04-20 — Sutra-managed, do not edit manually)

Per D31, every method default = false for new clients. Sutra pushes updates via PROTO-018 to enable specific methods per client. File feedback to `feedback/` if you believe an enablement should change — never flip switches locally.

## Enabled Hooks (D32, 2026-04-20 — Sutra-managed, do not edit manually)

Per D32, the PostToolUse dispatcher will fire a hook only when listed in `os/hooks/posttool-registry.jsonl` AND marked `true` here. Default for every declared hook: false. Only Sutra flips via PROTO-018. Clients never toggle locally.

enabled_hooks:
  auto-coverage.sh: true   # approved 2026-04-20 (D31 Phase 3 v0, ff1048a)

## Enabled Methods (D31, 2026-04-20 — Sutra-managed, do not edit manually)

enabled_methods:
  INPUT-ROUTING: true
  ENGINE-ADAPTIVE: true
  GATE-PRESCORING: true
  ENGINE-ESTIMATION: true
  PHASE-OBJECTIVE: true
  PHASE-OBSERVE: true
  GATE-RESEARCH: true
  PHASE-SHAPE: true
  GATE-HLD: true
  GATE-ADR: true
  PHASE-PLAN: true
  GATE-PARALLEL: true
  PHASE-EXECUTE: true
  VERIFY-BASIC: true
  VERIFY-EVIDENCE: true
  VERIFY-STAGED: true
  VERIFY-MULTISTAGE: true
  PHASE-MEASURE: true
  GATE-FINDINGS: true
  PHASE-LEARN: true
  GATE-RETRO: true
  EXPERT-CONSULT: true
  RESEARCH-MARKET: true
  REVIEW-INDEPENDENT: true
  RETRO-FULL: true
  TRIAGE-LOG: true

# Rationale: Sutra-self is tier-3 platform and must dogfood its own full spec.
# Future Sutra sessions may tune this based on real coverage data.
