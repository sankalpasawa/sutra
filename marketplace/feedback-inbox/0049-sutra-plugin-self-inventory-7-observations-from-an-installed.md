---
issue: 49
title: "Sutra plugin self-inventory + 7 observations from an installed session (v2.9.1)"
author: sankalpasawa
state: OPEN
created: 2026-04-30T19:35:00Z
updated: 2026-04-30T19:35:00Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/49
comments: []
---

# #49 Sutra plugin self-inventory + 7 observations from an installed session (v2.9.1)

**Author:** sankalpasawa  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-30T19:35:00Z  |  **Updated:** 2026-04-30T19:35:00Z
**URL:** https://github.com/sankalpasawa/sutra/issues/49

---

Hi Sutra team — sharing a structured inventory of what your plugin ships, observed from inside a running Claude Code session (core@sutra v2.9.1 installed via marketplace). Companion to a parallel inventory of the Claude Code harness, intended to help you gap-check coverage.

## What's installed

- Plugin: core@sutra v2.9.1 (commit 070dbad9), installed 2026-04-27, last updated 2026-04-30
- Cache versions on disk: 2.1.0, 2.6.0, 2.9.1
- Path: `~/.claude/plugins/cache/sutra/core/2.9.1`

## Slash commands (10)
`/core:start`, `/core:status`, `/core:update`, `/core:learn`, `/core:workflow`, `/core:depth-check`, `/core:permissions`, `/core:sbom`, `/core:feedback`, `/core:uninstall`

## Skills (9)
input-routing, depth-estimation, blueprint, readability-gate, output-trace, skill-explain, workflow, codex-sutra, sutra-learn

## Hooks (77 shell scripts) — grouped
- **Governance gates**: blueprint-check, depth-marker-pretool, input-classification-gate, permission-gate, policy-coverage-gate, policy-only-sensor, enforce-boundaries, build-layer-check, architecture-awareness
- **Codex review path (PROTO-019)**: codex-directive-detect/-gate/-sweep, codex-review-gate
- **Estimation/triage**: estimation-collector, estimation-enforcement, estimation-stop, triage-collector, log-triage, measurement-logger, time-allocation-tracker
- **Feedback loop (PROTO-024 / D36)**: feedback-auto-abandonment, feedback-auto-correction, feedback-auto-override, feedback-channel-guard, feedback-routing-rule, log-skill-feedback, assistant-feedback
- **Telemetry/KPI**: emit-metric, flush-telemetry, latency-collector, kpi-tracker, posttool-counter, session-logger, session-checkpoint, rotate-logs
- **Lifecycle**: sessionstart-auto-activate, sessionstart-privacy-notice, session-start-rotate, per-turn-discipline-prompt, reset-turn-markers, update-banner, onboarding-self-check
- **Discipline/output linting**: narration-not-artifact, output-behavior-lint, principle-regression, process-fix-check, operationalization-check, self-assess-before-foundational
- **Subagent/dispatcher**: subagent-dispatch-brief, dispatcher-pretool, dispatcher-posttool, dispatcher-stop, agent-completion-check
- **Assistant lifecycle (D37)**: assistant-decommission, assistant-explain, assistant-kill-switch, assistant-observer
- **Health/safety/resilience**: hook-health-sensor, tripwire-hook-sizes, resilience, keys-in-env-vars, cascade-check, context-budget-check, structural-move-check, new-path-detector
- **Misc**: bash-summary-pretool, posttool-mcp-compress, artifact-check, completion-protocol-check, compliance-tracker, check-graduation, lifecycle-check, research-cadence-check, test-in-production-check, rtk-auto-rewrite, rtk-health-check

## Engines
BLUEPRINT-ENGINE, ESTIMATION-ENGINE, COVERAGE-ENGINE, ADAPTIVE-PROTOCOL, MEASUREMENT-PROTOCOL — plus method-registry.jsonl, estimation-log.jsonl, coverage-log.jsonl.

## Charters
FEEDBACK, OPERATIONALIZATION, PEDAGOGY, PERMISSIONS, PRIVACY, SECURITY, SPEED, SPEED-phase-taxonomy, TOKENS.

## Layered repo
- layer1-abstraction (research/synthesis)
- layer2-operating-system (manifests v1.7/v1.9, OPERATING-MODEL, ENFORCEMENT, PARALLELIZATION-ARCHITECTURE, POLICY-COVERAGE, READABILITY-STANDARD, TASK-LIFECYCLE + a-company-architecture / b-agent-architecture / c-human-agent-interface / d-engines / templates)
- layer3-modules (b2c-ai-agent, b2c-consumer-app)
- layer4-practice-skills (PRINCIPLES-BY-FUNCTION)

## State surface
state/system.yaml (SoT), schema.json, override-schema.json, charter-coverage.yaml, direction-coverage.yaml, run-tests.mjs, validate.mjs, test-framework.mjs.

## Privacy posture (good)
Default telemetry OFF, explicit opt-in via `/core:start`, env opt-outs `SUTRA_TELEMETRY=0` / `SUTRA_FEEDBACK_FANOUT=0`, sentinel file `~/.sutra-feedback-fanout-disabled`, 3-level kill-switch (env / fs / SUTRA-CONFIG) for BLUEPRINT.

## Companion: Sutra Native v1.0.2
TypeScript-native engine — source preview only (no compiled main/exports, ships .ts, no bin/ or skills/). 4 primitives, 6 laws, Skill Engine R4 contract, Workflow Engine 5-stage runtime. Hook-activated plugin surface planned for v1.x.

---

## Observations / suggested actions

1. **Version drift**: marketplace.json advertises core v2.8.5, but the installed plugin is v2.9.1. Either publish updated manifest or align.
2. **Native v1.0.2 is preview-only**: anyone installing it gets nothing runnable today. Worth a clearer "EVALUATION ONLY" tag in marketplace summary.
3. **Harness-primitive coverage gap**: no skill currently fronts WebFetch, WebSearch, RemoteTrigger, Task* (cloud agents), EnterWorktree, EnterPlanMode, MCP tools, or ScheduleWakeup. BLUEPRINT/depth gates are tied to Edit/Write/Bash/Agent — these other tool surfaces bypass governance.
4. **Subagent governance**: subagent-dispatch-brief and dispatcher-* hooks exist, but worth confirming spawned subagents inherit the depth marker and BLUEPRINT requirement (and that hooks fire on subagent tool calls, not just main thread).
5. **Memory integration**: Sutra has its own `state/` and `coverage-log.jsonl`, but no skill reads/writes the harness's typed memory at `~/.claude/projects/.../memory/` (user/feedback/project/reference). Two parallel memory systems — possible to consolidate or bridge.
6. **Hook count is high (77)**: a coverage/dedup sweep may be due. hook-health-sensor and tripwire-hook-sizes already exist — worth running a coverage map against `posttool-registry.jsonl`.
7. **codex-sutra wrapper**: marketplace description claims user-facing `/codex` references were rewired to `/codex-sutra` in v2.8.0 — worth a final grep to confirm none remain (esp. in older docs / archive/).

### Bonus finding (meta)

Discovered while submitting: `/core:feedback --public` help text says it posts via `gh issue create` after a `yes` prompt, but the actual flow tried to clone a `sutra-data` repo and deferred when that failed — no `gh issue create` and no confirmation prompt. Help text and behavior have drifted; this issue was ultimately posted via direct `gh` invocation instead.

Happy to expand any section. — captured from a Claude Code session at abhishek@testlify.com
