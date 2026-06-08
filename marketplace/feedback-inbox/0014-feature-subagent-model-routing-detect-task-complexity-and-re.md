---
issue: 14
title: "[Feature] Subagent model routing \u2014 detect task complexity and recommend/set model:haiku for simple subtasks instead of defaulting to main session model"
author: vinitharmalkar
state: OPEN
created: 2026-04-27T14:26:57Z
updated: 2026-04-28T08:08:14Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/14
comments: [{'id': 'IC_kwDOR5MNCs8AAAABAkrlBA', 'author': {'login': 'vinitharmalkar'}, 'authorAssociation': 'NONE', 'body': "**Related: #23 — Dynamic Main-Session Model Switching**\n\nThis issue (#14) covers subagent routing via the Agent tool's `model` parameter.\n\nIssue #23 is the complementary spec for **main-session** model switching — same classification logic, same model tiers, but targeting the primary session model rather than spawned subagents.\n\n#23 is currently blocked by a Claude Code platform constraint (no mid-session model switch API). When that constraint is lifted, the keyword classifier and model tier mapping defined in this issue (#14) should be the single source of truth — #23 inherits from here rather than duplicating.\n\nTogether: #14 handles the subagent layer, #23 handles the main session layer.", 'createdAt': '2026-04-28T08:08:14Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/14#issuecomment-4333430020', 'viewerDidAuthor': False}]
---

# #14 [Feature] Subagent model routing — detect task complexity and recommend/set model:haiku for simple subtasks instead of defaulting to main session model

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-27T14:26:57Z  |  **Updated:** 2026-04-28T08:08:14Z
**URL:** https://github.com/sankalpasawa/sutra/issues/14

---

## Problem

When Claude Code spawns a subagent via the Agent tool, it inherits the main session model by default. In practice this means:

- A Haiku-tier task (grep a file, look up a value, run a quick bash check) runs on Sonnet or Opus
- A 49-minute extraction job that should have been a 2-minute Python script runs on Sonnet
- Every spawned agent — regardless of task complexity — costs the same per-token as the main session

This is a direct, addressable waste. The Agent tool accepts a `model` parameter. Nothing in Claude Code or Sutra today sets it based on task type.

## What Anthropic won't build

A routing layer that says "this subtask is simple enough for Haiku — use that instead of Opus" directly reduces per-call revenue on their most expensive models. Anthropic will never proactively recommend model downgrade. This is Sutra's lane.

Haiku is ~15–20x cheaper than Opus per token. On agent-heavy sessions — common in production Sutra usage — routing even 30% of subagents to Haiku materially reduces session cost.

## Why mid-session model switching is a non-starter

Claude Code sets the model at session start. There is no `/switch-model` command, no hook output field that overrides the main session model per-turn. This is a hard platform constraint.

**Subagents are different.** The Agent tool's `model` parameter is the only sanctioned mid-session model change mechanism. This feature targets only that surface — not the main session.

## Proposed Feature: Two-layer approach

### Layer 1 — CLAUDE.md governance instruction (immediate, zero code)

Add a routing rule to the governance block that Sutra writes into `CLAUDE.md`:

```markdown
## Subagent Model Routing

When spawning a subagent via the Agent tool, select model by task type:

| Task type | Model | Rationale |
|---|---|---|
| File lookup, grep, simple bash, format conversion | haiku | Cheap, fast, sufficient |
| Data extraction, pattern matching, counting | haiku | No reasoning required |
| Cross-reference, summarisation, light analysis | sonnet | Moderate complexity |
| Architecture decisions, complex debugging, planning | opus | Full reasoning required |
| Research with web search | sonnet | Balanced cost/quality |

Default: inherit session model only if task type is unclear.
```

This requires zero hook code — it's a governance instruction that shapes Claude's Agent tool calls immediately.

### Layer 2 — `UserPromptSubmit` complexity classifier hook (enforcement)

A lightweight hook that detects when the user is asking for a task that will likely spawn subagents, classifies complexity, and prepends a model recommendation:

```
[SUTRA MODEL ROUTE]
Task type: file-lookup (keyword match: "find", "locate", "check if")
Recommended subagent model: haiku
Rationale: read-only lookup, no reasoning required
[END ROUTE]
```

#### Classification (keyword-based, no ML)

```python
HAIKU_SIGNALS   = ["find", "locate", "grep", "check if", "list", "count", 
                    "format", "convert", "extract column", "read file",
                    "does X exist", "what is the value of"]

SONNET_SIGNALS  = ["summarise", "compare", "analyse", "cross-reference",
                    "research", "explain why", "investigate"]

OPUS_SIGNALS    = ["design", "architect", "plan", "debug complex",
                    "write strategy", "evaluate tradeoffs"]
```

Score by signal hits → emit recommendation → Claude uses it when constructing Agent tool call.

### What this does NOT do

- Does not change the main session model
- Does not force a model — it recommends. Claude can override with reasoning.
- Does not add any API calls or latency-producing steps
- Does not apply to non-Agent tool calls

## Expected impact

On a session like the one that prompted this issue (49-min, 50K token extraction task):
- The extraction subagent was Sonnet-complexity work (it needed reasoning about format)
- But the cross-reference step (compare 77 IDs against 979 items) was Haiku-tier
- Routing the dedup subagent to Haiku: same result, ~15x cheaper for that call

Across a typical agent-heavy session (5–10 subagents), routing 2–3 to Haiku saves an estimated 30–50% of subagent token cost.

## Implementation notes

- **Layer 1**: CLAUDE.md governance block update — ships in next `sutra start` run
- **Layer 2**: `UserPromptSubmit` hook, python3 keyword scorer, no new dependencies
- **Model constants**: `haiku` = `claude-haiku-4-5`, `sonnet` = `claude-sonnet-4-6`, `opus` = `claude-opus-4-7` (update on model releases)
- **Kill-switch**: `SUTRA_MODEL_ROUTE=0` or `~/.sutra-model-route-disabled`
- **Profile**: on for `project` and `company`; off for `individual` (too opinionated for personal use)

---
**Filed:** 2026-04-27 · Sutra 2.4.0 · Reported by Vinit (Testlify Founders Office)
