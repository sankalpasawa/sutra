---
part-id: Tenant
bucket: primitives
template: L9-primitive-spec
parity-source: §2.8
parity-source-sha256: f5fa1a086544ebc4bc2c3e32dcee70c1a0cc94591f3d4728ad35383301ecd51e
status: DRAFT v1
authored: 2026-05-09
---

# Tenant

## Purpose

The Tenant primitive is Native's isolation boundary. Every Domain is owned by exactly one Tenant (I-13). Tenants declare their isolation contract (filesystem + capability isolation), parent tenancy (null for root), and the absolute path to the Tenant's DecisionProvenance JSONL audit log. Cross-tenant operations require an explicit `delegates_to` edge — implicit cross-tenant ops are HARD-stopped by HS-3 (NATIVE-ENGINE.md §2.8; ADR-006).

There are TWO Tenant artifacts in Native canon — disambiguation per the native-author-part skill slug convention:

- **Tenant primitive** (this file, `primitives/tenant.md`) — the typed runtime contract.
- **Tenant surface** (`surfaces/tenant.md` — Phase 8) — the operator-facing CLI/UX layer (`sutra tenant list`, etc.).

## Type signature (TypeScript-style)

```typescript
type Tenant = {
  id: string;                       // T-hash — content-addressed
  name: string;                     // non-empty
  isolation_contract: object;       // filesystem + capability isolation declaration
  parent_tenant_id: string | null;  // null for root Tenant
  audit_log_path: string;           // absolute path to Tenant's DecisionProvenance JSONL
};
```

## Invariants (must hold)

- **Content-addressed id**: `id = sha256(canonical_form(tenant))`. Immutable; any field change yields a new Tenant id and a new mint.
- **Non-empty name**: `name` MUST be non-empty (NATIVE-ENGINE.md §2.8).
- **Root tenant rule**: `parent_tenant_id === null` IFF this is the root Tenant. Otherwise `parent_tenant_id` MUST resolve to an existing Tenant.
- **Absolute audit path**: `audit_log_path` MUST be an absolute filesystem path (NATIVE-ENGINE.md §2.8 row). Persistence-layer reject on relative paths.
- **I-13 (Domain-Tenant binding)**: every Domain has a non-null `tenant_id` referencing this Tenant or a sibling — the binding is required at Domain mint (ADR-006).
- **I-8 (boundary discipline)**: Tenant boundary is NOT crossed without an explicit `delegates_to` edge. Implicit crosses emit `tenant_boundary_violation` (§3.2 #26) — HS-3 fires.
- **Isolation_contract enforcement**: the `isolation_contract` object declares filesystem + capability isolation; runtime enforcement is via TenantIsolation.assertCrossTenantAllowed (§3.1) — throws on deny.

## Lifecycle (created → terminal states)

1. **Mint**: founder (or governance Workflow) emits Tenant JSON; LiteExecutor validates non-empty name + absolute audit_log_path + parent_tenant_id resolution (or null for root); content-addressed id computed; row persisted to user-kit Tenants registry.
2. **Active**: Tenant available for reference by Domains (`tenant_id`), Workflows (`custody_owner`), and Executions (`tenant_context.tenant_id`). DecisionProvenance rows append to `audit_log_path`.
3. **Subtenant mint**: child Tenants may be minted with this Tenant's id as `parent_tenant_id` — extends the isolation tree.
4. **Cross-tenant ops**: when an Execution attempts a cross-tenant op, TenantIsolation.assertCrossTenantAllowed evaluates the `delegates_to` graph; if denied, throws and emits `tenant_boundary_violation` (§3.2 #26).
5. **Terminal**: NOT specified in canon §2.8. Tenants are effectively permanent once minted in v1.0. Tenant decommission semantics (audit log archival, child re-parenting) are runtime implementation choices; future ADR may codify.

Note on I-14: Tenant is not an Execution; I-14's terminal-event set does NOT apply to Tenant lifecycle.

## Serialization (JSONL row shape)

User-kit registry rows at `~/.sutra-native/user-kit/tenants/T-<hash>.json` (single Tenant JSON per file):

```jsonl
{"id":"T-<hash>","name":"<string>","isolation_contract":{...},"parent_tenant_id":"T-<hash>|null","audit_log_path":"/abs/path/to/T-<hash>/decision-provenance.jsonl","ts_minted_ms":<unix-ms>}
```

Index at `~/.sutra-native/user-kit/tenants/INDEX.jsonl` enumerates `{id, parent_tenant_id, audit_log_path, ts_minted_ms}` for fast lookup. The Tenant's audit log is a separate JSONL file written to `audit_log_path` (typically under `~/.sutra-native/user-kit/audit/T-<hash>/`), append-only per ADR-013.

## Cross-primitive references

- **Domain** (`../primitives/domain.md`): I-13 binds every Domain to exactly one Tenant via `Domain.tenant_id`.
- **Workflow** (`../primitives/workflow.md`): `Workflow.custody_owner: TenantId | null` declares state ownership.
- **ExecutionResult** (`../primitives/execution-result.md`): `ExecutionResult.tenant_context.tenant_id` binds the Execution to a Tenant for I-8 enforcement.
- **EngineEvent** (`../primitives/engine-event.md`): event #26 `tenant_boundary_violation` (HS-3) on illegal cross-tenant ops.
- **DecisionProvenance** (`../primitives/decision-provenance.md`): `scope === 'TENANT'` decisions cite this Tenant; rows append to `audit_log_path`.
- **Charter** (`../primitives/charter.md`): Charter ACL is per-Tenant; cross-tenant access requires explicit ACL entry.

## References

- NATIVE-ENGINE.md §2.8 — canonical Tenant field table.
- NATIVE-ENGINE.md §4 — I-8 (boundary discipline), I-13 (Domain-Tenant binding).
- NATIVE-ENGINE.md §3.1 — `TenantIsolation.assertCrossTenantAllowed` signature.
- NATIVE-ENGINE.md §3.2 #26 — `tenant_boundary_violation` event.
- NATIVE-ENGINE.md §6.2 — multi-tenant isolation runtime operations.
- ADR-006 — multi-tenant isolation primitive.
- ADR-013 — audit log persistence + fsync.
- HS-3 — tenant boundary hardstop.
