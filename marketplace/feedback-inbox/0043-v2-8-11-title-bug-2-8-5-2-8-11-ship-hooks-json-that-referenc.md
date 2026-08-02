---
issue: 43
title: "[v2.8.11] title: \"Bug: 2.8.5 + 2.8.11 ship hooks.json that references a never-shipped inbo"
author: vinitharmalkar
state: OPEN
created: 2026-04-30T11:14:25Z
updated: 2026-04-30T11:14:25Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/43
comments: []
---

# #43 [v2.8.11] title: "Bug: 2.8.5 + 2.8.11 ship hooks.json that references a never-shipped inbo

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-30T11:14:25Z  |  **Updated:** 2026-04-30T11:14:25Z
**URL:** https://github.com/sankalpasawa/sutra/issues/43

---

---
title: "Bug: 2.8.5 + 2.8.11 ship hooks.json that references a never-shipped inbox-display.sh"
plugin_version: "core@2.8.11"
captured_at: "2026-04-30T09:47:20Z"
captured_by: "Vinit Harmalkar (Founder's Office, Testlify)"
install_id: "379c80b799d9270b"
project_id: "9005f911b7c8"
severity: "low (non-blocking, noisy)"
affected_versions:
  - "core@2.8.5"
  - "core@2.8.11"
unaffected_versions:
  - "core@2.7.3"
  - "core@2.4.0"
  - "core@2.0.2"
  - "core@2.0.0"
  - "core@1.9.4"
  - "core@1.12.0"
---

# Bug: SessionStart hook references `inbox-display.sh` but the script was never shipped

## One-line symptom

Every `SessionStart:resume` event prints:

```
SessionStart:resume hook error
  Failed with non-blocking status code: /bin/sh:
  <HOME>/.claude/plugins/cache/sutra/core/2.8.11/hooks/inbox-display.sh:
  No such file or directory
```

Non-blocking (the session continues fine), but visible on every `claude -r <session-id>` invocation. Accumulates as user-perceived noise / "broken plugin" signal.

## Root cause

`hooks/hooks.json` declares a `SessionStart` hook calling `${CLAUDE_PLUGIN_ROOT}/hooks/inbox-display.sh`, but **the script file does not exist** anywhere in the plugin tree. The manifest references a never-shipped artifact.

### Evidence — manifest declares the hook

File: `core/2.8.11/hooks/hooks.json`, lines 32–36:

```json
{
  "type": "command",
  "command": "${CLAUDE_PLUGIN_ROOT}/hooks/inbox-display.sh",
  "timeout": 8
}
```

This entry sits among 6 other working SessionStart hooks (update-banner.sh, sessionstart-auto-activate.sh, session-logger.sh, sessionstart-privacy-notice.sh, codex-directive-sweep.sh, session-start-rotate.sh) — all of which exist in the same `hooks/` directory and run cleanly. Only `inbox-display.sh` is missing.

### Evidence — script absent across all installed Sutra versions

