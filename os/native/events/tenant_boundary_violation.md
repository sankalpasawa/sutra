---
part-id: tenant_boundary_violation
bucket: events
template: L9-event-spec
parity-source: §3.2 row #26
parity-source-sha256: 3ad25a1f9cec35577602841da6748f2b073c69d123dbf6c4f01f2de3a5ffd98b
status: DRAFT v1
authored: 2026-05-09
---

# tenant_boundary_violation

## Purpose

Signals that a cross-tenant operation was attempted without a TenantDelegation edge (per §3.2 row #26 + HS-3 + ADR-006). Fail-closed per I-8: the operation is blocked, the event records the attempt for audit + escalation. STRIDE: Information Disclosure (per §7 threat model).

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "tenant_boundary_violation",
  "source": "/native/runtime/tenant-isolation",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "src_tenant": "<T-hash>",
    "dst_tenant": "<T-hash>",
    "op": "<sanitized operation descriptor>",
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #26: `src_tenant`, `dst_tenant`, `op`.

## Emitter

TenantIsolation engine (`TenantIsolation.assertCrossTenantAllowed` per §3.1; exclusive emitter). Fires when `assertCrossTenantAllowed(src, dst, op)` would throw (cross-tenant op attempted; no `delegates_to` edge present per I-8).

## Consumers

- AUDIT surface — persists per ADR-013.
- HS-3 escalation path — per §6.9 HS-3 "Block + log + escalate". The violation is recorded and routed to founder HITL.
- Telemetry sink (§5.6) — tenant-boundary violation count (security alerting signal).
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, HS-3 escalation router, security alerting.

## Ordering invariants

- Not bound to a specific Execution lifecycle event; may fire at any point a cross-tenant op is attempted.
- Per I-8 (Tenant boundary not crossed without delegation), this event records the attempt; the operation itself is BLOCKED — no downstream `step_completed` (#6) for the offending step.

## Replayability

- **Idempotent on replay**: informational; the operation is blocked at the boundary, so replay does not change state.
- **Audit-critical**: required for cross-tenant security audit + STRIDE Information Disclosure trace.
- **Fail-closed on emission failure** (per HS-4): emission failure across all 3 channels fires HS-4; per ADR-013 the stderr beacon is last-resort. No fail-open semantic. HS-3 + HS-4 stack: even if audit fails, the BLOCK at HS-3 holds (the cross-tenant op never proceeded).

## References

- NATIVE-ENGINE.md §3.2 row #26.
- NATIVE-ENGINE.md §3.1 Engine API (`TenantIsolation.assertCrossTenantAllowed`).
- NATIVE-ENGINE.md §4 I-8 (Tenant boundary invariant), I-13 (Domain.tenant_id required).
- NATIVE-ENGINE.md §6.2 Multi-tenant isolation.
- NATIVE-ENGINE.md §6.9 HS-3 (Tenant boundary cross attempted without TenantDelegation).
- NATIVE-ENGINE.md §7 Threat Model (Information Disclosure row).
- ADR-006 — Tenant primitive + delegates_to edges.
- ADR-013 — 3-channel audit durability.
- ../primitives/tenant.md
- ../hardstops/HS-3-tenant-boundary.md
- ../hardstops/HS-4-audit-unwritable.md
