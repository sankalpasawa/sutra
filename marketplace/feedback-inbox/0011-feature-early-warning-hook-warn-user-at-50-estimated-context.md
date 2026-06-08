---
issue: 11
title: "[Feature] Early Warning Hook \u2014 warn user at ~50% estimated context fill, before auto-compaction fires at 95%"
author: vinitharmalkar
state: OPEN
created: 2026-04-27T14:17:38Z
updated: 2026-04-27T14:17:38Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/11
comments: []
---

# #11 [Feature] Early Warning Hook — warn user at ~50% estimated context fill, before auto-compaction fires at 95%

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-27T14:17:38Z  |  **Updated:** 2026-04-27T14:17:38Z
**URL:** https://github.com/sankalpasawa/sutra/issues/11

---

## Problem

Claude Code's auto-compaction fires at 95% context capacity. By that point:

- You've already paid for all the tokens that inflated the context
- The compaction summary loses nuance you may still need
- The timing is reactive, not preventive

The ideal intervention point is **~50% fill** — early enough that a `/compact` preserves high-quality context, late enough that you've done meaningful work since the last clean state.

Anthropic won't build this because early compaction recommendations directly reduce per-session token spend. Sutra will.

## Proposed Feature: Context Fill Estimator + Early Warning

### Estimation approach

Sutra cannot read the live token count from Claude Code's internals directly. But it can estimate fill from measurable signals:

```
estimated_fill = (system_prompt_tokens + conversation_tokens + tool_output_tokens) / context_limit

Where:
  system_prompt_tokens  = measured once at SessionStart (stable)
  conversation_tokens   = turns × avg_tokens_per_turn (rolling average)
  tool_output_tokens    = cumulative PostToolUse output sizes ÷ 4
  context_limit         = 200,000 (claude-sonnet-4-6 / claude-opus-4-7)
```

This is an estimate, not an exact count. It is labeled as such. The error margin is acceptable for a "heads up" warning — it doesn't need to be precise to be useful.

### Warning trigger

When estimated fill crosses **50%**, emit once per session on the next UserPromptSubmit:

```
⚠️  Context est. ~52% full (~104K / 200K tokens)
    Tool outputs account for ~68K of that.
    Consider: /compact (preserves more context now vs at the 95% wall)
    Suppress: SUTRA_CONTEXT_WARN=0
```

Key design decisions:
- **Fires once per session**, not every turn (not nagging)
- **Actionable**: tells user exactly what to type
- **Suppressable**: env var or touch file kill-switch
- **Honest**: "est." prefix on every number — never claims false precision
- **Threshold configurable**: default 50%, user can set via `~/.sutra/config` (e.g. `context_warn_pct=40`)

### Why 50% and not 70%?

At 50% fill, a `/compact` produces a high-fidelity summary — you still have substantial context for Claude to work from. At 70%, the summary is already compressed under pressure. At 95%, auto-compaction fires and you lose the choice.

The goal is to give users the *option* before the *wall*, not to force compaction.

## What this is not

- **Not a compaction feature** — Sutra doesn't compress anything. It just tells the user when now is a good time to use Claude Code's existing `/compact`.
- **Not a cost calculator** — No dollar amounts. Token estimates only.
- **Not intrusive** — One warning per session, suppressable, opt-out by default for `individual` profile.

## Implementation notes

- **Hooks**: SessionStart (measure system prompt size), PostToolUse (accumulate output sizes), UserPromptSubmit (check threshold, emit warning once)
- **State**: `~/.sutra/context-estimate-{session_id}.json` — running totals
- **Profile behavior**: `individual` profile → off by default; `project`/`company` → on by default
- **No new permissions**: all hooks already registered; bash arithmetic only

## Why Anthropic won't build this

Auto-compaction at 95% is designed to keep sessions alive at the limit — it's a quality-of-life feature that enables *more* usage. A proactive warning at 50% that says "compact now and save tokens" is a cost-reduction recommendation that conflicts with their per-token revenue model. That's Sutra's job.

---
**Filed:** 2026-04-27 · Sutra 2.4.0 · Reported by Vinit (Testlify Founders Office)
