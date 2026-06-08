---
issue: 9
title: "[Misleading] Telemetry opt-in flag does nothing in v2.0 \u2014 push disabled, but telemetry_optin:true set by default"
author: vinitharmalkar
state: CLOSED
created: 2026-04-27T14:03:35Z
updated: 2026-04-28T13:58:12Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/9
comments: [{'id': 'IC_kwDOR5MNCs8AAAABAnB12g', 'author': {'login': 'sankalpasawa'}, 'authorAssociation': 'OWNER', 'body': 'Fixed (verified on plugin **v2.8.5+** today).\n\n`scripts/start.sh:264-271` now distinguishes the two states:\n- Banner: `Telemetry: on — legacy push active (SUTRA_LEGACY_TELEMETRY=1)` when push is genuinely active\n- Banner: local-only state when push is disabled\n\nREADME L17 now states: *"Local telemetry (v2.0+ privacy model) — signals captured to `~/.sutra/metrics-queue.jsonl` locally; **push to a data store is disabled by default**. Legacy push available via `SUTRA_LEGACY_TELEMETRY=1`. See `PRIVACY.md`."*\n\nThe privacy-axis trust hit is closed: users now see what is actually happening with their data.', 'createdAt': '2026-04-28T13:58:11Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/9#issuecomment-4335891930', 'viewerDidAuthor': True}]
---

# #9 [Misleading] Telemetry opt-in flag does nothing in v2.0 — push disabled, but telemetry_optin:true set by default

**Author:** vinitharmalkar  |  **State:** CLOSED  |  **Labels:** —
**Created:** 2026-04-27T14:03:35Z  |  **Updated:** 2026-04-28T13:58:12Z
**URL:** https://github.com/sankalpasawa/sutra/issues/9

---

## Finding

The README states:
> **Local telemetry** — `~/.sutra/metrics-queue.jsonl`; opt-in push to a data store

`/core:start` prints:
> `Telemetry: on (edit .claude/sutra-project.json to flip)`

Both imply that `telemetry_optin: true` means data is being collected and pushed. It isn't.

---

## What actually happens in v2.0

`scripts/push.sh` opens with:

```bash
# v2.0.0: Legacy telemetry gated behind explicit env flag.
# New privacy model (PRIVACY.md): signals captured locally, no auto-push.
# To use legacy push: SUTRA_LEGACY_TELEMETRY=1 bash push.sh
if [ "${SUTRA_LEGACY_TELEMETRY:-0}" != "1" ]; then
  echo "push disabled in v2.0 privacy model — signals stay local"
  echo "to restore legacy behavior: SUTRA_LEGACY_TELEMETRY=1 <cmd>"
  echo "see $PLUGIN_ROOT/PRIVACY.md for new model"
  exit 0
fi
```

Push is **unconditionally disabled** unless `SUTRA_LEGACY_TELEMETRY=1` is set. The `telemetry_optin` flag in `sutra-project.json` is checked later in `push.sh` — but that code is **never reached** because push exits at line 9.

The Stop hook calls `flush-telemetry.sh`, which calls `push.sh`. Same result: exits immediately with "push disabled."

---

## The contradiction

| What the user sees | What actually happens |
|---|---|
| `/core:start` prints `Telemetry: on` | Metrics queue is written locally only |
| `telemetry_optin: true` in sutra-project.json | Flag is never checked — push exits before reaching it |
| README: "opt-in push to a data store" | Push is disabled regardless of opt-in flag |
| `sutra push` subcommand exists | Always prints "push disabled in v2.0 privacy model" |

---

## Two separate problems

**Problem A — False confirmation of push**
Users who see `Telemetry: on` in the start banner believe they are sending data to Sutra. They aren't. If the intent of v2.0 is local-only by default, the banner should say `Telemetry: local-only (push disabled)`, not `on`.

**Problem B — `telemetry_optin` flag is vestigial**
`sutra-project.json` has `telemetry_optin: true` set by default (for `project` and `company` profiles). Users can flip it to `false`. Neither state changes the actual behavior: push is disabled in both cases. The flag controls nothing in v2.0 and should either be removed or redefined.

---

## Requested fix

1. **Update the start banner** to reflect actual behavior:
   - `project` profile: `Telemetry: local-only` (not `on`)
   - If push is ever re-enabled: `Telemetry: on (pushing to sutra-data)`

2. **Update README** to accurately describe the v2.0 model:
   > "Metrics are written locally to `~/.sutra/metrics-queue.jsonl`. Remote push is disabled by default in v2.0; use `SUTRA_LEGACY_TELEMETRY=1 sutra push` to restore legacy behavior."

3. **Either remove `telemetry_optin` or redefine it** to mean something actionable (e.g., controls whether local queue is written at all).

---
**Session context:** 2026-04-27 · Sutra 2.4.0 · macOS darwin 25.3.0 · Reported by Vinit (Testlify)
