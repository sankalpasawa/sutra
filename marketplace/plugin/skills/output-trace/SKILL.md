---
name: output-trace
description: Use at the end of every response before the final text. Emits a one-line OS trace showing what the system did — routing, gates fired, nodes traversed, terminal state. Three verbosity levels, user-controlled.
---

# Output Trace

Every response ends with a one-line trace showing what the OS actually did. Makes the system legible.

## Level 1: MINIMAL (default)

One line, post-response:

```
OS: Input Routing (task) > Depth 3 > 2 tool calls > Readability gate > Complete
```

## Level 2: STANDARD (user says "show trace")

Show files and protocols that fired:

```
OS TRACE:
  Route:  task > <protocol>
  Gate:   PROTO-XXX (boundary OK)
  Nodes:  N (budget: $X of $Y)
  Terminal: specificity N/M
```

## Level 3: VERBOSE (user says "show os")

Everything — each node's observe/shape/terminal step, parked branches, working paper.

## Toggle rules

- "show trace" → Level 2 for remainder of session
- "show os" → Level 3
- "trace off" → Level 0 (no trace)
- default → Level 1

## Format

- Single line for Level 1, appended to response
- Multi-line block for Level 2/3, before TRIAGE/ESTIMATE lines
- Never insert trace mid-response — only at the end
