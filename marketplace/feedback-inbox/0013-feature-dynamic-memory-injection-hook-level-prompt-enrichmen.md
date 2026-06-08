---
issue: 13
title: "[Feature] Dynamic memory injection \u2014 hook-level prompt enrichment with relevant memory entries before Claude sees the message"
author: vinitharmalkar
state: OPEN
created: 2026-04-27T14:26:17Z
updated: 2026-04-27T14:26:17Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/13
comments: []
---

# #13 [Feature] Dynamic memory injection — hook-level prompt enrichment with relevant memory entries before Claude sees the message

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-27T14:26:17Z  |  **Updated:** 2026-04-27T14:26:17Z
**URL:** https://github.com/sankalpasawa/sutra/issues/13

---

## Problem

Sutra's current memory system is passive: CLAUDE.md loads the full MEMORY.md index into every session's system context, and Claude decides what's relevant. This works but has two inefficiencies:

1. **All memory loads every turn** — MEMORY.md index is always in context regardless of whether it's relevant to the current prompt. For users with large memory stores, this is wasted tokens every turn.
2. **Relevance is Claude's job at response time** — Claude has to mentally scan memories while also processing the task. The shaping and the doing happen in the same step.

The smarter pattern: *before* the prompt reaches Claude, a hook scans the user's message, matches it against memory keywords, and injects only the 2–3 most relevant memory entries as structured context. Claude arrives at a pre-enriched prompt and can focus entirely on the task.

This is prompt shaping — but at zero latency cost (no API call, pure text pattern matching in bash/python) and with surgical precision (only relevant entries, not the full index).

## Why not a Haiku pre-call?

Adding a separate Haiku API call before every turn to "optimise the prompt" adds:
- 0.5–2s latency on every message
- Haiku tokens + output added to context
- Risk of misinterpreting and rewriting prompt intent incorrectly

A stateless keyword-match injection achieves 80% of the benefit at 0% of the cost.

## Proposed Feature: `UserPromptSubmit` Memory Injection Hook

### How it works

On every `UserPromptSubmit`:

1. Read the user's message text from hook stdin JSON
2. Load memory file index from `~/.claude/projects/{project}/memory/MEMORY.md`
3. For each memory entry, extract keywords from the `description` field
4. Score entries by keyword overlap with the user message (simple word intersection, no ML)
5. If top match score > threshold: read that memory file and inject it as structured context

### Injection format (appended to user message before Claude sees it)

```
[SUTRA MEMORY INJECT — 2 entries matched]
─ user_role_context.md: Vinit is Founder's Office at Testlify. Active: RFP pipeline, revenue reports, CEO dashboard.
─ reference_sutra_bot_docs.md: GDrive file IDs — TWSC doc (1WzlL63y...), CEO exec summary (1glHQmyE...).
[END INJECT]
```

### Match scoring (lightweight, no dependencies)

```python
def score(memory_description, user_message):
    desc_words = set(memory_description.lower().split())
    msg_words  = set(user_message.lower().split())
    return len(desc_words & msg_words)  # word intersection count

# Inject if score >= 2 (at least 2 words in common)
# Max 3 entries injected per turn
```

### What it replaces / complements

| Current approach | With this feature |
|---|---|
| Full MEMORY.md index always in system context | MEMORY.md index still loads (safety net), but pre-enrichment adds precision |
| Claude scans all memories at response time | Relevant memories surfaced before Claude processes |
| All-or-nothing recall | Scored, ranked, selective injection |

### When it does NOT inject

- User message < 5 words (too short to score meaningfully)
- No memory files exist
- `SUTRA_MEMORY_INJECT=0` env var set
- `~/.sutra-memory-inject-disabled` exists (kill-switch)

## Why Anthropic won't build this

Anthropic's memory feature (released April 2026) auto-summarises conversations and stores facts. It does not do targeted pre-prompt enrichment from a structured, user-curated knowledge base. Their system is retrospective (captures what happened); this is prospective (enriches what's about to happen). Different jobs.

More importantly: better prompt enrichment means fewer clarification turns, fewer retries, fewer tokens per completed task. Anthropic has no incentive to reduce turns-per-task.

## Implementation notes

- **Hook**: `UserPromptSubmit` (already registered in hooks.json)
- **Hook output**: `hookSpecificOutput.additionalContext` or equivalent injection field
- **Dependencies**: Python 3 (already required by Sutra), no pip installs
- **State**: reads existing `memory/` directory — no new files written
- **Performance**: keyword scoring on 10–20 memory files takes < 20ms

---
**Filed:** 2026-04-27 · Sutra 2.4.0 · Reported by Vinit (Testlify Founders Office)
