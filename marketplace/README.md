# Sutra Marketplace

_Department activated: 2026-04-18_
_Status: P2 CLEARED 2026-04-18. P3 PRIORITIZE active. Frame: **functionality > GTM**; DayFlow is the canary. Work cadence: one chunk per session, no agents._

## Mission

Ship Sutra as a Claude Code plugin that anyone can install and use as Sutra intends.

Install target: `/plugin install sutra@<marketplace>`
Brand: **Sutra** (bare — Asawa hidden per founder direction 2026-04-18)

## What lives here

```
sutra/marketplace/
├── README.md           ← This file. Nav + current state.
├── plugin/
│   └── plugin.json     ← Claude Code plugin manifest (stub — schema validated in P4).
└── design/
    └── 2026-04-18-deployment-dag.md   ← Live design DAG. Produced via Sutra Kernel workflow.
```

Directories not yet created (activate when phase needs them, per doctrine §4 Simple):

- `plugin/skills/`, `plugin/commands/`, `plugin/resources/` — populated during P4 DEEPEN
- `install-flow/profiles/` — populated when profile onboarding designed
- `distribution/` — populated when Friend-0 plan drafted
- `runtime/installs.jsonl` — created on first real install

## Relationship to `sutra/package/`

| Channel | How installed | Primary audience | Status |
|---|---|---|---|
| `sutra/package/` (npm) | `npx sutra-os@latest` | Terminal-native users; existing flow | Live (v1.9) |
| `sutra/marketplace/` (Claude Code plugin) | `/plugin install sutra@<marketplace>` | Anyone in Claude Code; non-technical friends; future primary channel | In design (P1 complete) |

Both channels install the same underlying Sutra OS. Plugin is the new primary channel; npm stays alive as long as anyone needs it (decision gate in P2).

## Current state — Sutra Kernel workflow progress

```
P0 CLASSIFY   DONE   — Complicated/TRAVERSE
P1 ENUMERATE  DONE   — 20 engineering + 9 customer/market = 29 factors
P2 VALIDATE   DONE   — 5 decisions cleared 2026-04-18 (pivot: functionality > GTM; DayFlow = canary)
P3 PRIORITIZE ACTIVE — Tier 1: F13 + CM3 + CM9 + F1 + F2 + F15
P4 DEEPEN     NEXT   — one chunk per session, no agents
P6 MEASURE    queued
```

**Frame**: functionality > GTM (founder 2026-04-18). Plugin must run DayFlow end-to-end before anything GTM ships.
**Cadence**: one chunk per session (founder 2026-04-18). No subagent fanout. No "do it all now" cascades.

Design DAG: `design/2026-04-18-deployment-dag.md`

## How to resume (new session bootstrap)

Paste into a fresh Claude Code session at `asawa-holding/` root. Each session picks ONE chunk and stops.

> Resume Sutra Marketplace plugin work. P3 done; P4 DEEPEN active. Read in order:
> 1. `sutra/marketplace/README.md` — this file, current state + chunk menu
> 2. `sutra/marketplace/design/2026-04-18-deployment-dag.md` — P3 Tier 1 + P4 chunk menu
> 3. `holding/FOUNDER-DIRECTIONS.md` D29 — cascade TODOs + DayFlow-via-plugin
>
> Then pick ONE P4 chunk (A, B, or C) and work ONLY on that chunk this session:
> - **Chunk A** — Read Claude Code plugin docs (context7/WebFetch), draft `sutra/marketplace/plugin/plugin.json` skeleton (F1). Doc-only, no install yet.
> - **Chunk B** — Map DayFlow's CEO session ops → plugin skills/commands list, written to `sutra/marketplace/design/2026-04-18-dayflow-content-map.md` (F2 + CM9, doc-only).
> - **Chunk C** — Script T+0 → T+60s plugin first-run, written to `sutra/marketplace/design/2026-04-18-first-run-script.md` (CM3 artifact, doc-only).
>
> Produce ONE artifact. Commit. Stop. Do not cascade to the next chunk. Do not launch agents.

State:
- P0-P3 DONE/ACTIVE. 29 factors locked.
- Pivot: functionality > GTM. Don't touch demo videos, listing copy, competitive analysis, pricing mechanisms — all Defer.
- Cadence: one chunk per session. No agents.
- DayFlow is the canary. Plugin ships when DayFlow runs on it.

What NOT to do:
- Do NOT re-enumerate factors (already at 29).
- Do NOT touch `sutra/package/` npm channel (F17 deferred).
- Do NOT do GTM work (CM4/CM6/CM8/Phase D/Phase F all Deferred).
- Do NOT launch subagents for plugin work.
- Do NOT pick more than ONE chunk in a single session.
- Do NOT publish the plugin until CM9 passes (DayFlow runs via plugin for a full cycle without manual hook-patching).
