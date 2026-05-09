---
part-id: WorkflowStep
bucket: primitives
template: L9-primitive-spec
parity-source: §2.4
parity-source-sha256: 11ac619c437926706e16f60e97316720758e6007cdd749a9c25510fb0f8a3ba3
status: DRAFT v1
authored: 2026-05-09
---

# WorkflowStep

## Purpose

The WorkflowStep primitive is the smallest unit of dispatchable work inside a Workflow's `step_graph`. Each Step is either a `skill_ref` (named pre-registered Skill) XOR an `action` (one of the registered action kinds: `invoke_host_llm`, `emit_event`, etc.) — never both (I-3). Steps carry typed inputs/outputs (DataRef-shaped with `authoritative_status` per ADR-008), an optional per-step `on_failure` override, a step-level `requires_approval` gate, an optional `timeout_ms`, and when the action is `invoke_host_llm`, a required `host` (claude or codex per ADR-005) and `prompt_template` (NATIVE-ENGINE.md §2.4).

## Type signature (TypeScript-style)

```typescript
type WorkflowStep = {
  skill_ref: string | null;          // XOR with action (I-3); references a Skill Workflow
  action: ActionKind | null;         // one of registered action kinds (e.g. 'invoke_host_llm', 'emit_event')
  host: 'claude' | 'codex' | null;   // required IFF action === 'invoke_host_llm' (ADR-005)
  inputs: DataRef[];                 // each carries schema_ref + authoritative_status (ADR-008)
  outputs: (DataRef | Asset)[];      // typed; sink rules per §6 Operations
  on_failure: FailurePolicy;         // one of {rollback, escalate, pause, abort, continue}; defaults to Workflow.failure_policy
  requires_approval: boolean;        // step-level approval gate (ADR-009)
  timeout_ms: number | null;         // per-step override; flows into host activity args
  prompt_template: string | null;    // required IFF action === 'invoke_host_llm'
};
```

## Invariants (must hold)

- **I-3 (skill_ref XOR action)**: every Step has `skill_ref` XOR `action` — exactly one is non-null. F-4 + F-5 forbid both-null and both-non-null. Mint-time HARD reject (NATIVE-ENGINE.md §4 + §2.4).
- **host requirement**: `host` is required IFF `action === 'invoke_host_llm'`; one of `claude` or `codex` per ADR-005. `host=null` for non-host-llm actions; rejected otherwise.
- **prompt_template requirement**: `prompt_template` is required IFF `action === 'invoke_host_llm'`; null for non-host-llm actions.
- **on_failure inheritance**: when `on_failure` is unset on the Step, it defaults to the parent `Workflow.failure_policy` (NATIVE-ENGINE.md §2.4 row `on_failure`). Same enum-of-5 as Workflow per ADR-011.
- **F-3 fail-mode discipline**: Step `on_failure` follows canon HS-1..HS-8 semantics — no fail-open invention (F3 source-fidelity rule). If the parent Workflow's `failure_policy` is `pause`, the Step's default `on_failure` is `pause`.
- **DataRef authoritative_status**: every `inputs[i]` and `outputs[i]` MUST carry `schema_ref` and `authoritative_status` per ADR-008.

## Lifecycle (created → terminal states)

A Step is dispatched within an Execution's running phase and emits step-level events:

1. **Dispatched**: parent Execution enters Running state (per Workflow.workflow_started, §3.2 #2); LiteExecutor calls `step_started` (§3.2 #5) carrying `step_index`, `host?`, `timeout_ms`.
2. **Approval gate (if requires_approval=true)**: LiteExecutor pauses BEFORE dispatching the action; emits `approval_requested` (§3.2 #15); persists ledger row at `user-kit/pending-approvals/E-<id>.json` (I-15); Execution state → `awaiting_approval`. Resume via `approve E-<id>` utterance → `NativeEngine.resumeApproved(execId)` → continue at this step.
3. **Action / skill dispatch**: `invoke_host_llm` spawns host subprocess; `emit_event` writes an EngineEvent row; `skill_ref` resolves to a sub-Workflow via SkillEngine.resolve.
4. **Terminal (one of):**
   - **Success** → `step_completed` (§3.2 #6) carrying `output_ref`, `duration_ms`; LiteExecutor advances to next Step.
   - **Failure** → `step_paused` (§3.2 #7) emits when `on_failure='pause'`; otherwise the failure routes per `on_failure` (rollback → §3.2 #19; escalate → #24; abort → terminates Execution with `workflow_failed`; continue → Execution state.partial=true and advances).
   - **Compensation (post-failure, if rollback path)**: `step_compensated` (§3.2 #20) on success or `step_compensation_failed` (§3.2 #21) — these are recovery events, not terminals for the Step itself.

Note: Step terminal-events (`step_completed`, `step_paused`) are NOT in I-14's terminal-event set — I-14 binds the parent Workflow Execution, not individual Steps.

## Serialization (JSONL row shape)

Steps are embedded as JSON array elements inside `Workflow.step_graph`; they do not have a separate registry path. Persisted as part of the parent Workflow at `~/.sutra-native/user-kit/workflows/W-<hash>.json`:

```jsonl
// inside Workflow.step_graph
{"skill_ref":null,"action":"invoke_host_llm","host":"claude","inputs":[...],"outputs":[...],"on_failure":"rollback","requires_approval":false,"timeout_ms":60000,"prompt_template":"<text>"}
```

Step-level events (each a separate JSONL row in `user-kit/decision-provenance.jsonl` and `user-kit/events.jsonl`):

```jsonl
{"event_type":"step_started","ts_ms":<unix-ms>,"execution_id":"E-<hash>","payload":{"step_index":<int>,"host":"claude","timeout_ms":60000},"agent_identity":{...}}
{"event_type":"step_completed","ts_ms":<unix-ms>,"execution_id":"E-<hash>","payload":{"step_index":<int>,"output_ref":"<DataRef>","duration_ms":<int>},"agent_identity":{...}}
```

## Cross-primitive references

- **Workflow** (`../primitives/workflow.md`): parent container; `Workflow.step_graph: WorkflowStep[]`. Step `on_failure` inherits from `Workflow.failure_policy`.
- **ExecutionResult** (`../primitives/execution-result.md`): each Step dispatch generates entries in `ExecutionResult.logs` and `ExecutionResult.results`.
- **EngineEvent** (`../primitives/engine-event.md`): Step lifecycle emits `step_started` (#5), `step_completed` (#6), `step_paused` (#7), and recovery events `step_compensated` (#20) / `step_compensation_failed` (#21).
- **Approval** (`../primitives/approval.md`): Step's `requires_approval=true` triggers the approval ledger flow.
- **DecisionProvenance** (`../primitives/decision-provenance.md`): every consequential Step decision (gate evaluation, on_failure routing) emits a DecisionProvenance row.

## References

- NATIVE-ENGINE.md §2.4 — canonical WorkflowStep field table.
- NATIVE-ENGINE.md §4 — I-3 (skill_ref XOR action).
- NATIVE-ENGINE.md §3.2 #5-#7, #20-#21 — Step lifecycle events.
- ADR-005 — host-LLM hosts (`claude`, `codex`).
- ADR-008 — DataRef + authoritative_status.
- ADR-009 — approval gate (step-level + workflow-level).
- ADR-011 — failure_policy enum (5-set).
