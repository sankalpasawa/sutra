# Permissions — What Sutra Asks For and Why

*Plugin version: 1.13.0 · Manifest updated: 2026-04-24*

Claude Code prompts before running shell commands and writing files outside the project. Sutra needs a small, auditable set of permissions to do its job. Since v1.13.0, the plugin **auto-approves its own in-scope operations on first invocation** so you don't have to paste anything or click "Allow" repeatedly.

This doc explains: how the auto-approve mechanism works, exactly which patterns are in scope, what's out of scope, and how to turn it off if you prefer manual consent.

---

## How v1.13 changes the install flow

| Phase | Before v1.13 | From v1.13 onward |
|---|---|---|
| 1. `/plugin install sutra@marketplace` | 1 consent (Claude Code native) | 1 consent (unchanged) |
| 2. First `/core:start` | ~8 individual prompts | **Auto-approved** by `permission-gate.sh` hook + each rule persisted to `.claude/settings.local.json` |
| 3. Next hook fires (marker writes, mkdir) | ~5 more prompts | **Auto-approved + persisted** |
| 4. Second session onward | Re-prompts (unless user pasted snippet) | **Zero hook invocations** — Claude Code's native allow-list catches the persisted rules directly |

Net: **≤2 prompts in the first 30 minutes after install** (North Star KPI per `sutra/os/charters/PERMISSIONS.md`). If you observe more, file an issue — that means an allow-list pattern is missing.

---

## The mechanism in one paragraph

Claude Code fires a `PermissionRequest` event before every permission dialog. Sutra's `hooks/permission-gate.sh` intercepts that event, checks whether the pending tool call matches a Sutra-scope pattern, and if so returns `{behavior: "allow", updatedPermissions: [addRules ...]}`. Claude Code then (a) runs the tool call without prompting and (b) persists the matched rule to `.claude/settings.local.json` so next time the native allow-list handles it — the hook doesn't even fire. If no pattern matches, the hook exits silently and Claude Code's normal prompt appears. **The hook never auto-denies.**

---

## Every permission Sutra may auto-approve (Tier 1 — always)

### Starting a session

| Pattern | When it fires | Why | Blast radius |
|---|---|---|---|
| `Bash(sutra)` | `/core:*` slash command with no args | Plugin dispatcher (`bin/sutra`) | Prints help |
| `Bash(sutra <sub>)` | Every `/core:*` command routes here | Runs `start`, `status`, `update`, `uninstall`, `push`, `permissions`, etc. | Plugin scripts only |
| `Bash(bash ${CLAUDE_PLUGIN_ROOT}/*)` | Legacy/internal script calls | Old v1.2 back-compat + internal hook bodies | Plugin cache dir only |

### Writing governance markers

| Pattern | When it fires | Why | Blast radius |
|---|---|---|---|
| `Write(.claude/depth-registered)` | Every task | Depth marker — wiped per-turn | Single file |
| `Write(.claude/input-routed)` | Every turn | Routing marker — wiped per-turn | Single file |
| `Write(.claude/sutra-deploy-depth5)` | Sutra-internal edits | Escape hatch for Depth 5 work | Single file |
| `Write(.claude/build-layer-registered)` | PROTO-021 enforced writes | Build-layer declaration marker | Single file |
| `Write(.claude/sutra-project.json)` | `/core:start` | install_id + project_id + telemetry_optin | Single file |
| `Write(.claude/sutra-estimation.log)` | Every Stop event | Session-local estimation log | Single file |
| `Write(.claude/logs/*)` | Dispatcher telemetry | Hook-fire log | `.claude/logs/` only |

### Filesystem setup

| Pattern | When it fires | Why | Blast radius |
|---|---|---|---|
| `Bash(mkdir -p .claude*)` | First use in a project | Creates `.claude/` and `.claude/logs/` if absent | `.claude/` subtree |
| `Bash(mkdir -p .enforcement*)` | First hook fire | Creates `.enforcement/` for audit logs | `.enforcement/` subtree |
| `Bash(mkdir -p .context*)` | Codex session start | Creates `.context/` for session IDs | `.context/` subtree |

### Lifecycle operations

| Pattern | When it fires | Why | Blast radius |
|---|---|---|---|
| `Bash(claude plugin marketplace update sutra)` | `/core:update` | Refreshes marketplace cache | Plugin cache only |
| `Bash(claude plugin update core*)` | `/core:update` | Applies version bump | Plugin cache only |
| `Bash(claude plugin uninstall core*)` | `/core:uninstall` | Removes the plugin | Plugin cache only |

