---
part-id: TENANT
bucket: surfaces
template: L9-surface-spec
parity-source: §14.7 + §2.8 + §6.2 + §3.2 #26 + §6.9 HS-3
parity-source-sha256: 3b45de1f3ac218a0a6c770e194e3c37ab4d89f4291c525ba89ad65c838e30b35
status: DRAFT v1
authored: 2026-05-09
---

# Surface: TENANT

> **Disambiguation**: This file is the TENANT *surface* (lives in `surfaces/`). The Tenant *primitive* (`Tenant` type per §2.8) lives in [`../primitives/tenant.md`](../primitives/tenant.md). Both exist by design; cross-refs use directory to disambiguate.

## Purpose

Provide each Tenant with an isolated audit log + ACL — so cross-Tenant operations require explicit delegation, every Tenant's DecisionProvenance is private by default, and cross-Tenant leakage is fail-CLOSED.

Canon: §14.7 row 6 — *"TENANT | Isolated audit log + ACL per company"*.

## Interface (operator-facing)

TENANT is consulted on every Execution dispatch and every cross-Tenant operation. It is not a CLI surface; it is enforced via `TenantIsolation.assertCrossTenantAllowed(srcTenant, dstTenant, op)` (§3.1) which throws on deny.

| Operator-visible touchpoint | Mechanism |
|---|---|
| Tenant creation | `Tenant` primitive minted in user-kit (per §2.8); `audit_log_path` declared |
| Tenant listing | `sutra-native tenant list` (§3.3) |
| Cross-Tenant op attempted | TenantIsolation throws → `tenant_boundary_violation` event emitted → HS-3 escalates |

## Invariants (must always hold)

| # | Invariant | Source |
|---|---|---|
| TENANT-I1 | Every `Domain` has a non-null `tenant_id` referencing a registered `Tenant`. | §2.1 Domain.tenant_id required + ADR-006 |
| TENANT-I2 | Every `Tenant` has a non-empty `name` and an absolute `audit_log_path`. | §2.8 invariants |
| TENANT-I3 | Cross-Tenant operations require `TenantDelegation`; absent that, `TenantIsolation.assertCrossTenantAllowed` throws and emits `tenant_boundary_violation` (#26). | §3.1 + §3.2 row 26 + §6.9 HS-3 |
| TENANT-I4 | Fail-CLOSED: when `workflow.custody_owner !== null` AND `tenant_context.tenant_id` is undefined → deny operation. | §6.2 |
| TENANT-I5 | Each Tenant's DecisionProvenance JSONL is private — readers from other Tenants do NOT see it absent explicit delegation. | §2.8 + ADR-006 |
| TENANT-I6 | HS-3 fires on any cross-Tenant violation: block + log + escalate. | §6.9 HS-3 |

Canon gap: §2.8 declares `isolation_contract: object` ("filesystem + capability isolation declaration") but does NOT specify the schema. NOT specified in canon — runtime implementation choice; future ADR may codify.

Canon gap: `TenantDelegation` is referenced by HS-3 ("Tenant boundary cross attempted without TenantDelegation") and §3.2 #26 ("Cross-tenant op attempted without delegation") but is NOT itself defined as a §2 primitive in canon v1. The delegation primitive shape is NOT specified in canon — runtime implementation choice; the v1 default appears to be "no cross-Tenant delegation supported" with HS-3 acting as the universal block.

## Integration points

- **Primitives consumed**: [`Tenant`](../primitives/tenant.md) (the primitive this surface enforces), [`Domain`](../primitives/domain.md) (every Domain carries `tenant_id`), [`ExecutionResult`](../primitives/execution-result.md) (`tenant_context` field), [`DecisionProvenance`](../primitives/decision-provenance.md) (scope='TENANT' for tenant-level decisions).
- **Events emitted**:
  - [`tenant_boundary_violation`](../events/tenant_boundary_violation.md) (#26)
  - [`policy_decision`](../events/policy_decision.md) (#8) — when TenantIsolation evaluates an op and emits an allow/deny decision via PolicyDispatcher.
- **Events consumed**: any event carrying a `tenant_context` — TENANT inspects the context to assert isolation.
- **Surfaces upstream**: ROUTE (Workflow match must respect Tenant scope), RUN (every Execution carries `tenant_context`), GATE (approval lives within a Tenant), EMERGE (per-Tenant pattern proposals per Q4 v2 configurability).
- **Surfaces downstream**: [AUDIT](audit.md) (per-Tenant audit log = `Tenant.audit_log_path`; HS-3 emissions persisted); [HS-3 hardstop](../hardstops/HS-3-tenant-boundary.md) (cross-Tenant violation escalation).

## C4 context

```
[Any surface: ROUTE / RUN / GATE / EMERGE]
        |
        | (op references tenant_context)
        v
[TENANT: TenantIsolation.assertCrossTenantAllowed(src, dst, op)]
        |
        +-- src == dst? --yes--> allow
        |
        +-- TenantDelegation present? --yes--> allow + emit policy_decision (allow)
        |
        +-- otherwise --> THROW
                          |
                          v
                  emit tenant_boundary_violation (#26)
                          |
                          v
                  HS-3 escalate: block + log + founder-HITL
                          |
                          v
                  [AUDIT JSONL: per-Tenant path]
```

TENANT is the multi-tenant fail-CLOSED surface (R5 mitigation per §14.8). Asawa's portfolio model — 1 founder operating N companies — depends on TENANT for the leakage guarantee.

## References

- `NATIVE-ENGINE.md` §14.7 row "TENANT"
- `NATIVE-ENGINE.md` §2.1 Domain.tenant_id
- `NATIVE-ENGINE.md` §2.8 Tenant primitive
- `NATIVE-ENGINE.md` §3.1 `TenantIsolation.assertCrossTenantAllowed`
- `NATIVE-ENGINE.md` §3.2 row 26 (`tenant_boundary_violation`)
- `NATIVE-ENGINE.md` §6.2 multi-tenant isolation
- `NATIVE-ENGINE.md` §6.9 HS-3
- `NATIVE-ENGINE.md` §14.8 R5
- ADR-006 (Tenant ownership)
- `../primitives/tenant.md`
- `../primitives/domain.md`
- `../primitives/execution-result.md`
- `../primitives/decision-provenance.md`
- `../events/tenant_boundary_violation.md`
- `../events/policy_decision.md`
- `../hardstops/HS-3-tenant-boundary.md`
- `../surfaces/route.md` + `../surfaces/run.md` + `../surfaces/gate.md` + `../surfaces/emerge.md` + `../surfaces/audit.md`
