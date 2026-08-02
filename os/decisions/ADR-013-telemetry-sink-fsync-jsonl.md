# ADR-013 — Telemetry Sink: fsync'd JSONL Append

## Status
Accepted 2026-05-07 (formalized as part of Native formalization v1.0). Charter contract: see `sutra/os/engines/NATIVE-ENGINE.md` §5.6, §5.3 (H-Sutra event bus); HARD-STOP HS-4.

## Context
Native emits two streams that need durable replay:

1. **EngineEvent** (26 typed event types per §3.2) — every Workflow lifecycle row.
2. **DecisionProvenance** (ADR-007) — every consequential decision.

Plus the H-Sutra producer ships a parallel JSONL row per founder turn (`holding/state/interaction/log.jsonl`).

Three sink shapes were considered, each evaluated against four constraints: (a) survives daemon restart, (b) zero new dependency, (c) append-only audit, (d) multi-process safe.

- **In-memory ring buffer** (`Router.decisionLog`) — fails (a): organic-emergence detector reads H-Sutra log directly; in-memory dies on daemon restart (codex P1.2 forced rejection in `organic-emergence-v1-SPEC.md` §0).
- **SQLite or structured DB** — passes (a)/(c)/(d) but fails (b): adds dependency, requires schema migrations, more brittle than fsync'd append for replay.
- **fsync'd JSONL append** — passes all four. Per-line append + fsync per write = crash-safe, zero-dep, multi-process safe (atomic line-level appends on POSIX).

Sources: `holding/research/2026-05-06-w-load-native-context-design.md` §2; `holding/research/2026-04-29-native-d2-decision-provenance-spec.md` §6.2 (stderr beacon fallback).

### Alternatives considered
- In-memory ring buffer — rejected: organic-emergence reader needs persistence across restart (codex P1.2).
- SQLite/DB — rejected: adds dep + schema migration overhead; JSONL won on append-only proof + zero-dep.

## Decision
Native engine MUST persist EngineEvent and DecisionProvenance as fsync'd JSONL append-only files; H-Sutra event bus MUST follow the same shape.

- One JSONL line per event/decision; UTF-8; no newline-in-field (sanitized at emit).
- `fsync` per append (durability) — never lose a row on crash.
- Stderr beacon fallback when primary path is unwritable; dual fallback to `/tmp` (HS-4 chain).
- Pattern detector (ADR-010) reads the log directly — no in-memory cache; restart-safe.

## Consequences

| Kind | Effect |
|---|---|
| + | Crash-safe — fsync per append; events survive daemon restart |
| + | Zero new runtime dependency — append-only file, OS-level guarantees |
| + | Multi-process safe — POSIX append atomicity holds for short lines |
| − | Disk I/O cost per event (fsync is not free) — acceptable for current event rate |
| − | No indexed query — replay is sequential scan; aggregation is downstream tooling |
| 0 | OTel production transport (OS-10) is the next-tier deferral — JSONL stays primary |
