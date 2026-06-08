---
issue: 23
title: "[feedback v2.7.3] from plugin"
author: vinitharmalkar
state: OPEN
created: 2026-04-28T08:07:38Z
updated: 2026-04-28T08:07:38Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/23
comments: []
---

# #23 [feedback v2.7.3] from plugin

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-28T08:07:38Z  |  **Updated:** 2026-04-28T08:07:38Z
**URL:** https://github.com/sankalpasawa/sutra/issues/23

---

Feature: Dynamic Main-Session Model Switching — user-permissioned model change based on task complexity

## Relationship to existing issues

This is the missing half of #14 (Subagent Model Routing).

Issue #14 covers routing spawned subagents (Agent tool) to Haiku/Sonnet/Opus by task complexity — and explicitly excluded main-session switching with this note:

  'Claude Code sets the model at session start. There is no /switch-model command, no hook output field that overrides the main session model per-turn. This is a hard platform constraint.'

This issue tracks the main-session version of that idea. It is NOT a duplicate — it is a forward spec to be implemented the moment the platform constraint is lifted.

---

## The Feature

When Sutra detects a task complexity mismatch — the current session model is over- or under-powered for what the user just asked — it should:

1. Detect the mismatch (via Depth Estimation + keyword classification already in #14)
2. Surface a recommendation to the user with reasoning
3. Ask for explicit permission (never switch silently)
4. Execute the switch if confirmed

Example interaction:

  [SUTRA MODEL SUGGEST]
  You asked: 'find all files that import lodash'
  Current model: Opus (claude-opus-4-7) — full reasoning, ~20x cost of Haiku
  Task type: file lookup — no reasoning required
  Recommendation: switch to Haiku for this task, return to Opus after
  Estimated saving: ~85% of this task's token cost

  Switch model for this task? [YES — use Haiku] [NO — stay on Opus] [ALWAYS for this task type]

---

## Trigger Logic (mirrors #14 classification)

Downgrade suggestions (expensive → cheaper):
  Opus → Sonnet: when task is summarise / compare / analyse / cross-reference
  Opus → Haiku:  when task is find / grep / list / count / format / check if
  Sonnet → Haiku: when task is pure lookup with no synthesis required

Upgrade suggestions (cheaper → more capable):
  Haiku → Sonnet: when task requires cross-file reasoning or ambiguity resolution
  Sonnet → Opus:  when task is architecture / planning / complex debugging / tradeoff evaluation

---

## User Permission Model

Three permission levels (configurable):

  SUGGEST:  Sutra recommends, user always confirms — default
  AUTO:     Sutra switches automatically, logs the change, user can undo
  OFF:      No switching, no suggestions

For SUGGEST mode, checkpoint integrates with the Cognitive Checkpoints system (#21) — model recommendation appears inside the Intent Lock block before execution starts.

---

## Session Context Preservation

On switch, Sutra must guarantee:
  - Full conversation context carries over (no truncation)
  - User is shown before/after model + estimated cost delta
  - A one-command undo: /core:model-restore
  - Switch is logged in session approval ledger (#20 — Approval Visibility Layer)

---

## Platform Constraint — CURRENT STATUS: BLOCKED

As of 2026-04-28, Claude Code does not expose a mid-session model switch API. The model is set at session start and cannot be changed per-turn via hook output.

THIS TICKET SHOULD BE REVISITED WHEN:
  - Claude Code / Anthropic API adds a per-turn or per-task model override parameter
  - Any LLM provider (OpenAI, Gemini, Mistral, etc.) exposes a mid-session model switch in their CLI or agent SDK
  - Claude Code releases a /switch-model command or equivalent
  - The Agent tool is extended to allow the main agent (not just subagents) to change its own model

Recommended: add a GitHub Action or manual review trigger — when any of the above ships, reopen and prioritize this ticket.

In the meantime, Layer 1 of this feature IS implementable today via CLAUDE.md governance instructions that prime Claude to recommend a model switch at the start of a new session when it detects task type mismatch. This is advisory only — not a real switch — but plants the habit.

---

## Connection to Related Issues

#14 — Subagent Model Routing: covers Agent tool subagents only. This issue covers the main session. The classification logic, keyword signals, and model tier mapping in #14 should be reused here verbatim — single source of truth for routing rules.

#20 — Approval Visibility Layer: model switches should appear in the green approval toast and session digest as a distinct category ('model changes').

#21 — Cognitive Checkpoints: model recommendation should appear inside the Intent Lock block — user picks task direction AND confirms model in the same checkpoint, not two separate interruptions.

---

## Implementation Plan (for when platform unblocks)

Phase 1 (advisory, ships today):
  - CLAUDE.md governance instruction that prompts Claude to recommend a session restart with different model when task type mismatches current model
  - Zero hook code required

Phase 2 (when /switch-model or equivalent ships):
  - UserPromptSubmit hook: classify task, detect mismatch, emit SUTRA MODEL SUGGEST block
  - User confirmation handler
  - Switch execution + context preservation check
  - Undo command: /core:model-restore
  - Logging to approval ledger

Phase 3:
  - ALWAYS rule persistence (user says 'always use Haiku for lookups' — Sutra remembers)
  - Cost savings report in session digest: 'Model routing saved ~/bin/zsh.23 this session'

---

Filed: 2026-04-28 · Sutra 2.7.3 · Reported by Vinit (Testlify Founders Office)
Blocked by: Claude Code platform constraint (no mid-session model switch API)
Revisit trigger: any LLM CLI/SDK adds per-task model override
