---
part-id: ExecutionResult
bucket: primitives
template: L9-primitive-spec
parity-source: §2.6
parity-source-sha256: 62ae64d11dbd52dfe0aba5f2473e44699dfa045e65062fff786a461d2ab21140
status: DRAFT v1
authored: 2026-05-09
---

# ExecutionResult

## Purpose

The ExecutionResult primitive is the runtime instantiation of a Workflow — a content-addressed `E-<hash>` row that captures the trigger that fired it, the running/terminal state, the append-only EngineEvent log, the per-step results, the parent/sibling lineage, the failure reason (when failed), the agent_identity chain (ADR-015), the tenant_context (ADR-006), and a `partial` flag for `failure_policy='continue'` semantics. Every founder-meaningful change to the system flows through some ExecutionResult; ExecutionResult IS the audit trail (NATIVE-ENGINE.md §2.6).

## Type signature (TypeScript-style)

```typescript
type ExecutionResult = {
  id: string;                          // E-hash — content-addressed
  workflow_id: string;                 // references parent Workflow
  trigger_event: object;               // the EngineEvent that initiated this Execution
  state: 'running' | 'success' | 'failed' | 'awaiting_approval' | 'paused' | 'declared_gap';
  logs: EngineEvent[];                 // append-only
  results: object;                     // per-step outputs (keyed by step_index)
  parent_exec_id: string | null;       // child Execution lineage
  sibling_group: string | null;        // sibling Execution lineage (fan_out group)
  failure_reason: string | null;       // null IFF state ∈ {success, declared_gap} (I-4)
  agent_identity: object;              // chain-shaped per OQ-D4-2; inferred per ADR-015
  tenant_context: object;              // { tenant_id }; required for cross-tenant ops (ADR-006)
  partial: boolean;                    // true when failure_policy='continue' advanced past failure
};
```

## Invariants (must hold)

- **Content-addressed id**: `id = sha256(canonical_form(execution))`. Computed at start of run; immutable.
- **State enum**: `state` MUST be one of the 6-set `{running, success, failed, awaiting_approval, paused, declared_gap}` (NATIVE-ENGINE.md §2.6).
- **I-4 (failure_reason discipline)**: `failure_reason === null` IFF `state ∈ {success, declared_gap}`. For `running`/`awaiting_approval`/`paused`/`failed`, failure_reason MAY be set (must be set for `failed`). HARD-checked at terminal_check.
- **I-14 (exactly one terminal event)**: every Execution emits EXACTLY ONE terminal EngineEvent from `{workflow_completed, workflow_failed, approval_requested}` (the last transitions state to `awaiting_approval`). Rollback events are recovery transitions and are NOT terminal.
- **I-15 (approval ledger)**: when `state === 'awaiting_approval'`, a persisted ledger row at `user-kit/pending-approvals/E-<id>.json` MUST exist (ADR-009).
- **I-7 (DecisionProvenance emit)**: every Execution emits ≥1 DecisionProvenance per consequential decision.
- **I-8 (tenant boundary)**: `tenant_context.tenant_id` MUST be non-null when crossing tenants; cross-tenant ops without an explicit `delegates_to` edge are HS-3 violations.
- **Append-only logs**: `logs[]` is append-only — never edit, never delete past events. Replay-safe.
- **Partial flag (F-3 semantics)**: `partial=true` ONLY when `Workflow.failure_policy === 'continue'` and the Execution advanced past a failed Step.

## Lifecycle (created → terminal states)

Per canon I-14, every Execution emits EXACTLY ONE terminal event from `{workflow_completed, workflow_failed, approval_requested}`. Rollback events (`workflow_rollback_started` → `workflow_rollback_complete` | `workflow_rollback_partial`) are RECOVERY transitions occurring AFTER `workflow_failed` under `failure_policy='rollback'` — NOT terminal themselves.

