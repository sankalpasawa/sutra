---
part-id: B20
bucket: blocks
template: L8-feature-spec
parity-source: net-new (ADR-028); post-cutover canon, not from pre-cutover monolith
status: DRAFT v1
authored: 2026-07-27
peer-review: deepseek consult 2026-07-27 — auto-apply consolidation for system-minted nodes folded (P1)
---

# B20: Domain Restructure + Consolidation

## 1-line summary

The path by which the Domain tree gets corrected — five operator-invoked operations (rename, merge, split, move, delete), plus a consolidation pass that may auto-apply merges **only** for nodes the system itself minted and the operator never touched.

## Scope (in / out)

**In scope (v1)**:
- Five operator-invoked operations: RENAME, MERGE, SPLIT, MOVE, DELETE.
- Charter re-homing when its Domain is merged, moved, or deleted.
- MECE re-validation after every operation — a result violating P5 rejects the whole operation.
- **Consolidation pass** with two tiers: auto-apply for system-minted untouched nodes; propose-only for everything else.
- Mechanical MECE checking (see below) — the guarantee becomes computable rather than asserted.

**Out of scope (v1)**:
- Automatic invocation of the five *operator* operations. Those run only when the operator asks (ADR-028 Decision 1).
- Editing Charter obligations. B20 moves Charters between Domains; it does not author promises.
- Cross-tenant restructure — a Domain cannot move between Tenants (I-13).
- Transactional undo; v1 offers reconstruction from superseded Placement rows.

## User outcome

> "When the tree the system built is wrong, I fix it in one pass, and everything that lived under the old shape follows automatically — and the system quietly cleans up its own duplicate guesses without bothering me."

Founder direction 2026-07-27: *"It is not left to the user unless the user explicitly asks to restructure the domains and make that a separate feature."*

## Why re-placement is now cheap (peer-review P1, folded)

Placement rows key on `domain_ref` — a **stable** id — not on the positional `domain_path` (I-P8). Consequences for every operation below:

| Operation | Placements re-minted? | Why |
|---|---|---|
| RENAME | none | name is display metadata |
| MOVE | **none** | position changes; `domain_ref` does not |
| SPLIT | only reassigned rows | members genuinely change domain |
| MERGE | only rows on the absorbed node | their `domain_ref` genuinely changes |
| DELETE | only rows on the deleted node | re-point to parent |

The original design keyed on the dotted path, which meant one MOVE re-minted every Placement in the subtree — millions of rows under load. That defect is closed at the primitive, so B20's expensive operation is now cheap.

## The two-tier consolidation pass

The pass is B20's answer to the drift B19 creates. Because the system mints freely and never asks, near-duplicate siblings accumulate — and a purely propose-only scan cannot keep pace with an auto-minting producer.

| Tier | Applies to | Behaviour |
|---|---|---|
| **AUTO** | Domains with `origin=system-minted` AND never renamed, never hand-edited, no operator-authored principles, similarity above the high threshold | **Merged automatically.** No operator prompt. The system is cleaning up its own guesses, not overriding an operator decision |
| **PROPOSE** | Anything the operator has ever touched, or similarity between thresholds | Surfaced as a proposal with evidence. Operator decides |

This is consistent with ADR-028 Decision 1 rather than an exception to it: Decision 1 gives the *system* authority over the taxonomy and reserves *operator* authority for what the operator has touched. Auto-merging two of the system's own untouched guesses stays entirely inside the system's lane. The moment an operator edits a node, it becomes theirs and drops to PROPOSE forever.

## Mechanical MECE checking (peer-review P2, folded)

P5 asserts MECE; nothing computed it. B20 makes it checkable:

- **Mutual exclusion**: for every sibling pair, compute overlap across name, principles, and the evidence signature of their Placements (file paths, artifact classes). Pairs above the overlap threshold are flagged as ME violations.
- **Collective exhaustion**: every work unit in the tenant resolves to exactly one current Placement. Any unaddressed work unit is a CE violation.
- Output is a **MECE report** — violation counts by kind, worst offending pairs, trend against the previous run.

The report is what makes P5's falsification test runnable instead of rhetorical.

## The five operations

