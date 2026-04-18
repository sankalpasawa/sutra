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

## How to resume (new session bootstrap)

Paste this prompt into a fresh Claude Code session at the asawa-holding root to continue plugin work exactly where it paused:

> Resume Sutra Marketplace plugin work. Read these files in order, then surface the 5 founder decisions awaiting approval at P2 GATE:
> 1. `sutra/marketplace/README.md` (this file — orientation)
> 2. `sutra/marketplace/design/2026-04-18-deployment-dag.md` (P0 + P1, paused at P2 GATE, 20 engineering factors)
> 3. `holding/research/2026-04-18-sutra-marketplace-customer-market-design.md` (customer/market supplement, 8 new factors CM1-CM8, 5 boxed founder decisions D-CM-1 through D-CM-5)
> 4. `holding/FOUNDER-DIRECTIONS.md` D29 (plugin = "Sutra" bare, Asawa hidden, Kernel workflow)
> 5. `holding/research/2026-04-18-workflow-architecture-spec-v1.0-COMMITTED.md` (Sutra Kernel workflow spec)
>
> After loading: present the 5 D-CM-1..D-CM-5 decisions as a single decision board for me to approve/revise/defer. After I clear all 5, fold CM1-CM8 into the deployment DAG and proceed to P3 PRIORITIZE.

State at pause:
- P0 CLASSIFY: DONE (Complicated/TRAVERSE)
- P1 ENUMERATE: DONE (20 engineering factors + 8 customer/market factors = 28 total)
- P2 VALIDATE: **GATE** — 5 founder decisions awaiting approval (see customer/market doc §J)
- P3-P6: queued

Recommended P3 ranking preview (from customer/market doc §I):
- Tier 1 must-resolve: F13 first-run UX, CM3 activation script, F1 plugin manifest, F15 Asawa-leak audit
- Tier 2 pre-listing: CM5 Friend-0 cohort, F2 content mapping, CM2 status quo benchmark, F5 marketplace repo, F18 deeper Friend-0
- Tier 3 + Defer: rest

What NOT to do in the new session:
- Do NOT re-enumerate factors (already at 28, well above the Complicated/TRAVERSE floor of 6)
- Do NOT touch `sutra/package/` npm channel — parallel-channel decision is deferred to P4 F17
- Do NOT publish the plugin or open the marketplace repo until Friend-0 cohort retains ≥50% at week 4 (per customer/market doc §E)
