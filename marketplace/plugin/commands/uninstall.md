---
name: uninstall
description: Remove the Sutra plugin. Shortcut for `claude plugin uninstall sutra@sutra`. Preserves local telemetry in ~/.sutra (pass --purge to remove that too).
disable-model-invocation: true
argument-hint: [--purge]
---

# /sutra:uninstall — Remove Sutra

!sutra uninstall $ARGUMENTS

## What this does

- Removes the Sutra plugin via `claude plugin uninstall sutra@sutra`
- Keeps `~/.sutra/` (local telemetry queue, session counters) by default
- Pass `--purge` to also remove `~/.sutra/`

Your `.claude/sutra-project.json` file in each project is left alone — delete it manually if you want.

To reinstall later:

```
claude plugin marketplace add sankalpasawa/sutra
claude plugin install sutra@sutra
/sutra:start
```
