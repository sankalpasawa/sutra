# Assistant — Sutra Interaction Layer

**Version**: v1.0 (2026-04-25)
**Status**: fleet-enabled via plugin v2.2.0
**Upstream spec**: `holding/research/2026-04-24-assistant-layer-design.md` (594 lines, 2 codex rounds, founder-approved)

## What

The **Assistant** is the first artifact in Sutra's **Interaction Layer** — a new architectural class that sits above the 5 foundational blocks (Workflow / Context / Artifact / OS / Governance) and consumes all five. It is the human-facing surface that makes Sutra legible, captures feedback at decision surfaces, and — in later slices — customizes per-user, tracks energy, and enables passenger-mode problem-solving.

Founder names their personal instance **Billu**. Internal/doc name = `assistant`.

## The 7 capabilities (from founder 2026-04-24 voice dump)

1. **Legibility** — human sees what Sutra is doing live
2. **Understanding** — human grasps *why*
3. **Feedback at right places** — narrow prompts at decision surfaces
4. **Per-human customization** — tuned to one specific operator
5. **Live learning** — profile updates on the fly
6. **Energy tracking** — senses state, helps manage
7. **Passenger mode** — problem-solves together with abstraction zoom

## What ships in v1.0 (S1)

Legibility + feedback-capture only. S2 (customization), S3 (passenger), S4 (live learning), S5 (energy) layer on later as event data accrues.

## Files

| File | Role |
|---|---|
| `hooks/assistant-kill-switch.sh` | 3-syscall zero-cost shim fired on Stop |
| `hooks/assistant-observer.sh` | Reads hook-log, appends `turn.observed` events, cursor-derived atomic |
| `hooks/assistant-explain.sh` | `--last K` / `--turn N` / no-args — narrative render |
| `hooks/assistant-feedback.sh` | `--ask` / `--list` / `--answer` / `--profile` — capture loop |
| `hooks/assistant-decommission.sh` | `--dry-run` / `--confirm` — product kill-switch |
| `hooks/hooks.json` | Registers kill-switch shim on Stop event |

## State

Per-client profile + event log at:
- `${CLAUDE_PROJECT_DIR}/holding/state/assistants/<client_id>/events.jsonl` (append-only)
- `${CLAUDE_PROJECT_DIR}/holding/state/assistants/<client_id>/profile.json` (materialized, flocked)

`client_id` follows D34 4-tier taxonomy: `holding` (T1), `owned-<name>` (T2), `project-<name>` (T3), `sutra-<hash>` (T4).

## Kill-switch (4 layers)

| Layer | Mechanism | Scope |
|---|---|---|
| L1 | `enabled_hooks.assistant_observer: false` in `os/SUTRA-CONFIG.md` | Sutra authority — default OFF per D32 |
| L2 | `SUTRA_ASSISTANT_DISABLED=1` env OR `~/.sutra-assistant-disabled` file OR `~/.sutra-disabled` file | User runtime |
| L3 | `enabled: false` in profile.json | Per-client |
| L4 | `assistant-decommission.sh --confirm` | **Product decommission** — unregisters hook, archives state (founder directive 2026-04-24) |

Each layer is additive. L2 shim fast-path verified ≤ 5ms avg over 100 runs; zero tokens when off.

## Operationalization (D30a)

1. **Measurement**: event log growth rate; `/assistant explain` invocations per session; answer rate on feedback prompts (target >70% at 7-day window).
2. **Adoption**: ships via plugin v2.2.0+. Default OFF at L1 for all tiers per D32. Owner flips it on.
3. **Monitoring**: stderr from any assistant script = bug (Analytics dept pulses at 24h). events.jsonl schema-validate failure = immediate patch (D11).
4. **Iteration trigger**: explain fidelity complaints → S3 passenger mode. Answer rate <50% over 14d → surface-design revision.
5. **DRI**: Sutra OS owner (founder during P1-P6; rotates when CoS product ships externally).
6. **Decommission**: L4 mechanism exists. Charter retires when a successor primitive supersedes (e.g., richer H↔Terminal charter absorbs the Interaction Layer).

## Future TODO stubs

- **H↔Terminal Interaction charter** (currently PAUSED per memory `project_ht_interaction_paused.md`) grafts into this Assistant when it resumes. Policy-consumption points enumerated in spec §12.
- **Event contract v1.1** expected at S2 (add confidence, source attribution, prompt lineage). v1.0 envelope stable; payloads evolve.

## Shipped

- **Plugin v2.2.0** (2026-04-25)
- **Asawa reference instance** live since 2026-04-24 (commits 54cda4a → e8bd7b0)
- **Test suite**: 39 assertions across `holding/hooks/tests/test-assistant-*.sh`

See upstream spec for full architecture decisions, codex-round absorption record, and open questions.
