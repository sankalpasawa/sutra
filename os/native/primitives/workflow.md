---
part-id: Workflow
bucket: primitives
template: L9-primitive-spec
parity-source: §2.3
parity-source-sha256: a483565d8263a0fd7805092b66c09e43cdaee2ad1bc0116c7036af16299c3657
status: DRAFT v1
authored: 2026-05-09
---

# Workflow

## Purpose

The Workflow primitive is the unit of named, gated, audited operator work in Native. Every operator utterance routes either to a matched Workflow (RUN surface fires it) or to a pattern proposal (EMERGE surface proposes one). A Workflow encodes the WHAT (steps), the WHEN (triggers via TriggerSpec), the GATING (preconditions / postconditions / requires_approval / failure_policy), and the OWNERSHIP (custody_owner / tenant boundaries).

## Type signature (TypeScript-style)

```typescript
type Workflow = {
  id: string;                         // content-addressed W-hash (sha256 of canonical form)
  preconditions: Predicate[];         // typed PNC; parsed per ADR-012; not free prose
  postconditions: Predicate[];        // typed PNC; same parser
  step_graph: WorkflowStep[];         // terminal_check T1-T6 must pass (I-5)
  failure_policy: 'rollback' | 'escalate' | 'pause' | 'abort' | 'continue';  // per ADR-011
  stringency: 'process' | 'directive' | 'principle';  // operator-visible enforcement level
  interfaces_with: string[];          // typed boundary refs (other Workflow ids)
  expects_response_from: string[];    // typed identity refs (operator | tenant_id)
  on_override_action: 'pause' | 'block' | 'audit-only';  // when operator overrides gate
  reuse_tag: boolean;                 // true → Workflow is also registered as a Skill
  return_contract: JSONSchema | null; // REQUIRED IFF reuse_tag=true; F-13 forbids null when reuse_tag=true
  custody_owner: TenantId | null;     // declares state ownership; null → tenant-free Workflow
  extension_ref: string | null;       // v1.0: MUST be null (future hook for Workflow-of-Workflows)
  modifies_sutra: boolean;            // true → requires reflexive_check Constraint cleared (L6); HS-1 if not
  requires_approval: boolean;         // per-workflow approval gate (ADR-009)
};
```

## Invariants (must hold)

- **I-5 (terminal check)**: `step_graph` MUST be reachable from step[0] via the failure_policy edges. T1-T6 terminal checks enforce no orphan steps, no unreachable terminal, no infinite loops without explicit `continue` policy.
- **F-13 (reuse_tag implies return_contract)**: `reuse_tag=true` requires non-null `return_contract`. Mint-time rejection.
- **F-7 (reflexive boundary)**: `modifies_sutra=true` Workflows REQUIRE `reflexive_check` Constraint cleared before mint. HS-1 fires otherwise. L6 REFLEXIVITY law guards.
- **Content-addressed id**: `id = sha256(canonical_form(workflow))` — any field change yields a new Workflow id (immutable; new mint required).
- **Tenant isolation (I-8)**: `custody_owner !== null` requires non-null `tenant_context_id` at every Execution. Fail-closed.
- **ADR-012 typed predicates**: `preconditions` and `postconditions` MUST parse as typed PNC predicates; free prose rejected at mint-time per L2 BOUNDARY.

## Lifecycle (created → terminal states)

1. **Mint**: operator (or pattern emergence post-approval) emits Workflow JSON; LiteExecutor validates schema + invariants; content-addressed id computed; row persisted to user-kit registry.
2. **Dormant**: Workflow exists in registry; not yet triggered. May be triggered by matching TriggerSpec OR by direct `run` CLI invocation.
3. **Triggered**: TriggerSpec matched OR operator runs explicitly; LiteExecutor instantiates an Execution.
4. **Running** (Execution state): `preconditions` cleared; `workflow_started` event emits; step[0] dispatches.
5. **Step transition**: each `WorkflowStep` dispatches → emits `step_started` / `step_completed` / `step_paused` per outcome.
6. **Terminal**: one of `workflow_completed` (success), `workflow_failed` (failure), or `workflow_rollback_started` → eventual rollback completion per failure_policy.
7. **Decommission**: Workflow registry entry can be `deprecated=true` to prevent new Executions; existing Executions complete or are rolled back; no field overwrite (immutability).

## Serialization (JSONL row shape)

User-kit registry rows at `~/.sutra-native/user-kit/workflows/<id>.json` (single-Workflow JSON per file). Reference index at `~/.sutra-native/user-kit/workflows/INDEX.jsonl`:

```jsonl
{"id":"W-<hash>","ts_minted_ms":<unix-ms>,"path":"workflows/W-<hash>.json","reuse_tag":true,"deprecated":false,"custody_owner":"<tenant-id|null>"}
```

Canonical form for content-addressing: JSON keys sorted alphabetically, no whitespace, UTF-8 encoded. SHA256 of canonical form = `W-<hex>`.

## Cross-primitive references

- **Charter** (`sutra/os/native/primitives/charter.md`): Workflow inherits stringency + on_override_action from Charter when interfaces_with includes a Charter id.
- **Domain** (`sutra/os/native/primitives/domain.md`): Workflow `custody_owner` is a Tenant; Domain principles govern which Workflows are mint-allowed per Tenant.
- **WorkflowStep** (`primitives/workflow-step.md`): step_graph is a list of WorkflowStep entries.
- **TriggerSpec** (`primitives/trigger-spec.md`): defines WHEN the Workflow fires.
- **ExecutionResult** (`primitives/execution-result.md`): runtime instantiation of a Workflow.
- **Tenant** (`primitives/tenant.md`): isolation boundary; custody_owner refs.
- **DecisionProvenance** (`primitives/decision-provenance.md`): every gate decision on this Workflow emits a typed row.
- **EngineEvent** (`primitives/engine-event.md`): 6 of 26 events directly reference Workflow (`workflow_started`, `workflow_completed`, `workflow_failed`, `workflow_rollback_started`, `workflow_rollback_complete`, `workflow_rollback_partial`).

## References

- NATIVE-ENGINE.md §2.3 (canonical primitive definition).
- NATIVE-ENGINE.md §3.1 — Engine API signatures (mint / fire / cancel).
- NATIVE-ENGINE.md §4 Invariants — I-5, I-8, F-7, F-13.
- ADR-009 — per-workflow approval gate.
- ADR-010 — pattern emergence k=4 + Workflow proposal flow.
- ADR-011 — failure_policy enum.
- ADR-012 — typed preconditions / postconditions (PNC parser).
- HS-1 — reflexive_check Constraint violation hardstop.
