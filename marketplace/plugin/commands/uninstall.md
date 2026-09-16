---
name: uninstall
description: Remove the Sutra plugin. Shortcut for `claude plugin uninstall core@sutra`. Preserves local telemetry in ~/.sutra (pass --purge to remove that too).
disable-model-invocation: true
argument-hint: [--purge]
---

# /core:uninstall — Remove Sutra

Run this command via the Bash tool:

```bash
${CLAUDE_PLUGIN_ROOT}/bin/sutra uninstall $ARGUMENTS
```

## What this does

- Removes the Sutra plugin via `claude plugin uninstall core@sutra`
- Keeps `~/.sutra/` (local telemetry queue, session counters) by default
- Pass `--purge` to also remove `~/.sutra/`

Your `.claude/sutra-project.json` file in each project is left alone — delete it manually if you want.

To reinstall later:

```
claude plugin marketplace add sankalpasawa/sutra
claude plugin install core@sutra
/core:start
```

## The managed CLAUDE.md block (contract_version)

`/core:start` writes a governance block into `.claude/CLAUDE.md`, between these two markers:

```
<!-- SUTRA GOVERNANCE (managed by /core:start — do not edit manually) -->
...
<!-- /SUTRA GOVERNANCE -->
```

The block carries a `contract_version` stamp naming the runtime contract it was written for. It matters in three places:

| Situation | What the stamp does |
|---|---|
| Plugin updated | SessionStart compares the stamp against the installed runtime; a mismatch prints a `systemMessage` telling you to re-run `/core:start`, so the instructions in the file and the hooks that enforce them never drift apart |
| Plugin pinned or rolled back | the stamp still names the older contract — re-run `/core:start` after the pin so the block matches the version you actually run |
| Plugin uninstalled | uninstall does **not** touch `.claude/CLAUDE.md` — the block and its stamp stay in your repo, describing a runtime that is no longer installed |

After uninstalling, delete the block by hand (everything from the begin marker to the end marker, inclusive) if you do not want those instructions in effect. Everything outside the two markers is yours and was never managed by Sutra.

To see the stamp that is in a file right now:

```bash
grep -n 'contract_version' .claude/CLAUDE.md
```

## Reversing the company-OS install (W2/W3 surfaces)

If `/core:start --profile company` installed operating surfaces, reverse them per item:

```bash
git config --unset core.hooksPath && rm -rf .githooks   # git test gates
bash ${CLAUDE_PLUGIN_ROOT}/bin/sutra-routine remove --all  # scheduled routines (launchd agents os.sutra.plugin.*)
rm -f ~/.sutra/bin/sutra-test-gate ~/.sutra/bin/sutra-routine  # stable shims
```

`os/` (your operating layer) and `.claude/CLAUDE.md` hold YOUR content — they are never auto-deleted; remove them manually if you want them gone. The Native runtime is the separate `native@sutra` plugin: `claude plugin uninstall native@sutra`.
