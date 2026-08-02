---
part-id: HS-6
bucket: hardstops
template: ADR-style-invariant
parity-source: §6.9 row HS-6 + §7 STRIDE Denial-of-Service rows
parity-source-sha256: a1b9ded24d4b833323e77a333ea8a5b82c8edf26456fd6348718625506e786bc
status: ACTIVE
authored: 2026-05-09
---

# HS-6: 3+ governance hooks fail in same turn

## Status

ACTIVE (v1.0 — shipped with Native runtime).

## Context (when this fires)

HS-6 fires when 3 or more governance hooks fail within the same turn.

Trigger conditions (per canon §6.9 row HS-6):
1. A turn is in progress.
2. AND 3+ distinct governance hooks register a failure during that turn.

Observable state at trigger time:
- Hook-self-test surface shows ≥3 hook failures within the active turn boundary.

(The set of "governance hooks" being counted, the definition of "fail" per-hook, and the turn-boundary delineation are NOT explicitly enumerated in canon §6.9 row HS-6. Runtime implementation chooses the concrete hook set and failure signature; future ADR may codify.)

## Decision (fail-mode)

**Suspend session; founder HITL** (per canon §6.9 row HS-6).

- The session is suspended (no further work proceeds in this session).
- A founder HITL gate opens — only the founder clears the suspension.

Contrast HS-2 (per-turn abort, no session suspension) and HS-4 (governance-hooks blocked but not framed as session-level suspension). HS-6 escalates to session-scope per canon.

(Specialized session-suspension state names, automatic-recovery thresholds, and whether queued work resumes vs is discarded are NOT specified in canon §6.9. Runtime implementation choice; future ADR may codify.)

## Recovery path

Per canon §6.9 row HS-6, recovery is gated on founder HITL action.

Specific clearance utterances, partial-resume semantics, and root-cause-fix expectations before clearance are NOT specified in canon; runtime implementation choice; future ADR may codify.

## Downstream effects

Per canon §6.9 row HS-6, the directly canon-specified downstream effects are:
- Session is suspended (no further work).
- Founder is the sole HITL clearer.

Cross-effects on in-flight Workflow Executions, on persisted approval ledger entries (per ADR-009 / I-15), on the cadence scheduler, and on the audit log are NOT specified in canon §6.9 row HS-6; runtime implementation may choose; future ADR may codify.

## STRIDE relevance

**Denial of Service** (operational class). HS-6 maps to the broader DoS surface in §7 — alongside HS-2 (governance overhead exhaustion) and the per-step / per-host hang row — but §7 does not enumerate HS-6 as its own STRIDE table row. Treat as: **DoS class, session-scope governance failure**.

The §7 row for "Governance overhead exhaustion" cites HS-2 specifically; the per-step / per-host hang row cites HS-7. HS-6 is the cousin guard for cascading hook failures within a single turn that indicate a session-level problem, not a per-turn or per-step one.

## References

- NATIVE-ENGINE.md §6.9 row HS-6 (canonical hardstop definition).
- NATIVE-ENGINE.md §7 STRIDE Denial-of-Service rows — sibling DoS guards (HS-2, HS-7 explicit; HS-6 by class).
- HS-2 — sibling per-turn governance overhead hardstop (per-turn scope vs HS-6's session scope).
- HS-4 — sibling audit-unwritable hardstop (blocks hooks but distinct from cascade failure semantics).
