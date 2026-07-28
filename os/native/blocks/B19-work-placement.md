---
part-id: B19
bucket: blocks
template: L8-feature-spec
parity-source: net-new (ADR-028); post-cutover canon, not from pre-cutover monolith
status: DRAFT v1
authored: 2026-07-27
---

# B19: Mandatory Work Placement (self-emergence)

## 1-line summary

Every unit of work is stamped with an address — one Domain, one Charter — **before** it executes; if no address exists the system creates one and continues, so the operator is never asked and never blocked.

## Scope (in / out)

**In scope (v1)**:
- Resolve a Domain + Charter address for every work unit before its first mutating action (I-P1).
- Match against the existing Domain tree; mint under the deepest matching ancestor when nothing matches (I-P4).
- Mint a Charter stub when the resolved Domain hosts none, with `obligations: []` plus a stated reason (I-P6).
- Emit `placement_assigned`, and `domain_minted` for each node created.
- Render the printed PLACEMENT block — expanded when something was created, compact when matched.
- Close the hole B3 line 27 left open ("auto-creating new Domains from emergent patterns → defers to ADR-010"), which ADR-010 never owned because it emits Workflows only.

**Out of scope (v1)**:
- Operator correction of the tree (rename / merge / split / move / delete) — that is B20, invoked explicitly.
- Addressing pre-existing work — B21 (on touch) and B22 (bulk scan).
- Filling Charter obligations or success metrics — never auto-generated (ADR-028 Decision 5).
- Semantic / embedding classification — v1 classifier is evidence-based (paths, utterance terms, artifact refs); F1 semantic retrieval remains v2+.
- Cross-tenant placement — forbidden; HS-3 fires.

## User outcome

> "Everything I do has a home, and I can see the home. I never stop to file paperwork, and I never have to invent the filing system."

Founder direction 2026-07-27: *"whenever someone does something, it has to be catalyzed in a domain … so that all the documentation and everything is mapped up properly"*, with the authority model set the same day: *"the system auto-decides the domains. It is not left to the user unless the user explicitly asks to restructure."*

## UX flow (narrative; terminal + audit log)

1. Operator input arrives, or a Workflow Execution is about to fire.
2. Classifier gathers evidence: utterance terms, target file paths, artifacts referenced, prior Placements for adjacent work.
3. Domain registry searched for the deepest node matching that evidence.
4. **Matched** → `origin='matched'`, compact one-line render, work proceeds.
5. **Not matched** → mint Domain as child of deepest matching ancestor; mint Charter stub if the Domain hosts none; `origin='minted'`; expanded tree render showing `[NEW]` markers; work proceeds.
6. `placement_assigned` emitted; Placement row persisted; PLACEMENT block printed.
7. Work executes. Nothing in steps 3-6 can halt it except registry-unwritable (HS-4).

## Acceptance criteria (Given / When / Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Domain `D3.D2 Native` exists and hosts Charter `"Native Canon Integrity"` | operator edits a Native part-file | Placement stamped `origin=matched`, `created={[],[]}`, compact one-line block printed, zero mint events |
| 2 | No Domain matches the work; nearest ancestor is `D3.D2` | work about to start | new Domain minted as child of `D3.D2` (never as an overlapping sibling); `domain_minted` emitted; expanded block prints with `[NEW]`; work proceeds without operator input |
| 3 | Resolved Domain hosts zero Charters | placement resolves | Charter stub minted with non-empty `title` + `purpose`, `obligations: []` and a stated reason satisfying I-2; `charter_id` non-null |
| 4 | Classifier confidence below the floor at every level | work about to start | **no child minted** (I-P9 floor-hold); work placed in the deepest matching *existing* ancestor; low-confidence event emitted for B20; **work is never blocked** |
| 4b | Two concurrent sessions resolve the same unmatched work under the same parent | both mint | atomic check-then-insert (I-P10) yields exactly ONE Domain; the loser adopts the winner's `ref` and emits `domain_minted` with `race_adopted: true` |
| 5 | Placement registry is unwritable | placement attempted | HS-4 fires (durability hardstop). This is the ONLY path that stops work, and it is a storage failure, not a taxonomy failure |
| 6 | Operator disagrees with the assigned address | operator says so | B19 offers no correction path; operator routes to B20. B19 never asks for ratification |
| 7 | Work unit already carries an authoritative Placement | work re-runs | existing Placement reused; no duplicate row; no second mint |
| 8 | Two work units in the same turn resolve to different Domains | both execute | two Placement rows, each with its own address; the printed block reflects the unit being executed |