| Op | What it does | What follows |
|---|---|---|
| **RENAME** | Change `name`; stable id unchanged | Display updates. Zero re-placement. Node drops to PROPOSE tier permanently |
| **MERGE** | Fold Domain B into Domain A | Placements on B re-point to A; B's Charters re-home; B's principles append to A |
| **SPLIT** | Divide A into A plus new children | Placements under A re-classify; ambiguous rows surface for operator choice |
| **MOVE** | Re-parent a Domain and its subtree | Display paths change for the subtree. **Zero re-placement** (I-P8) |
| **DELETE** | Remove a Domain | Its Placements re-point to the parent; its Charters re-home. Deleting the root is forbidden |

## UX flow (narrative)

1. Operator invokes restructure explicitly — by command or in words.
2. B20 renders the tree with per-node Placement counts, so the operator sees weight, not just shape.
3. The MECE report renders alongside: current violations and trend.
4. Consolidation runs. AUTO-tier merges are applied and **reported** (not asked). PROPOSE-tier candidates are listed.
5. Operator selects operations from the proposal list plus any of their own.
6. B20 shows the blast radius before applying: rows re-pointed, Charters re-homed, display paths changed.
7. Operator confirms. Operations apply. `domain_restructured` emits. MECE re-validation runs; a P5-violating result rejects the whole operation.

## Acceptance criteria (Given / When / Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Two system-minted, never-touched siblings above the high similarity threshold | consolidation runs | **merged automatically**; operator informed, not asked; `domain_restructured` emitted with `tier=auto` |
| 2 | Two siblings, one renamed by the operator last month | consolidation runs | **not** auto-merged; surfaced as a PROPOSE candidate with evidence |
| 3 | Operator moves a Domain under a different parent | move applies | display paths change for the whole subtree; **zero Placement rows re-minted**; blast radius reported as 0 |
| 4 | Operator merges B into A | merge applies | Placements on B get superseding rows pointing at A; old rows retained; B's Charters re-home to A |
| 5 | An operation would leave two Domains overlapping | MECE re-validation runs | operation rejected in full; tree unchanged; violating pair named |
| 6 | Operator deletes a Domain holding 40 Placements | delete applies | all 40 re-point to the parent; zero orphans |
| 7 | Operator attempts to delete the root | delete attempted | rejected — root has no parent to absorb its Placements |
| 8 | Nobody invokes B20 for six months | time passes | operator operations never fire. AUTO consolidation still runs on system-minted nodes, so drift is bounded even under total operator neglect |
| 9 | A restructure would move a Domain across Tenants | attempted | rejected per I-13; `tenant_boundary_violation` emitted |
| 10 | MECE report run twice with no changes between | second run | identical violation set; the check is deterministic |

## Data model

No new primitive. Operates on `../primitives/domain.md`; mints superseding `../primitives/placement.md` rows only where `domain_ref` genuinely changes.

New event `domain_restructured` carries `{operation, tier: 'auto'|'operator', before_refs[], after_refs[], placements_repointed, charters_rehomed}`.

## Edge cases

- **Split with ambiguous members** → rows the classifier cannot confidently assign surface as a short list. The one place B20 asks a question, and only because the operator already chose to restructure.
- **Restructure mid-execution** → in-flight Executions complete against their existing Placement; new addresses apply to subsequent work (composes with 7e).
- **AUTO merge of two nodes the operator is about to edit** → operator edits always win going forward; the merge is reported and reversible via a subsequent operator SPLIT.
- **Merge of Domains with conflicting principles** → principles are append-only, so both sets survive. Contradictions surface; they are not silently resolved.

## Telemetry

Events: `domain_restructured` (new), `placement_assigned` (superseding rows), `policy_decision`, `tenant_boundary_violation`.

Metrics:
- **MECE violation count** — the number consolidation drives down; the runnable form of P5's falsification test.
- **Auto-merge rate** — how much the system cleans up unprompted. Rising rate means B19's classifier is minting noise.
- **Operator restructure frequency** — how often a human must intervene. The real measure of whether Decision 1 is working.

## Dependencies

- **Primitives**: `domain`, `charter`, `placement`, `tenant`.
- **Blocks**: B19 (produces what B20 corrects), B3 (MECE rule), B13 (concurrency), 7e (mid-execution mutation).
- **Pillars**: P5 (MECE), P6 (operator controls explanation).
- **Hardstops**: HS-3.
- **ADRs**: ADR-028 Decision 1 + peer-review fold.

## References

- ADR-028 — system decides; operator corrects; consolidation tiers.
- B19 (`./B19-work-placement.md`) — the producer this block corrects.
- P5 (`../pillars/P5-mece-domains.md`) — the invariant now mechanically checked.
- deepseek consult 2026-07-27 — auto-apply tier and mechanical MECE checking originate here.
