---
issue: 35
title: "[feedback v2.8.5] from plugin"
author: vinitharmalkar
state: CLOSED
created: 2026-04-28T11:20:51Z
updated: 2026-04-28T13:58:21Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/35
comments: [{'id': 'IC_kwDOR5MNCs8AAAABAnB5zQ', 'author': {'login': 'sankalpasawa'}, 'authorAssociation': 'OWNER', 'body': 'Fixed in **v2.8.6** (commit `8b915ff`).\n\n`scripts/start.sh` now accepts `.claude/` directory as a valid project marker. Updated marker-list now reads: `.git / package.json / pyproject.toml / Cargo.toml / go.mod / CLAUDE.md / .claude/`. A directory containing only `.claude/settings.local.json` and `.claude/heartbeats` is now recognized as a Claude Code project — no `--force` needed.\n\n10/10 existing test-start-guard.sh assertions still pass; new smoke test confirms `.claude/`-only tempdir is accepted and empty-dir is still refused.\n\nRun `/core:update` to pick up v2.8.6+.', 'createdAt': '2026-04-28T13:58:20Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/35#issuecomment-4335892941', 'viewerDidAuthor': True}]
---

# #35 [feedback v2.8.5] from plugin

**Author:** vinitharmalkar  |  **State:** CLOSED  |  **Labels:** —
**Created:** 2026-04-28T11:20:51Z  |  **Updated:** 2026-04-28T13:58:21Z
**URL:** https://github.com/sankalpasawa/sutra/issues/35

---

Bug: sutra start fails with 'no project markers' error in a directory that has .claude/settings.local.json and .claude/heartbeats — clearly a Claude Code project directory. The check should recognize .claude/ as a valid project marker, or at minimum suggest --force more prominently as the first option in the error message. User had to run /core:start twice before finding the --force workaround.
