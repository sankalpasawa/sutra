---
name: sutra
description: Activate the Sutra operating system for this session. Loads all four core skills (input-routing, depth-estimation, readability-gate, output-trace) and prints session status.
disable-model-invocation: true
---

# /sutra — Session Activation

Announce Sutra is active, then apply the four core skills to the rest of the session.

## Actions

1. Emit the activation banner:

```
🧭 Sutra v0.1 active
   Skills: input-routing, depth-estimation, readability-gate, output-trace
   Hooks:  depth-marker-pretool (warn-only), estimation-stop (log)
   Trace:  Level 1 (minimal) — say "show trace" to upgrade
```

2. Read the current project's `.claude/depth-registered` if it exists:

```!
cat .claude/depth-registered 2>/dev/null || echo "no depth marker set"
```

3. Apply input-routing, depth-estimation, readability-gate, and output-trace to all subsequent turns in this session.

## What changes after /sutra

- Every user message is classified via input-routing before any tool call
- Every task gets a depth + estimation block before work begins
- Every output passes through the readability gate
- Every response ends with a one-line OS trace (Level 1 default)

## What does NOT change

- Existing memory, CLAUDE.md, and permission settings
- Tool access (Sutra is guidance — the hooks warn but do not block in v0.1)
- The user's right to override any skill with a direct instruction
