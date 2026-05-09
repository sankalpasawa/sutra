---
part-id: B14
bucket: blocks
template: L8-feature-spec
parity-source: §12.17 row B14 + §12.16 founder voice round 5 + §10.2 P13 + Q34
parity-source-sha256: 76e9dd081d70e9cacfe1ae393bc59d4c203dd8a00d055633b4ad26ff3b4384b2
status: DRAFT v1
authored: 2026-05-09
---

# B14: Multi-Human-Org Architecture

## 1-line summary

Org-Tenant has child Human-Tenants; each Human-Tenant runs its own Native instance with isolated audit log + ACL; Org-Tenant carries org-shared artifacts.

## Scope (in / out)

**In scope (v1 schema; deferred logic per Q34)**:
- EXTEND existing Tenant (§2.8) — `Org-Tenant` has children = `Human-Tenants` per §12.17 row B14.
- Each Human-Tenant has isolated audit log + ACL.
- Org-Tenant carries org-shared artifacts.
- Per Q34 default (2026-05-09) — introduce in v1 schema (deferred logic stub); built into Tenant.parent_tenant_id day-1 to prevent v2 schema migration.

**Out of scope (v1)**:
- Runtime Org-Tenant logic (full multi-human orchestration) — Q34 ships schema only v1.
- Cross-org A2A — v3+ per P13.
- Org-level governance rules beyond canon — gap per F2.

## User outcome

Operator at an org sees their own Native instance scoped to their own work + a shared Org surface for things they share with co-workers. Founder voice round 5: "in an organization, there is one human, there are multiple humans, and each human has their own Chief of Staff of Native".

## UX flow (narrative; terminal + audit log)

1. Org-Tenant declared via Tenant primitive (per §2.8 + Tenant.parent_tenant_id).
2. Each human in the org gets a Human-Tenant whose `parent_tenant_id` = Org-Tenant.
3. Each Human-Tenant runs its own Native instance per §6.3 (replica isolation via SUTRA_NATIVE_HOME per ADR-016).
4. Cross-Human-Tenant reads route via PolicyDispatcher per Q34 (canon ADR-006 pattern referenced in §12.17 row B15).
5. Org-Tenant artifacts visible to all child Human-Tenants per their ACL.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Tenant declared with `parent_tenant_id` set | Tenant created | Tenant resolves as Human-Tenant (child of Org-Tenant) per Q34 schema |
| 2 | Human-Tenant A attempts read on Human-Tenant B artifact | TenantIsolation engine evaluates per §6.2 | `tenant_boundary_violation` (§3.2) emitted; HS-3 fires per §6.9.3 |
| 3 | Human-Tenant attempts read on Org-Tenant shared artifact | Tenant evaluates parent-child relationship | allowed per ACL; specific ACL rule NOT specified in canon (gap per F2; runtime implementation choice) |
| 4 | Runtime logic for full multi-human orchestration requested | v1 | not v1 per Q34; schema-only v1; logic deferred v2 |

## Data model

Per §12.17 row B14: EXTEND existing Tenant (§2.8). No new §2 primitive (per F5).

```
Tenant (extended) = {
  ...existing §2.8 fields,
  parent_tenant_id: string | null    // canon-existing per §2.8 + Q34
  // Org-Tenant: parent_tenant_id = null AND children exist
  // Human-Tenant: parent_tenant_id = Org-Tenant.id
}
```

Cross-refs:
- `../primitives/tenant.md` (host)
- `../primitives/engine-event.md` (Tenant boundary events)

## Edge cases

- **Human-Tenant orphaned (parent deleted)** → behavior NOT specified in canon (gap per F2).
- **Cyclic Tenant hierarchy** → must be rejected; specific check NOT specified in canon (gap per F2; ADR may codify acyclicity invariant).
- **Multi-org membership for one human** → not v1; gap per F2.
- **Org-Tenant artifact eviction** — overlaps OS-14 sink-policy; deferred.

## Telemetry

Events (canon-existing only):
- `tenant_boundary_violation` (§3.2) — on cross-Human-Tenant read attempt.
- `policy_decision` — ACL evaluations.

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Operator-Hours-Saved (future — multi-human use case lands) — Org-level sharing reduces inter-human coordination friction.

## Dependencies

- **Primitives**: `tenant` (host), `engine-event`.
- **Events**: `tenant_boundary_violation`, `policy_decision`.
- **Surfaces**: `tenant` (cross-ref `../surfaces/tenant.md`), `audit`.
- **Hardstops**: HS-3 (tenant-boundary) — B14's primary fail-mode anchor.
- **Blocks**: B15 (Local vs Org artifacts — runs on B14's Tenant hierarchy), B16 (Native-Native A2A — operates over B14's instances), B18 (Person scoped per Human-Tenant).
- **Pillars**: P13 (Multi-human-org-Native architecture) — B14's anchor.
- **ADRs**: ADR-006 (Tenant isolation pattern), ADR-016 (replica isolation — substrate).

## References

- NATIVE-ENGINE.md §12.17 row B14 (founder voice round 5).
- NATIVE-ENGINE.md §2.8 Tenant primitive.
- NATIVE-ENGINE.md §10.2 P13.
- NATIVE-ENGINE.md §6.2 Multi-tenant isolation.
- Q34 (§12.19) — v1 schema only; deferred logic.
