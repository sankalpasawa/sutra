# Sutra

Operating system for building with AI. Brings governance — input routing, depth estimation, readability gate, output trace — to every Claude Code session.

## What you get

Install Sutra and Claude Code starts behaving like a senior practitioner.

- **Input routing** — every user message gets classified (direction / task / feedback / new concept / question) before any action.
- **Depth + estimation** — every task gets a depth rating (1-5) and a cost/effort estimate before work starts.
- **Readability gate** — outputs are formatted for the reader: tables over prose, numbers over adjectives, decisions boxed for visibility.
- **Output trace** — every response ends with a one-line OS trace so you can see what happened.

Plus hooks that warn when a depth marker is missing before Edit/Write, and log estimation metrics on session end.

## Install

```
/plugin install sutra@<marketplace>
```

Marketplace repo announced at https://sutra.os.

## First run

Type `/sutra` to activate. The four core skills then auto-invoke based on context:

- `/input-routing` — classify the next input
- `/depth-estimation` — rate the next task
- `/readability-gate` — format the next output
- `/output-trace` — emit the OS trace line

For manual depth gating, use `/depth-check`.

## What v0.1 does NOT do

- No hard enforcement. Hooks warn, don't block. (v0.2.)
- No per-profile defaults (individual / project / company). (v0.2.)
- No cross-session state. The estimation log is session-local.
- No paid tier. The OS is free forever.

## License

MIT.

## Status

v0.1 — early. Built for functional validation. Expect sharp edges. File issues at the repo listed in `plugin.json` once announced.
