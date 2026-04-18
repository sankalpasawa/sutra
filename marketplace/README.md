# Sutra Marketplace

_Department activated: 2026-04-18_
_Status: P0-P1 complete. Awaiting founder validation of factor list._

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
P1 ENUMERATE  DONE   — 20 factors across 10 disciplines
P2 VALIDATE   GATE   — awaiting founder approval of factor list
P3 PRIORITIZE queued
P4 DEEPEN     queued
P6 MEASURE    queued
```

Design DAG: `design/2026-04-18-deployment-dag.md`

## How to resume

If you're picking this up in a future session:

1. Read `design/2026-04-18-deployment-dag.md` for the live design state
2. Read `holding/research/2026-04-18-workflow-architecture-spec-v1.0-COMMITTED.md` for the Kernel workflow spec
3. Read `holding/FOUNDER-DIRECTIONS.md` D29 for the plugin deployment directions
4. Current gate (in dag file) tells you what founder needs to approve next
