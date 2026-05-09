---
part-id: HS-2
bucket: hardstops
template: ADR-style-invariant
parity-source: §6.9 row HS-2 + §7 STRIDE row "Governance overhead exhaustion" + §4 I-6
parity-source-sha256: b324f8296e8770296e30aa327bebc480813d2c0c692dd469b40f1ae6a3329fff
status: ACTIVE
authored: 2026-05-09
---

# HS-2: Governance overhead >25%

## Status

ACTIVE (v1.0 — shipped with Native runtime).

## Context (when this fires)

HS-2 fires when per-turn governance overhead exceeds 25% of the token budget.

Trigger conditions (per canon §6.9 row HS-2 + §4 I-6 + §7 STRIDE "Governance overhead exhaustion"):
1. Per-turn governance overhead measurement (I-6) is computed for the active turn.
2. AND that measured overhead exceeds the 25% threshold.

Observable state at trigger time:
- Governance overhead metric > 0.25 of the token budget for the current turn.
- Per §4 I-6, the soft target is ≤15% and HARD-STOP threshold is >25%.

(How "per-turn governance overhead" is measured — which token sinks count, the budget reference, the measurement window granularity — is NOT specified in canon §4 I-6 or §6.9. Runtime implementation chooses these; this part-file is the spec, not the implementation. Future ADR may codify the measurement contract.)

## Decision (fail-mode)

**Abort turn; emit HARD-STOP DecisionProvenance** (per canon §6.9 row HS-2).

- The current turn is aborted at the point HS-2 is detected.
- A DecisionProvenance row is emitted with the HARD-STOP marker referencing `policy_id='HS-2'`.
- The hook self-test / OTel emitter pathway carries the I-6 measurement that triggered the abort (per §7 STRIDE mitigation column for this row).

(Specialized state names, fire-count escalation thresholds, per-tenant debit semantics, and N* metric impact are NOT specified in canon. Runtime implementation choice; future ADR may codify.)

## Recovery path

Per canon §6.9 row HS-2, the canonical recovery action is the turn-abort itself plus the HARD-STOP DecisionProvenance write — there is no founder-HITL gate cited for HS-2 (unlike HS-5/HS-6/HS-7). The operator's next turn proceeds normally; recovery is per-turn-scoped.

Specific resume mechanics (whether the next turn re-runs the aborted intent automatically, or requires a fresh utterance) are NOT specified in canon; runtime implementation choice; future ADR may codify.

## Downstream effects

Per canon §6.9 + §7 + §4 I-6, the directly canon-specified downstream effects are:
- The triggering turn does not complete its work output.
- A HARD-STOP DecisionProvenance row is appended to the audit JSONL.
- Subsequent turns are not blocked by HS-2 itself (HS-2 is per-turn, not session-wide; this contrasts with HS-6 which suspends the session).

Cross-effects on other governance hooks, on cadence schedulers, on in-flight Workflow Executions, and on N* are NOT specified in canon for HS-2; runtime implementation may choose; future ADR may codify.

## STRIDE relevance

**Denial of Service** (per canon §7 STRIDE row "Governance overhead exhaustion"). HS-2 guards against per-turn governance overhead consuming >25% of the token budget — a DoS class attack where the discipline layer itself starves the productive work layer.

Per §7 row, the mitigation column cites: "I-6 governance overhead measurement; HS-2 HARD-STOP at >25%". HS-2 is the terminal guard; I-6 is the measurement that makes the guard observable.

## References

- NATIVE-ENGINE.md §6.9 row HS-2 (canonical hardstop definition).
- NATIVE-ENGINE.md §4 I-6 — invariant defining governance overhead target (≤15%) and HARD-STOP threshold (>25%).
- NATIVE-ENGINE.md §7 STRIDE row — Denial of Service / Governance overhead exhaustion.
- DecisionProvenance primitive (§2.9) — the audit row written on trigger.
- `policy_decision` event (§3.2 row #8) — the EngineEvent surface for the abort.
