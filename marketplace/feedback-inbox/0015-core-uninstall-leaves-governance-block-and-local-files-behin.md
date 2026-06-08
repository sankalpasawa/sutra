---
issue: 15
title: "/core:uninstall leaves governance block and local files behind"
author: sankalpasawa
state: CLOSED
created: 2026-04-27T17:45:38Z
updated: 2026-04-27T17:54:02Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/15
comments: [{'id': 'IC_kwDOR5MNCs8AAAABAgu-qg', 'author': {'login': 'sankalpasawa'}, 'authorAssociation': 'OWNER', 'body': 'Closing — this issue was filed via an unsanctioned channel (direct `gh issue create` invoked as fallback after the `sutra feedback --public` binary failed on a missing label).\n\nThe reported bugs are real and are being tracked internally on the Sutra Assistant Layer charter. Filing a public issue against an internal Sutra repo is not the intended feedback path; `/core:feedback` (local) is the supported channel until the public path is hardened (binary label handling + CLI bypass guard, both being fixed now).\n\nContent captured locally; no information lost.', 'createdAt': '2026-04-27T17:54:01Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/15#issuecomment-4329291434', 'viewerDidAuthor': True}]
---

# #15 /core:uninstall leaves governance block and local files behind

**Author:** sankalpasawa  |  **State:** CLOSED  |  **Labels:** —
**Created:** 2026-04-27T17:45:38Z  |  **Updated:** 2026-04-27T17:54:02Z
**URL:** https://github.com/sankalpasawa/sutra/issues/15

---

Running `/core:uninstall` (Sutra 2.6.0) removed the plugin successfully but left the following on disk, with no warning or prompt:

1. **Sutra governance block in `~/.claude/CLAUDE.md`** — the marker-delimited block injected by `/core:start` is still active, so Claude continues emitting INPUT/DEPTH/OS traces in every response after uninstall.
2. **`~/.sutra/`** — telemetry queue, session counters, consent files, etc. Documented as default; `--purge` flag is mentioned but not surfaced in the uninstall command UX.
3. **Stray files in `~/.claude/`** — `sutra-estimation.log` and `sutra-project.json` left at the top level.

## Expected

Uninstall should either (a) clean these up by default, or (b) print a clear "to fully remove, also do X / Y / Z" message at the end. Currently the script just says `Done.` which suggests a complete removal.

## Repro

```
claude plugin install core@sutra
/core:start
/core:uninstall
# governance block still in ~/.claude/CLAUDE.md
# Claude still emits INPUT/DEPTH/OS scaffolding
# ~/.sutra/ and stray ~/.claude/sutra-* files remain
```

## Env

- macOS Darwin 23.6.0
- Sutra 2.6.0
- plugin scope: user
