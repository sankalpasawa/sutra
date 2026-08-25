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

## Reversing the company-OS install (W2/W3 surfaces)

If `/core:start --profile company` installed operating surfaces, reverse them per item:

```bash
git config --unset core.hooksPath && rm -rf .githooks   # git test gates
bash ${CLAUDE_PLUGIN_ROOT}/bin/sutra-routine remove --all  # scheduled routines (launchd agents os.sutra.plugin.*)
rm -f ~/.sutra/bin/sutra-test-gate ~/.sutra/bin/sutra-routine  # stable shims
```

`os/` (your operating layer) and `.claude/CLAUDE.md` hold YOUR content — they are never auto-deleted; remove them manually if you want them gone. The Native runtime is the separate `native@sutra` plugin: `claude plugin uninstall native@sutra`.
