# test-strategy — eval pack

Three evals validate that the skill produces a TEST-STRATEGY.md that is:
- structurally complete (8 sections present)
- domain-coherent (pyramid shape matches subject)
- non-generic (anti-patterns named are specific to the subject)

## Running

Each eval is a markdown file with three sections:
1. **Input** — the prompt fed to Claude with `core:test-strategy` invoked
2. **Required assertions** — structural facts the output MUST contain
3. **Anti-assertions** — things the output MUST NOT contain

Manual runner (until we wire automated eval CI):

```bash
# In a fresh Claude Code session
# 1. Paste the Input from the eval file
# 2. Save Claude's TEST-STRATEGY.md output
# 3. Grep for the Required assertions; check Anti-assertions absent
# 4. Pass/fail per assertion; pass overall = >=80% assertions hit
```

## Baseline comparison

For each eval, also run WITHOUT the skill (plain prompt to Claude). Compare:
- Section completeness (skill should win 7+/8 sections vs ~3-4 for baseline)
- Pyramid heuristic match (skill cites the heuristic table; baseline guesses)
- Anti-patterns named for THIS subject (skill specific; baseline generic)

Skill is shipping when it beats baseline on all 3 axes for ≥2/3 evals.

## Cadence

Re-run on every plugin version bump. Rotate evals every 90 days.

Telemetry: append one row per run to `holding/research/skill-adoption-log.jsonl` with `eval_id` + `assertions_hit` + `baseline_delta`.
