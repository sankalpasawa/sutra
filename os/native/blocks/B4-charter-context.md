---
part-id: B4
bucket: blocks
template: L8-feature-spec
parity-source: §12.9 row B4 + §12.8 founder voice round 3 + Q28
parity-source-sha256: 3fc55e69f54b515096be7663b6b36c1343fef3c930d6b6bbc1271d5b1c35dda8
status: DRAFT v1
authored: 2026-05-09
---

# B4: Charter ↔ Context Boundary

## 1-line summary

Each Charter declares a bounded `context_scope` (included artifacts + excluded artifacts) so Charter-level retrieval is scoped — Charters function over time, made of Workflows, and pick up only the relevant context per the boundary.

## Scope (in / out)

**In scope (v1)**:
- EXTEND existing Charter primitive (§2.2) with `context_scope: {included_artifacts[], excluded_artifacts[]}` per §12.9 row B4.
- Charter-level retrieval is bounded by `context_scope` — composes with 7b localized intelligence.
- Cross-Charter delegation default per Q28 (2026-05-09) — audit-logged; per-Workflow override deferred v2.

**Out of scope (v1)**:
- Dynamic context_scope reshape mid-Charter — not specified in canon (gap per F2).
- Multi-Charter joint context (one Workflow needs context from N Charters) — Q28 default = cross-Charter delegation; deeper composition deferred v2.
- Per-Charter retention policy on context_scope — not v1 (overlaps §8 OS-14 deferred sink-policy).

## User outcome

Charters carry their own context boundary; Workflows inside a Charter pick up only that Charter's relevant artifacts; cross-Charter borrowing is explicit + audit-logged. Founder voice round 3: "Charters are made of various workflows ... right boundaries in terms of which context is for what charters. We pick up the relevant things as well."

## UX flow (narrative; terminal + audit log)

1. Charter declares `context_scope` at creation time (per B10 typed config consumption).
2. Workflow fires inside Charter.
3. 7a context-structuring retrieval applies Charter's `context_scope` filter on top of Tenant scope (per §6.2) + Domain scope (per B3).
4. Filtered artifact set handed to B11 PromptBuilder.
5. Cross-Charter artifact requested → routed via canon Q28 default (delegation audit-logged); `policy_decision` event emitted.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Charter declares `context_scope.included_artifacts=[A,B]` | Workflow in Charter fires retrieval | retrieval returns only A, B (filtered against Tenant + Domain scope) |
| 2 | Workflow requests artifact in `context_scope.excluded_artifacts` | retrieval fires | request denied; specific denial-event shape NOT specified in canon (gap per F2) |
| 3 | Cross-Charter delegation requested per Q28 | delegation fires | audit-logged via `policy_decision` per ADR-007; not blocked v1 |
| 4 | `context_scope` undeclared on Charter | retrieval fires | falls back to Tenant + Domain scope; default behavior NOT specified in canon (gap per F2) |

## Data model

Per §12.9 row B4: EXTEND existing Charter (§2.2) with `context_scope`. No new §2 primitive (per F5).

```
Charter (extended) = {
  ...existing §2.2 fields,
  context_scope: {
    included_artifacts: string[]
    excluded_artifacts: string[]
  }
}
```

Cross-refs:
- `../primitives/charter.md` (host)
- `../primitives/workflow.md` (Workflows live in Charter)
- `../primitives/domain.md` (Charter lives in Domain per §2.1 + §2.2)

## Edge cases

- **included AND excluded both list same artifact** → conflict-resolution rule NOT specified in canon (gap per F2).
- **Charter's context_scope is empty list** → behaves as default Tenant-wide OR strict-empty (canon-silent — gap per F2).
- **Charter declared without parent Domain** → rejected per canon §2.2 invariants.
- **Multi-Workflow Charter — Workflows mutate Charter's context_scope concurrently** → handled per B13 ConcurrencyCoordinator.

## Telemetry

Events (canon-existing only):
- `policy_decision` (§3.2) — context_scope filter evaluations + cross-Charter delegation decisions.
- `tenant_boundary_violation` — for cross-Tenant attempts (Charter cannot cross Tenant).
- `artifact_registered` (#9) — when filtered context bundle persisted as derived artifact.

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Operator-Hours-Saved — Charter-scoped retrieval reduces irrelevant-context noise.
- Pattern-detection precision — Charter scope sharpens emergence.

## Dependencies

- **Primitives**: `charter` (host), `domain`, `workflow`, `tenant`.
- **Events**: `policy_decision`, `tenant_boundary_violation`, `artifact_registered`.
- **Surfaces**: `tenant`, `route`, `audit`.
- **Hardstops**: HS-3 (tenant-boundary), HS-4 (audit-unwritable).
- **Blocks**: B3 (Domain parent), 7a (composes with retrieval), 7b (localized intelligence joint filter), B10 (Charter typed config — `context_scope` declared via B10 channel), B11 (PromptBuilder consumes filtered set).
- **Pillars**: P5 (MECE domains), P11 (Constrained problem construction).
- **ADRs**: ADR-006 (Tenant isolation pattern referenced by Q28).

## References

- NATIVE-ENGINE.md §12.9 row B4 (founder voice round 3).
- NATIVE-ENGINE.md §2.2 Charter primitive.
- Q28 (§12.11) — cross-Charter delegation default v1 (audit-logged); per-Workflow override v2.
