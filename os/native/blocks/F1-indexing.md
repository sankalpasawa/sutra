---
part-id: F1
bucket: blocks
template: L8-feature-spec
parity-source: §12.13 row F1 + §12.12 founder voice round 4 + Q32
parity-source-sha256: 8949b0314ed51dfff982128178a7a94caf64e4832355d640401d9be07af8cf3c
status: DRAFT v1
authored: 2026-05-09
---

# F1: Indexing + Context-Retrieval Mechanisms (future feature)

## 1-line summary

Indexing + context-retrieval mechanisms for the artifact catalog — semantic indexing and embedding retrieval — DEFERRED to v2+ per canon §12.13 row F1; v1 ships exact-match-by-id only per Q32.

## Scope (in / out)

**In scope (future — v2+ semantic; v3+ embeddings)**:
- Indexing mechanisms over the artifact catalog (semantic, embedding-based, hybrid).
- Context-retrieval beyond exact-match-by-id (which is v1 minimum per Q32).
- "Right kind of mechanisms to get the context" per founder voice round 4 — internal AND external tools.

**Out of scope (v1)**:
- Semantic indexing — v2+.
- Embedding retrieval over Artifact bodies — v3+ per Q32 + B9 scope.
- v1 uses naive concat OR canonical-rank retrieval per §12.13 row F1.

## User outcome

Future: operator's relevant context is retrieved via semantic + embedding-based methods, including external tools, so reasoning is well-fitted to the task at scale. v1: exact-match-by-id is the minimum required to keep B9 closed-loop functional.

## UX flow (narrative; terminal + audit log — future-state, not v1)

1. (v2+) Workflow step requests context for a query.
2. F1 indexing engine consults semantic index over artifact catalog.
3. Top-N artifacts returned by semantic similarity score under budget.
4. (v3+) Embedding retrieval over artifact bodies extends 7a 3D scoring.
5. (v2+) External-tool context (Slack history, Email, etc. per B17 Connectors) joins retrieval set.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | v1 ship gate | F1 invoked v1 | F1 path stubbed; falls back to exact-match-by-id per Q32 minimum; semantic / embedding paths return "deferred" marker (specific marker shape NOT specified in canon — gap per F2) |
| 2 | (v2+) Semantic index requested | query fires | semantic index returns top-N by similarity score; budget-bounded |
| 3 | (v3+) Embedding retrieval requested | query fires | embedding similarity returns top-N over artifact bodies |
| 4 | (v2+) External-tool context requested | query fires | B17 Connectors enumerated; per-tool retrieval composed (canon-silent on cross-tool ranking — gap per F2) |

## Data model

Per §12.13 row F1: F1 is DEFERRED to v2+; no v1 primitive materialized. References memory `project_context_sphere_research` for graph + 3D scoring sketch.

v1 shape minimum (per Q32):

```
ArtifactLookup = {
  by_id: (id) => Artifact | null     // exact-match v1
}
```

v2+ extensions NOT specified in canon (gap per F2; future ADR may codify semantic index + embedding contract).

Cross-refs:
- `../primitives/engine-event.md` (substrate for artifact catalog reads)
- `../primitives/tenant.md` (scope boundary for retrieval)

## Edge cases

- **v1 query without artifact-id** → no semantic fallback v1; query returns empty or surfaces gap notice (canon-silent on exact behavior — gap per F2).
- **Future: stale index** → re-indexing trigger NOT specified in canon (gap per F2).
- **Future: index corruption** → recovery routes via canon §6.8 recovery (no new recovery semantics per F3).
- **Cross-Tenant index access attempt** → HS-3 fires per canon §6.9.3.

## Telemetry

Events (canon-existing):
- `routing_decision` (§3.2 #1) — when retrieval-policy decision applies.
- `policy_decision` — when index-policy applies.

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Operator-Hours-Saved (future) — semantic retrieval is the big OHS lever once it lands.
- Pattern-detection precision — better retrieval → better proposals.

## Dependencies

- **Primitives**: `engine-event`, `tenant`.
- **Events**: `routing_decision`, `policy_decision`.
- **Surfaces**: `audit`, `route`.
- **Hardstops**: HS-3 (tenant-boundary), HS-4 (audit-unwritable).
- **Blocks (downstream)**: B9 (substrate F1 indexes), 7a (composes with F1 once F1 ships), B11 (PromptBuilder consumes F1 retrieval output).
- **Pillars**: P11 (Constrained problem construction).

## References

- NATIVE-ENGINE.md §12.13 row F1 (future feature note).
- NATIVE-ENGINE.md §12.12 founder voice round 4 (verbatim).
- Q32 (§12.15) — v1 minimum exact-match; semantic v2+; embedding v3+.
- Memory `project_context_sphere_research` — graph + 3D scoring sketch.
