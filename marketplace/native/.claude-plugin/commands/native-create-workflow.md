---
description: Create a Sutra Workflow at runtime with a step graph. Wraps `sutra-native create-workflow`.
allowed-tools: Bash
---

# /native:create-workflow

Create a new Workflow in the user-kit with an executable step graph.

**Usage:** `/native:create-workflow <W-id> <step1>[,<step2>...]`

**Examples:**
- `/native:create-workflow W-evening-checkin wait,terminate`
- `/native:create-workflow W-noop wait`

**Step actions supported at v1.1.2 (CLI subset)**:
- `wait` — no-op, succeed immediately
- `terminate` — emit workflow_completed early, success
- `spawn_sub_unit` — no-op stub (logs intent, succeeds)

`invoke_host_llm` is NOT exposed via this CLI subcommand (requires `host` qualifier — direct API only at v1.1.2).

When invoked, Claude will:

1. Parse `$ARGUMENTS`:
   - first token = `<W-id>` (must match `W-.+`)
   - second token = comma-separated step actions

2. Resolve the binary (same pattern as create-domain) and run:
   ```bash
   "$NATIVE_BIN" create-workflow --id <W-id> --steps "<csv-actions>"
   ```

3. Print stdout. The CLI auto-assigns `step_id` (1..N), wires `on_failure='continue'` for all but the last step, `on_failure='abort'` for the last.

The Workflow is persisted at `$SUTRA_NATIVE_HOME/user-kit/workflows/<W-id>.json`. Run it later with `/native:run <W-id>`.

**Source**: `src/cli/sutra-native.ts` `cmdCreateWorkflow` (v1.1.2+).
