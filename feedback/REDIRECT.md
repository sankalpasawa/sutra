# REDIRECT — this folder is retired (2026-04-28)

Per founder direction (D36 follow-up, 2026-04-28): **all Sutra feedback now goes to GitHub issues at [sankalpasawa/sutra](https://github.com/sankalpasawa/sutra/issues).**

## Why

Previously, feedback fragmented across 7 channels (this folder, `sutra/feedback-from-companies/`, `holding/feedback-to-sutra/`, marketplace `FEEDBACK-LOG.md`, per-client `os/feedback-to-sutra/`, `~/.sutra/feedback/manual/`, `sutra-data` git rail). The result: vinitharmalkar's 11 issues filed on 2026-04-27 were invisible to the founder until day later. The fix is consolidation, not adding another channel.

## What replaces this folder

| Channel | Who files | How |
|---|---|---|
| GitHub issues at `sankalpasawa/sutra` | everyone — T4 marketplace users, T2/T3 internal companies, founder | `/sutra:feedback --public` from plugin OR https://github.com/sankalpasawa/sutra/issues/new |
| Local readable mirror | (auto-generated, read-only) | `sutra/marketplace/feedback-inbox/` + `sutra/marketplace/FEEDBACK-LOG.md` |

Sync runs via standing instruction `feedback-sync` (cadence: 1h) — see `sutra/state/system.yaml#standing_instructions`.

## What about the files in this folder

Kept for historical context per "archive, never delete" policy. They reflect a feedback channel that ran 2026-04-03 → 2026-04-17. Don't add new files here.

## Existing files (snapshot at retirement)

- `2026-04-03-onboarding-friction.md`
- `2026-04-17-sutra-to-holding-v1.9-propagation-gaps.md`

## Pointer back to canonical

- Canonical index: [`sutra/marketplace/FEEDBACK-LOG.md`](../marketplace/FEEDBACK-LOG.md)
- Canonical source: https://github.com/sankalpasawa/sutra/issues
- Sync script: `holding/scripts/sync-feedback-from-gh.sh`
- Founder direction: `holding/FOUNDER-DIRECTIONS.md` D36 (line 431, "Feedback Channel Guarded")
- Charter: `sutra/os/charters/OPERATIONALIZATION.md` (Roadmap §6 #14 — charter→engine reclassification pending)
