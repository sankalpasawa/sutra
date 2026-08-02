---
part-id: B3
bucket: blocks
template: L8-feature-spec
parity-source: §12.9 row B3 + §12.8 founder voice round 3 + §10.2 P5 + Q21
parity-source-sha256: 5b0a125778091070e6c33a34e729112dfaa4f63b2c607eafdad5f0cb19fd4e06
status: DRAFT v1
authored: 2026-05-09
---

# B3: Domain Hierarchy (MECE)

## 1-line summary

Domains are MECE (Mutually Exclusive, Collectively Exhaustive) per user — every Workflow lives in exactly one Domain, no overlap, together they cover the user's full surface.

## Scope (in / out)

**In scope (v1)**:
- EXTEND existing Domain primitive (§2.1) with MECE-validation invariant per §12.9 row B3.
- Every Workflow lives in exactly one Domain (per Q21 confirmed 2026-05-09 — "MISI kind of domains" reads as MECE).
- No Domain overlap — invariant enforced at Workflow registration time.
- Together the user's Domains cover the operator's full surface (collectively exhaustive).

**Out of scope (v1)**:
- Dynamic Domain reorganization mid-Workflow — now owned by [B20](./B20-domain-restructure.md) (operator-invoked restructure).
- ~~Auto-creating new Domains from emergent patterns — defers to canon ADR-010 organic emergence~~ — **SUPERSEDED by [ADR-028](../../decisions/ADR-028-mandatory-work-placement.md) / [B19](./B19-work-placement.md)**. The original deferral was broken: ADR-010 proposes **Workflows** at k≥4, never Domains, so this hole had no owner. B19 now owns Domain auto-creation, at k=1, system-decided, never operator-gated.
- Cross-user Domain federation — multi-human-org per B14.

**Scope extension (ADR-028)**: B3 bound only **Workflows**, and only at registration time. Work executed outside a registered Workflow — inline utterances, ad-hoc edits, commits — was never bound to any Domain. [B19](./B19-work-placement.md) extends the binding to every unit of work via the [Placement](../primitives/placement.md) primitive, and [B20](./B20-domain-restructure.md) makes this block's MECE assertion mechanically checkable for the first time.

## User outcome

Operator's surface is cleanly partitioned — every piece of work has a clear home Domain; nothing falls between Domains. Founder voice round 3: "different contexts of different things ... MISI [MECE] kind of domains ... different parts of MySystem set up for a particular user".

## UX flow (narrative; terminal + audit log)

1. Tenant has N Domains declared (per §2.1).
2. Workflow registration submits Workflow with declared `domain_id`.
3. B3 invariant check: `domain_id` exists AND Workflow does not overlap another Domain's scope.
4. Pass → Workflow registered; Fail → registration rejected.
5. Periodic surface check (canon-silent on cadence — gap per F2) verifies collective exhaustiveness.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Workflow declares `domain_id` matching exactly one Domain | registration fires | Workflow accepted; MECE invariant holds |
| 2 | Workflow declares scope that overlaps another Domain | invariant check evaluates | registration rejected; specific error shape NOT specified in canon (gap per F2) |
| 3 | Workflow declares non-existent `domain_id` | invariant check | registration rejected per canon (Domain.tenant_id integrity per §2.1) |
| 4 | Tenant has gaps in Domain coverage | surface check fires | surfaced to operator (specific notification mechanism NOT specified in canon — gap per F2) |

## Data model

Per §12.9 row B3: EXTEND existing Domain (§2.1) with MECE-validation invariant. No new §2 primitive (per F5).

Canon §2.1 Domain primitive carries `tenant_id`. B3 adds invariant (declared, not new field): "exactly-one Domain per Workflow; non-overlapping per Tenant".

**Defect fix (ADR-028)**: the UX flow above and the cross-ref below originally cited `Workflow.domain_id` — a field that did not exist on the Workflow primitive. B3's MECE check was therefore specified against a phantom and could never have run. The field is now materialised as `Workflow.domain_ref`, keyed on the Domain's **stable** id rather than its positional D-path (placement.md I-P8). Read every `domain_id` reference in this file as `domain_ref`.

Cross-refs:
- `../primitives/domain.md` (host)
- `../primitives/workflow.md` (`Workflow.domain_ref` — materialised by ADR-028)
- `../primitives/placement.md` (extends the binding from Workflows to every unit of work)
- `../primitives/tenant.md` (Tenant boundary)

## Edge cases

- **Domain split** (operator splits one Domain into two) → migration semantics NOT specified in canon (gap per F2).
- **Two Tenants share a Domain** → not v1; Tenant isolation per §6.2 forbids cross-Tenant Domain sharing.
- **Workflow needs context from multiple Domains** → cross-Domain delegation pattern overlaps B4 (Charter ↔ Context Boundary); Q28 default = cross-Charter delegation audit-logged.
- **Gap in Domain coverage** (collectively exhaustive violated) → surfacing mechanism NOT specified in canon (gap per F2).

## Telemetry

Events (canon-existing only):
- `policy_decision` (§3.2) — MECE invariant evaluation as a policy decision.
- `tenant_boundary_violation` (§3.2) — if cross-Tenant Domain access attempted.

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Operator-Hours-Saved (long-tail) — clean Domain partitioning reduces context-discovery overhead.

## Dependencies

- **Primitives**: `domain`, `workflow`, `tenant`.
- **Events**: `policy_decision`, `tenant_boundary_violation`.
- **Surfaces**: `tenant` (cross-ref `../surfaces/tenant.md`), `route`, `audit`.
- **Hardstops**: HS-3 (tenant-boundary), HS-4 (audit-unwritable).
- **Blocks**: B4 (Charter ↔ Context Boundary — Domain is the parent of B4's Charter scope), 7b (localized intelligence respects Domain boundary).
- **Pillars**: P5 (MECE domains) — B3's anchor.

## References

- NATIVE-ENGINE.md §12.9 row B3 (founder voice round 3).
- NATIVE-ENGINE.md §2.1 Domain primitive.
- NATIVE-ENGINE.md §10.2 P5 (MECE domains).
- Q21 (§12.11) — "MISI" confirmed as MECE.
- ADR-006 (Tenant isolation).
