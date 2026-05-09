---
part-id: RUN
bucket: surfaces
template: L9-surface-spec
parity-source: §14.7 + §3.1 + §3.2 #2-#6 + §5.1 + §6.5
parity-source-sha256: e8ac7b5311f9e6bb8555ee65b920b753097b769b531bef69eef5946f76dc8db3
status: DRAFT v1
authored: 2026-05-09
---

# Surface: RUN

## Purpose

Fire a matched Workflow → dispatch each WorkflowStep → for `action='invoke_host_llm'` steps, hand the prompt to the configured host (`claude --bare` or `codex exec`) → persist a typed Execution log.

Canon: §14.7 row 2 — *"RUN | Fire matched Workflow → host-LLM executes step"*.

## Interface (operator-facing)

Operators reach RUN by two paths:

| Path | API | Source |
|---|---|---|
| Via ROUTE matched-workflow | `NativeEngine.run(workflowId, ctx)` invoked from `handleHSutraEvent` | §3.1 |
| Via CLI | `sutra-native run <workflow-id>` | §3.3 |

Inputs: `workflowId` (Workflow.id, W-hash, §2.3), `RunContext` (carries `tenant_context`, `trigger_event`, agent_identity per §2.6 + §3.1).

Return: `ExecutionResult` (§2.6) — terminal state ∈ `{success, failed, awaiting_approval, paused, declared_gap}`. `awaiting_approval` and `paused` are non-terminal-but-returned (Execution persists; GATE surface picks up).

## Invariants (must always hold)

| # | Invariant | Source |
|---|---|---|
| RUN-I1 | Every fired Workflow emits exactly one `workflow_started` event at run begin. | §3.2 row 2 |
| RUN-I2 | Every step dispatch emits exactly one `step_started` and (on completion) one of `step_completed` / `step_paused` / step_failed. | §3.2 rows 5-7 |
| RUN-I3 | Terminal Execution emits exactly one of `workflow_completed` / `workflow_failed` / `workflow_rollback_complete` / `workflow_rollback_partial`. (Per canon I-14: exact terminal-event set; rollback_started is NOT terminal.) | §3.2 rows 3-4 + 19-23 + I-14 |
| RUN-I4 | `WorkflowStep.action='invoke_host_llm'` requires `host ∈ {claude, codex}` AND `prompt_template` non-null. | §2.4 invariants |
| RUN-I5 | `ExecutionResult.failure_reason` is null IFF state ∈ {success, declared_gap}. | I-4 §2.6 |
| RUN-I6 | `failure_policy` ∈ `{rollback, escalate, pause, abort, continue}` — exactly one routes a step failure. | §6.5 + ADR-011 |
| RUN-I7 | Per-step `timeout_ms` defaults to host-class default when null: 60s for `claude --bare`; ≥300s expected for complex codex tasks per §6.7. | §6.7 |

Canon gap: §3.1 declares `NativeEngine.on_host_llm_result(execId, stepIdx, r)` (§8 OS-1 wire) as the resumption callback after host-LLM returns, but the exact wire is open per §8 OS-1. RUN's contract for awaiting that callback is implementation-shaped, not canon-shaped — flagged in OS-1.

## Integration points

- **Primitives consumed**: [`Workflow`](../primitives/workflow.md), [`Step`](../primitives/step.md), [`ExecutionResult`](../primitives/execution-result.md), [`Tenant`](../primitives/tenant.md) (for tenant_context), [`DecisionProvenance`](../primitives/decision-provenance.md) (emitted per step + policy decision).
- **Events emitted**:
  - [`workflow_started`](../events/workflow_started.md) (#2)
  - [`workflow_completed`](../events/workflow_completed.md) (#3)
  - [`workflow_failed`](../events/workflow_failed.md) (#4)
  - [`step_started`](../events/step_started.md) (#5)
  - [`step_completed`](../events/step_completed.md) (#6)
  - [`precondition_check`](../events/precondition_check.md) (#10) at workflow entry (ADR-012)
  - [`postcondition_check`](../events/postcondition_check.md) (#11) at workflow exit
  - [`artifact_registered`](../events/artifact_registered.md) (#9) when a step produces an Asset
  - [`workflow_rollback_started`](../events/workflow_rollback_started.md) (#19), [`step_compensated`](../events/step_compensated.md) (#20), [`step_compensation_failed`](../events/step_compensation_failed.md) (#21), [`workflow_rollback_complete`](../events/workflow_rollback_complete.md) (#22), [`workflow_rollback_partial`](../events/workflow_rollback_partial.md) (#23) — for `failure_policy='rollback'`
  - [`workflow_escalated`](../events/workflow_escalated.md) (#24) — for `failure_policy='escalate'`
  - [`commitment_broken`](../events/commitment_broken.md) (#25) — when workflow failure misses an L4-COMMITMENT obligation
- **Events consumed**: `routing_decision` (#1) from ROUTE (the matched routing decision is the trigger that calls `NativeEngine.run`). Host-LLM result returns asynchronously via `on_host_llm_result` (§8 OS-1).
- **Surfaces upstream**: [ROUTE](route.md) (matched-workflow path).
- **Surfaces downstream**: [GATE](gate.md) (when a step has `requires_approval=true` — RUN emits `step_paused` and hands to GATE; resumption via `NativeEngine.resumeApproved`); [AUDIT](audit.md) (every emitted event persisted).

## C4 context

```
[ROUTE matched workflow] --> [RUN: NativeEngine.run(wfId, ctx)]
                                      |
                                      v
                              [LiteExecutor.executeWorkflow]
                                      |
                       step[i].action='invoke_host_llm'
                                      |
                                      v
                              [host-LLM dispatch]
                                |          |
                       claude --bare    codex exec
                                |          |
                                v          v
                              [on_host_llm_result]
                                      |
                       step.requires_approval? --yes--> [GATE]
                                      |
                                      no
                                      v
                              [step_completed]
                                      |
                                      v
                              [workflow_completed | _failed | _rollback_*]
                                      |
                                      v
                              [AUDIT JSONL]
```

RUN executes within the Native daemon. The host-LLM session is the effector boundary (§5.1) — file/git/network mutations declared in the Workflow happen there, not in Native. Native persists EngineEvents; the host writes the actual side effects.

## References

- `NATIVE-ENGINE.md` §14.7 row "RUN"
- `NATIVE-ENGINE.md` §2.3 Workflow + §2.4 WorkflowStep + §2.6 ExecutionResult
- `NATIVE-ENGINE.md` §3.1 `NativeEngine.run` + `LiteExecutor.executeWorkflow` + `on_host_llm_result`
- `NATIVE-ENGINE.md` §3.2 rows 2-6, 9-11, 19-25
- `NATIVE-ENGINE.md` §5.1 host-llm effector boundary (ADR-004, ADR-005)
- `NATIVE-ENGINE.md` §6.5 on_failure machinery (ADR-011)
- `NATIVE-ENGINE.md` §6.7 per-step timeout
- `NATIVE-ENGINE.md` §8 OS-1 (host-LLM wire — partially open)
- `NATIVE-ENGINE.md` I-14 terminal-event set
- `../surfaces/route.md`
- `../surfaces/gate.md`
- `../surfaces/audit.md`
- `../primitives/workflow.md` + `../primitives/step.md` + `../primitives/execution-result.md`
