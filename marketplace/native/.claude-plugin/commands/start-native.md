---
description: Activate Native productization layer for this Claude Code session — H-Sutra connector + engine
allowed-tools: Bash
---

# /start-native

Manually activate Native (the Wave 1 SessionStart hook auto-activates on
session start, so this slash command is **operator affordance** — useful
for re-activation after a manual `sutra-native stop` or when the
SessionStart hook was disabled via `SUTRA_NATIVE_DISABLED=1`).

When you invoke this command, Claude will:
1. Run `sutra-native start` from the Native plugin's `bin/` directory.
2. Acquire a PID lock so a second activation in the same session is detected.
3. Print the activation banner (version, host kind, PID).
4. The next founder input you type will flow: Sutra Core H-Sutra layer → classified event → Native HSutraConnector → Router via TriggerSpec → (Wave 2) Workflow execution → SOP recorded.

**Wave 1 contract**: SessionStart hook auto-activates the engine. Workflow execution lands in Wave 2.

**Dependency**: Native depends on `core@sutra` (or equivalent) writing H-Sutra events to a JSONL log. Install `core@sutra` first if not already.

Per founder direction 2026-05-02: Native is **additive**. Sutra Core is unchanged. Native subscribes to the H-Sutra log file (read-only at v1.0) and processes events downstream.

After activation, `/start-native` is idempotent — running it twice within an active session reports the existing PID and exits 1 (no harm done).

To stop: `sutra-native stop` (or wait for session Stop hook).
To check state: `sutra-native status`.

Source: `marketplace/native/src/cli/sutra-native.ts` (CLI) + `src/runtime/lifecycle.ts` (PID lock) + `hooks/session-start.sh` (auto-activate).
Spec: `holding/plans/native-productization-v1.0/SPEC.md` §C11 + R-NPD-START.
