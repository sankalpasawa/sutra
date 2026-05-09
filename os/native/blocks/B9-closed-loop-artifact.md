---
part-id: B9
bucket: blocks
template: L8-feature-spec
parity-source: §12.12 (founder-voice round-4) + §14.15.2 (top-5 outcomes) + §14.0 (concise PRD)
parity-source-sha256: 9c46c0b52a95d8b49e6527c3e9bc1c34ac45d5e98a6849d573bc76ed1d6954aa
status: DRAFT v1
authored: 2026-05-09
---

# B9: Closed-Loop Artifact

## 1-line summary

Every typed input, every operator utterance, every LLM output is stored as a Native-recognized typed Artifact and re-consumed by the LLM on the next iteration — Native's outputs become Native's next inputs.

## Scope (in / out)

**In scope**:
- Every Workflow step output emits an Artifact row (typed, addressable, system-readable).
- Operator utterances captured by H-Sutra log become Artifact-type=`utterance`.
- LLM call outputs become Artifact-type=`llm_output` with lineage chain back to the calling Workflow.
- Artifact catalog auto-feeds next Workflow's context-load step (B11 PromptBuilder reads from catalog).
- Exact-match Artifact lookup by `id` (per Q32 v1 minimum).

**Out of scope (v1)**:
- Semantic indexing of Artifacts (deferred v2+ per Q32; uses F1 indexing primitive).
- Embedding retrieval over Artifact bodies (deferred v3+).
- Distributed Artifact catalog (single-tenant catalog v1; v2+ for multi-org).
- Auto-deletion / lifecycle eviction (DOC-ONLY at v1; sink-policy enforcement deferred per §8 OS-14).

## User outcome

> "Anything I produce is logged + reused" (per §14.15.2 rank 1).

The operator never loses prior decisions, learnings, or in-flight context. The next time the operator picks up similar work, Native already has the prior Artifacts available — no manual context-reconstruction.

## UX flow (narrative; terminal + audit log)

1. Operator types an utterance OR a Workflow step produces output.
2. Native emits `artifact_registered` EngineEvent (event #9 per §3.2).
3. Artifact catalog persists the row to JSONL audit log (per ADR-013 + 3-channel durability).
4. Next Workflow's context-load step queries catalog by Artifact-type + lineage chain.
5. PromptBuilder (B11) composes prompt with relevant Artifacts as explicit context.
6. LLM call fires with explicit Artifact-derived context (per P11 constrained problem construction).
7. LLM output → new Artifact → loop closes.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Operator utterance arrives via H-Sutra | classifier routes utterance | Artifact-type=`utterance` row persisted to catalog with timestamp + tenant_id + lineage_parent_id=null |
| 2 | Workflow step emits output | step exits successfully | Artifact row persisted with lineage_parent_id=step's execution_id + Artifact-type derived from step's `return_contract` |
| 3 | Workflow N+1 starts in same Tenant | context-load step fires | catalog returns prior Artifacts for same Tenant; PromptBuilder embeds in step[1] prompt |
| 4 | Artifact lookup by id called | row exists | exact-match returned in <50ms (v1 perf target) |
| 5 | Artifact catalog write fails | all 3 channels (JSONL + tmp fallback + stderr beacon) unwritable | HS-4 fires; governance hooks block; founder HITL escalation |

## Data model

Artifact (typed primitive — references `sutra/os/native/primitives/asset.md` + `primitives/data-ref.md`):

```typescript
type Artifact = {
  id: string;                        // content-addressed UUIDv7
  type: 'utterance' | 'llm_output' | 'artifact_doc' | 'decision' | 'metric_observation' | string;
  body_ref: DataRef;                 // pointer to actual content (file, blob, inline)
  tenant_id: string;                 // multi-tenant isolation per Tenant primitive
  lineage_parent_id: string | null;  // chain backward through prior steps/utterances
  execution_id?: string;             // which Execution emitted this (if step-emitted)
  workflow_id?: string;              // which Workflow produced it
  ts_ms: number;                     // emission time
  agent_identity: string;            // who emitted (operator | claude | codex | host-LLM)
  retention: 'session' | 'execution' | 'tenant_permanent';
  return_contract_ref?: string;      // if step-emitted, the Workflow's return_contract JSON Schema id
};
```

## Edge cases

- **Lineage cycle**: a Workflow consumes its own prior Artifact + emits a derived one. Allowed; lineage chain becomes a graph not a tree. Catalog must handle non-tree lineage.
- **Cross-tenant read attempt**: TenantIsolation engine intercepts; emits `tenant_boundary_violation` (event #26); HS-3 fires.
- **Schema evolution**: Artifact type catalog grows over time. v1 = enum + open-string; v2 = strict typed registry per ADR-018+ (TBD).
- **Retention vs lifecycle conflict**: Artifact `retention='session'` but operator restarts session mid-Workflow. Session-scoped Artifacts dropped at session end; Workflow re-consumes nothing. Workflow design must declare which Artifacts persist.
- **Race**: Workflow N writes Artifact A; Workflow N+1 starts before fsync flush. Catalog reads must use `read-after-write consistency` (fsync barrier per ADR-013).

## Telemetry

Events emitted by B9:
- `artifact_registered` (#9 in §3.2) — every Artifact creation.
- `routing_decision` (#1) — when Workflow N+1 routes based on prior Artifact-derived context.

Metrics affected (cross-refs `sutra/os/native/metrics/north-star-ohs-per-week.md`):
- Operator-Hours-Saved (N*) — closed-loop artifact is foundational; without it, operator manually reconstructs context each session.
- Pattern-emergence precision (leading input) — k=4 pattern detection works on Artifact-stored utterances.

## Dependencies

- **Primitives** (cross-refs `sutra/os/native/primitives/*.md`): Asset, DataRef, Tenant, EngineEvent, Workflow, ExecutionResult, DecisionProvenance.
- **Events**: `artifact_registered` (#9), `routing_decision` (#1), `workflow_started` (#2), `step_completed` (#6).
- **Surfaces**: ROUTE (consumes Artifacts for matching), RUN (emits Artifacts per step), AUDIT (persists Artifact rows), TENANT (enforces per-Tenant catalog).
- **Hardstops that fire here**: HS-4 (audit log unwritable; v1 fail-closed semantic).
- **ADRs**: ADR-013 (3-channel JSONL durability + fsync), ADR-018+ (typed Artifact registry — future).

## References

- NATIVE-ENGINE.md §12.12 (founder voice round-4) — verbatim founder direction on closed-loop.
- NATIVE-ENGINE.md §14.15.2 (top-5 outcome ordering, rank 1).
- NATIVE-ENGINE.md §14.0 concise PRD — Top-5 v1 outcomes.
- NATIVE-ENGINE.md §10.2 P1 (artifact-first pillar) — philosophical anchor.
- NATIVE-ENGINE.md §10.3 P1 falsification — "If artifacts are NOT consumed by next iteration → P1 broken; system not closed-loop".
- Q32 (§14.10) — exact-match Artifact lookup by id required v1.
