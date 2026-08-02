---
issue: 12
title: "[Feature] Tool Output Audit \u2014 flag oversized Bash/MCP outputs at point of occurrence and suggest leaner alternatives"
author: vinitharmalkar
state: OPEN
created: 2026-04-27T14:17:40Z
updated: 2026-04-27T14:17:40Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/12
comments: []
---

# #12 [Feature] Tool Output Audit — flag oversized Bash/MCP outputs at point of occurrence and suggest leaner alternatives

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-27T14:17:40Z  |  **Updated:** 2026-04-27T14:17:40Z
**URL:** https://github.com/sankalpasawa/sutra/issues/12

---

## Problem

The single biggest source of context bloat in a Claude Code session is not conversation length — it's **large tool outputs that persist in the context window for every subsequent turn.**

Research-backed breakdown of what fills context fastest:
1. Large Bash outputs (full file dumps, `python3` with huge stdout, `cat` on big files)
2. Large MCP tool outputs (Google Drive reads, database dumps)
3. Accumulated conversation history (grows slowly, ~200-500 tokens/turn)

Sutra's existing MCP compression hook (`posttool-mcp-compress.sh`) compresses MCP outputs ≥4KB *before Claude sees them* — that's excellent. But:
- Bash outputs have no equivalent hook
- The compression is silent — no user education
- There's no "here's a leaner way to do this" guidance at point of occurrence

## Proposed Feature: Tool Output Audit Hook

A PostToolUse hook that fires after every Bash and MCP call, flags outputs above a threshold, and emits an actionable recommendation.

### Trigger thresholds

| Output size | Action |
|---|---|
| < 8KB | Silent pass-through |
| 8KB – 30KB | Log to context-health file only (no interruption) |
| > 30KB | Emit inline advisory to user |
| > 80KB | Emit advisory + suggest immediate mitigation |

### Advisory format (emitted to stderr → Claude sees it)

```
📦 Large tool output: Bash returned ~18K tokens (72KB)
   This stays in your context window for all future turns.
   Leaner alternatives:
     • Use Read tool with offset/limit instead of python3 print-all
     • Pipe: command | head -100  (instead of full stdout)
     • Use jq -c for compact JSON instead of pretty-printed
   To suppress: RTK_AUDIT_SKIP=1 before your command
```

```
📦 Large MCP output: mcp__google_drive__read_file_content returned ~50K tokens (200KB)
   [C3c hook already compressed to ~25K tokens]
   Residual is still large. Consider:
     • Use search_files + targeted read instead of full document read
     • Request specific sections if the MCP supports it
```

### Command pattern recognition

For Bash outputs, pattern-match the command that produced the large output and suggest the known-good leaner equivalent:

| Pattern detected | Suggestion |
|---|---|
| `python3 ... print(...)` with large output | "Use Write to file + Read with limit/offset" |
| `cat <file>` > 30KB | "Use Read tool with offset+limit instead" |
| `find / -name ...` with many results | "Add `-maxdepth 3` or pipe to `head -50`" |
| `jq '.'` pretty-print > 30KB | "Use `jq -c` for compact output" |
| `git log` without `--oneline -20` | "RTK should have caught this — check rtk hook health" |
| `openpyxl` full sheet dump | "Slice rows: `ws.iter_rows(min_row=X, max_row=Y)`" |

### Connection to existing hooks

This complements — does not replace — the existing MCP compression hook:
- MCP compression fires *before* Claude sees the output (stealth optimization)
- This audit hook fires *after* and educates the user at point of occurrence
- Together: compress silently + teach explicitly

### Learning loop

The advisory is not just noise — it changes behavior:
- User learns "this command pattern always bloats context"
- They start using leaner patterns proactively
- Over time, context fill rate decreases without any hook intervention
- This is the highest-leverage token efficiency mechanism: **changing habits, not just patching outputs**

## Why Anthropic won't build this

The recommendation "use `head -100` instead of full stdout" actively reduces token consumption per equivalent outcome. A tool that teaches users to generate less output per task is structurally opposed to per-token revenue growth. Sutra's job is the user's efficiency, not Anthropic's revenue.

Anthropic will build better compaction, longer context windows, and smarter caching. They will not build a coach that says "you just added 50K tokens unnecessarily — here's how to avoid it next time."

## Implementation notes

- **Hook**: PostToolUse (Bash + mcp__.*)
- **Does not block**: advisory only, exits 0 always
- **Size measurement**: `${#OUTPUT}` bash string length, ÷ 4 for token estimate
- **Pattern matching**: small case/grep table in the hook itself (no external deps)
- **Kill-switch**: `touch ~/.sutra-audit-disabled` or `AUDIT_SKIP=1` per-call
- **Profile behavior**: on for all profiles; `individual` can suppress via config

---
**Filed:** 2026-04-27 · Sutra 2.4.0 · Reported by Vinit (Testlify Founders Office)
