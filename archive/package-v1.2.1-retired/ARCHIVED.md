# sutra/package/ — Archived 2026-04-23

This directory was `sutra/package/` — the npm distribution channel (`sutra-os@1.2.1`) of Sutra OS. It is RETIRED.

## Why

Founder directive 2026-04-23: **"Decommission the package. Everything via the Sutra plugin."**

Sutra is now distributed exclusively via the Claude Code plugin at `sutra/marketplace/plugin/`. The parallel npm channel that this directory backed is no longer the vehicle.

## What retirement means here

- **Archived in place** — not deleted. All 40 hooks, 6 commands, os-core reference material, templates, and outcome tests are preserved at their original relative paths under this directory. History is intact (`git log` works through the rename).
- **Not active** — no Asawa-holding hook or CI runs anything from this tree. The references in `holding/hooks/verify-os-deploy.sh`, `holding/hooks/policy-only-sensor.sh`, and related test fixtures have been updated to skip this path (retired-clean semantic).
- **npm listing is a separate track** — the `sutra-os@1.2.1` package listing on the public npm registry is untouched by this commit. Deprecation via `npm deprecate sutra-os@"*" "retired — use Sutra Claude Code plugin instead"` is queued as a separate follow-up.

## If you need something from here

The 29 hooks in this archive with NO counterpart in `sutra/marketplace/plugin/hooks/` (at the time of archival) are candidates for revival via the forthcoming BUILD-LAYER protocol (PROTO-021, draft at `holding/research/2026-04-23-build-layer-protocol-design.md`, pending founder sign-off). Revival path:

1. Identify the capability you want back
2. File a BUILD-LAYER L1 staging proposal in the authoring instance (`holding/hooks/`)
3. Add owner + acceptance criteria + promotion target
4. On promotion: land the resurrected version in `sutra/marketplace/plugin/hooks/` (NOT back in this archive)

## Hook counterpart table (as of 2026-04-23)

Hooks with a plugin counterpart (candidate for deletion once parity confirmed):
- `dispatcher-posttool.sh` ↔ `marketplace/plugin/hooks/dispatcher-posttool.sh`
- `rtk-auto-rewrite.sh` ↔ `marketplace/plugin/hooks/rtk-auto-rewrite.sh`
- `operationalization-check.sh` ↔ (plugin equivalent pending)

Hooks without a plugin counterpart (29 total):
agent-completion-check, architecture-awareness, artifact-check, auto-coverage, cascade-check, codex-review-gate, compliance-tracker, context-budget-check, coverage-gate, coverage-report, dispatcher-pretool, dispatcher-stop, enforce-boundaries, estimation-enforcement, hook-health-sensor, kpi-tracker, lifecycle-check, live_test_4, log-coverage, log-skill-feedback, log-triage, measurement-logger, new-path-detector, onboarding-self-check, policy-coverage-gate, process-fix-check, reset-turn-markers, resilience, session-checkpoint, session-logger, test-in-production-check, time-allocation-tracker, update-check, version-governance, wait-gate.

Note: several of these (e.g., `dispatcher-pretool`, `reset-turn-markers`, `cascade-check`) are live in `holding/hooks/` which is the authoritative source for Asawa. The copies here were downstream deploy targets of the package channel.

## Status flags

- **Tier**: retired
- **DRI historical**: Sutra Forge (Asawa authoring team)
- **DRI post-archive**: none
- **Revival path**: BUILD-LAYER L1 (PROTO-021 pending)
- **Git move SHA**: this directory begins at the commit following `deb81ac`
- **Prior commit (pre-archive cleanup)**: `deb81ac`
- **Related research**: `holding/research/2026-04-23-build-layer-protocol-design.md`
- **Related direction**: D29 (Sutra bare name), D33 (client firewall), founder 2026-04-23 amendment (decommission package)

## Do not edit files here

Files in this archive are frozen. If you need to change behavior, revive via the BUILD-LAYER path above, landing the new version in `sutra/marketplace/plugin/hooks/`.
