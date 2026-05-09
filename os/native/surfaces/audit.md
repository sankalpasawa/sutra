---
part-id: AUDIT
bucket: surfaces
template: L9-surface-spec
parity-source: §14.7 + §3.2 (full 26) + §2.7 + §2.9 + §5.6 + §6.1 + §6.9 HS-4
parity-source-sha256: 47da900838392f4721393b88412b6b64db6eec9bc522113e13e9ccd2fbc62e23
status: DRAFT v1
authored: 2026-05-09
---

# Surface: AUDIT

## Purpose

Every state transition across every surface emits exactly one typed EngineEvent + (for consequential decisions) one DecisionProvenance row. AUDIT is the persistence + replay surface for those rows.

Canon: §14.7 row 5 — *"AUDIT | Every transition emits typed EngineEvent + DecisionProvenance"*.

## Interface (operator-facing)

AUDIT is not directly invoked. Every other surface (ROUTE/RUN/GATE/EMERGE/TENANT) calls `UserKit.appendDecisionProvenance(dp)` (§3.1) or emits EngineEvent rows that AUDIT persists.

Read-side surfaces:
- DecisionProvenance JSONL — append-only telemetry sink (§5.6).
- EngineEvent JSONL — append-only audit log per Tenant at `Tenant.audit_log_path` (§2.8).
- Replay surface: §6.1 — every consequential decision rebuildable from `agent_identity + policy_id + policy_version + data_refs + outcome`.

## Invariants (must always hold)

| # | Invariant | Source |
|---|---|---|
| AUDIT-I1 | Every state transition across every surface produces ≥1 EngineEvent row (append-only). | §14.7 row 5 + §2.7 ("Append-only typed audit row") |
| AUDIT-I2 | Every consequential decision (per I-7) produces exactly one DecisionProvenance row. | I-7 + §2.9 |
| AUDIT-I3 | EngineEvent ordering: `ts_ms` is monotonic per process; assigned at emit. | §2.7 ts_ms invariant |
| AUDIT-I4 | DecisionProvenance `reason` field is sanitized (no colons, no newlines) — guarantees JSONL parseability. | §2.9 |
| AUDIT-I5 | DecisionProvenance is durable: fsync per append; 3-channel fallback; stderr beacon last-resort (HS-4 mitigation). | §5.6 + §6.9 HS-4 + ADR-013 |
| AUDIT-I6 | HS-4 trigger: if DecisionProvenance log is unwritable across ALL 3 channels → block ALL governance hooks; emit stderr beacon. (Fail-CLOSED on audit, never fail-open.) | §6.9 HS-4 |
| AUDIT-I7 | `policy_id` + `policy_version` are non-empty on every DecisionProvenance (F-8 + I-9). | §2.9 + I-9 |
| AUDIT-I8 | `agent_identity` chain-shaped (parent → child) per ADR-015 + OQ-D4-2; persisted on every emit. | §2.9 + §2.7 + ADR-015 |

Canon: AUDIT persists ALL 26 EngineEvent types listed in §3.2 — full catalog: routing_decision, workflow_started, workflow_completed, workflow_failed, step_started, step_completed, step_paused, policy_decision, artifact_registered, precondition_check, postcondition_check, pattern_proposed, proposal_approved, proposal_rejected, approval_requested, approval_granted, approval_denied, approval_already_handled, workflow_rollback_started, step_compensated, step_compensation_failed, workflow_rollback_complete, workflow_rollback_partial, workflow_escalated, commitment_broken, tenant_boundary_violation.

Canon gap: cross-process replay deferred per §8 OS-3. Within a single process AUDIT supports replay; cross-process is NOT specified in canon as of v1.

## Integration points

- **Primitives consumed**:
  - [`EngineEvent`](../primitives/engine-event.md) — every event is an instance.
  - [`DecisionProvenance`](../primitives/decision-provenance.md) — every consequential decision is an instance.
  - [`Tenant`](../primitives/tenant.md) — `Tenant.audit_log_path` is the per-Tenant JSONL sink.
  - [`ExecutionResult`](../primitives/execution-result.md) — `logs: EngineEvent[]` append-only field.
- **Events emitted**: AUDIT itself does not emit events — it persists events emitted by other surfaces. (Canon gap: an "audit_log_write_failed" event is not in §3.2 — HS-4 uses stderr beacon, not an EngineEvent. Implementation choice; future ADR may codify a `audit_failure` event type if cross-process replay lands.)
- **Events consumed**: all 26 types in §3.2 — full catalog persisted to JSONL.
- **Surfaces upstream**: ROUTE, RUN, GATE, EMERGE, TENANT — all upstream surfaces emit events that AUDIT persists.
- **Surfaces downstream**: replay surface (§6.1) feeds back to debugging, codex review, policy evolution; per-Tenant audit log readable by [TENANT](tenant.md) for boundary-violation forensics.

## C4 context

```
[ROUTE] -----+
[RUN]   -----+
[GATE]  -----+--> [AUDIT: UserKit.appendDecisionProvenance + EngineEvent JSONL emit]
[EMERGE]-----+              |
[TENANT]-----+              v
                    [fsync per append; 3-channel durability]
                            |
                            v
                    [Telemetry sink JSONL]
                            |
              +-------------+-------------+
              v             v             v
        [Replay §6.1]  [Per-Tenant   [HS-4 trigger:
                       audit log]    stderr beacon
                                     + block all hooks]
```

AUDIT is the substrate surface — it is invoked by every other surface and is the SINGLE source of truth for what happened, when, by whom, under which policy. HS-4 enforces fail-CLOSED semantics: if AUDIT cannot write, governance halts.

## References

- `NATIVE-ENGINE.md` §14.7 row "AUDIT"
- `NATIVE-ENGINE.md` §2.7 EngineEvent primitive
- `NATIVE-ENGINE.md` §2.8 Tenant.audit_log_path
- `NATIVE-ENGINE.md` §2.9 DecisionProvenance primitive
- `NATIVE-ENGINE.md` §3.1 `UserKit.appendDecisionProvenance` (fsync per ADR-013)
- `NATIVE-ENGINE.md` §3.2 full 26-event catalog
- `NATIVE-ENGINE.md` §5.6 Telemetry sink
- `NATIVE-ENGINE.md` §6.1 Telemetry replay
- `NATIVE-ENGINE.md` §6.9 HS-4 (DecisionProvenance unwritable)
- `NATIVE-ENGINE.md` §8 OS-3 (cross-process replay future)
- ADR-013 (durability)
- ADR-015 (agent_identity)
- `../primitives/engine-event.md` + `../primitives/decision-provenance.md` + `../primitives/tenant.md`
- `../hardstops/HS-4-audit-unwritable.md`
- `../surfaces/route.md` + `../surfaces/run.md` + `../surfaces/gate.md` + `../surfaces/emerge.md` + `../surfaces/tenant.md`
