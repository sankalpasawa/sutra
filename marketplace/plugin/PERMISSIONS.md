# Permissions — What Sutra Asks For and Why

*Plugin version: 1.5.1 · Updated: 2026-04-22*

Claude Code prompts before running shell commands and writing files outside the project. Sutra needs a small, auditable set of permissions to do its job. This doc lists every one of them and explains why.

## The short story

- Install + configure is a **one-line allowlist** pasted into `.claude/settings.local.json` (or user-level `~/.claude/settings.json`).
- Run `/core:permissions` inside Claude Code or `sutra permissions` in a terminal to print the exact snippet.
- All commands and writes stay inside your project or `~/.sutra/`. No `/etc/`, no `/System/`, no photo library, no credentials.

## One-shot bypass (recommended)

Paste this into `.claude/settings.local.json` (create the file if it doesn't exist). One paste, zero prompts for any Sutra operation.

```json
{
  "permissions": {
    "allow": [
      "Bash(sutra:*)",
      "Bash(sutra)",
      "Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
      "Bash(claude plugin marketplace update sutra)",
      "Bash(claude plugin update core:*)",
      "Bash(claude plugin uninstall core:*)",
      "Write(.claude/sutra-project.json)",
      "Write(.claude/depth-registered)",
      "Write(.claude/input-routed)",
      "Write(.claude/sutra-deploy-depth5)",
      "Write(.claude/sutra-estimation.log)",
      "Write(.claude/logs/*)",
      "Bash(mkdir -p .claude*)"
    ]
  }
}
```

Equivalent for project-scope (shared with your team via git): put it in `.claude/settings.json` instead.

## Every permission, grouped by what they do

### Bash — running the plugin itself

| Pattern | When it fires | Why |
|---|---|---|
| `Bash(sutra:*)` | Any `/core:*` slash command | Plugin's unified dispatcher (bin/sutra) handles subcommands |
| `Bash(sutra)` | `sutra` with no args | Same dispatcher, help output |
| `Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/*:*)` | Legacy back-compat | Old v1.2 and earlier scripts still callable |

### Bash — Claude Code lifecycle passthroughs

| Pattern | When it fires | Why |
|---|---|---|
| `Bash(claude plugin marketplace update sutra)` | `/core:update` | Refreshes marketplace cache |
| `Bash(claude plugin update core:*)` | `/core:update` | Applies version bump |
| `Bash(claude plugin uninstall core:*)` | `/core:uninstall` | Removes the plugin |

### Write — project-local state

| Path | When it fires | Why |
|---|---|---|
| `.claude/sutra-project.json` | `/core:start` | Your install_id + project_id + telemetry_optin flag |
| `.claude/depth-registered` | Every task | Depth marker so PreToolUse hook knows depth was assessed |
| `.claude/input-routed` | Every turn | Routing marker so PreToolUse hook knows input was classified |
| `.claude/sutra-deploy-depth5` | Sutra-internal edits | Escape hatch marker for high-depth work |
| `.claude/sutra-estimation.log` | Every Stop event | Session-local estimation log (not transmitted) |
| `.claude/logs/*` | Dispatcher telemetry | Local log of hook fires (fallback when holding/ layout absent) |

### Bash — tiny filesystem ops

| Pattern | When it fires | Why |
|---|---|---|
| `Bash(mkdir -p .claude*)` | First use in a project | Creates `.claude/` and `.claude/logs/` if absent |

## What Sutra does NOT need permission for

These are NEVER requested:

- Read/Write anywhere outside `.claude/` and `~/.sutra/` in your project
- No access to Photos, Documents, Downloads, or any system library
- No read of `~/.ssh`, `~/.aws`, `~/.gnupg`, or any credentials directory
- No network calls except the optional `sutra push` (auto-fires on Stop when `telemetry_optin=true`; needs gh auth, not a Claude Code permission)
- No SSH key generation, no keychain access, no OS-level settings change

## Why so many items?

Claude Code treats each distinct shell command and each distinct file path as a separate permission scope. A single `/core:start` invocation can touch 3-4 paths, which translates to 3-4 prompts the first time.

The v1.3.0 `bin/sutra` refactor collapsed per-script-path Bash prompts to one (the `sutra` bare command). The remaining prompts are for file writes inside `.claude/` which Claude Code asks about because `.claude/` is technically outside the "plain project source" scope.

## If you don't want to paste the snippet

You can click "Allow" on each prompt the first time you use `/core:start`. Claude Code remembers your choice for the session. Future sessions re-prompt unless you save the choice (Claude Code shows a "Save permission" checkbox).

The paste-once approach is faster and gets you through first-run in 10 seconds.

## Questions

- `PRIVACY.md` — what data gets transmitted (hint: nothing, unless you opt in)
- `VERSIONING.md` — how we bump versions
- `/core:permissions` — prints the snippet above for easy copy
- Open an issue: <https://github.com/sankalpasawa/sutra/issues>
