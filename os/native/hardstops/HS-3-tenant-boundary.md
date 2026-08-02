---
part-id: HS-3
bucket: hardstops
template: ADR-style-invariant
parity-source: §6.9 row HS-3 + §7 STRIDE row "Cross-tenant leakage" + §4 I-8 + §4 I-13
parity-source-sha256: 69970b94d878062cdcf68d6e6633fa350f91ccaa531d57f895c1712b642513e5
status: ACTIVE
authored: 2026-05-09
---

# HS-3: Tenant boundary cross without TenantDelegation

## Status

ACTIVE (v1.0 — shipped with Native runtime).

## Context (when this fires)

HS-3 fires when an Execution attempts to cross a Tenant boundary without an explicit `delegates_to` edge.

Trigger conditions (per canon §6.9 row HS-3 + §4 I-8 + §4 I-13 + §7 STRIDE "Cross-tenant leakage" + ADR-006):
1. An `Execution` carries `tenant_context.tenant_id` (per §4 I-13: every Domain owned by exactly one Tenant via `tenant_id`).
2. AND a step within that Execution targets a resource whose effective tenant differs from `Execution.tenant_context.tenant_id`.
3. AND no explicit `delegates_to` edge authorizes that boundary cross (per §4 I-8).

Observable state at trigger time (per §7 STRIDE mitigation column for "Cross-tenant leakage"):
- `Execution.tenant_context.tenant_id` is set.
- The step's effective tenant differs.
- `TenantIsolation.assertCrossTenantAllowed` (per §6.2) returns deny.
- Fail-closed when `workflow.custody_owner !== null` AND `tenant_context_id` is undefined.

(How `delegates_to` edges are minted, granted, revoked, and audited is NOT specified in canon §6.9 — see ADR-006 for the delegation primitive contract. This part-file does not codify mint mechanics.)

## Decision (fail-mode)

**Block + log + escalate** (per canon §6.9 row HS-3).

- The cross-tenant op is blocked at the `TenantIsolation.assertCrossTenantAllowed` check (per §6.2).
- A `tenant_boundary_violation` event emits (per §3.2 row #26) carrying `src_tenant`, `dst_tenant`, `op`.
- A DecisionProvenance row is logged with `policy_id='HS-3'` (per §4 I-7 — every consequential decision emits provenance).
- The violation is escalated.

(Escalation target audience — founder vs Tenant owner vs both, channel — is NOT explicitly specified in canon §6.9 row HS-3. Contrast HS-5 which names "founder + Tenant owner HITL". Runtime implementation chooses HS-3 escalation routing; future ADR may codify.)

## Recovery path

Per canon §6.9 row HS-3, recovery requires the operator to authorize the cross via an explicit `delegates_to` edge (per §4 I-8 + ADR-006).

Specific authorization utterances, per-Execution-vs-per-Workflow scope of the delegation, and whether the rejected Execution can resume in-place or must be re-dispatched are NOT specified in canon; runtime implementation choice; future ADR may codify.

## Downstream effects

Per canon §6.9 + §7 + §4 I-8 + §3.2 row #26, the directly canon-specified downstream effects are:
- The blocked op does not execute (no cross-tenant read/write occurs).
- A `tenant_boundary_violation` EngineEvent is emitted.
- AUDIT surface persists the DecisionProvenance row.
- Escalation fires per the §6.9 escalation column.

Whether the parent Execution transitions to a terminal state, pauses, or continues with the violating step skipped is NOT specified in canon §6.9 — runtime implementation may consult `Workflow.failure_policy` (per §6.5) but the canon hardstop row does not name a specific terminal disposition. Future ADR may codify.

## STRIDE relevance

**Information Disclosure** (per canon §7 STRIDE row "Cross-tenant leakage"). HS-3 guards against a Workflow executing under Tenant A reading or writing a Tenant B resource without delegation.

Per §7 row, the mitigation column cites: "TenantIsolation engine: runtime-derived enforcement; F-6 at terminal_check; fail-closed when `custody_owner !== null` AND `tenant_context_id` undefined". HS-3 is the runtime guard; F-6 (forbidden coupling) is the terminal_check guard; I-8 is the structural invariant.

## References

- NATIVE-ENGINE.md §6.9 row HS-3 (canonical hardstop definition).
- NATIVE-ENGINE.md §4 I-8 — invariant: Tenant boundary not crossed without an explicit `delegates_to` edge.
- NATIVE-ENGINE.md §4 I-13 — invariant: Every Domain is owned by exactly one Tenant via `tenant_id`.
- NATIVE-ENGINE.md §7 STRIDE row — Information Disclosure / Cross-tenant leakage.
- NATIVE-ENGINE.md §3.2 row #26 — `tenant_boundary_violation` EngineEvent.
- NATIVE-ENGINE.md §6.2 — Multi-tenant isolation runtime (`TenantIsolation.assertCrossTenantAllowed`).
- ADR-006 — Tenant primitive + delegation contract.
- F-6 forbidden coupling — companion terminal_check guard.
