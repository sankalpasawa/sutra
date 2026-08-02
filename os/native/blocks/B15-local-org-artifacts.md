---
part-id: B15
bucket: blocks
template: L8-feature-spec
parity-source: §12.17 row B15 + §12.16 founder voice round 5
parity-source-sha256: 1eb9dc25af7767b003008c987526cd0abe6332c341165759e8e725d440a2f0e9
status: DRAFT v1
authored: 2026-05-09
---

# B15: Local vs Org Artifacts

## 1-line summary

Artifact carries a `scope` ∈ {`local-tenant`, `org-tenant`}; cross-tenant reads require PolicyDispatcher allow per the ADR-006 Tenant-isolation pattern.

## Scope (in / out)

**In scope (v1)**:
- EXTEND Artifact (closed-loop substrate per B9 / canon §12.13) with `scope: 'local-tenant' | 'org-tenant'` per §12.17 row B15.
- Cross-tenant read requires PolicyDispatcher allow per ADR-006 pattern (referenced in §12.17 row B15).
- Org-Tenant artifacts visible to all humans in the org per ACL (composes with B14).

**Out of scope (v1)**:
- Auto-classification (Native decides scope automatically) — operator-declared v1; gap per F2 for auto-classification rule.
- Scope mutation post-write — canon-silent (gap per F2).
- External-tenant artifact federation — overlaps B17 / cross-org; v3+.

## User outcome

Operator distinguishes work that's private to them vs work shared at the org level — both addressable, both auditable. Founder voice round 5: "how do they create their artifacts locally? How do they create artifacts at the org level?".

## UX flow (narrative; terminal + audit log)

1. Workflow step produces output.
2. B15 attaches `scope` ∈ {`local-tenant`, `org-tenant`} (operator-declared at Workflow author time OR step author time).
3. Artifact persisted via B9 with scope marker.
4. Cross-tenant read request → routed via canon PolicyDispatcher per ADR-006 pattern; allow / deny per ACL.
5. Allowed → artifact returned. Denied → `tenant_boundary_violation` emitted; HS-3 fires.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Workflow declares step output `scope='local-tenant'` | step completes | Artifact persisted with `scope='local-tenant'`; only owning Human-Tenant can read |
| 2 | Workflow declares step output `scope='org-tenant'` | step completes | Artifact visible to all child Human-Tenants of the Org-Tenant per B14 |
| 3 | Cross-tenant read request | PolicyDispatcher evaluates | per ADR-006 allow/deny; `policy_decision` emitted; denial → `tenant_boundary_violation` + HS-3 |
| 4 | Scope not declared | step completes | default scope NOT specified in canon (gap per F2; runtime implementation choice — likely `local-tenant` for safety) |

## Data model

Per §12.17 row B15: EXTEND Artifact substrate (per F5, B9's alias note applies — Artifact is event-aliased + Asset/DataRef in canon). No new §2 primitive.

```
Artifact (alias, extended) = {
  ...B9 alias fields,
  scope: 'local-tenant' | 'org-tenant'    // NEW per B15
}
```

Cross-refs:
- `../primitives/tenant.md` (scope boundary)
- `../primitives/engine-event.md` (artifact_registered substrate)

## Edge cases

- **Scope upgrade** (operator promotes local → org) → not specified in canon (gap per F2; future ADR may codify).
- **Scope downgrade** (org → local) → information-disclosure risk; gap per F2.
- **Cross-org read** (artifact in Org-Tenant A read from Org-Tenant B) → not v1; v3+ federation deferred per P13.
- **Org-Tenant artifact deletion** — overlaps §8 OS-14 sink-policy; deferred.

## Telemetry

Events (canon-existing only):
- `artifact_registered` (§3.2 #9) — with scope payload.
- `policy_decision` — cross-tenant read ACL decision.
- `tenant_boundary_violation` — on denied cross-tenant read.

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Cross-company decision-replay success rate — scope determines what an Execution can see for replay.

## Dependencies

- **Primitives**: `tenant`, `engine-event`.
- **Events**: `artifact_registered`, `policy_decision`, `tenant_boundary_violation`.
- **Surfaces**: `audit`, `tenant`.
- **Hardstops**: HS-3 (tenant-boundary) — B15's enforcement anchor.
- **Blocks**: B9 (Artifact alias substrate), B14 (Tenant hierarchy host), B17 (External tools may flow artifacts into either scope).
- **Pillars**: P13 (Multi-human-org-Native architecture), P1 (Artifact-first — closed loop preserved across scope).
- **ADRs**: ADR-006 (Tenant isolation + PolicyDispatcher pattern).

## References

- NATIVE-ENGINE.md §12.17 row B15 (founder voice round 5).
- NATIVE-ENGINE.md §12.13 row B9 (Artifact substrate).
- §6.2 Multi-tenant isolation.
- ADR-006 (Tenant isolation + PolicyDispatcher).
