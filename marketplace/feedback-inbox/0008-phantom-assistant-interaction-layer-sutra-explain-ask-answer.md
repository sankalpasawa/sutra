---
issue: 8
title: "[Phantom] Assistant Interaction Layer (sutra explain/ask/answer/pending) ships as L1 build-layer, observer hook unregistered, holding/ path missing"
author: vinitharmalkar
state: OPEN
created: 2026-04-27T14:03:33Z
updated: 2026-04-27T14:03:33Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/8
comments: []
---

# #8 [Phantom] Assistant Interaction Layer (sutra explain/ask/answer/pending) ships as L1 build-layer, observer hook unregistered, holding/ path missing

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-27T14:03:33Z  |  **Updated:** 2026-04-27T14:03:33Z
**URL:** https://github.com/sankalpasawa/sutra/issues/8

---

## Finding

`bin/sutra` exposes these subcommands (labeled `v2.2.0+` in the source):
```
sutra enable / disable / explain / ask / answer / pending / profile / decommission
```

The README does not mention these. They are undocumented but functional-looking CLI surface. On inspection, three serious problems exist:

---

### Problem 1: Scripts are marked `BUILD-LAYER: L1` — pre-production, not promoted

`hooks/assistant-explain.sh` header:
```
# BUILD-LAYER: L1 (single-instance:asawa-holding)
#   Promotion target: sutra/marketplace/plugin/commands/assistant-explain (slash cmd at P5)
#   Acceptance (P3): renders last turn + --turn N + --last K
```

`hooks/assistant-observer.sh` header:
```
# BUILD-LAYER: L1 (single-instance:asawa-holding)
#   Promotion target: sutra/marketplace/plugin/hooks/assistant-observer.sh
#   Promotion by: 2026-05-24 (30d L1 stability + P5 plugin promotion)
#   Stale disposition: delete holding copy 30d after plugin-side promotion
```

`L1` is Sutra's own build-layer designation for single-instance pre-production code. These files are from an internal project (`asawa-holding`) and are explicitly scheduled for promotion **in the future** (2026-05-24). They shipped into the marketplace plugin before that promotion.

---

### Problem 2: `assistant-observer.sh` is NOT registered in `hooks.json`

The observer is the core collector — it's supposed to write `events.jsonl` on every turn so that `sutra explain` has data to read. But scanning `hooks.json`:

- `SessionStart`: update-banner, sessionstart-auto-activate, session-logger, sessionstart-privacy-notice
- `PreToolUse`: feedback-auto-override, depth-marker-pretool, operationalization-check, rtk-auto-rewrite, codex-directive-gate, bash-summary-pretool, keys-in-env-vars, enforce-boundaries
- `PostToolUse`: posttool-counter, cascade-check, estimation-enforcement, artifact-check, completion-protocol-check, posttool-mcp-compress
- `Stop`: estimation-stop, flush-telemetry, estimation-collector, session-logger, log-triage, log-skill-feedback, measurement-logger, compliance-tracker, feedback-auto-abandonment, **assistant-kill-switch**

`assistant-observer.sh` is **absent** from all hook registrations. The kill-switch runs on Stop, but the observer that feeds it never fires. Result: `events.jsonl` is never written, so `sutra explain` always reads an empty or nonexistent file.

---

### Problem 3: Scripts reference `holding/` paths that don't exist in the plugin

`bin/sutra` for `explain`:
```bash
EXP="$PLUGIN_ROOT/hooks/assistant-explain.sh"
[ -x "$EXP" ] || EXP="$PWD/holding/scripts/assistant-explain.sh"
exec bash "$EXP" "$@"
```

`assistant-explain.sh` itself:
```bash
STATE_DIR="${SUTRA_ASSISTANT_STATE_DIR:-$REPO_ROOT/holding/state/assistants/$CLIENT_ID}"
HOOK_LOG="${SUTRA_ASSISTANT_HOOK_LOG:-$REPO_ROOT/holding/hooks/hook-log.jsonl}"
EVENTS="$STATE_DIR/events.jsonl"
```

`holding/` does not exist in the plugin:
```bash
$ ls /Users/vinit/.claude/plugins/cache/sutra/core/2.4.0/holding/
# ls: cannot access ... No such file or directory
```

When a user runs `sutra explain`, it reads from `$REPO_ROOT/holding/state/assistants/holding/events.jsonl` — a path in the user's project directory that will never exist unless they happen to be inside the `asawa-holding` internal repo.

---

## What `sutra explain` actually does when called

1. Looks for `holding/state/assistants/holding/events.jsonl` in the current directory
2. File doesn't exist → either silent failure or "no events found"
3. User sees no useful output

The entire `explain/ask/answer/pending/profile/decommission` surface is inert for all users outside the internal `asawa-holding` project.

## Requested fix

1. **Remove `sutra enable/disable/explain/ask/answer/pending/profile/decommission` from `bin/sutra`** until the L1→plugin promotion is complete, OR
2. **Gate them behind a feature flag** with a clear "this feature is in preview / not yet available" message, OR
3. **Complete the promotion**: register `assistant-observer.sh` in `hooks.json`, remove `holding/` path dependencies, write the slash command surface

The `sutra help` output currently shows none of these subcommands — they're only discoverable by reading `bin/sutra` source. That's the only reason this hasn't caused more user confusion yet.

---
**Session context:** 2026-04-27 · Sutra 2.4.0 · macOS darwin 25.3.0 · Reported by Vinit (Testlify)
