# incremental-architect — eval pack

Three evals validate that the skill produces a MIGRATION-PLAN.md that is:
- structurally complete (9 sections present, never silently omitted)
- pattern-coherent (selected migration pattern matches the migration goal)
- decommission-disciplined (specific gate criteria; no permanent parallel-run)

## Running

Each eval is a markdown file with three sections:
1. Input (prompt fed to Claude with `core:incremental-architect` invoked)
2. Required assertions (structural facts the output MUST contain)
3. Anti-assertions (things the output MUST NOT contain)

Manual runner:

```bash
# 1. In a fresh Claude Code session, paste the Input
# 2. Save Claude's MIGRATION-PLAN.md output
# 3. Grep for Required assertions; check Anti-assertions absent
# 4. Pass/fail per assertion; pass overall = >=80% assertions hit
```

## Baseline comparison

For each eval, also run WITHOUT the skill (plain prompt to Claude). Compare:
- Section completeness (skill should win 8+/9 vs ~4-6 baseline)
- Pattern selection rationale (skill enforces; baseline often skips)
- Per-phase rollback (skill always; baseline often "fix forward")
- Decommission gate (skill always specific; baseline often vague or absent)

Skill is shipping when it beats baseline on all 4 axes for ≥2/3 evals.

## Cadence

Re-run on every plugin version bump. Rotate evals every 90 days.
