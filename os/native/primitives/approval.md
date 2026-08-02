---
part-id: Approval
bucket: primitives
template: L9-primitive-spec
parity-source: ADR-009 + §3.2 events #15-#18 + §3.4 + §6.6 + I-14 + I-15
parity-source-sha256: 3473e5bf017c6dec02678caf985f8bf48d0b7f509f880705c4a4e74ff2512057
status: DRAFT v1
authored: 2026-05-09
---

# Approval

## Purpose

The Approval primitive is the runtime gate that pauses Workflow Executions at `requires_approval=true` steps (or Workflow-level approval) until the founder utters `approve E-<id>` or `reject E-<id> <reason>`. The Approval primitive is the contract for the pending-approvals ledger row (per ADR-009 + I-15), the four typed events covering its lifecycle (`approval_requested` #15, `approval_granted` #16, `approval_denied` #17, `approval_already_handled` #18), and the resumption path through `NativeEngine.resumeApproved(execId)` (§3.1).

**Canon-derivation note (per F2)**: Approval is NOT enumerated as a standalone primitive in NATIVE-ENGINE.md §2.1-§2.9. The §2 primitive set covers Domain / Charter / Workflow / WorkflowStep / TriggerSpec / ExecutionResult / EngineEvent / Tenant / DecisionProvenance — Approval is absent. This part-file documents Approval as a CANON-DERIVED primitive whose specification is composed from:
- **ADR-009** — "Approval Gate as Workflow-Level Primitive" (the originating decision).
- **§3.2 events #15-#18** — the four typed lifecycle events.
- **§3.4** — the operator utterances `approve E-<id>` / `reject E-<id> <reason>`.
- **§6.6 Approval ledger** — the persistence shape at `user-kit/pending-approvals/E-<id>.json`.
- **I-14 + I-15** — the terminal-event status of `approval_requested` and the ledger-row existence requirement.

A future ADR may elevate Approval to a §2-listed primitive (likely §2.10) if its surface grows past the current ledger-row + utterance-parse shape. Until then, this part-file flags the gap explicitly per the source-fidelity F2 rule and does NOT invent fields beyond canon.

## Type signature (TypeScript-style)

```typescript
type Approval = {
  // Ledger row schema per §6.6
  execution_id: string;       // E-<hash> — the paused Execution
  workflow_id: string;        // W-<hash> — the parent Workflow
  step_index: number;         // the Step where the gate fired (per ADR-009 step-level + workflow-level scopes)
  ts_ms: number;              // ts of approval_requested emit; monotonic
  prompt_summary: string;     // a summary of what is being approved (per §6.6 payload)
};

// Resolution utterances (per §3.4) — these are HSutraEvents the Router maps to Approval state transitions:
type ApprovalUtterance =
  | { kind: 'approve_execution'; execution_id: string }   // 'approve E-<id>'
  | { kind: 'approve_proposal';  proposal_id: string }    // 'approve P-<id>' (pattern-emergence; see ADR-010 — DISTINCT from Execution approval)
  | { kind: 'reject_execution';  execution_id: string; reason: string };  // 'reject E-<id> <reason>'

// Lifecycle events (per §3.2 #15-#18) — Approval state is derivable from this sequence:
type ApprovalEvent =
  | { event_type: 'approval_requested';  payload: { execution_id, step_index, prompt_summary } }   // #15 TERMINAL per I-14 (Execution → awaiting_approval)
  | { event_type: 'approval_granted';    payload: { execution_id, approver_id } }                  // #16
  | { event_type: 'approval_denied';     payload: { execution_id, reason } }                       // #17
  | { event_type: 'approval_already_handled'; payload: { execution_id, prior_outcome } };          // #18 idempotent re-fire
```

## Invariants (must hold)

- **I-14 (approval_requested is terminal)**: `approval_requested` (§3.2 #15) is one of THREE terminal EngineEvents for a Workflow Execution. It transitions the Execution to state `awaiting_approval`. (NATIVE-ENGINE.md §4.)
- **I-15 (ledger row existence)**: every Execution in `awaiting_approval` MUST have a persisted ledger row at `user-kit/pending-approvals/E-<id>.json` carrying `{workflow_id, step_index, ts_ms, prompt_summary}` (NATIVE-ENGINE.md §4 + ADR-009 + §6.6). Hardstop on absence.
- **Idempotent re-fire (event #18)**: when an Execution that is no longer in `awaiting_approval` receives a resolution utterance, `approval_already_handled` (§3.2 #18) emits carrying `prior_outcome`. Resolution is one-shot.
- **Single-founder approval (v1 — Q5 ratified 2026-05-09)**: v1 ships with single-founder approval. Multi-party quorum is deferred to v2+ per OS-15 / Q5. (NATIVE-ENGINE.md §8 OS-15; §14.10 Q5.)
- **Utterance grammar (§3.4)**: the only resolution utterances are `approve E-<id>`, `reject E-<id> <reason>`, and (DISTINCT) `approve P-<id>` for proposed Workflows (ADR-010, NOT this primitive's domain).
- **Resumption invariant**: `NativeEngine.resumeApproved(execId)` continues at `step_index+1` of the original Execution (per §6.6). Whether resumption mutates the original Execution or mints a child Execution with `parent_exec_id` is NOT explicitly specified in canon — runtime implementation choice (future ADR may codify).
- **F-3 fail-mode discipline**: when a Step with `requires_approval=true` is reached, LiteExecutor MUST pause (emit #15) before dispatching the action — fail-CLOSED. No fail-open invention.

## Lifecycle (created → terminal states)

1. **Gate reached**: LiteExecutor reaches a Step (or Workflow) with `requires_approval=true`. BEFORE dispatching the action, it:
   - Persists ledger row at `user-kit/pending-approvals/E-<id>.json` (per I-15 + §6.6).
   - Emits `approval_requested` (§3.2 #15) — this is TERMINAL per I-14 for the parent Execution.
   - Transitions Execution state → `awaiting_approval`.
2. **Awaiting (Execution state = awaiting_approval)**: the Execution is pinned at this state. Router watches for the resolution utterance.
3. **Resolution path A — approve**: founder utters `approve E-<id>`; Router parses (per §3.4) → emits `approval_granted` (§3.2 #16) → `NativeEngine.resumeApproved(execId)` continues at `step_index+1`. Note: resumption emits a NEW `workflow_started` for the continued Execution (or continues the same one, per runtime); the original Execution's I-14 terminal remains `approval_requested`.
4. **Resolution path B — reject**: founder utters `reject E-<id> <reason>`; Router emits `approval_denied` (§3.2 #17). The Execution then routes per `Workflow.failure_policy` (typically `abort` or `escalate`) to its FINAL terminal (`workflow_failed`). Note: the Execution emitted `approval_requested` first (one I-14 terminal); the subsequent `workflow_failed` is a SECOND apparent terminal. Canon I-14 says "exactly one terminal" — this tension is resolved by canon's intent: `approval_requested` is the terminal of the ORIGINAL Execution; the post-rejection failure terminal is for the RESUMED phase. Exact event-stream semantics for rejected resumption are NOT fully nailed down in canon §3.2; runtime implementation choice (future ADR may clarify).
5. **Idempotent re-fire**: if a resolution utterance arrives for an Execution that already resolved (granted OR denied), `approval_already_handled` (§3.2 #18) emits carrying `prior_outcome`. The Approval ledger row is removed on first resolution.
6. **Terminal**: Approval has no separate "terminal state" beyond the resolution event (`approval_granted` | `approval_denied`) and the ledger-row removal. The PARENT Execution's terminal per I-14 is `approval_requested` (one terminal); subsequent post-resolution events are part of a logically continuous Execution.

## Serialization (JSONL row shape)

**Ledger row** (per §6.6) — one JSON file per pending Execution:

```jsonl
// ~/.sutra-native/user-kit/pending-approvals/E-<hash>.json
{"execution_id":"E-<hash>","workflow_id":"W-<hash>","step_index":2,"ts_ms":1715299215000,"prompt_summary":"Step 2 will write 3 files in holding/departments/; approve to proceed."}
```

Ledger rows are removed upon resolution (first `approval_granted` or `approval_denied`). Subsequent re-fire utterances find no ledger row and emit `approval_already_handled` (#18).

**Lifecycle events** (per §3.2 #15-#18) — append-only JSONL rows in the Execution's event log and in the global `events.jsonl`:

```jsonl
{"event_type":"approval_requested","ts_ms":1715299215000,"execution_id":"E-<hash>","payload":{"execution_id":"E-<hash>","step_index":2,"prompt_summary":"..."},"agent_identity":{...}}
{"event_type":"approval_granted","ts_ms":1715299300000,"execution_id":"E-<hash>","payload":{"execution_id":"E-<hash>","approver_id":"founder"},"agent_identity":{...}}
```

## Cross-primitive references

- **Workflow** (`../primitives/workflow.md`): `Workflow.requires_approval` declares a Workflow-level gate; ADR-009.
- **WorkflowStep** (`../primitives/step.md`): `WorkflowStep.requires_approval` declares a step-level gate; ADR-009.
- **ExecutionResult** (`../primitives/execution-result.md`): `ExecutionResult.state === 'awaiting_approval'` is the paused state; resumed via `NativeEngine.resumeApproved` per §3.1.
- **EngineEvent** (`../primitives/engine-event.md`): events #15-#18 are the typed lifecycle of an Approval.
- **DecisionProvenance** (`../primitives/decision-provenance.md`): every approval grant/deny emits a DecisionProvenance row with `outcome ∈ {allow, deny}` per I-7.
- **Tenant** (`../primitives/tenant.md`): cross-tenant Workflow execution may require Tenant-owner approval (per ADR-006 ACL rules) — Approval ledger may carry a Tenant scope in such cases (NOT explicitly specified in canon; runtime implementation choice).

## References

- NATIVE-ENGINE.md §2 — explicitly NOT listed in §2.1-§2.9 (canon-derivation per F2; see top of file).
- NATIVE-ENGINE.md §3.2 events #15-#18 — Approval lifecycle.
- NATIVE-ENGINE.md §3.4 — approval utterances grammar.
- NATIVE-ENGINE.md §6.6 — approval ledger persistence.
- NATIVE-ENGINE.md §4 — I-14 (terminal-event uniqueness), I-15 (ledger-row existence).
- NATIVE-ENGINE.md §8 OS-15 — multi-party approval (deferred to v2+).
- NATIVE-ENGINE.md §14.10 Q5 — single-founder approval ratified 2026-05-09.
- ADR-009 — Approval Gate as Workflow-Level Primitive.
- ADR-010 — pattern emergence + `approve P-<id>` (DISTINCT proposal-approval flow).
- ADR-015 — agent_identity chain for approver attribution.
