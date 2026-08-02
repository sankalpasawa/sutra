---
issue: 3
title: "feat: play system notification tone when Bash permission approval is waiting"
author: vinitharmalkar
state: OPEN
created: 2026-04-25T09:12:07Z
updated: 2026-04-25T09:12:07Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/3
comments: []
---

# #3 feat: play system notification tone when Bash permission approval is waiting

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-25T09:12:07Z  |  **Updated:** 2026-04-25T09:12:07Z
**URL:** https://github.com/sankalpasawa/sutra/issues/3

---

## Summary

When Sutra's permission gate fires on a Bash command and waits for the user
to approve or deny, there is currently no audio or system-level signal.
The approval dialog appears silently. If the user has stepped away, is
in another window, or is running a long task in the background, they have
no way of knowing that execution has paused and is waiting on them.

## Proposed behaviour

When a Bash permission prompt is raised and is waiting for user input,
Sutra should emit a short, non-intrusive system notification tone —
the same way macOS plays a soft ping when a Terminal process requests
attention or a download completes.

## Why this matters

- Long agentic tasks (multi-file rewrites, build pipelines, deploy scripts)
  frequently pause mid-way for a single approval. The user cannot see this
  without actively watching the window.
- Silent pauses read as "Claude is still working" — the user waits
  unnecessarily, sometimes for several minutes, before realising approval
  is needed.
- A tone costing ~0.1 seconds of attention prevents minutes of idle waiting.

## Suggested implementation path

The `hooks/permission-gate.sh` hook already fires at the `PermissionRequest`
event before the dialog is shown. A single line at the top of that hook —
`afplay /System/Library/Sounds/Tink.aiff 2>/dev/null &` on macOS,
`paplay` equivalent on Linux — would cover the majority of the fleet
with no new dependencies.

A kill-switch (`SUTRA_PERMISSION_SOUND=0` or `~/.sutra-permission-sound-disabled`)
should be included from day one, consistent with how every other Sutra hook
handles opt-out.

## Environment

- macOS (primary fleet): `afplay` built-in, no install needed
- Linux: `paplay` (PulseAudio) or `aplay` (ALSA), both standard
- Windows/WSL2: out of scope per existing Sutra platform matrix

## Related

- v1.13.0 — `permission-gate.sh` (PermissionRequest hook, where this would live)
- v1.14/v1.15 — `bash-summary-pretool.sh` (companion UX work on permission clarity)
- v2.4.0 — Tier 1.5 compositional reads (reduces total prompt count; remaining
  prompts are higher-stakes and therefore even more worth surfacing with sound)
