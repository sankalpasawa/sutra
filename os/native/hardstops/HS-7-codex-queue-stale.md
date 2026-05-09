---
part-id: HS-7
bucket: hardstops
template: ADR-style-invariant
parity-source: §6.9 row HS-7 + §7 STRIDE row "Per-step / per-host hang"
parity-source-sha256: 0511dd5f53c86b45dc74bba672ac366208531620e6c6fa113c4235d0f317f8dd
status: ACTIVE
authored: 2026-05-09
---

# HS-7: Codex review queue >20 OR >7d stale

## Status

ACTIVE (v1.0 — shipped with Native runtime).

## Context (when this fires)

HS-7 fires when the codex review queue exceeds 20 items OR contains any item that is >7 days stale.

Trigger conditions (per canon §6.9 row HS-7):
1. The codex review queue depth count exceeds 20 items, OR
2. At least one queued item has been in the queue for more than 7 days without progression.

Observable state at trigger time:
- Queue depth count > 20, OR
- Max queued-item age > 7 days.

(How "the codex review queue" is enumerated, what counts as "stale", which queue surface is the source of truth — these are NOT specified in canon §6.9 row HS-7. Runtime implementation chooses; future ADR may codify the queue-surface contract.)

## Decision (fail-mode)

**Block shipment; founder HITL** (per canon §6.9 row HS-7).

- Shipment is blocked (no new shipping operations advance past the gate).
- A founder HITL gate opens — founder clears the block.

(What "shipment" specifically blocks — git pushes, plugin releases, cutover advances, Workflow ratifications — is NOT enumerated in canon §6.9 row HS-7. Runtime implementation chooses the concrete block-scope; future ADR may codify.)

## Recovery path

Per canon §6.9 row HS-7, recovery requires founder HITL action.

Typically the founder action drains the queue (codex review completion) or explicitly waives the gate. Specific clearance utterances, queue-drain procedures, and partial-clear semantics (e.g., does clearing 1 stale item restore shipment if queue depth still >20?) are NOT specified in canon; runtime implementation choice; future ADR may codify.

## Downstream effects

Per canon §6.9 row HS-7, the directly canon-specified downstream effects are:
- Shipment-class operations block.
- Founder HITL is the only unblock path.

Cross-effects on in-flight Executions that depend on shipped artifacts, on the cadence scheduler, on auto-canary, and on N* are NOT specified in canon §6.9 row HS-7; runtime implementation may choose; future ADR may codify.

## STRIDE relevance

HS-7 does NOT map directly to a STRIDE class in §7. The closest §7 row is "Denial of Service / Per-step / per-host hang" which cites HS-7 in its invariant-guard column — but HS-7 itself guards an operational queue-health surface (codex review pipeline), not a specific attack class. Treat as: **operational queue-health gate, shipment-scope**.

Per §7 row "Per-step / per-host hang" mitigation column: "Per-step timeout configurable; 15-min hard cap on codex per `core:codex-sutra`; daemon kills wedged child on timeout". HS-7 sits adjacent — when codex itself is healthy but the codex *review backlog* signals process-health collapse.

## References

- NATIVE-ENGINE.md §6.9 row HS-7 (canonical hardstop definition).
- NATIVE-ENGINE.md §7 STRIDE row — Denial of Service / Per-step / per-host hang (cites HS-7 in invariant-guard column).
- `core:codex-sutra` skill — codex CLI wrapper that produces the review verdicts feeding the queue.
- PROTO-019 / D40 G2 — codex review gate that drives queue inflow.
