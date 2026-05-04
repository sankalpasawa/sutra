# architect — eval pack

Three evals validate that the skill produces an ARCHITECTURE.md that is:
- structurally complete (8 sections present, not silently omitted)
- coherent (C4 levels agree; ADRs have real consequences; threat model is system-specific)
- non-generic (build-layer assignments and ADRs reflect THIS system's constraints, not boilerplate)

## Running

Each eval is a markdown file with three sections:
1. **Input** — the prompt fed to Claude with `core:architect` invoked
2. **Required assertions** — structural facts the output MUST contain
3. **Anti-assertions** — things the output MUST NOT contain

Manual runner:

```bash
# 1. In a fresh Claude Code session, paste the Input
# 2. Save Claude's ARCHITECTURE.md output
# 3. Grep for Required assertions; check Anti-assertions absent
# 4. Pass/fail per assertion; pass overall = >=80% assertions hit
```

## Baseline comparison

For each eval, also run WITHOUT the skill (plain prompt to Claude). Compare:
- Section completeness (skill should win 7+/8 vs ~3-5 baseline)
- ADR Consequences quality (skill enforces real consequences; baseline often has all-upside)
- Build-layer assignments (skill specific to Sutra D38; baseline absent)
- C4 L1↔L2↔L3 coherence (skill self-checks; baseline often diverges)

Skill is shipping when it beats baseline on all 4 axes for ≥2/3 evals.

## Cadence

Re-run on every plugin version bump. Rotate evals every 90 days.

Telemetry: append one row per run to `holding/research/skill-adoption-log.jsonl`.
