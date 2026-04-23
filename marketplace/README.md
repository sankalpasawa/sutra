# Sutra Marketplace

_Department activated: 2026-04-18_
_Status: **shipped v1.12.3+** (2026-04-23 Phase 0-6 restructure complete; Kernel reserved for next iteration). Frame: functionality > GTM; DayFlow is the canary validator. Work cadence: case-by-case per founder feedback; no agent fanout on plugin work._

## Mission

Ship Sutra as a Claude Code plugin that anyone can install and use as Sutra intends.

Install target: `/plugin install sutra@<marketplace>` — see `sutra/marketplace/plugin/EXTERNAL-CLIENT-INSTALL.md` for the one-command install contract.
Brand: **Sutra** (bare — Asawa hidden per founder direction 2026-04-18)

## What lives here

```
sutra/marketplace/
├── README.md                  ← This file. Nav + current state.
├── plugin/
│   ├── plugin.json            ← Claude Code plugin manifest (shipped).
│   ├── CHANGELOG.md           ← Version history (v1.12.3+ current).
│   ├── EXTERNAL-CLIENT-INSTALL.md ← One-command install contract for new clients.
│   ├── hooks/                 ← 22 hook registrations live (see `hooks/hooks.json`).
│   ├── skills/                ← Per-turn OS gates (input-routing, depth-estimation, readability-gate, output-trace).
│   ├── os/                    ← Engines + method-registry shipped via plugin.
│   └── lib/                   ← Shared helpers (override-audit, parse-manifest-registry).
└── design/
    └── 2026-04-18-deployment-dag.md   ← Historical design DAG from P0-P3 enumeration.
```

## Relationship to retired `sutra/package/` (npm)

| Channel | How installed | Primary audience | Status |
|---|---|---|---|
| `sutra/archive/package-v1.2.1-retired/` (was npm) | `npx sutra-os@latest` | Terminal-native users; existing flow | Retired 2026-04-23 (archived in-place) |
| `sutra/marketplace/plugin/` (Claude Code plugin) | `/plugin install sutra@marketplace` | Anyone in Claude Code; portfolio companies; external clients | **active — primary channel** |

The plugin is the single enforcement channel (per D33 client firewall: external clients at `~/Claude/<name>/` only cross via plugin install/update).

## Current state — Phase 0-6 restructure shipped (2026-04-23)

```
Phase 0 CLASSIFY   DONE — Complicated/TRAVERSE, Department Registry landed
Phase 1 PROMOTE    DONE — 21 artifacts promoted to plugin L0 (see rollout-gate gate 2)
Phase 2 CONTRACTS  DONE — INTERFACE-CONTRACTS.md (Pack Loader, SUTRA-CONFIG keys, Boundary roles)
Phase 3 DOGFOOD    DONE — Sutra Co. runs on its own plugin per sutra/CLAUDE.md
Phase 5 EXTERNAL   DONE — EXTERNAL-CLIENT-INSTALL.md shipped to marketplace/plugin/
Phase 6 ROLLOUT    DONE — rollout-gate 5/5 green; tests 9/9 green
Phase 7 KERNEL     RESERVED — next iteration (State Persistence · Event Bus · ABI · Capability model)
```

**Frame**: functionality > GTM (founder 2026-04-18). DayFlow canary validates plugin functionality end-to-end; GTM work deferred per memory `feedback_functionality_over_gtm_marketplace`.
**Cadence**: case-by-case per founder feedback; no agent fanout on plugin work.

Interface contracts: `sutra/INTERFACE-CONTRACTS.md`
External client install: `sutra/marketplace/plugin/EXTERNAL-CLIENT-INSTALL.md`
Historical design: `design/2026-04-18-deployment-dag.md`

## Client registry (who's running the plugin)

See `sutra/CURRENT-VERSION.md` §Client Registry for pinned versions. D33 firewall clients (DayFlow, Paisa when migrated, Billu when migrated) install via `/plugin install sutra@marketplace` from their standalone repos; submodule clients (Maze, PPR) ride the pointer bump.

What NOT to do:
- Do NOT resurrect `sutra/package/` npm channel — archived 2026-04-23 in-place at `sutra/archive/package-v1.2.1-retired/`.
- Do NOT create `plugin/extensions/` placeholder dirs — Extension ABI is Phase-2-contract-reference only; dirs materialize when Kernel iteration enables the Pack Loader.
- Do NOT bypass D33 firewall: external clients edit their own `os/SUTRA-CONFIG.md`; Asawa cannot edit their files.
- Do NOT launch subagents for marketplace changes (prior P3 rule retained per codex 2026-04-18 cadence guidance).
