---
name: start
description: The one command. Onboards this project, enables local telemetry, activates the four core skills, writes a depth marker, prints what's active. Run this first.
disable-model-invocation: false
---

# /core:start — Activate Sutra here

One command. Everything.

Run this command via the Bash tool:

```bash
${CLAUDE_PLUGIN_ROOT}/bin/sutra start
```

## What happens

1. **Identity** — writes `.claude/sutra-project.json` with deterministic `install_id` + `project_id` (stable per user+version, per repo)
2. **Telemetry** — `telemetry_optin = true` (edit the JSON file to flip; see PRIVACY.md)
3. **Skills** — input-routing, depth-estimation, readability-gate, output-trace now auto-apply to every turn
4. **Depth marker** — a sensible default so the first Edit/Write doesn't trip the PreToolUse warn
5. **Queue** — local metrics queue initialized at `~/.sutra/metrics-queue.jsonl`

Idempotent — re-running is safe.

## After `/core:start`

Ask Claude to do anything. Every response should now include:

- An **input-routing block** (TYPE / ROUTE / FIT CHECK) before any Write/Edit
- A **depth + estimation block** before any task
- A **readability gate** formatting the output (tables, numbers, boxes)
- A **one-line OS trace** at the end of each response

## Related

- `/core:status` — inspect install / queue / telemetry state
- `/core:update` — pull the latest plugin version
- `/core:uninstall` — remove Sutra
- `/core:depth-check` — manual depth marker before a big task
