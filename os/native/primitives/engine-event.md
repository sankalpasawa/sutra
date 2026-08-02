---
part-id: EngineEvent
bucket: primitives
template: L9-primitive-spec
parity-source: §2.7
parity-source-sha256: 5a09cfd50fc1957fae14ba83794105a1a689de08412396542e3c0c44c5f07501
status: DRAFT v1
authored: 2026-05-09
---

# EngineEvent

## Purpose

The EngineEvent primitive is Native's append-only typed audit row — one JSONL line per event. EngineEvents form the complete audit trail for Workflows, Executions, Triggers, approvals, rollbacks, pattern emergence, commitments, and tenant boundary violations. The catalog of 26 event_type values is exhaustive (§3.2); every event carries `event_type`, `ts_ms`, `execution_id?`, `payload`, and `agent_identity` (per ADR-015). Persistence is per ADR-013 (NATIVE-ENGINE.md §2.7).

## Type signature (TypeScript-style)

```typescript
type EngineEvent = {
  event_type: EventType;        // enum of 26 values — see §3.2 catalog (exhaustive)
  ts_ms: number;                // monotonic; assigned at emit
  execution_id: string | null;  // null for events outside an Execution (e.g. routing_decision pre-match)
  payload: object;              // type-specific; validated against per-event schema
  agent_identity: object;       // per ADR-015 — inferred chain
};

type EventType =
  | 'routing_decision'           // #1
  | 'workflow_started'           // #2  (terminal-eligible parent — see I-14)
  | 'workflow_completed'         // #3  TERMINAL per I-14
  | 'workflow_failed'            // #4  TERMINAL per I-14
  | 'step_started' | 'step_completed' | 'step_paused'  // #5-#7
  | 'policy_decision'            // #8
  | 'artifact_registered'        // #9
  | 'precondition_check' | 'postcondition_check'  // #10-#11
  | 'pattern_proposed' | 'proposal_approved' | 'proposal_rejected'  // #12-#14
  | 'approval_requested'         // #15 TERMINAL per I-14 (transitions to awaiting_approval)
  | 'approval_granted' | 'approval_denied' | 'approval_already_handled'  // #16-#18
  | 'workflow_rollback_started' | 'step_compensated' | 'step_compensation_failed'  // #19-#21 (recovery, NOT terminal)
  | 'workflow_rollback_complete' | 'workflow_rollback_partial'  // #22-#23 (recovery, NOT terminal)
  | 'workflow_escalated'         // #24
  | 'commitment_broken'          // #25
  | 'tenant_boundary_violation'; // #26
```

## Invariants (must hold)

- **Exhaustive enum**: `event_type` MUST be one of the 26 listed values in §3.2. New event-types require a NATIVE-ENGINE.md amendment + ADR. Mint-time reject on unknown event_type.
- **Monotonic ts_ms**: `ts_ms` is monotonic (assigned at emit). Replay safety depends on this — events MUST NOT be re-ordered by ts_ms after persistence.
- **Append-only**: once persisted, an EngineEvent row is immutable — no edit, no delete. Replay derives full state from the log.
- **Per-event payload schema**: `payload` is validated against the per-event-type schema declared in §3.2's "Key payload fields" column. Mint-time reject on schema violation.
- **agent_identity per ADR-015**: every EngineEvent carries an `agent_identity` chain (parent → child) per ADR-015.
- **I-14 (terminal-event uniqueness)**: exactly ONE of `{workflow_completed, workflow_failed, approval_requested}` is emitted per Execution. Recovery events (`workflow_rollback_*`, `step_compensated`, `step_compensation_failed`) are POST-terminal transitions; they do NOT count as additional terminals.
- **I-16 (commitment_broken referential integrity)**: every `commitment_broken` event references a Charter obligation id that resolves in the registry.
- **I-9 + I-17 (policy decisions)**: `policy_decision` events MUST carry `policy_id` AND `policy_version` (F-8 forbidden coupling avoidance).
- **null execution_id rule**: `execution_id === null` is valid ONLY for events outside an Execution lifecycle — e.g. `routing_decision` BEFORE a Workflow is selected. Once dispatched, all subsequent events MUST carry the resolved `execution_id`.

