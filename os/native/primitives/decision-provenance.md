---
part-id: DecisionProvenance
bucket: primitives
template: L9-primitive-spec
parity-source: §2.9
parity-source-sha256: 11a8af53176ec2d11f03152ad68f37986ffe0af6f528c01fb81eabc69703c77c
status: DRAFT v1
authored: 2026-05-09
---

# DecisionProvenance

## Purpose

The DecisionProvenance primitive is Native's typed audit row for every consequential decision — Workflow-level, Step-level, Hook-level, Tenant-level, or Cutover-level. Every Workflow / Execution / Hook emits ≥1 DecisionProvenance per consequential decision (I-7). Schema per ADR-007. Each row carries unique uuid id, monotonic ts_ms, agent_identity chain (ADR-015), `policy_id` + `policy_version` (I-9 + I-17 + F-8), scope, outcome, sanitized reason, and typed DataRefs with authoritative_status (ADR-008) — see NATIVE-ENGINE.md §2.9.

## Type signature (TypeScript-style)

```typescript
type DecisionProvenance = {
  id: string;                        // uuid v4 — unique
  ts_ms: number;                     // monotonic
  agent_identity: object;            // chain (parent → child) per ADR-015
  policy_id: string;                 // non-empty (I-9; F-8)
  policy_version: string;            // non-empty (I-9; F-8)
  scope: 'WORKFLOW' | 'STEP' | 'HOOK' | 'TENANT' | 'CUTOVER';
  outcome: 'allow' | 'deny' | 'pause' | 'escalate';
  reason: string;                    // sanitized — no colons, no newlines
  data_refs: DataRef[];              // each with authoritative_status per ADR-008
};
```

## Invariants (must hold)

- **Unique uuid id**: `id` is a uuid v4 — globally unique. Mint-time collision reject (probability vanishingly low; reject on hit nonetheless).
- **Monotonic ts_ms**: `ts_ms` is monotonic at emit. Replay safety depends on this.
- **I-9 + I-17 + F-8 (policy reference)**: `policy_id` AND `policy_version` MUST be non-empty for every DecisionProvenance row. Empty either field is a HARD reject (F-8 forbidden coupling).
- **Scope enum**: `scope` MUST be one of the 5-set `{WORKFLOW, STEP, HOOK, TENANT, CUTOVER}`.
- **Outcome enum**: `outcome` MUST be one of the 4-set `{allow, deny, pause, escalate}`.
- **Reason sanitization**: `reason` MUST NOT contain colons (`:`) or newlines (`\n`) — protects JSONL parsing and downstream sanitizers from format-string injection (NATIVE-ENGINE.md §2.9 row `sanitized (no colons / newlines)`).
- **I-7 (per-Execution emit)**: every Workflow Execution emits ≥1 DecisionProvenance per consequential decision; absence of DecisionProvenance on a consequential decision is itself a F-8-class violation.
- **DataRef authoritative_status (ADR-008)**: every `data_refs[i]` MUST carry `authoritative_status ∈ {authoritative, advisory}`. Readers honor authoritative entries over advisory ones.
- **agent_identity chain (ADR-015)**: `agent_identity` is the chain shape per ADR-015 — parent → child — not a flat identity.

## Lifecycle (created → terminal states)

DecisionProvenance rows are inert immutable records — they have no lifecycle beyond emit-and-persist:

1. **Emit**: PolicyDispatcher.evaluate(scope, evidence) (per §3.1) OR a Workflow / Step / Hook decision site constructs a DecisionProvenance row with uuid id + scope + outcome + reason + data_refs.
2. **Schema validation**: `policy_id` + `policy_version` non-empty (F-8); enum validation on scope + outcome; reason sanitizer check.
3. **Persist (per ADR-013)**: UserKit.appendDecisionProvenance(dp) (§3.1) fsync-writes the row to `~/.sutra-native/user-kit/decision-provenance.jsonl` AND to the owning Tenant's `audit_log_path` (when scope === 'TENANT' or when the decision touches a Tenant).
4. **Terminal**: a DecisionProvenance row is its own terminal — once persisted it is final. No state transitions.

Note: I-14's terminal-event set applies to Execution, not to DecisionProvenance. DecisionProvenance rows are the substrate that proves WHY each decision was made along the way to the Execution's I-14 terminal.

## Serialization (JSONL row shape)

Per ADR-013, every DecisionProvenance row is one JSONL line. Primary sink: `~/.sutra-native/user-kit/decision-provenance.jsonl` (append-only, fsync per ADR-013):

```jsonl
{"id":"<uuid-v4>","ts_ms":1715299215000,"agent_identity":{"chain":["founder","claude-bare-pid-1234","workflow:W-abc"]},"policy_id":"P-charter-obligation-3","policy_version":"v1.2","scope":"WORKFLOW","outcome":"allow","reason":"obligation cleared by step 2 output ref X","data_refs":[{"ref":"DataRef:abc","authoritative_status":"authoritative","schema_ref":"<uri>"}]}
{"id":"<uuid-v4>","ts_ms":1715299220000,"agent_identity":{...},"policy_id":"P-tenant-isolation","policy_version":"v1.0","scope":"TENANT","outcome":"deny","reason":"cross-tenant op without delegates_to edge","data_refs":[...]}
```

Secondary sinks: when `scope === 'TENANT'`, the row is ALSO appended to the Tenant's `audit_log_path` (per `Tenant.audit_log_path` field, §2.8). Per-Execution slice rows ALSO appear in `ExecutionResult.logs[]` when emitted within an Execution (per I-7).

## Cross-primitive references

- **Workflow** (`../primitives/workflow.md`): every Workflow Execution emits ≥1 DecisionProvenance per I-7; `scope='WORKFLOW'` decisions cite the parent Workflow id.
- **WorkflowStep** (`../primitives/step.md`): `scope='STEP'` decisions cite the step_index within an Execution.
- **EngineEvent** (`../primitives/engine-event.md`): event #8 `policy_decision` is the primary EngineEvent carrier for DecisionProvenance rows.
- **Tenant** (`../primitives/tenant.md`): `scope='TENANT'` rows append to the Tenant's `audit_log_path`; I-8 boundary decisions emit here.
- **Charter** (`../primitives/charter.md`): obligation/invariant evaluations emit DecisionProvenance citing the Charter's obligation id.
- **Domain** (`../primitives/domain.md`): `policy_id` may carry a Domain anchor when the decision is governed by Domain principles.

## References

- NATIVE-ENGINE.md §2.9 — canonical DecisionProvenance field table.
- NATIVE-ENGINE.md §4 — I-7 (per-Execution emit), I-9 + I-17 (policy_id + policy_version), I-8 (tenant boundary).
- NATIVE-ENGINE.md §3.1 — `PolicyDispatcher.evaluate`, `UserKit.appendDecisionProvenance` signatures.
- NATIVE-ENGINE.md §3.2 #8 — `policy_decision` event.
- ADR-007 — DecisionProvenance schema.
- ADR-008 — DataRef + authoritative_status.
- ADR-013 — persistence + fsync.
- ADR-015 — agent_identity chain.
- F-8 — forbidden coupling: DecisionProvenance without policy_id+policy_version.
