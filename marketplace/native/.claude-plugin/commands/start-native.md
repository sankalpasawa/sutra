---
description: Activate Native productization layer for this Claude Code session — H-Sutra connector + engine
allowed-tools: Bash
---

# /start-native

Activate Native for this Claude Code session.

When you invoke this command, Claude will:
1. Run `sutra-native start` from the Native plugin's `bin/` directory.
2. Acquire a PID lock so a second activation in the same session is detected.
3. Print the activation banner (version, host kind, PID).
4. The next founder input you type will flow: Sutra Core H-Sutra layer (existing) → classified event → Native engine routes via TriggerSpec → Workflow execution → SOP recorded.

Per founder direction 2026-05-02: Native is **additive**. Sutra Core is unchanged. Native subscribes to the H-Sutra log file (read-only at v1.0) and processes events downstream.

If `sutra-native` is not on PATH yet (Native plugin source-preview), invoke directly:

```
bash $CLAUDE_PROJECT_DIR/sutra/marketplace/native/bin/sutra-native start
```

After activation, `/start-native` is idempotent — running it twice within an active session reports the existing PID and exits 1 (no harm done).

To stop: `kill <pid>` (printed in banner) or wait for session end.

To check state: run `sutra-native status` from terminal.

Source: `sutra/marketplace/native/src/cli/sutra-native.ts` (CLI) + `src/runtime/lifecycle.ts` (PID lock).
Spec: `holding/plans/native-productization-v1.0/SPEC.md` §C11 + R-NPD-START.
