---
issue: 7
title: "[Phantom] RTK auto-rewrite silently does nothing \u2014 rtk binary undeclared dependency, absent on most machines"
author: vinitharmalkar
state: CLOSED
created: 2026-04-27T14:03:30Z
updated: 2026-04-28T13:58:09Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/7
comments: [{'id': 'IC_kwDOR5MNCs8AAAABAnBz_Q', 'author': {'login': 'sankalpasawa'}, 'authorAssociation': 'OWNER', 'body': 'Fixed in **v2.7.3** (verified on v2.8.5+ today).\n\nThree changes shipped:\n\n1. **README** marked `(opt-in)` and explicitly states *"Requires `rtk` binary installed separately (not bundled with the plugin); inactive when binary missing — start banner shows live status."*\n2. **Start banner** prints live status: `RTK rewrite: active` or `inactive — rtk binary not installed (opt-in; see README)` based on a `shutil.which("rtk")` check.\n3. Source comment in `scripts/start.sh:272` cites this issue: `# v2.7.3 honesty (vinit#7): RTK rewrite is opt-in external dep, not bundled.`\n\nThe hook still no-ops when the binary is missing — but that is now the documented opt-in semantics, not a phantom claim. Run `/core:update` to confirm.', 'createdAt': '2026-04-28T13:58:07Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/7#issuecomment-4335891453', 'viewerDidAuthor': True}]
---

# #7 [Phantom] RTK auto-rewrite silently does nothing — rtk binary undeclared dependency, absent on most machines

**Author:** vinitharmalkar  |  **State:** CLOSED  |  **Labels:** —
**Created:** 2026-04-27T14:03:30Z  |  **Updated:** 2026-04-28T13:58:09Z
**URL:** https://github.com/sankalpasawa/sutra/issues/7

---

## Finding

The README advertises:
> **RTK auto-rewrite** — PreToolUse hook forces `rtk` wrap on voluminous bash (git status/log/diff/blame/show) for 30-60% tool-output reduction

The hook file `hooks/rtk-auto-rewrite.sh` exists and is registered in `hooks.json` (PreToolUse Bash matcher). But line 22 of the hook is:

```bash
if ! command -v rtk >/dev/null 2>&1; then
  exit 0
fi
```

**`rtk` is not on this machine.** Confirmed:
```bash
$ command -v rtk
# (empty — not found)
```

When `rtk` is absent the hook silently exits 0 — no blocking, no wrapping, no output reduction. The feature is **completely inert** and the user has no indication it isn't working.

## What's missing

`rtk` is not:
- Installed as part of `claude plugin install core@sutra`
- Listed as a dependency anywhere in `README.md`, `PERMISSIONS.md`, or `ARCHITECTURE.yaml`
- Referenced in `sutra help` output
- Mentioned in `/core:start` output
- Available via any documented install path

Searching the entire 2.4.0 plugin tree for rtk install instructions returns nothing.

## Impact

Every user who installs Sutra without separately discovering and installing `rtk` gets zero benefit from this advertised feature. The banner, README, and hook are all silent about the dependency. Users believe the feature is active; it isn't.

## Requested fix

Either:
1. Add `rtk` installation to `sutra install-shell-helpers` and document it as a dependency in the README, OR
2. Remove the RTK auto-rewrite claim from the README feature list and mark it as requiring opt-in install of an external tool, OR
3. Print a one-time warning in `/core:start` when `rtk` is not found: `"RTK auto-rewrite: inactive (rtk not installed — see X for setup)"`

The current state — advertising a feature that silently does nothing for most users — is the same class of issue as `session-retrieve`.

---
**Session context:** 2026-04-27 · Sutra 2.4.0 · macOS darwin 25.3.0 · Reported by Vinit (Testlify)