## Data model

Introduces the **Placement** primitive (`../primitives/placement.md`) — the first new §2 primitive since the original roster. Extends three existing primitives:

| Primitive | Change | Why |
|---|---|---|
| `domain.md` | stable `ref` separate from positional `id`; system auto-mint path; `origin`, `touched_by_operator`, `mint_evidence`; atomic mint (I-D2) | I-P7 system decides; I-P8 position is not identity; I-P10 concurrency |
| `charter.md` | `title` (required, ≤60 chars); `domain_ref` home | render must be readable; B4's "Charter lives in a Domain" made explicit and stored, settling a three-way canon contradiction |
| `workflow.md` | add `domain_ref` | **defect fix** — B3 lines 38 + 59 specify the MECE check against `Workflow.domain_id`, a field that never existed in the primitive |

**Peer-review folds (deepseek 2026-07-27, CHANGES-REQUIRED)**: this block's resolution path is bound by I-P8 (Placement keys on the stable `domain_ref`, never the positional path — so restructure re-mints nothing), I-P9 (confidence floor: floor-hold at the nearest existing ancestor instead of minting noise), and I-P10 (atomic check-then-insert so concurrent sessions cannot create duplicate siblings). See ADR-028 §Peer review.

## Edge cases

- **Work spans two Domains** → the work unit is cut at the Domain boundary into two units, each placed. Domains are MECE; a work unit that genuinely spans them was two units.
- **Domain tree is empty (first run)** → `D0` is minted as the root from the tenant name, then the chain descends normally.
- **Classifier picks a wrong-but-plausible Domain** → accepted, stamped, recorded with its confidence. Correction is B20's job, not a gate here. Cost is a mis-filed row; benefit is a never-blocked operator.
- **Rapid repeated novel work** → many shallow siblings minted. This is the known drift risk (ADR-028 open question OQ-028-1); B20's consolidation scan is the mitigation.
- **Concurrent placements in the same tenant** → resolved per B13 ConcurrencyCoordinator; content-addressed ids make duplicate mints of identical Domains idempotent.

## Telemetry

Events:
- `placement_assigned` (new, `../events/placement_assigned.md`) — one per stamped work unit.
- `domain_minted` (new, `../events/domain_minted.md`) — one per Domain or Charter created.
- `policy_decision` (existing) — the match-vs-mint decision as a policy decision per ADR-007.
- `tenant_boundary_violation` (existing) — cross-tenant placement attempt.

Metrics:
- **Placement coverage** — share of work units carrying an authoritative Placement. Target 100% for new work.
- **Mint rate** — mints per 100 work units. Should decay toward zero as the tree matures; a flat or rising mint rate signals classifier weakness or genuine expansion, and is the leading indicator for the drift risk.
- **Operator-Hours-Saved** (`../metrics/north-star-ohs-per-week.md`) — addressed work makes retrieval cheap.

## Dependencies

- **Primitives**: `placement` (new), `domain`, `charter`, `workflow`, `tenant`, `decision-provenance`.
- **Events**: `placement_assigned`, `domain_minted`, `policy_decision`, `tenant_boundary_violation`.
- **Blocks**: B3 (MECE rule preserved), B4 (Charter context boundary), B20 / B21 / B22 (siblings), B13 (concurrency).
- **Pillars**: P5 (MECE domains) — the constraint B19 must never break; P7 (Native grows with operator).
- **Hardstops**: HS-3, HS-4.
- **ADRs**: ADR-028 (this feature), ADR-006 (tenant isolation), ADR-007 (provenance), ADR-010 (distinct — Workflow emergence at k≥4, untouched by B19).

## References

- ADR-028 — the decision record.
- B3 line 27 — the out-of-scope note B19 now owns.
- P5 — MECE constraint.
- Founder direction 2026-07-27 (mandatory self-emergence; system authority).
