---
name: permissions
description: Print a paste-ready .claude/settings.local.json snippet that allows every Sutra operation in one go. Stops all permission prompts for the plugin.
disable-model-invocation: true
---

# /core:permissions — One-paste allowlist

!sutra permissions

## What this does

Prints a JSON snippet containing every `Bash(...)` and `Write(...)` rule Sutra needs. Paste it into `.claude/settings.local.json` (project-local, gitignored) or `.claude/settings.json` (shared with team via git).

One paste, zero further prompts.

## What the snippet allows

- Sutra's own commands (`sutra`, `/core:*`)
- Claude Code plugin lifecycle passthroughs (`claude plugin update/uninstall`)
- Writes inside `.claude/` for markers + logs + project state
- `mkdir -p .claude*` for first-use directory creation

Full explanation at `PERMISSIONS.md` in the plugin repo.

## What it does NOT grant

- No home directory, no system, no credentials, no network beyond gh push for telemetry

## Related

- `/core:start` — activate Sutra in this project
- `PRIVACY.md` — what data leaves your machine (nothing unless opt-in)
