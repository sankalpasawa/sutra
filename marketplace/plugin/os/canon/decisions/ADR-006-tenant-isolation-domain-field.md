<!-- MIRROR (read-only distribution copy). Canonical: sutra/os/decisions/ADR-006-tenant-isolation-domain-field.md. -->
# ADR-006 — Tenant Isolation via `Domain.tenant_id`

## Status
Accepted 2026-05-07 (formalized as part of Native formalization v1.0). Charter contract: see `sutra/os/engines/NATIVE-ENGINE.md` §2.1, §2.8, §6.2; invariants I-8, I-13.

## Context
Multi-tenant isolation requires the engine to refuse a Workflow under Tenant A from reading Tenant B's resources without an explicit delegation. The system already had two adjacent constructs that were proposed as the carrier:

- **Cohort** — batch-targeting primitive (e.g. "all T2 owned" or "T4 fleet"); routing label, not isolation boundary.
- **D33 settings.json firewall** — bidirectional deny rules at the Claude Code config layer; intent-level, not capability-enforced.

Sources `holding/research/2026-04-29-native-d1-authority-map.md` §3 S-TENANT and `holding/research/2026-04-29-native-d4-primitives-composition-spec.md` §1.1 surfaced an explicit gap (gap-audit `PS-7 / Q1`): Cohort was being conflated with Tenant in some prose, but the two primitives have different invariants and overload risks correctness.

### Alternatives considered
- Reuse Cohort for tenant ownership — rejected because Cohort is a routing/targeting primitive (a Workflow can target multiple Cohorts; a Domain belongs to exactly one Tenant). Conflation breaks I-8.
- Rely solely on D33 settings.json deny — rejected because it is intent-level (Claude Code config), not enforced by Native at primitive-mint or execution time. No invariant guard.

## Decision
Native engine MUST model tenant isolation as a first-class required field `Domain.tenant_id` (T-hash) referencing a `Tenant` primitive.

- Every Domain belongs to exactly one Tenant (I-13 — required field, no nullable).
- `Execution.tenant_context` carries `{tenant_id}` and `TenantIsolation.assertCrossTenantAllowed(src, dst, op)` is called unconditionally when a step touches a different tenant.
- Cross-tenant ops without an explicit `delegates_to` edge fail-closed and emit `tenant_boundary_violation` (HS-3, I-8).
- D33 settings.json firewall stays as a defense-in-depth layer at the Claude Code config; Native does NOT depend on it.

## Consequences

| Kind | Effect |
|---|---|
| + | Tenant boundary is a typed schema field — checked at primitive-mint AND execution |
| + | Audit trail records every cross-tenant attempt (success or violation) |
| + | Cohort stays clean as routing primitive; Workflow can target multi-cohort within one tenant |
| − | Migration cost: every existing Domain must be assigned a `tenant_id` (no default) |
| − | Hierarchical / nested tenancy (multi-level parent_tenant_id) is declared in schema but execution semantics are v1.x backlog |
| 0 | OS-17 open seam: first multi-cohort routing use case may revisit Cohort vs Tenant separation |
