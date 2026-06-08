---
issue: 6
title: "[Feedback] session-retrieve is phantom output + Sutra has no real cross-session memory vs Claude's native memory (released today)"
author: vinitharmalkar
state: CLOSED
created: 2026-04-27T13:59:13Z
updated: 2026-04-28T13:58:04Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/6
comments: [{'id': 'IC_kwDOR5MNCs8AAAABAnBx7A', 'author': {'login': 'sankalpasawa'}, 'authorAssociation': 'OWNER', 'body': 'Fixed in an earlier release (verified on plugin **v2.8.5+** today, 2026-04-28).\n\nThe hardcoded `session-retrieve` line is gone from `scripts/start.sh`. Banner now reads:\n> Skills loaded: input-routing, depth-estimation, readability-gate, output-trace\n\nNo `session-retrieve` skill exists in the plugin tree (verified via find). README cross-session memory claim removed.\n\nAnthropic shipped native Claude Code memory 2026-04-23 — that is the right surface for cross-session recall now. Sutra plugin no longer claims this capability.\n\nThanks for catching the phantom claim — this was a real trust hit. Subsequent versions tightened the audit trail (every banner string is now generated dynamically; no more hardcoded skill lists).', 'createdAt': '2026-04-28T13:58:03Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/6#issuecomment-4335890924', 'viewerDidAuthor': True}]
---

# #6 [Feedback] session-retrieve is phantom output + Sutra has no real cross-session memory vs Claude's native memory (released today)

**Author:** vinitharmalkar  |  **State:** CLOSED  |  **Labels:** —
**Created:** 2026-04-27T13:59:13Z  |  **Updated:** 2026-04-28T13:58:04Z
**URL:** https://github.com/sankalpasawa/sutra/issues/6

---

## Summary

Sutra claims cross-session memory recall as a feature, and lists `session-retrieve` as a loaded skill on every `/core:start`. Neither claim holds up to inspection. Meanwhile, Anthropic shipped native persistent memory for Claude Code on **April 23–27, 2026**, making this gap materially worse today than it was last week.

---

## Finding 1: `session-retrieve` is hardcoded phantom output

The `/core:start` banner always prints:
```
Skills loaded:   input-routing, depth-estimation, readability-gate, output-trace, session-retrieve
```

This line is **hardcoded** in `scripts/start.sh` (line 215):
```python
print("   Skills loaded:   input-routing, depth-estimation, readability-gate, output-trace, session-retrieve")
```

It is not dynamically detected. It does not reflect what is actually installed. The `session-retrieve` skill **does not exist** anywhere in the Sutra 2.4.0 file tree:

```
/skills/depth-estimation/SKILL.md     ← exists
/skills/input-routing/SKILL.md        ← exists
/skills/output-trace/SKILL.md         ← exists
/skills/readability-gate/SKILL.md     ← exists
/skills/sutra-learn/...               ← exists
session-retrieve/                     ← DOES NOT EXIST
```

`find /Users/vinit/.claude/plugins/cache/sutra -name "*session-retrieve*"` returns zero results.

The README describes it as *"recover abruptly-closed sessions after a laptop crash"* — but there is no hook, no script, no SKILL.md, and no implementation of any kind.

**This is a false claim on every start banner.** Users see it, trust it, and may make decisions (like not worrying about crash recovery) based on it.

---

## Finding 2: Sutra's "memory" is passive instruction delegation, not a memory system

Sutra's CLAUDE.md governance block includes instructions telling Claude to write markdown files to a `memory/` directory and maintain a `MEMORY.md` index. This is what produces the cross-session memory effect in practice.

But this is not Sutra doing memory. It is Sutra's system-prompt instructions telling **Claude** to do memory. The distinction matters:

| Property | Sutra's current approach | A real memory system |
|---|---|---|
| Who writes memories | Claude, when it decides to | Autonomous agent or hook |
| Triggered how | Claude notices something worth saving | Session-end hook, every turn, or on explicit save |
| Cross-session recall | MEMORY.md loaded via CLAUDE.md system context | Proactive retrieval, semantic search, relevance ranking |
| Crash recovery | None | Session state captured before crash |
| Memory quality | Depends on Claude's in-context judgment | Deterministic, auditable |
| User can query memory | Only via natural language to Claude | Direct API / CLI |

