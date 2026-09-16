---
name: update
description: Update the Sutra plugin to the latest version from the marketplace. Shortcut for `claude plugin marketplace update sutra && claude plugin update core@sutra`.
disable-model-invocation: false
---

# /core:update — Pull the latest Sutra version

Run this command via the Bash tool:

```bash
${CLAUDE_PLUGIN_ROOT}/bin/sutra update
```

## What this does

Refreshes the Sutra marketplace cache, then applies any version bump to the installed plugin. Equivalent to:

```
claude plugin marketplace update sutra
claude plugin update core@sutra
```

**After this command, run `/reload-plugins` to apply the new code to your current session** (or restart Claude Code). Without this, the new version is downloaded but not active in the running session.

Most Claude Code sessions auto-update on startup. Run this mid-session if you want the latest without waiting for a restart.

## Pin or roll back

An update you do not want is undone by installing an explicit version. Pinning and rolling back are the same operation — name the version you want:

```
claude plugin install core@sutra@<version>
```

Then `/reload-plugins` (or restart Claude Code). Without the reload the pinned code is on disk but the running session still holds the old one.

| Step | Command | Why |
|---|---|---|
| 1. Find the version | `ls ~/.claude/plugins/cache/sutra/core/` | every version you have installed, newest last; `CHANGELOG.md` in the plugin says what changed in each |
| 2. Install it | `claude plugin install core@sutra@<version>` | pins that exact version — this is also how you roll back |
| 3. Apply it | `/reload-plugins` | the session keeps running the old code until you do |
| 4. Confirm | `${CLAUDE_PLUGIN_ROOT}/bin/sutra --version` | prints the version that is actually live |

A pin stays put: `claude plugin update core@sutra` moves off it again when you are ready, followed by `/reload-plugins`.

**Faster than a rollback, when the problem is the governance runtime itself**: turn the runtime off and let the legacy hooks run unchanged.

```bash
touch ~/.sutra-runtime-disabled     # every session, until you remove the file
SUTRA_RUNTIME_DISABLED=1 <command>  # one command only
```

Both fall back to the individually registered hooks. Remove the file (`rm ~/.sutra-runtime-disabled`) to turn the runtime back on. Use a version pin when a specific release broke something; use the kill-switch when you want the previous behaviour immediately and will diagnose later.
