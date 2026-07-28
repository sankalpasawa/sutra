---
part-id: B21
bucket: blocks
template: L8-feature-spec
parity-source: net-new (ADR-028); post-cutover canon, not from pre-cutover monolith
status: DRAFT v1
authored: 2026-07-27
---

# B21: Backfill on Touch (lazy legacy addressing)

## 1-line summary

Pre-existing work that was never addressed gets classified the moment it is next touched — the migration happens as a side effect of normal activity, at zero operator cost, and never for work nobody looks at.

## Scope (in / out)

**In scope (v1)**:
- Detect that a work unit about to be touched has no current Placement.
- Classify it from the evidence available at touch time and stamp a Placement with `origin='backfilled'`.
- Apply the same never-blocks contract as B19 (I-P3): mint if nothing matches, continue regardless.
- Apply the same confidence floor as B19 (I-P9): below the floor, place in the nearest existing ancestor rather than minting a noise node.
- Track coverage — what fraction of touched legacy work is now addressed.

**Out of scope (v1)**:
- Addressing work nobody touches. That is B22's job, and deliberately so — lazy backfill has an infinite tail.
- Rewriting history. A backfilled Placement is stamped now, for work done earlier; `ts_ms` is the stamp time, and `work_ref` carries the original work's identity.
- Re-classifying work that already carries a current Placement. B21 fires only on the unaddressed.

## User outcome

> "I never ran a migration. The old work just started having homes as I went back to it."

Founder direction 2026-07-27: *"for previous work, whenever we are touching that, let's classify them into domains and charters … we can do it on the fly whenever we touch an existing thing."*

## Why lazy is the right default

| Property | Lazy (B21) | Bulk (B22) |
|---|---|---|
| Operator cost | zero — rides on work already happening | one deliberate run |
| Coverage | only what gets touched | everything reachable |
| Evidence quality | **high** — the touch itself is evidence of what the work is for | lower — structure only, no usage signal |
| Cost profile | amortised, invisible | one concentrated burst |
| Tail | infinite — untouched work is never addressed | none |

Lazy produces *better* classifications than bulk, because touching something reveals intent that static structure does not. Bulk produces *complete* coverage. The two are complementary, which is why both ship.

## UX flow (narrative)

1. A work unit is about to execute against a pre-existing target (a file, a commit, an artifact).
2. Placement resolution runs as normal (B19).
3. No current Placement exists for that target → B21 path taken.
4. Classifier reads evidence: the target's path, its content signature, adjacent already-addressed work, and the operator's current utterance.
5. Address resolved — matched, or minted under the deepest matching ancestor (I-P4, I-P10), or floor-held in the nearest ancestor (I-P9).
6. Placement stamped with `origin='backfilled'`, `phase='pre-flight'`.
7. The printed block flags it as a backfill so the operator sees legacy coverage growing.
8. Work proceeds. Nothing ever waits on this.

## Acceptance criteria (Given / When / Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | A file with no Placement, in a repo where the tree already covers its area | operator edits it | Placement stamped `origin=backfilled`, matched to the existing Domain; no mint; compact block prints |
| 2 | A file with no Placement, in an area the tree does not cover | operator edits it | Domain minted under the deepest matching ancestor; `origin=backfilled`; expanded block prints; **work not delayed** |
| 3 | A file that already carries a current Placement | operator edits it | B21 does not fire; existing address reused; no duplicate row |
| 4 | Classifier confidence below the floor on legacy content | touch happens | placed in nearest existing ancestor per I-P9; no noise node minted; low-confidence event emitted |
| 5 | 10,000 legacy files exist; operator touches 12 this week | week passes | exactly 12 backfill Placements exist. The other 9,988 stay unaddressed until touched or until B22 runs |
| 6 | Registry unwritable | touch happens | HS-4 fires — the single case where work stops, and it is a storage failure |
| 7 | Two sessions touch two different unaddressed files that both need the same new Domain | concurrent | atomic check-then-insert per I-P10 yields ONE Domain, not two siblings |

## Data model

No new primitive. Produces `../primitives/placement.md` rows with `origin='backfilled'`.

Coverage is read from the Placement index: `backfilled_count / known_legacy_units`. The denominator is only knowable after a B22 scan has enumerated the corpus — before that, coverage is reported as an absolute count, not a percentage. Stating an honest denominator matters more than showing a reassuring ratio.

## Edge cases

- **Touched work whose evidence contradicts an adjacent Placement** → classified on its own evidence; the divergence is a signal for B20's MECE report, not a blocker.
- **Very old work with stale paths** (file since moved) → `work_ref` records the identity available now. Historical path reconstruction is out of scope.
- **A touch that is itself a restructure** → B20 operations do not trigger B21; restructure is not "work" in the placeable sense.
- **Bulk edit touching 500 files at once** → 500 backfill placements; the printed block collapses to a summary line rather than 500 expanded trees.

## Telemetry

Events: `placement_assigned` (with `origin=backfilled`), `domain_minted`, `policy_decision`.

Metrics:
- **Legacy coverage (absolute)** — count of backfilled Placements. The honest number before a B22 scan establishes a denominator.
- **Backfill mint rate** — how often touching old work requires a new Domain. High and sustained means the tree does not yet describe the existing corpus, which is the signal to run B22.

## Dependencies

- **Primitives**: `placement`, `domain`, `charter`, `tenant`.
- **Blocks**: B19 (shares the resolution path and every invariant), B22 (the complementary bulk path), B20 (consolidates whatever B21 mints).
- **Pillars**: P5 (MECE), P7 (Native grows with operator) — B21 is P7 in its most literal form.
- **Hardstops**: HS-3, HS-4.
- **ADRs**: ADR-028.

## References

- ADR-028 — legacy addressing strategy (lazy + bulk).
- B19 (`./B19-work-placement.md`) — shared resolution contract.
- B22 (`./B22-domain-discovery-scan.md`) — the complementary one-time path.
- Founder direction 2026-07-27 ("whenever we are touching that, let's classify them").