Sutra is a governance layer telling Claude "remember things if you think they're important." That is not the same as a memory infrastructure.

---

## Finding 3: Anthropic shipped native persistent memory for Claude Code on April 23–27, 2026

As of today (2026-04-27), Claude has **three native memory mechanisms**:

1. **Claude.ai consumer memory** — Auto-summarizes conversations every ~24 hours. Stores key facts, proactively recalled in future sessions. User can view, edit, delete.

2. **Claude Code auto memory** — Automatically accumulates build commands, debugging insights, architecture notes, code style preferences per project. Loads in new sessions. File-backed, inspectable.

3. **Managed Agents memory (public beta since April 23)** — Filesystem-backed memories exported/managed via API. Supports version rollback and content redaction.

Sutra's `memory/` directory approach and CLAUDE.md system-context loading are now **structurally equivalent to what Claude Code does natively** — but with less automation (Sutra relies on Claude noticing things; native memory runs hooks automatically).

**The result:** Sutra's memory claim is now not just incomplete — it is a duplicate of what Claude ships out of the box, with extra friction and a phantom skill name on top.

---

## What this means for users

| Expectation set by Sutra | Reality |
|---|---|
| "session-retrieve is loaded" | No such skill exists. Banner is hardcoded. |
| "Persistent memory across sessions" | Works via CLAUDE.md instruction to Claude — but only if Claude decides to save, only what Claude chooses to write |
| "Recover abruptly-closed sessions" (README) | No implementation of any kind |
| Memory is a Sutra feature | Memory is Claude Code's native feature. Sutra adds instructions but no infrastructure |

---

## Requested Changes

### Fix 1 — Remove or implement `session-retrieve` from the banner
The banner must only list skills that actually exist. Either:
- Remove `session-retrieve` from line 215 of `scripts/start.sh`, OR
- Implement the skill (SKILL.md + crash-recovery mechanism)

The current state — listing a non-existent skill — is misleading.

### Fix 2 — Honest memory documentation
The README and marketing copy should reflect what the memory system actually is:
> "Memory relies on Claude Code's built-in auto-memory system. Sutra's CLAUDE.md governance block includes instructions for Claude to write memory files and maintain a MEMORY.md index. This is loaded as system context on each session."

That's accurate and still valuable — it's just not "Sutra does memory."

### Fix 3 — Consider integrating with Claude's native memory
Now that Claude Code has native auto-memory (April 2026), Sutra should evaluate:
- Does the CLAUDE.md memory instruction still add value, or does it conflict/duplicate native memory?
- Should Sutra's session-end hooks (if they ever ship) write to the native memory format rather than a custom directory?
- Should `/core:status` show native memory state alongside Sutra governance state?

### Fix 4 — If session-retrieve is on the roadmap, track it publicly
If crash-recovery session retrieval is a planned feature, it should be a GitHub issue with a milestone — not a shipped feature listed in the active banner.

---

## Evidence

```bash
# session-retrieve skill file: zero results
find /Users/vinit/.claude/plugins/cache/sutra/core/2.4.0 -name "*session-retrieve*"
# (empty)

# The banner is hardcoded, not dynamic
sed -n '215p' /Users/vinit/.claude/plugins/cache/sutra/core/2.4.0/scripts/start.sh
# print("   Skills loaded:   input-routing, depth-estimation, readability-gate, output-trace, session-retrieve")

# Actual skills in 2.4.0
ls /Users/vinit/.claude/plugins/cache/sutra/core/2.4.0/skills/
# depth-estimation  input-routing  output-trace  readability-gate  sutra-learn
```

---

## Session context
- Date: 2026-04-27
- Sutra version: 2.4.0
- Claude Code model: claude-sonnet-4-6
- Claude native memory feature confirmed released: April 23–27, 2026
- Reported by: Vinit (Founders Office, Testlify)
