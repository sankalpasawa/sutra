---
part-id: 7e
bucket: blocks
template: L8-feature-spec
parity-source: §12.6 row 7e + §12.5 round 2 founder voice + Q17
parity-source-sha256: da847c84426ba33ed07f7e16a6494522f17d9224d2624639bf7aee9ed48d02b0
status: DRAFT v1
authored: 2026-05-09
---

# 7e: Mid-Execution Mutation

## 1-line summary

Operator may edit a Workflow during its run; system gates the edit by change-class (trivial auto-approved, material founder-approved) — backed by canon reflexive_check Constraint (HS-1) + Approval primitive + full audit log.

## Scope (in / out)

**In scope (v1)**:
- Operator edits Workflow definition while it is running per §12.6 row 7e.
- Change-class gating: trivial (typo / threshold-tune / cosmetic) auto-approved; material (logic / scope / new step / new dep) founder-approved — per Q17 default 2026-05-09.
- Uses existing Workflow.modifies_sutra + reflexive_check Constraint (HS-1) per §12.6 row 7e.
- DecisionProvenance row per mutation per ADR-007.

**Out of scope (v1)**:
- Per-class config that operator tunes (which classes auto-approved vs gated) — deferred v2 per Q17.
- Mutation of in-flight ExecutionResult primitive directly (canon terminal-state invariant §4 I-5 forbids mid-Execution state hand-edit — per F4 cannot invent override).
- Cross-Workflow cascade mutation (one edit propagates to dependent Workflows) — not specified in canon (gap per F2).

## User outcome

Operator can change a Workflow without stopping it, when the change is safe — and the system catches risky changes for explicit approval. Founder voice round 2: "I can help dynamically change it, but that would require some system approvals or something like that."

## UX flow (narrative; terminal + audit log)

1. Workflow is running (ExecutionResult in non-terminal state per §4 I-5).
2. Operator submits a Workflow definition mutation.
3. 7e classifies change: trivial vs material per Q17 default (specific classifier rule NOT specified in canon — gap per F2; runtime implementation choice).
4. Trivial → auto-approve → mutation applied → `policy_decision` event emitted → DecisionProvenance row per ADR-007.
5. Material → routes via canon Approval primitive → `approval_requested` → founder reviews → `approval_granted` or `approval_denied`.
6. If Workflow has `modifies_sutra=true`, reflexive_check Constraint (HS-1) fires per canon §6.9.1.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Mutation classified trivial | mutation submitted | auto-approved; mutation applied; `policy_decision` emitted; DecisionProvenance row recorded per ADR-007 |
| 2 | Mutation classified material | mutation submitted | routes via canon Approval per ADR-009; `approval_requested` (§3.2 #15) emitted; founder reviews |
| 3 | Workflow has `modifies_sutra=true` | mutation classified material | HS-1 reflexive_check fires per canon §6.9.1 (cross-ref `../hardstops/HS-1-reflexive-check.md`); fail-closed per F3 if reflexive_check fails |
| 4 | Mutation submitted but ExecutionResult is in terminal state per §4 I-5 | mutation arrives | rejected; cannot mutate completed Execution; per F4 no terminal-state override invented |
| 5 | Material mutation approved | approval granted | mutation applied; current step may need restart depending on mutation kind (specific restart-semantic NOT specified in canon — gap per F2; future ADR may codify) |

## Data model

Per §12.6 row 7e: 7e EXTENDS existing Workflow.modifies_sutra + reflexive_check Constraint + Approval primitive. No new §2 primitive (per F5).

Classifier output (canon-silent specifics; runtime implementation choice per F2):

```
MutationClass = 'trivial' | 'material'
```

Per Q17 default: trivial = {typo, threshold-tune, cosmetic}; material = {logic, scope, new-step, new-dep}.

Cross-refs:
- `../primitives/workflow.md` (host)
- `../primitives/approval.md` (substrate for material gate)
- `../primitives/decision-provenance.md` (audit row per mutation)
- `../primitives/execution-result.md` (state context — cannot mutate terminal)

## Edge cases

- **Trivial classification disputed** → operator may force-promote to material (canon-silent on mechanism — gap per F2).
- **Mutation triggers HS-1 failure** → fail-closed per canon; mutation rejected.
- **Concurrent mutations** → race handled per canon ADR-009 ApprovalRouter idempotency + B13 (ConcurrencyCoordinator).
- **Mutation arrives mid-step** → applied at step boundary OR step-restart (NOT specified in canon — gap per F2).
- **Operator submits mutation that violates I-5 / I-14 terminal-state invariants** → rejected per F4 (no canon override).

## Telemetry

Events (canon-existing only):
- `policy_decision` (§3.2) — for trivial classification + auto-approval.
- `approval_requested` (#15) / `approval_granted` (#16) / `approval_denied` (#17) — for material.

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Operator-Hours-Saved — mid-exec mutation avoids full restart of a long Workflow.
- Approval-gate latency (canon §14.9 ≤2 min median) — material mutations queue at gate.

## Dependencies

- **Primitives**: `workflow`, `approval`, `decision-provenance`, `execution-result`.
- **Events**: `policy_decision`, `approval_requested`, `approval_granted`, `approval_denied`.
- **Surfaces**: `gate`, `run`, `audit`.
- **Hardstops**: HS-1 (reflexive-check — Workflow.modifies_sutra path), HS-4 (audit-unwritable).
- **Blocks**: 7c (block-by-block mode may compose with mutation), B11 (PromptBuilder rebuilds prompt after mutation).
- **Pillars**: P14 (Outcomes drive design), P4 (Product-POV before tech-POV).
- **ADRs**: ADR-009 (Approval), ADR-007 (DecisionProvenance).

## References

- NATIVE-ENGINE.md §12.6 row 7e (founder voice round 2 — dynamic change with system approvals).
- NATIVE-ENGINE.md §6.9.1 HS-1 reflexive_check.
- Q17 (§12.7) — trivial vs material change-class.
- ADR-009 + ADR-007.
