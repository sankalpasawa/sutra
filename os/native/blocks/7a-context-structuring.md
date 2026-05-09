---
part-id: 7a
bucket: blocks
template: L8-feature-spec
parity-source: §12.6 row 7a + §12.5 round 2 founder voice + Q19
parity-source-sha256: 4c7c1eb149ba0da3be52280eccc36833c3f51c389998fd9824ddb9a39921de34
status: DRAFT v1
authored: 2026-05-09
---

# 7a: Context Structuring

## 1-line summary

Native creates and structures context for the operator's autonomous mode — graph + 3D scoring (depth / weight / recency) + budget-constrained retrieval over the artifact catalog so the next LLM call has the right, bounded context.

## Scope (in / out)

**In scope (v1)**:
- Context-structuring primitive per §12.6 row 7a — graph + 3D scoring (depth/weight/recency) + budget-constrained retrieval.
- v1 = RETRIEVE only (per Q19 default 2026-05-09 — retrieve v1 / passive); synthesize deferred to v2.
- Reads from existing substrate: H-Sutra log + execution trace + ESTIMATION-LOG (per §12.6 row 7a "Context Engine partial").
- Cross-refs Sutra core IP "weight distribution engine" (memory `project_sutra_core_ip` — depth = weighting) referenced at §12.6.

**Out of scope (v1)**:
- Active synthesis (Native composes NEW context bundles from existing artifacts) — deferred v2 per Q19.
- Semantic indexing — deferred per F1 (future feature; v2+).
- Embedding retrieval — deferred per F1 + §12.15 Q32 (v3+).
- Distributed retrieval across Tenants — single-Tenant v1; cross-Tenant deferred to B14 / B15.

## User outcome

Operator's autonomous mode gets effective context retrieval — the LLM is reasoning against bounded, relevant, scored context, not raw artifact dumps. Founder voice round 2: "create context and have structuring of context, which can help in effective retrieval".

## UX flow (narrative; terminal + audit log)

1. A Workflow's context-load step (W-load-native-context per §5.5) fires.
2. Context-structuring engine queries artifact catalog (per B9) for the active Tenant.
3. Each candidate artifact scored on 3 dimensions: depth (canon-silent on exact formula per F2), weight (per Sutra core IP per memory), recency (timestamp delta).
4. Budget-constrained retrieval selects top-N by composite score under a token / count budget (specific budget value NOT specified in canon — gap per F2).
5. Selected artifacts handed to B11 PromptBuilder for prompt assembly.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Active Tenant has ≥1 artifact in catalog (per B9) | context-load step fires | retrieval returns scored artifact list bounded by budget; v1 is exact-match-by-id capable (per Q32 v1 minimum) |
| 2 | Operator triggers retrieval with explicit artifact-id (per Q32 v1) | retrieval runs | exact-match returned in <50ms (matches B9 acceptance #4 — v1 perf target) |
| 3 | No artifacts in catalog (cold start) | retrieval runs | empty bundle returned; B11 falls back to no-context prompt; no error |
| 4 | Retrieval crosses Tenant boundary | TenantIsolation engine intercepts per §6.2 | `tenant_boundary_violation` (event in §3.2) emitted; HS-3 fires (cross-ref `../hardstops/HS-3-tenant-boundary.md`) |

## Data model

Per §12.6 row 7a: Context Engine is partial via H-Sutra log + execution trace + ESTIMATION-LOG. 7a EXTENDS the existing substrate; no new §2 primitive materialized (per F5).

Specific score-formula + graph-shape NOT specified in canon — runtime implementation choice per F2; future ADR may codify.

Cross-refs:
- `../primitives/engine-event.md` (substrate — H-Sutra log is EngineEvent-shaped)
- `../primitives/tenant.md` (scope boundary)
- `../primitives/workflow.md` (context-load step lives in W-load-native-context per §5.5)

## Edge cases

- **Score-tie** → tie-break rule NOT specified in canon (gap per F2).
- **Budget exhausted before required artifact retrieved** → high-weight artifact may be excluded; specific eviction rule NOT specified in canon (gap per F2).
- **Artifact catalog mutation mid-retrieval** → read-after-write consistency per ADR-013 fsync barrier (cross-ref B9 edge cases).
- **Cross-Tenant artifact requested** → HS-3 fires per §6.9.3.

## Telemetry

Events emitted by 7a (canon-existing only):
- `routing_decision` (§3.2 #1) — when context-structuring selects artifact set as a routing choice.
- `policy_decision` — when retrieval policy applies (which scoring, which budget).
- `artifact_registered` (#9) — if structured context bundle is persisted as a derived artifact (per P1 closed-loop).

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Operator-Hours-Saved (long-tail) — context-fit reduces reasoning waste.
- Pattern-detection precision — context-aware proposals raise approval rate.

## Dependencies

- **Primitives**: `engine-event`, `tenant`, `workflow`, `step`.
- **Events**: `routing_decision`, `policy_decision`, `artifact_registered`, `tenant_boundary_violation`.
- **Surfaces**: `route` (consumes structured context for matching), `run` (steps consume retrieved context), `audit` (persists retrieval decisions).
- **Hardstops**: HS-3 (tenant-boundary).
- **Blocks (downstream)**: B9 (substrate B9 produces; 7a consumes), B11 (PromptBuilder consumes 7a output), 7d (lifecycle OBSERVE phase consumes 7a).
- **Pillars**: P11 (Constrained problem construction), P1 (Artifact-first).

## References

- NATIVE-ENGINE.md §12.6 row 7a (founder voice round 2 — context structuring + effective retrieval).
- NATIVE-ENGINE.md §12.5 round 2 voice (verbatim founder utterance).
- NATIVE-ENGINE.md §5.5 (W-load-native-context — Workflow that fires this).
- Q19 (§12.7) — retrieve v1; synthesize v2.
- Q32 (§12.15) — exact-match by id required v1.
- Memory `project_sutra_core_ip` — weight distribution engine (referenced).
