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
- Transactional undo; v1 offers reconstruction from superseded Placement rows, plus the one-time damage-recovery sweeps below.

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
| **DELETE** | Retire a Domain (I-D5: the row is stamped, never unlinked) | Its Placements re-point to the parent; its Charters re-home. Deleting the root is forbidden. The Charter half was **missing in code** until Phase 0; `repair` (§Damage recovery) is the sweep for Domains deleted before the fix |

## Damage recovery — the v1 path for harm already done

The five operations above describe how the tree gets corrected *going forward*. They do not address the registries that already ran the earlier build, where MERGE and DELETE called `os.remove()` on `domains/<ref>.json`. Deleting those calls (I-D5) stops new destruction; it recovers nothing. Two idempotent one-time verbs do, plus one diagnostic that proves when they are finished. **None of the three is part of the steady-state lifecycle** — they exist only because the damage predates the invariant, and each is safe to re-run at any time.

| Verb | The damage it addresses | What it does | Blocks? |
|---|---|---|---|
| **`lint --full`** | The damage was invisible, not absent. The shipped lint samples `CURRENT.jsonl[-50:]` and always exits 0 ("visibility, never blockage") — and MERGE appends superseding rows for the *surviving* target before removing the source file, so on any realistic registry the stale rows fall outside that window and the check passes on corrupt data | Scans **every** `CURRENT.jsonl` row, every Placement body and every Charter body; groups dangling refs by ref with citation counts | **Yes — exit 2.** The sampled lane is unchanged and still exits 0 |
| **`reconcile`** | Every Placement row and Charter citing a `domain_ref` whose file was unlinked. The ref is permanently unresolvable and I-D5 forbids deleting the history that cites it, so there is no other legal way to clear it | Mints one minimal **tombstone** per orphaned ref — `status='retired'`, `retire_reason_code='reconstructed'`, `name='[unrecovered] <ref>'` — so the ref resolves again as a node that accepts no new work, which is what it already was | No; exit 2 only if there is no live root to re-home under |
| **`repair`** | DELETE re-pointed Placements and re-parented child Domains but had **no Charter loop**, unlike MERGE. Every Charter on a previously deleted Domain is already orphaned and unreachable through `charters_for()` — the operation table's DELETE row ("its Charters re-home") was never true in code | Re-homes each orphaned Charter to the first live node along `successor_refs`, else the nearest live ancestor, else the root. Mints a successor with `supersedes` set — never rewrites `domain_ref` inside the old content-addressed body | No |

Rules that make them safe to run on a live registry:

- **A tombstone is not a reconstruction.** Name, principles and `mint_evidence` are gone; the tombstone says `[unrecovered]` rather than pretending otherwise. `reconstructed` is refused as an operator `retire --reason`, because it asserts the row was never authored, only inferred.
- **Tombstones never renumber anything.** `ts_minted_ms` is the sweep's own clock. Back-dating it from the INDEX would slot the tombstone into the middle of its parent's ts-ordered sibling list and shift every live sibling after it, violating D-number permanence.
- **`repair` skips anything already superseded.** A legitimately merged Domain is retired with its Charters' successors already minted; without that guard, `repair` would mint a second successor for every Charter after every MERGE, forever.
- **`repair` does not move Placements.** A current Placement citing an orphaned Charter still resolves once `reconcile` has tombstoned its Domain. Moving live work is `retire` / `charter reassign` — an operator verb with a disposition report — not a recovery sweep.
- **Order and proof.** `reconcile` → `repair` → `lint --full`. The sequence is finished when `lint --full` exits 0; a ref resolving to a tombstone is grounded, so a legitimate `retire` never turns it red.

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
| 11 | A registry carrying pre-I-D5 damage: >100 CURRENT rows, a `domain_ref` whose file was `os.remove`'d, the stale rows outside the last 50 | `lint` then `lint --full` | sampled lane exits 0 and reports nothing; `--full` exits **2** and names the ref with its full citation counts |
| 12 | The same registry | `reconcile` | one tombstone per orphaned ref, `status='retired'`, `retire_reason_code='reconstructed'`; **zero** live siblings change their D-number; a second run mints nothing |
| 13 | A Charter homed to a Domain deleted before the fix | `repair` | re-homed to the nearest live ancestor via a successor with `supersedes` set; original body untouched and still hashing to its own id; one `charter_repaired` event; a second run reports 0 moved |
| 14 | A Domain merged *legitimately*, its Charters' successors already minted | `repair` | **zero** further re-homes — already-superseded Charters are skipped |
| 15 | `reconcile` then `repair` have both run | `lint --full` | exits **0** — every cited ref resolves, tombstones included |

## Data model

No new primitive. Operates on `../primitives/domain.md`; mints superseding `../primitives/placement.md` rows only where `domain_ref` genuinely changes.

New event `domain_restructured` carries `{operation, tier: 'auto'|'operator', before_refs[], after_refs[], placements_repointed, charters_rehomed}`.

Damage recovery adds two rows, both defined in `../primitives/domain.md` §Serialization: `domain_reconstructed` on `domains/INDEX.jsonl` (one per tombstone `reconcile` mints) and `charter_repaired` on `charters/INDEX.jsonl` (one per Charter `repair` re-homes, carrying `{id, successor_id, from_domain_ref, to_domain_ref, resolution, placements_citing}`). Every Domain field write outside these operations goes through one locked `_save_domain()` and appends `domain_updated {ref, before, after, ts_ms}`.

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
