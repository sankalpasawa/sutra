---
part-id: HS-5
bucket: hardstops
template: ADR-style-invariant
parity-source: §6.9 row HS-5 + §4 I-10
parity-source-sha256: 454b1d0c8ae766f7badd00059f4c98ca4afcc96cc8af08722f40d07e984e0292
status: ACTIVE
authored: 2026-05-09
---

# HS-5: Cutover rollback fails

## Status

ACTIVE (v1.0 — shipped with Native runtime).

## Context (when this fires)

HS-5 fires when a cutover rollback itself fails — i.e., the recovery path that was supposed to undo a failed cutover cannot complete.

Trigger conditions (per canon §6.9 row HS-5 + §4 I-10):
1. A cutover is in progress (per §4 I-10: cutover canary observes `behavior_invariants` throughout `canary_window`).
2. AND the cutover triggers a rollback (whether due to canary regression — see HS-8 — or another cutover failure mode).
3. AND that rollback operation itself fails to restore the prior state.

Observable state at trigger time:
- Cutover engine has entered rollback.
- Rollback completion does not occur within its expected window or returns a failure status.

(The cutover engine's full runtime is aspirational per §8 OS-4. Specific rollback mechanics — what "restore" means per-step, what failure signature constitutes "fails" — are NOT specified in canon §6.9 row HS-5. Runtime implementation choice; future ADR may codify the rollback-failure contract.)

## Decision (fail-mode)

**Pause cutover; founder + Tenant owner HITL** (per canon §6.9 row HS-5).

- The cutover is paused (neither advancing forward nor continuing the failed rollback).
- A HITL (human-in-the-loop) gate is opened naming two parties: founder AND Tenant owner.
- Cutover state is held until both HITL parties take action.

(The specific utterance / approval form, the order of HITL clearances, parallel-vs-sequential approval, and re-attempt vs abandon decision authority are NOT specified in canon §6.9. Runtime implementation choice; future ADR may codify the HITL contract.)

## Recovery path

Per canon §6.9 row HS-5, recovery is gated on founder + Tenant owner HITL action. The HITL parties decide whether to re-attempt the rollback, fall forward, or take a manual recovery path outside the cutover engine.

Specific resume mechanics, retry budgets, and the disposition of any partially-rolled-back state are NOT specified in canon; runtime implementation choice; future ADR may codify.

## Downstream effects

Per canon §6.9 row HS-5, the directly canon-specified downstream effects are:
- The cutover pauses in place (no automatic advance and no automatic retry).
- Two HITL gates open (founder + Tenant owner).

Cross-effects on in-flight Executions targeting the cutover-affected components, on the cadence scheduler, and on N* are NOT specified in canon §6.9 row HS-5; runtime implementation may choose; future ADR may codify. Note: full cutover engine production wiring is itself an open seam (§8 OS-4) — HS-5 is the canonical fail-mode for that engine once wired.

## STRIDE relevance

HS-5 does NOT map to a single STRIDE class in §7. It is a cross-cutting operational hardstop covering the post-deploy cutover surface — a failure mode of the change-management mechanism rather than of a specific attack class. Treat as: **operational cutover-failure guard, post-deploy scope**.

Per §7 column "Native primitive at risk", the cutover-related rows are about behavior invariants and canary observation; HS-5 is the recovery guard when the recovery itself collapses.

## References

- NATIVE-ENGINE.md §6.9 row HS-5 (canonical hardstop definition).
- NATIVE-ENGINE.md §4 I-10 — invariant: cutover canary observes `behavior_invariants` throughout `canary_window`.
- NATIVE-ENGINE.md §8 OS-4 — open seam: cutover engine production wiring still aspirational.
- HS-8 — canonical sibling hardstop for production canary regression (the typical upstream trigger of a rollback).
- D1 §11 — cutover-as-defense reference (cited from §7 preamble).
