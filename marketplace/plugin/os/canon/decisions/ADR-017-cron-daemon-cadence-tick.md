<!-- MIRROR (read-only distribution copy). Canonical: sutra/os/decisions/ADR-017-cron-daemon-cadence-tick.md. -->
# ADR-017 — Cadence Scheduling: Daemon-Side setInterval Tick

## Status
Accepted 2026-05-07 (formalized as part of Native formalization v1.0). Charter contract: see `sutra/os/engines/NATIVE-ENGINE.md` §6.4 (cadence scheduling), §3.1 (`CadenceScheduler` API), §2.5 (`TriggerSpec.cadence`); invariant I-12.

## Context
Native needs periodic Trigger firing — per-hour Sutra-OS monitoring, per-6h team tick, daily Asawa pulse, weekly authoritative-vs-advisory drift report, monthly cso comprehensive audit, quarterly V2.x stress-test (`sutra/os/engines/NATIVE-ENGINE.md` §6.4 cadence table).

Two implementation shapes were live:

- **External cron / launchd** — register entries in macOS `launchd` or Linux `cron`; OS fires bash, bash invokes `sutra-native run W-<id>`.
- **Daemon-side `setInterval` tick** — `CadenceScheduler.start(intervalMs)` runs inside the Native daemon; on each tick, scheduled cadences within the ±5 min window fire `TriggerEvent` rows.

External cron is portable in principle but introduces three problems sourced in `holding/research/2026-04-29-native-d5-invariant-register.md` I-12 + `holding/research/2026-04-29-native-gap-audit.md` PS-15 + `RESUME-V1.X.md` §2 Wave 3:

1. macOS uses `launchd`; Linux uses `cron`/`systemd-timer`. No portable CLI surface.
2. External cron has no integration with Native's TriggerEvent lifecycle — fires are not Executions, no DecisionProvenance.
3. ±5 min tolerance window (I-12) is hard to enforce across OS schedulers.

### Alternatives considered
- External `cron` / `launchd` — rejected: not portable across macOS/Linux; no integration with Native TriggerEvent lifecycle; no DecisionProvenance on fire (I-12 unmet).
- Polling at 1s granularity — rejected: wasteful CPU + no proof of delivery.
- Pure cron-style escape hatch (cron string in TriggerSpec) — partially accepted as `TriggerSpec.cadence.cron` field; daemon evaluates it at tick time (kept inside daemon).

## Decision
Native engine MUST implement cadence scheduling as a daemon-side `setInterval` tick; MUST NOT depend on external `cron` / `launchd`.

- `CadenceScheduler.start(intervalMs)` runs inside the daemon process.
- On each tick: enumerate scheduled cadences whose next-fire time falls within the ±5 min window (I-12) → fire `TriggerEvent` rows → route to Workflow registry.
- Each fire emits an EngineEvent + DecisionProvenance — replayable like any other Trigger.
- Higher-level rate spec vs cron-style escape hatch open seam (`sutra/os/engines/NATIVE-ENGINE.md` §8 OS-16).

## Consequences

| Kind | Effect |
|---|---|
| + | Portable across macOS / Linux — daemon-internal, no OS scheduler required |
| + | Each fire emits TriggerEvent + DecisionProvenance — replayable + auditable |
| + | I-12 (±5 min tolerance) verifiable inside the engine, not at OS layer |
| − | Daemon must stay running for cadences to fire (start/stop discipline matters) |
| − | Per-tick CPU cost (small, but non-zero) — `setInterval` runs even when no cadences are due |
| 0 | OS-16 open seam: higher-level rate spec API revisits when first complex cadence lands |
