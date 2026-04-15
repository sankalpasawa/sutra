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
