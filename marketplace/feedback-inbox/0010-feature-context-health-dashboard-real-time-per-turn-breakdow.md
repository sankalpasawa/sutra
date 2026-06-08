---
issue: 10
title: "[Feature] Context Health Dashboard \u2014 real-time per-turn breakdown of what's consuming the context window"
author: vinitharmalkar
state: OPEN
created: 2026-04-27T14:17:36Z
updated: 2026-04-27T14:17:36Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/10
comments: []
---

# #10 [Feature] Context Health Dashboard — real-time per-turn breakdown of what's consuming the context window

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-27T14:17:36Z  |  **Updated:** 2026-04-27T14:17:36Z
**URL:** https://github.com/sankalpasawa/sutra/issues/10

---

## Problem

In a long Claude Code session, token costs compound non-linearly. By turn 30, a simple question can cost 75,000+ tokens — but users have no visibility into *what* is eating their context. The conversation just gets slower and more expensive with no explanation.

Claude Code has `/compact` and auto-compaction at 95% capacity. Both are reactive — they fire when you've already hit the wall. Neither tells you *why* you're there or *which turns caused it*.

Anthropic won't build proactive token-waste visibility because cost transparency at the per-turn level conflicts with revenue maximization. This is Sutra's lane.

## Proposed Feature: Context Health per Turn

A PostToolUse hook that tracks cumulative tool output size across the session and produces a per-turn context growth signal.

### What it tracks

Every tool call has an output. That output stays in the context window for all future turns. The hook measures:

| Signal | Source | Proxy for |
|---|---|---|
| Tool output size (bytes) | PostToolUse stdin JSON | Tokens added this turn |
| Cumulative tool output | Running total across session | Context window fill from tools |
| Single large outputs | Threshold flag (e.g. >10KB) | Point-in-time spikes |
| Tool output share | Cumulative vs conversation estimate | "Tools vs chat" split |

Token approximation: `chars ÷ 4 ≈ tokens` — acknowledged rough but directionally accurate without a costly API round-trip to count exactly.

### What it shows (Stop hook report)

At end of session, emit to `~/.sutra/context-health.jsonl`:

```json
{
  "session_id": "...",
  "turns": 24,
  "tool_output_bytes_cumulative": 284000,
  "tool_output_tokens_est": 71000,
  "largest_single_output": {"tool": "Bash", "bytes": 48200, "turn": 7, "cmd": "python3 ..."},
  "top_3_contributors": [
    {"turn": 7,  "tool": "Bash",  "bytes": 48200},
    {"turn": 12, "tool": "mcp__google_drive__read_file_content", "bytes": 39800},
    {"turn": 19, "tool": "Bash",  "bytes": 22400}
  ]
}
```

And print a terse summary on Stop:

```
── Context Health ──────────────────────────────────
  Turns:              24
  Tool output (est):  71,000 tokens
  Largest output:     Turn 7 — Bash (48K tokens) — python3 inline script
  Advice:             3 outputs exceeded 10K tokens. Use Read tool with
                      offset/limit or pipe | head -100 to reduce context load.
────────────────────────────────────────────────────
```

### What it does NOT do

- Does not compress or modify anything
- Does not count conversation tokens (no API call overhead)
- Does not pretend to be exact — estimates are labeled as estimates
- Does not fire mid-turn unless an individual output exceeds a large threshold (e.g. 50KB)

## Why Anthropic won't build this

Anthropic's incentive is sustained usage, not minimal usage. A per-turn cost breakdown that shows "turn 7 cost you 48K tokens, here's how to avoid it" actively discourages the behavior that drives API revenue. Their tools (caching, compaction) extend sessions — they don't make them cheaper.

Sutra's job is the user's advocate for efficiency. This is that feature.

## Implementation notes

- **Hook**: PostToolUse (all tools) + Stop
- **State file**: `~/.sutra/context-health-{session_id}.jsonl` (per-session running log)
- **No new permissions needed**: PostToolUse already fires; reading stdin size is pure bash
- **Kill-switch**: `touch ~/.sutra-context-health-disabled`

---
**Filed:** 2026-04-27 · Sutra 2.4.0 · Reported by Vinit (Testlify Founders Office)