## Lifecycle (created → terminal states)

EngineEvents have no lifecycle beyond emit-and-persist — they are inert immutable rows. The lifecycle is at the producer/consumer level:

1. **Emit**: a producer (Router, LiteExecutor, CadenceScheduler, PolicyDispatcher, Pattern detector) calls into the persistence layer with a typed event.
2. **Schema validation**: persistence layer validates `event_type` enum + per-event payload schema + monotonic ts_ms.
3. **Persist (per ADR-013)**: append JSONL row to the appropriate sink — Execution-scoped log at `~/.sutra-native/user-kit/executions/E-<hash>.events.jsonl`, or global sink at `~/.sutra-native/user-kit/events.jsonl`, or DecisionProvenance sink. fsync-on-write per ADR-013 durability requirement.
4. **Consumed**: replay, audit, telemetry-sink fan-out (§5.6), H-Sutra event bus (§5.3) consume the events read-only.
5. **Terminal**: an EngineEvent row is its own terminal — once persisted it is final. No state transitions.

Note: I-14's terminal-event set applies to the PARENT Execution, not to EngineEvent itself. EngineEvents are the substrate that PROVES which terminal an Execution reached.

## Serialization (JSONL row shape)

Per ADR-013, every EngineEvent is one JSONL line. Per-Execution event log:

```jsonl
{"event_type":"workflow_started","ts_ms":1715299200000,"execution_id":"E-abc123","payload":{"workflow_id":"W-def456","trigger_event_id":"<uuid>"},"agent_identity":{"chain":["founder","claude-bare-pid-1234"]}}
{"event_type":"step_completed","ts_ms":1715299205000,"execution_id":"E-abc123","payload":{"step_index":0,"output_ref":"DataRef:abc","duration_ms":5000},"agent_identity":{...}}
{"event_type":"workflow_completed","ts_ms":1715299210000,"execution_id":"E-abc123","payload":{"results_ref":"..."},"agent_identity":{...}}
```

Sinks:
- `~/.sutra-native/user-kit/executions/E-<hash>.events.jsonl` — per-Execution
- `~/.sutra-native/user-kit/events.jsonl` — global append-only log (replay source)
- `~/.sutra-native/user-kit/decision-provenance.jsonl` — DecisionProvenance subset (those carrying policy_id)

## Cross-primitive references

- **ExecutionResult** (`../primitives/execution-result.md`): `ExecutionResult.logs[]` is a sequence of EngineEvents; terminal event per I-14 dictates Execution terminal state.
- **Workflow** (`../primitives/workflow.md`): 6 of 26 event types directly reference Workflow (#2, #3, #4, #19, #22, #23).
- **WorkflowStep** (`../primitives/step.md`): Step lifecycle emits #5-#7 + recovery #20-#21.
- **Trigger** (`../primitives/trigger.md`): every Trigger match emits #1 `routing_decision`.
- **Charter** (`../primitives/charter.md`): event #25 `commitment_broken` references Charter obligations per I-16.
- **Tenant** (`../primitives/tenant.md`): event #26 `tenant_boundary_violation` (HS-3) on illegal cross-tenant ops.
- **Approval** (`../primitives/approval.md`): events #15-#18 cover the approval flow.
- **DecisionProvenance** (`../primitives/decision-provenance.md`): #8 `policy_decision` is the primary DecisionProvenance carrier.

## References

- NATIVE-ENGINE.md §2.7 — canonical EngineEvent field table.
- NATIVE-ENGINE.md §3.2 — full 26-event catalog with payload fields.
- NATIVE-ENGINE.md §4 — I-9, I-14, I-16, I-17.
- ADR-013 — persistence + fsync semantics.
- ADR-015 — agent_identity chain.
- F-8 — forbidden coupling: policy_decision without policy_id+policy_version.
