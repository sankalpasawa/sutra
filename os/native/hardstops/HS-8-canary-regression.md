---
part-id: HS-8
bucket: hardstops
template: ADR-style-invariant
parity-source: §6.9 row HS-8 + §4 I-10
parity-source-sha256: 567306a4dae68303c05ce801b30d7e39999e83558ba8036faccd763eefdaae97
status: ACTIVE
authored: 2026-05-09
---

# HS-8: Production canary regression

## Status

ACTIVE (v1.0 — shipped with Native runtime).

## Context (when this fires)

HS-8 fires when the production canary observes a regression against the cutover `behavior_invariants`.

Trigger conditions (per canon §6.9 row HS-8 + §4 I-10):
1. A cutover is live (per §4 I-10: cutover canary observes `behavior_invariants` throughout `canary_window`).
2. AND the canary observes a regression against one or more declared `behavior_invariants` during the canary window.

Observable state at trigger time:
- Active `canary_window` is in progress.
- At least one `behavior_invariant` measurement deviates from baseline in the regression direction.

(The full set of `behavior_invariants` evaluated, the regression detection mechanism, and the threshold per-invariant are NOT specified in canon §6.9 row HS-8 or §4 I-10. Runtime implementation chooses concrete invariants and thresholds; future ADR may codify the canary-contract surface. The cutover engine itself remains aspirational per §8 OS-4.)

## Decision (fail-mode)

**Auto-rollback; founder notify** (per canon §6.9 row HS-8).

- An automatic rollback is initiated (no HITL gate required to start the rollback).
- The founder is notified.

Contrast HS-5 / HS-6 / HS-7 which require founder (and sometimes Tenant owner) HITL to act. HS-8 is the unique canon hardstop with auto-rollback semantics — the regression IS the signal, the rollback IS the response.

(Notification channel, content shape, and timing relative to rollback start are NOT specified in canon §6.9. Runtime implementation choice; future ADR may codify the notification contract.)

## Recovery path

Per canon §6.9 row HS-8, the recovery action is the auto-rollback itself. The founder is notified but is not the unblock gate — the system unblocks itself via the rollback.

If the rollback then fails, control transfers to HS-5 ("Cutover rollback fails") which DOES require HITL (founder + Tenant owner). HS-8 → HS-5 is the canonical escalation path when auto-recovery itself collapses.

Whether the regression-causing change can be re-attempted, and under what additional gating, is NOT specified in canon; runtime implementation choice; future ADR may codify.

## Downstream effects

Per canon §6.9 row HS-8 + §4 I-10, the directly canon-specified downstream effects are:
- Auto-rollback executes against the cutover.
- Founder receives a notification.
- If rollback succeeds: prior state is restored.
- If rollback fails: HS-5 fires (escalation to HITL).

Cross-effects on in-flight Executions targeting the rolled-back component, on the cadence scheduler, and on N* are NOT specified in canon §6.9 row HS-8; runtime implementation may choose; future ADR may codify.

## STRIDE relevance

HS-8 does NOT map directly to a STRIDE class in §7. It is an operational regression-detection hardstop covering the post-deploy canary surface — a quality/safety guard rather than an attack-class guard. Treat as: **operational rollback guard, post-deploy scope**.

§7 STRIDE rows are about attack vectors; HS-8 protects against accidental regression (or upstream attack manifesting as regression). The defensive structure pairs: HS-8 detects + auto-rolls-back; HS-5 catches the case where rollback itself fails.

## References

- NATIVE-ENGINE.md §6.9 row HS-8 (canonical hardstop definition).
- NATIVE-ENGINE.md §4 I-10 — invariant: cutover canary observes `behavior_invariants` throughout `canary_window`.
- NATIVE-ENGINE.md §8 OS-4 — open seam: cutover engine production wiring still aspirational.
- HS-5 — canonical sibling hardstop for cutover-rollback failure (escalation target when HS-8 auto-rollback collapses).
- D1 §11 — cutover-as-defense reference (cited from §7 preamble).
