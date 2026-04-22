---
name: sutra
description: Activate Sutra mode for this session. Pulls CEO day from os/*.md (priorities, OKRs, status). Apply input-routing, depth-estimation, readability-gate, output-trace to every subsequent turn.
disable-model-invocation: true
---

# /sutra — Activate Sutra mode

## Actions

1. Check install state:

```!
test -f .claude/sutra-version && echo "INSTALLED" || echo "NOT_INSTALLED"
```

2. If `NOT_INSTALLED`, tell the user:

```
Sutra isn't deployed to this folder yet. Run:
  npx -y github:sankalpasawa/sutra-os init

Then restart Claude Code and try /sutra again.
```

3. If `INSTALLED`, pull CEO-day context:

```!
echo "Sutra version: $(cat .claude/sutra-version 2>/dev/null | head -1)"
cat CLAUDE.md 2>/dev/null | head -5
echo "---"
cat TODO.md 2>/dev/null | head -15
echo "---"
cat os/STATUS.md 2>/dev/null | head -10
echo "---"
cat os/OKRs.md 2>/dev/null | head -15
```

4. Render the CEO day dashboard using content above. Apply the readability gate (tables, progress bars, boxed decisions).

5. Announce:

```
🧭 Sutra is ACTIVE for this session.

From this point on:
  • Every message → input routing (emit the 5-line block)
  • Every task → depth + estimation block (1-5 scale)
  • Every output → readability gate
  • Every response → one-line OS trace

Say "trace off" to quiet the output trace. Say "/sutra-help" for commands.
```

Apply input-routing, depth-estimation, readability-gate, and output-trace to all subsequent turns.

## What Sutra governs automatically via hooks (already wired in .claude/settings.json)

- Edit/Write without a depth marker → blocked with a helpful message
- Hook fires log to `.claude/logs/hook-fires.jsonl`
- Stop event logs session summary
- SessionStart checks for newer Sutra on github

The plugin does not re-implement these — they're active the moment you opened Claude Code in this folder.
