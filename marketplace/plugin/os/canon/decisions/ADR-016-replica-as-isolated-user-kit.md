<!-- MIRROR (read-only distribution copy). Canonical: sutra/os/decisions/ADR-016-replica-as-isolated-user-kit.md. -->
# ADR-016 — Asawa Replica as Isolated `SUTRA_NATIVE_HOME` User-Kit

## Status
Accepted 2026-05-07 (formalized as part of Native formalization v1.0). Charter contract: see `sutra/os/engines/NATIVE-ENGINE.md` §5.7, §6.3.

## Context
Asawa needs to dogfood Native at full scale: 21 Domains + 8 Charters + 6 Workflows + 6 Triggers replicating the holding company's structure as Native primitives. Two install topologies were considered:

- **Add Asawa primitives to the primary user-kit** at `$HOME/.sutra-native/user-kit/` — single registry, simplest install.
- **Separate user-kit** at `$HOME/.sutra-native-asawa-replica/` (different `SUTRA_NATIVE_HOME` env var) — isolated registry, distinct PID lock, distinct telemetry.

The primary user-kit serves as the production install — it gets primitives that Native ships out of the box, plus T4-fleet test fixtures, plus any per-user emergent workflows. Adding 21+8+6+6 Asawa primitives to that kit creates contamination risk: Workflow IDs (W-hash) might collide with production fixture IDs; reset/cleanup of the dogfood kit would also wipe production fixtures; telemetry from dogfood runs would mix with production runs in the same JSONL.

Sources: `holding/research/2026-05-04-asawa-native-replica.md` §What this is; `holding/plans/native-v1.x/RESUME-V1.X.md` §4; `holding/RESUME-NATIVE-CHARTER.md`.

### Alternatives considered
- Add Asawa primitives to primary user-kit — rejected: contamination risk (ID collision; mixed telemetry; no clean reset path for dogfood).
- Single user-kit with namespaced IDs (e.g. `W-asawa-*`) — rejected: namespace convention does not prevent cleanup mistakes; reset of dogfood would still need surgical filtering.

## Decision
Native engine MUST honor `SUTRA_NATIVE_HOME` env var to redirect user-kit reads/writes; the Asawa replica MUST live at `$HOME/.sutra-native-asawa-replica/`.

- Primary user-kit: `$HOME/.sutra-native/user-kit/` (production / fleet / emergent).
- Asawa replica: `$HOME/.sutra-native-asawa-replica/` — set `SUTRA_NATIVE_HOME=$HOME/.sutra-native-asawa-replica` for any Asawa-scoped work.
- Reset script: `bash holding/scripts/build-asawa-native-replica.sh` (idempotent — wipes + rebuilds replica without touching primary).
- Distinct PID locks + distinct telemetry JSONL — daemons can run side-by-side without interference.

## Consequences

| Kind | Effect |
|---|---|
| + | Clean reset path: dogfood wipe never touches production fixtures |
| + | Telemetry separation: replay analysis on Asawa runs is isolated |
| + | Side-by-side daemons supported — primary + replica each get own PID lock |
| − | Two daemons = two memory + CPU footprints when both are running |
| − | Operator must remember to set `SUTRA_NATIVE_HOME` for Asawa work |
| 0 | Sets pattern for future per-tenant kit isolation as multi-tenant matures |
