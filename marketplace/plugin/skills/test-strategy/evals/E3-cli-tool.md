# Eval E3 — CLI Tool (golden-file E2E dominant)

## Input

> Design the test strategy for a new CLI tool. Subject: a Bash + jq tool called `rtk` that compresses verbose `git`/`find`/`log` output into compact summaries (~70% size reduction). Reads from stdin or args, writes to stdout, uses no network or persistent state. Risk profile: internal tooling. Existing infra: bats test framework, golden file fixtures already convention in repo. Failure modes the team is most worried about: regression in compression ratio, behavior drift across macOS/Linux jq versions, breakage on malformed input.

## Required assertions (output MUST contain)

| # | Assertion | Where to check |
|---|---|---|
| 1 | All 7 main sections + anti-patterns emitted (8 total) | grep section headings |
| 2 | Risk profile correctly classified as `internal-only` (or `internal tooling`) | section 1 |
| 3 | Pyramid skews E2E-heavy (≥40%); golden-file tests prominent; matches "CLI tool" heuristic | section 2 |
| 4 | Golden file fixtures declared as primary fixture mechanism; bats as runner | section 3 |
| 5 | Mock-vs-real: file system uses tmpdir (real); no third-party APIs to mock | section 4 |
| 6 | Coverage targets at internal-tooling defaults (~60% line, 50% branch) — NOT safety-critical levels | section 5 |
| 7 | AI eval-pack section is present with a not-applicable placeholder (non-AI subject) — section is NOT silently omitted | section 6 |
| 8 | CI gates: bats E2E blocks merge; cross-platform matrix (macOS + Linux) at least nightly | section 7 |
| 9 | Anti-patterns named for THIS subject: ≥3 of {brittle goldens that fail on cosmetic whitespace, no malformed-input fixtures, single-platform testing for a tool that ships cross-platform, regression in compression ratio not measured, jq version pinning absent} | section 8 |
| 10 | Compression-ratio regression OR cross-platform jq drift named as a failure mode + has a corresponding test class | sections 1, 8 |

Pass = ≥8/10 assertions hit.

## Anti-assertions (output MUST NOT contain)

- Pyramid that puts unit tests above 35% (CLI domain favors E2E)
- AI eval-pack content (no AI here)
- Coverage targets at safety-critical (95%) or user-facing (80%) — should be internal-tooling
- Mocking the file system — golden-file tests use real tmpdir
- Generic CLI anti-patterns without naming the compression-ratio + cross-platform-jq risks specifically

## Baseline comparison

Without the skill, Claude typically:
- Suggests unit tests for jq filter logic (~50% pyramid weight)
- Doesn't propose golden-file fixtures unless the user mentions them
- Doesn't think about compression-ratio regression (it's domain-specific to this tool)
- Picks 80% line coverage default
- Doesn't address jq cross-version drift

Skill should win on assertions 3, 6, 9, 10 vs baseline.
