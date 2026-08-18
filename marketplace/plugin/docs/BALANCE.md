---
title: Balance — founder coach
status: shipping
updated: 2026-08-18
---

# Balance — the founder coach

Balance watches how you actually work — from your own messages and their timing, never by interrupting — and coaches you with evidence: earned praise, honest gaps, and a small set of actionables that close only when proof appears or you say so.

## What you get

| Surface | What it shows |
|---|---|
| Balance screen (desktop app) | greeting, day strip (96 windows), coach cards, live actionables with done-checkboxes |
| The Five Hats dashboard | TODAY / THIS WEEK / MONTH tabs: role heatmap, shipped timeline, per-role coaching |
| Daily pass (21:30) | folds the ledger, auto-closes evidence-met actionables, regenerates the dashboard |
| Weekly rollup (Sundays) | opened/closed/moved counts + late-night days, one honest sentence |

## The rules it lives by

1. **Observe-only.** Signals come from your messages; machine activity filtered; it never interrupts.
2. **No fabricated measurement.** Sparse data lowers confidence and says so.
3. **Two doors to done.** A checkable predicate (file-exists / fixed-string grep / builtin) closes an actionable automatically the night its evidence appears; everything else closes only on your explicit word. A witness may not attest to its own testimony: coach-written files are banned as evidence.
4. **Recurrence is arithmetic.** Open items resurface daily with `open Nd`; escalation is a stall clock (progress notes reset it) plus a hard total-age cap — closing beats note-taking.
5. **Start small.** Active actionables are capped (`max_active`, default 3); the rest park visibly.

## Adopting Balance in your instance

1. State lives at `$CLAUDE_PROJECT_DIR/.sutra/balance/` (or set `SUTRA_BALANCE_STATE_DIR`).
2. Schedule `scripts/balance/balance-observe.sh` every 15 min and `scripts/balance/balance-daily-pass.sh` daily (launchd/cron templates in the scripts' headers).
3. Optional Slack digest: invite your bot to a channel, set `slack_channel` in `coach-profile.json`.

Marking done from the app requires the desktop build (the write endpoint is desktop-token-gated; browsers are read-only by design).

---
provenance: authored 2026-08-18 (PLAN-25 step 24), session d9227850; engine: scripts/balance/; doctrine: insights-balance EVIDENCE.md; decision: os/decisions/ADR-033.
