---
description: Execute a user-kit Workflow via the LiteExecutor; events stream to terminal.
allowed-tools: Bash
---

# /native:run

Execute a Workflow you've previously created with `/native:create-workflow`. Each step's start/complete event prints one line of stdout via the terminal renderer.

**Usage:** `/native:run <W-id> [<execution-id>]`

**Examples:**
- `/native:run W-evening-checkin`
- `/native:run W-evening-checkin E-2026-05-03-001`

When invoked, Claude will:

1. Parse `$ARGUMENTS`:
   - first token = `<W-id>` (the Workflow id you created)
   - optional second token = `<execution-id>` (defaults to `E-<unix-ms>` if absent)

2. Resolve the `sutra-native` binary (same pattern as the other commands).

3. Invoke:
   ```bash
   "$NATIVE_BIN" run <W-id> [--execution-id <execution-id>]
   ```

4. Print the streamed event lines verbatim. Final summary line ends with `OK: N step(s) completed, M failed, Tms` on success, or `FAIL: ...` on failure.

**Exit codes:**
- 0 — workflow completed successfully
- 1 — workflow ran but finished in `failed` state
- 2 — usage error (missing W-id)
- 3 — workflow id not found in user-kit (try `/native:list workflows`)

**Source**: `src/cli/sutra-native.ts` `cmdRun` (v1.1.2+); executor at `src/runtime/lite-executor.ts`.
