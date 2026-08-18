---
title: ADR-033 — Balance graduates from Asawa-local to plugin
status: accepted
updated: 2026-08-18
---

# ADR-033 — Balance graduates from Asawa-local (L2) to plugin (L0)

## Status

Accepted 2026-08-18 (founder direction: "complete all the waves"; PLAN-25 steps 18-20).

## Context

Balance — the founder-wellbeing coach (15-min observer, event-sourced coach ledger, nightly pass, tabbed dashboard, live actionables in the desktop app) — was built Asawa-local under `holding/` per insights-balance DESIGN.md v0.x. The engine proved out: evidence-first actionable closes (EVIDENCE.md four-rule doctrine), derived-never-emitted recurrence, consult-reviewed at every wave, endpoint + smoke suites green. The desktop integration (PR #113) already ships in the plugin. Keeping the engine instance-local splits one feature across two custody tiers.

## Decision

Graduate the ENGINE to the plugin; keep INSTANCE STATE local.

| Piece | Custody | Where |
|---|---|---|
| Observer, coach pass, renderer, daily wrapper | plugin L0 (fleet) | `marketplace/plugin/scripts/balance/` |
| API read model + write endpoint + panel UI | plugin L0 (shipped, PR #113) | `sutra-ui/` |
| State contract (ledger, profile, logs, dashboard html) | instance-local, NEVER shipped | `$CLAUDE_PROJECT_DIR/.sutra/balance/` (Asawa keeps `holding/state/balance/`) |
| Evidence doctrine | travels with the engine | EVIDENCE.md (copied to plugin docs at adoption) |
| launchd scheduling | instance opt-in | per-instance plists; not auto-installed |

State-dir resolution (all engine files): `SUTRA_BALANCE_STATE_DIR` (validated absolute) → `$CLAUDE_PROJECT_DIR/.sutra/balance` → legacy `holding/state/balance` (Asawa back-compat).

## Consequences

- Fleet instances can adopt Balance by creating the state dir + scheduling the pass; no Asawa paths required.
- Asawa remains the dogfood instance; its `holding/scripts/balance-*` copies retire after one stable fleet release (decommission gate: plugin copies green in Asawa's own nightly for 7 days).
- Version/tag for the shipping release is HELD for the maintainer (2.99.1 vs published-cache 2.101.0 reconciliation — see CHANGELOG Unreleased).
- Slack digest stays config-gated per instance (bot membership is a per-workspace founder action).

---
provenance: authored 2026-08-18, session d9227850, PLAN-25 wave C; sources: insights-balance DESIGN.md/ROADMAP.md/EVIDENCE.md, PR #113, dual-lane consult transcripts.