1. **Instantiated**: TriggerSpec fires OR `NativeEngine.run(workflow_id, ctx)` called; LiteExecutor mints `E-<hash>`; state → `running`; `workflow_started` (§3.2 #2) appends to logs.
2. **Precondition check**: `precondition_check` (§3.2 #10) per Workflow.preconditions; on fail, state → `failed` with failure_reason, emits `workflow_failed` (§3.2 #4) — terminal.
3. **Step dispatch loop**: each Step emits `step_started`/`step_completed`/`step_paused` into logs[]; results[step_index] populated.
4. **Approval pause (if Step.requires_approval=true)**: state → `awaiting_approval`; emits `approval_requested` (§3.2 #15) — TERMINAL per I-14; persists ledger row per I-15. Subsequent `approve E-<id>` utterance → `NativeEngine.resumeApproved` instantiates a NEW Execution (lineage via parent_exec_id) OR continues this one — exact resumption semantics covered in approval primitive.
5. **Postcondition check**: on Step exhaustion, `postcondition_check` (§3.2 #11) per Workflow.postconditions; on pass, state → `success`, emits `workflow_completed` (§3.2 #3) — terminal.
6. **Failure path**: any Step failure routes per `Step.on_failure` (defaults to `Workflow.failure_policy`):
   - `abort` → state → `failed`, emits `workflow_failed` (terminal).
   - `escalate` → emits `workflow_escalated` (§3.2 #24), state typically `failed` (terminal).
   - `rollback` → emits `workflow_failed` (terminal) THEN recovery events (§3.2 #19-#23) — recovery is post-terminal.
   - `pause` → state → `paused`, emits `step_paused` (§3.2 #7) — NOTE: `paused` is a non-terminal Execution state; canon §2.6 lists it as a valid state but I-14 enumerates terminal events only as {`workflow_completed`, `workflow_failed`, `approval_requested`}. Resumption semantics for `paused` distinct from `awaiting_approval` are NOT fully specified in canon; runtime implementation choice.
   - `continue` → state stays `running`, sets `partial=true`, proceeds to next Step.
7. **Declared gap**: state → `declared_gap` when Workflow declares it cannot complete and explicitly logs the gap; per I-4 failure_reason is null. (Specific event-type for declared_gap NOT in §3.2's 26-event catalog; runtime implementation choice — likely a typed DecisionProvenance row, future ADR may add an event.)

## Serialization (JSONL row shape)

User-kit registry rows at `~/.sutra-native/user-kit/executions/E-<hash>.json` (single Execution JSON per file). Live append-only log embedded as `logs[]` or split into adjacent `~/.sutra-native/user-kit/executions/E-<hash>.events.jsonl`:

```jsonl
{"id":"E-<hash>","workflow_id":"W-<hash>","trigger_event":{...},"state":"running","ts_started_ms":<unix-ms>,"agent_identity":{...},"tenant_context":{"tenant_id":"T-<hash>"},"partial":false}
```

Per-Execution event log (one JSONL line per EngineEvent, append-only):

```jsonl
{"event_type":"workflow_started","ts_ms":<unix-ms>,"execution_id":"E-<hash>","payload":{...},"agent_identity":{...}}
{"event_type":"step_started","ts_ms":<unix-ms>,"execution_id":"E-<hash>","payload":{"step_index":0,...},"agent_identity":{...}}
{"event_type":"workflow_completed","ts_ms":<unix-ms>,"execution_id":"E-<hash>","payload":{"results_ref":"..."},"agent_identity":{...}}
```

## Cross-primitive references

- **Workflow** (`../primitives/workflow.md`): `workflow_id` references the parent Workflow; Execution is the runtime instance.
- **WorkflowStep** (`../primitives/step.md`): each Step dispatch generates entries in `logs[]` and `results[step_index]`.
- **EngineEvent** (`../primitives/engine-event.md`): `logs[]` is an append-only sequence of EngineEvents; terminal event per I-14.
- **Approval** (`../primitives/approval.md`): state `awaiting_approval` triggers approval ledger flow per ADR-009 + I-15.
- **Tenant** (`../primitives/tenant.md`): `tenant_context.tenant_id` binds the Execution to a Tenant; I-8 enforces boundary.
- **DecisionProvenance** (`../primitives/decision-provenance.md`): every consequential decision in the Execution emits a DecisionProvenance row per I-7.

## References

- NATIVE-ENGINE.md §2.6 — canonical ExecutionResult field table.
- NATIVE-ENGINE.md §4 — I-4, I-7, I-8, I-14, I-15.
- NATIVE-ENGINE.md §3.2 — full 26-event catalog (Execution lifecycle events #2-#7, #10-#11, #15-#24).
- NATIVE-ENGINE.md §3.1 — `NativeEngine.run`, `NativeEngine.resumeApproved`, `LiteExecutor.executeWorkflow` signatures.
- ADR-006 — multi-tenant isolation + tenant_context.
- ADR-009 — approval gate primitive.
- ADR-011 — failure_policy enum.
- ADR-015 — agent_identity chain.
