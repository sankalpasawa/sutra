---
part-id: C2
bucket: components
template: L8-feature-spec
parity-source: ADR-023 (net-new; post-cutover canon, not from pre-cutover monolith)
status: DRAFT v0.1 — LLD, PARKED pending HLD lock (see components/INDEX.md)
authored: 2026-06-13
---

# C2: Charter + Domain Browser (UI Kit component)

> **PARKED — LLD.** Gated behind HLD lock (components/INDEX.md). Dual-lane verdict: PASS-WITH-MODIFY (cleanest of the three — no ADR-022 dependency, reads durable registry only). Note: domain-tree / charter-viewer projections are attributed to the **Authority+Tenancy** block (their governance home), with persistence in System of Record. Inherits P6 (default-quiet · operator-tunable · no surface inversion) per ADR-023 Decision 4 — for a read-only browser, P6 = no auto-expansion of sensitive sub-trees.

## 1-line summary

Read-only navigator of the Domain authority tree (D-numbered scopes + subdomains) and the Charters attached to each Domain — operator can walk the tree and open any Charter to see its purpose, scope, obligations, invariants, success metrics, ACL, and termination conditions. Gives the named-but-unspec'd Charter Console Module (§1.4) its spec base.

## Category

UI Kit **component** (ADR-023 Decision 2). Two sub-views (domain tree + charter viewer) that the Charter Console Module composes alongside C1 (Approval Inbox).

## Scope (in / out)

**In scope (v1)**:
- Render the Domain tree from `D0` down via `parent_id` chains (domain.md): id, name, accountable role, append-only principles, authority scope, owning tenant.
- Render a Charter detail view (charter.md): purpose, scope_in/scope_out, obligations, invariants, success_metrics, constraints, ACL, cutover_contract (if any), termination — all read-only.
- Show, per Domain, which Charters attach to it (via Charter.authority + ACL).
- Cross-tenant tree traversal ONLY under an explicit delegated read capability (ADR-023 Decision 3); default is tenant-scoped deny.

**Out of scope (v1)**:
- Editing/minting Charters or Domains (Charters are immutable content-addressed `C-<hash>`; a change mints a NEW Charter — that is the existing engine path, not a browser concern).
- DecisionProvenance drill-down per obligation (that is C-future / the System-of-Record audit browser, ADR-023 Decision 3 SoR row).
- Live obligation-satisfaction status (whether each obligation currently holds — depends on PolicyDispatcher evaluation surfacing; flag as gap).

## User outcome

> "I can see every domain and subdomain running, and read exactly what each charter promises — what's in scope, what it must always hold, who can touch it."

This is the founder's request verbatim ("users will want to see various domains and subdomains and charters of what is exactly running").

## Read model (ADR-023 Decision 1b — sourced, truth-class-tagged)

| Field group | Source block | Truth-class |
|---|---|---|
| Domain tree (id, name, parent_id, accountable, principles, authority, tenant_id) | System of Record / user-kit registry (`domains/<id>.json` + `INDEX.jsonl`) | authoritative / durable |
| Charter detail (purpose, scope, obligations, invariants, metrics, ACL, termination) | System of Record / user-kit registry (`charters/C-<hash>.json`) | authoritative / durable |
| Charter→Domain attachment edges | derived from Charter.authority + ACL | authoritative / durable |

> Note: unlike C1/C3, C2 reads ONLY durable registry state — it has **no ADR-022 #1 dependency** and can ship at full fidelity today.

## Exposure-contract row (ADR-023 Decision 3 field schema)

```
projection: charter-domain-browser
source_blocks: [Authority+Tenancy, System of Record]
truth_class: authoritative (registry reads)
tenant_scope: operator's tenant subtree by default; cross-tenant nodes require delegated read capability
required_capability: read:domain:<id> / read:charter:<C-hash>
redaction: ACL entries + cross-tenant principals hidden absent capability; charter obligations naming other tenants masked
freshness: registry read latency (no live recompute)
auditable: read access itself logged per AUDIT surface where capability-gated
```

## UX flow (narrative)

1. Operator opens the browser → C2 reads the domain registry INDEX and renders the `D0`-rooted tree (tenant-scoped).
2. Operator expands a Domain → sees its principles, accountable role, authority scope, and the list of attached Charters.
3. Operator opens a Charter → read-only detail view of purpose/scope/obligations/invariants/metrics/ACL/termination.
4. A subdomain owned by a different tenant renders only if the operator holds a delegated read capability; otherwise it shows as a sealed node ("cross-tenant — access not granted").

## Acceptance criteria (Given / When / Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | A domain tree D0 → D1 → D1.D2 in the operator's tenant | operator opens C2 | full tree renders with each node's accountable role + principles; leaf-to-root parent chain is navigable |
| 2 | A Domain with 3 attached Charters | operator expands that Domain | all 3 Charters listed; opening one shows obligations + invariants + ACL read-only |
| 3 | A subdomain owned by another tenant, operator lacks delegated capability | tree renders | that node appears sealed (name only or hidden per redaction); its Charters are not readable |
| 4 | A Charter with a `cutover_contract` | operator opens it | rollback gate + behavior_invariants + canary_window render; nothing is editable |
| 5 | operator attempts any edit/mint action | (no such control exists) | component exposes no write path; mint/amend routes through the existing engine API, out of scope |

## Dependencies

- domain.md · charter.md · tenant.md · ADR-006 (tenant isolation) · I-13 (Domain owned by one Tenant) · I-16 (commitment_broken cites Charter obligation).
- No ADR-022 #1 dependency (durable registry reads only).

## Open gaps

- Live obligation-satisfaction status (does each invariant currently hold?) needs PolicyDispatcher to surface evaluation state — deferred; v1 shows the declared contract, not its live compliance.
- Whether principle-level diffs across Domain versions are shown (principles are append-only) — deferred.
