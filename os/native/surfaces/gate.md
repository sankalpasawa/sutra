---
part-id: GATE
bucket: surfaces
template: L9-surface-spec
parity-source: §14.7 + §3.1 + §3.2 #7,#15-#18 + §3.4 + §6.6
parity-source-sha256: df34b63ccd06e98f6e21afe9c32727584a97ea703d9b8ed7e53be3fe1235f82f
status: DRAFT v1
authored: 2026-05-09
---

# Surface: GATE

## Purpose

Pause an Execution at a `requires_approval` step → surface a structured approval-request to the founder → resume on `approve E-<id>` or terminate on `reject E-<id> <reason>`.

Canon: §14.7 row 3 — *"GATE | Pause on `requires_approval` → surface to founder"*.

## Interface (operator-facing)

The operator's approval interface is the founder utterance set (§3.4):

| Utterance | Effect |
|---|---|
| `approve P-<id>` | Approve a proposed Workflow (routes to EMERGE, NOT GATE) — see Note |
| `approve E-<id>` | Resume an Execution in `awaiting_approval` → `NativeEngine.resumeApproved(execId)` |
| `reject E-<id> <reason>` | Deny pending Execution; emit `approval_denied` |

Approval ledger (§6.6): pending approvals persist at `user-kit/pending-approvals/E-<id>.json` carrying `{workflow_id, step_index, ts_ms, prompt_summary}` until resolved.

**Note**: §3.4 lists `approve P-<id>` in the same table as `approve E-<id>`, but the P-form approves a *proposed Workflow* (handled by EMERGE per §3.2 #13 `proposal_approved`). GATE handles only E-form utterances (Execution-level approvals). Cross-surface boundary documented here to disambiguate.

## Invariants (must always hold)

| # | Invariant | Source |
|---|---|---|
| GATE-I1 | Reaching a step with `step.requires_approval=true` OR `workflow.requires_approval=true` emits exactly one `approval_requested` event + one `step_paused` event. | §3.2 rows 7, 15 |
| GATE-I2 | Execution state transitions to `awaiting_approval` (one of §2.6 enum values); persists at `user-kit/pending-approvals/E-<id>.json`. | §2.6 state enum + §6.6 |
| GATE-I3 | `approve E-<id>` triggers `NativeEngine.resumeApproved(execId)` → continues at `step_index+1` → emits `approval_granted`. | §3.1 + §3.2 row 16 + §6.6 |
| GATE-I4 | `reject E-<id> <reason>` emits `approval_denied` and terminates Execution (`state=failed`, `failure_reason` non-null per I-4). | §3.2 row 17 + I-4 |
| GATE-I5 | Idempotent: re-firing `approve E-<id>` on an already-resolved approval emits `approval_already_handled`, not a second `approval_granted`. | §3.2 row 18 |

Canon gap: §14.7 says "surface to founder" but does NOT specify the surfacing channel (terminal stdout? notification? log-only?). §6.6 specifies persistence at `user-kit/pending-approvals/E-<id>.json` but the founder-facing notification path is NOT specified in canon — runtime implementation choice; the founder is expected to poll or be alerted by the host-LLM session.

Canon gap (multi-party): Q5 ANSWERED 2026-05-09 to single-founder approval v1. Multi-party quorum is OS-15 (open seam) — deferred to v2+. GATE-I3 assumes single-approver authority.

## Integration points

- **Primitives consumed**: [`Approval`](../primitives/approval.md), [`ExecutionResult`](../primitives/execution-result.md) (state transitions through `awaiting_approval`), [`Workflow`](../primitives/workflow.md) (the `requires_approval` field), [`Step`](../primitives/step.md) (the step-level `requires_approval`).
- **Events emitted**:
  - [`step_paused`](../events/step_paused.md) (#7)
  - [`approval_requested`](../events/approval_requested.md) (#15)
  - [`approval_granted`](../events/approval_granted.md) (#16)
  - [`approval_denied`](../events/approval_denied.md) (#17)
  - [`approval_already_handled`](../events/approval_already_handled.md) (#18)
- **Events consumed**: From RUN — the step-level signal that a step has `requires_approval=true`. (Strictly: RUN evaluates `requires_approval`; if true, RUN itself emits `step_paused` and stops dispatching — GATE then takes over via its consumption of the persisted Approval row. The exact internal handshake between RUN and GATE is not specified in canon; runtime implementation choice.)
- **Surfaces upstream**: [RUN](run.md) (an Execution reaches a `requires_approval` step).
- **Surfaces downstream**: [RUN](run.md) (on `approve E-<id>` → `resumeApproved` returns the Execution to RUN to continue at `step_index+1`); [AUDIT](audit.md) (every emitted event persisted).

## C4 context

```
[RUN dispatches step[i]]
        |
        v
step.requires_approval=true?
        |
        yes
        v
[GATE: emit step_paused + approval_requested]
        |
        v
[Persist: user-kit/pending-approvals/E-<id>.json]
        |
        +--<-- founder utterance "approve E-<id>"  --> emit approval_granted --> [RUN resumes at step_index+1]
        |
        +--<-- founder utterance "reject E-<id> <reason>" --> emit approval_denied --> [Execution terminates state=failed]
        |
        +--<-- re-fire on resolved --> emit approval_already_handled (idempotent)
        |
        v
[AUDIT JSONL]
```

GATE is a passive surface — it does not poll; it persists a pending row and waits for the founder utterance to arrive via the H-Sutra bus or CLI. The single-founder approval authority follows Q5 (ratified 2026-05-09).

## References

- `NATIVE-ENGINE.md` §14.7 row "GATE"
- `NATIVE-ENGINE.md` §2.6 ExecutionResult state enum (includes `awaiting_approval`, `paused`)
- `NATIVE-ENGINE.md` §3.1 `NativeEngine.resumeApproved(execId)`
- `NATIVE-ENGINE.md` §3.2 rows 7, 15-18
- `NATIVE-ENGINE.md` §3.4 Approval utterances
- `NATIVE-ENGINE.md` §6.6 Approval ledger
- `NATIVE-ENGINE.md` I-4 + I-15
- `NATIVE-ENGINE.md` §8 OS-15 (multi-party approval future)
- ADR-009 (Approval primitive)
- `../surfaces/run.md`
- `../surfaces/audit.md`
- `../primitives/approval.md` + `../primitives/execution-result.md`
- `../open-questions/Q5-multi-party-approval.md`
