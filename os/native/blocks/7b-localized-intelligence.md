---
part-id: 7b
bucket: blocks
template: L8-feature-spec
parity-source: §12.6 row 7b + §12.5 round 2 founder voice
parity-source-sha256: 7b1da26d66897fc67cf9492b75c1bacb0a7aba867ce8b9a2b437cb1ec324936b
status: DRAFT v1
authored: 2026-05-09
---

# 7b: Localized Intelligence

## 1-line summary

Per-task context-window declaration so the LLM's attention is localized to the task's relevant context — Tenant + Project + Workflow scoping turns global artifact catalog into a task-specific working set.

## Scope (in / out)

**In scope (v1)**:
- Per-task context scope primitive per §12.6 row 7b — explicit context-window declaration on the Workflow / step.
- Tenant + Project + Workflow scoping (uses existing Tenant.tenant_id isolation per §6.2 + Workflow.scope_in / scope_out per §2.3 partial).
- Localized model attention — LLM call receives only artifacts that match the declared scope (composed with 7a context-structuring retrieval).

**Out of scope (v1)**:
- Project primitive as first-class container — deferred per §12.3 row 1 (capability-1 gap; queued).
- Cross-scope leakage detection beyond canon Tenant isolation (HS-3) — gap per F2.
- Dynamic scope adjustment mid-execution (operator widens / narrows scope while step runs) — overlaps 7e (mid-exec mutation).

## User outcome

Operator runs a task and Native's reasoning is localized to that task's relevant context — not a global dump. Founder voice round 2: "for localized intelligence, it can use that particular context".

## UX flow (narrative; terminal + audit log)

1. Workflow declares scope via `Workflow.scope_in` / `Workflow.scope_out` (canon §2.3 partial — 7b extends this).
2. At step fire, 7b composes with 7a retrieval — retrieval applied to artifacts within the declared scope only.
3. LLM call receives only in-scope artifacts.
4. Cross-scope read attempt → routed via canon TenantIsolation engine per §6.2 → HS-3 fires.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Workflow declares `scope_in=['domain-A']` | step fires | only artifacts in domain-A returned by retrieval (per §2.3 partial + 7a composition) |
| 2 | Workflow attempts to read artifact outside declared scope | TenantIsolation engine evaluates per §6.2 | `tenant_boundary_violation` (§3.2) emitted; HS-3 fires (cross-ref `../hardstops/HS-3-tenant-boundary.md`); fail-closed per F3 |
| 3 | No scope declared on Workflow | step fires | default scope = Tenant-wide (canon §6.2); specific default behavior NOT specified in canon (gap per F2) |
| 4 | Cross-Charter delegation requested per Q28 default 2026-05-09 | delegation evaluates | audit-logged per Q28 default; not blocked v1 |

## Data model

Per §12.6 row 7b: 7b EXTENDS existing Workflow.scope_in / scope_out + Tenant.tenant_id. No new §2 primitive (per F5).

Per Q28 default (§12.11) — cross-Charter delegation is default v1 (audit-logged); per-Workflow override deferred v2.

Cross-refs:
- `../primitives/workflow.md` (scope_in / scope_out fields)
- `../primitives/tenant.md` (Tenant.tenant_id boundary)
- `../primitives/charter.md` (Charter-level context per B4)

## Edge cases

- **Empty scope_in** → fallback to Tenant-wide default (canon-silent on exact semantic; gap per F2).
- **scope_in AND scope_out overlap** → conflict-resolution rule NOT specified in canon (gap per F2; future ADR may codify).
- **Cross-Charter delegation cascade** → audit-logged per Q28 default; specific cascade-depth limit NOT specified in canon (gap per F2).
- **Operator changes scope mid-Workflow** → overlaps 7e (mid-exec mutation); routed via 7e's mutation gating.

## Telemetry

Events (canon-existing):
- `routing_decision` (§3.2 #1) — when scope routing applies.
- `policy_decision` — scope-policy evaluation.
- `tenant_boundary_violation` — on out-of-scope read.

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Operator-Hours-Saved — localized attention reduces irrelevant-context reasoning waste.
- Pattern-detection precision — narrower context = sharper proposals.

## Dependencies

- **Primitives**: `workflow`, `tenant`, `charter`, `engine-event`.
- **Events**: `routing_decision`, `policy_decision`, `tenant_boundary_violation`.
- **Surfaces**: `route`, `run`, `audit`, `tenant` (cross-ref `../surfaces/tenant.md`).
- **Hardstops**: HS-3 (tenant-boundary).
- **Blocks**: 7a (composes with retrieval), B4 (Charter-context boundary), B11 (PromptBuilder consumes scoped artifact set).
- **Pillars**: P5 (MECE domains), P11 (Constrained problem construction).

## References

- NATIVE-ENGINE.md §12.6 row 7b (founder voice round 2 — localized intelligence).
- NATIVE-ENGINE.md §2.3 (Workflow scope_in / scope_out partial).
- NATIVE-ENGINE.md §6.2 Tenant isolation.
- Q28 (§12.11) — cross-Charter delegation default v1.