---

## Tier 2 — opt-in only (requires `os/SUTRA-CONFIG.md` flag)

These patterns are **NOT** auto-approved by default. They unlock only when you enable the corresponding feature in your project's `os/SUTRA-CONFIG.md`.

| Feature | Additional patterns | How to enable |
|---|---|---|
| `telemetry_optin=true` | `Bash(gh auth status)` + network calls from `sutra push` | Set `telemetry_optin: true` in SUTRA-CONFIG |
| `codex_review` | `Write(.enforcement/codex-reviews/*)`, `Write(.claude/codex-directive-pending)` | Set `enabled_hooks.codex-review-gate: true` |
| `keys-in-env-vars` | Read-only content scan (no Write scope added) | Set `enabled_hooks.keys-in-env-vars: true`. Default-OFF per D32. |

---

## Tier 3 — NEVER auto-approved (hard-coded deny)

Sutra's `permission-gate.sh` refuses to auto-approve any of the following, even inside an otherwise-matching pattern:

| Pattern | Why forbidden |
|---|---|
| Any path outside `.claude/`, `.enforcement/`, `.context/`, or the plugin cache | Sutra is a governance OS, not a general-purpose filesystem tool |
| Any network call other than `sutra push` (opt-in only) | Privacy floor — see `PRIVACY.md` |
| Any access to `~/.ssh`, `~/.aws`, `~/.gnupg`, system Keychain | Credentials are outside Sutra's threat model |
| Any `sudo`, `su`, privilege escalation | Sutra runs at user-level only |
| Shell combinators widening scope past Sutra operations: `;`, `&&`, `\|\|`, `\|`, backticks, `$(...)`, redirections | Defense against command-injection inside matched patterns. Example: `sutra status; rm -rf /` is rejected by the hook — it falls through to a normal prompt. |

---

## Kill-switch (opt out of auto-approve entirely)

If you prefer the old paste-or-click flow, disable the hook:

```
# Per-user global (all projects, all sessions)
touch ~/.sutra-permissions-disabled

# Per-session env var
SUTRA_PERMISSIONS_DISABLED=1 claude
```

With the kill-switch on, every Sutra operation prompts normally. You can still paste the snippet below to pre-populate your allow-list by hand.

---

## Fallback: manual paste snippet (pre-v1.13 workflow)

Run `/core:permissions` inside Claude Code to print this, or paste directly into `.claude/settings.local.json`:

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
      "Write(.claude/build-layer-registered)",
      "Write(.claude/sutra-estimation.log)",
      "Write(.claude/logs/*)",
      "Bash(mkdir -p .claude*)",
      "Bash(mkdir -p .enforcement*)"
    ]
  }
}
```

---

## What Sutra does NOT need permission for

Never requested:

- Read/Write anywhere outside `.claude/`, `.enforcement/`, `.context/`, or `~/.sutra/`
- Photos, Documents, Downloads, or any system library
- `~/.ssh`, `~/.aws`, `~/.gnupg`, or any credentials directory
- Network calls except optional `sutra push` (auto-fires on Stop when `telemetry_optin=true`; needs `gh auth`, not a Claude Code permission)
- SSH key generation, Keychain access, OS-level settings change

---

## Audit trail (last 3 changes)

| Date | Change | Why |
|---|---|---|
| 2026-04-24 | v1.13.0 — shipped `permission-gate.sh` (PermissionRequest hook) + PERMISSIONS charter | Founder direction: eliminate recurring prompts; make manifest human-readable |
| 2026-04-22 | v1.5.1 — human-readable grouping + `/core:permissions` command | First-pass readability improvement |
| 2026-04-20 | v1.3.0 — `bin/sutra` refactor collapsed per-script Bash prompts to one | Reduced surface from N scripts to one dispatcher |

---

## Related

- `sutra/os/charters/PERMISSIONS.md` — governance charter (what Sutra MAY request, policy ceiling)
- `hooks/permission-gate.sh` — the mechanism
- `tests/permission-gate-test.sh` — PROTO-000 test (18/18 passing)
- `PRIVACY.md` — what data leaves your machine (nothing unless opt-in)
- `VERSIONING.md` — how we bump versions
- `/core:permissions` — prints the paste-snippet for the fallback workflow
- Open an issue: <https://github.com/sankalpasawa/sutra/issues>
