# deterministic-testing — eval pack

Three evals validate that the skill produces I/O determinism test scaffolding that is:
- structurally complete (test files + fixtures + property tests + FIXTURES.md)
- technique-appropriate (right combination of golden / snapshot / property / contract for the subject domain)
- non-brittle (snapshots assert shape not exact text when subject has cosmetic variability)

## Running

Each eval is a markdown file with three sections:
1. **Input** — the prompt fed to Claude with `core:deterministic-testing` invoked
2. **Required assertions** — structural facts the output MUST contain
3. **Anti-assertions** — things the output MUST NOT contain

Manual runner:

```bash
# 1. In a fresh Claude Code session, paste the Input
# 2. Capture the test files + fixture files Claude writes
# 3. Grep for Required assertions; check Anti-assertions absent
# 4. Pass/fail per assertion; pass overall = >=80% assertions hit
```

## Baseline comparison

For each eval, also run WITHOUT the skill (plain prompt to Claude). Compare:
- Fixture spread (skill enforces happy + edge + failure ≥3; baseline often 1-2)
- Property invariants (skill always emits ≥1; baseline often 0)
- FIXTURES.md presence (skill always; baseline rarely)
- Snapshot SHAPE-not-text discipline (skill enforces; baseline often exact-text snapshots → brittle)

Skill is shipping when it beats baseline on all 4 axes for ≥2/3 evals.

## Cadence

Re-run on every plugin version bump. Rotate evals every 90 days.