Cross-version probe (run on the user's machine, all versions cached locally):

| Version | `inbox-display.sh` exists? | Manifest references it? |
| --- | --- | --- |
| core@1.9.4 | NO | 0 |
| core@1.12.0 | NO | 0 |
| core@2.0.0 | NO | 0 |
| core@2.0.2 | NO | 0 |
| core@2.4.0 | NO | 0 |
| core@2.7.3 | NO | 0 |
| **core@2.8.5** | **NO** | **1** |
| **core@2.8.11** | **NO** | **1** |

So the dangling reference was **introduced in core@2.8.5** and **persists unchanged through core@2.8.11** (verified via `diff` of the SessionStart hook array between the two versions — zero differences in that block).

### Evidence — no documentation, no CHANGELOG mention

`grep -rln "inbox-display"` against the entire Sutra plugin tree returns only the two `hooks.json` files. Specifically:

- **No script** — `find <HOME>/.claude -name "inbox-display.sh"` returns empty.
- **No CHANGELOG entry** — `core@2.8.11/CHANGELOG.md` does not mention `inbox-display`. The string "inbox" appears in CHANGELOG, but only in two unrelated contexts:
  1. GitHub issue inbox triage (issue title formatting per vinit#25 bug 2)
  2. PROTO-024 V1 client→team feedback inbox (`sankalpasawa/sutra-data` git rail)
  Neither matches a "SessionStart inbox display" hook semantically.
- **No README mention** in `core@2.8.11/README.md`.
- **No skill or doc file** in the plugin references this hook by name.

The 8-second timeout (longer than most hooks at 3–5s) suggests the hook was intended to do something non-trivial (perhaps display unread Sutra-data feedback inbox count, given the PROTO-024 V1 client-team inbox? — speculation).

## Reproduction steps

1. Install Sutra core@2.8.5 or core@2.8.11 (`claude plugin install core@sutra` or version-pinned).
2. Activate Sutra in a project: `/core:start`.
3. Open a Claude Code session and let it write at least one entry to its session JSONL.
4. Exit Claude Code.
5. Resume the session: `claude -r <session-id>`.
6. Observe the error banner printed at session start (non-blocking).

The error fires on **`SessionStart:resume`** specifically. It probably also fires on `SessionStart:startup` (fresh sessions) for the same reason — the manifest doesn't event-discriminate within the SessionStart array — but in this user's case it was first observed during a `claude -r` resume.

## Impact assessment

| Dimension | Assessment |
| --- | --- |
| Functional impact | None — Claude Code prints the error and continues normally |
| User-perceived impact | Medium — every resume shows a "broken plugin" banner. Users who don't read shell error output carefully will assume governance is degraded |
| Trust impact | Plugin appears malformed at first contact. For governance tooling, broken-on-startup is a credibility issue |
| Telemetry impact | Likely emits a hook-failure metric to `~/.sutra/metrics-queue.jsonl` on every resume — potential noise floor in fleet metrics |
| Frequency | Once per `SessionStart` event — i.e. once per fresh launch and once per resume |

## Suggested fixes — pick one

| # | Fix | Effort | Tradeoff |
| --- | --- | --- | --- |
| 1 | **Ship the missing script** in the next release. If the hook is intended to display PROTO-024 inbox count or similar, write the implementation and bundle it. | High (requires designing what the hook does) | Closes the gap by providing the intended functionality |
| 2 | **Remove the manifest reference** until the script is ready. Drop lines 32–36 of `hooks/hooks.json` in a 2.8.12 patch release. | Trivial (5-line JSON edit) | Stops the noise immediately; deferred functionality |
| 3 | **Make the hook tolerant of a missing script** — wrap the command with a guard: `[ -f "$CLAUDE_PLUGIN_ROOT/hooks/inbox-display.sh" ] && bash "$_" || true`. Or convert to a shell command that no-ops when the file is absent. | Low | Future-proofs against this class of error; preserves the slot for when the script ships |

**Recommended**: Fix #2 in a 2.8.12 patch *now*, then re-introduce in a future minor release together with Fix #1.

## Surrounding context (from the affected user's environment)

- macOS Darwin 25.3.0 (zsh)
- Single-Mac install (no remote sessions, no shared cache)
- All older Sutra versions still cached locally (multi-version cache via `.claude/plugins/cache/sutra/core/<version>/`) — none have the script either, so this isn't a partial-uninstall artifact
- Plugin source: `https://sutra.os` / marketplace `sankalpasawa/sutra` (per `marketplace.json`)
- Active profile: `project` (warn-only, telemetry on)
- 7 SessionStart hooks declared; 6 work; 1 (this one) fails

## How this was caught

Discovered during a `claude -r 33a9fe88-9720-4370-9e2e-78a3baff0ccf` session resume on 2026-04-29. Surfaced as a chat-visible error banner. Subsequent investigation traced the dangling reference and verified script absence across all 8 cached Sutra versions on the machine.

## What would help close-out

A short note in 2.8.12 release notes confirming whether (a) the script was forgotten in 2.8.5/2.8.11 packaging and is now re-included, or (b) the manifest reference was removed until functionality is ready. Either is fine; what's confusing right now is that the manifest implies functionality that doesn't exist with no documentation explaining the gap.

---

**Reporter note**: Filed via Sutra's sanctioned `/core:feedback --public` channel. No `gh issue create` shortcuts; routing-rule.sh respected.
