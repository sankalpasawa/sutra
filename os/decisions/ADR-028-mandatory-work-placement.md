# ADR-028 — Mandatory Work Placement (system-decided, never-blocking)

## Status

PROPOSED 2026-07-27. Founder direction same day. Peer-reviewed by deepseek (CHANGES-REQUIRED, 4×P1 / 3×P2 — all folded before authoring, see §Peer review). Codex lane unavailable (usage limit until 2026-08-19); deepseek substituted under explicit founder authority.

Canon surfaces: [placement.md](../native/primitives/placement.md) · [B19](../native/blocks/B19-work-placement.md) · [B20](../native/blocks/B20-domain-restructure.md) · [B21](../native/blocks/B21-backfill-on-touch.md) · [B22](../native/blocks/B22-domain-discovery-scan.md).

## Context

Canon had a hole with no owner.

[B3](../native/blocks/B3-domain-hierarchy-mece.md) binds a **Workflow** to exactly one Domain, checked at **registration** time. Three problems followed:

1. **Work outside a registered Workflow had no address at all.** An operator utterance handled inline, an ad-hoc edit, a commit — none of it touched the Domain tree. The MECE guarantee of [P5](../native/pillars/P5-mece-domains.md) covered the taxonomy but not the activity.
2. **B3 specified its check against a field that did not exist.** Lines 38 and 59 reference `Workflow.domain_id`; the Workflow primitive has no such field. The MECE check was written against a phantom.
3. **B3 line 27 put "auto-creating new Domains from emergent patterns" out of scope, deferring to [ADR-010](ADR-010-organic-emergence-propose-approve.md)** — but ADR-010 proposes **Workflows**, never Domains. The deferral pointed at an owner that does not own it.

Separately, the Charter→Domain relationship was described three incompatible ways: `charter.md` said Charters scope to Domain**s** (plural, spanning); `B4` said a Charter **lives in** a Domain (singular, required); `C2` rendered Domain→many-Charters. No field stored the relationship in any of the three readings — it was inferred from `authority` + ACL at read time.

Founder direction 2026-07-27 set the requirement: *"whenever someone does something, it has to be catalyzed in a domain … so that all the documentation and everything is mapped up properly"*, with authority settled the same day: *"the system auto-decides the domains. It is not left to the user unless the user explicitly asks to restructure."*

### Alternatives considered

- **Threshold-gated emergence (k≥4, mirroring ADR-010)** — rejected. k≥4 is right for minting a *reusable Workflow* (you do not want a Workflow per typo). Placement is an *address on work that already happened*; k=1 is correct. Two different objects, two different thresholds.
- **Operator ratification of each new Domain** — rejected by founder. Turns every novel task into a taxonomy interview.
- **Block work until a Domain exists** — rejected. Strictest reading of "mandatory", but it stops the operator mid-flow to do filing.
- **Quarantine pen for unplaceable work** — rejected. A pen is a catch-all bucket by another name, which P5 explicitly forbids.
- **Post-hoc-only placement** — rejected. Accurate but cannot scope context retrieval, since retrieval has already happened by then.

## Decision

Native MUST stamp every unit of work with a **Placement** — one Domain, one Charter — before that work executes. Six sub-decisions:

**Decision 1 — System authority.** The system decides the taxonomy. The operator is never asked, never gated, never required to ratify. Operator correction routes exclusively through B20. Corollary added after peer review: B20's consolidation may **auto-apply** merges for Domains the system itself minted and the operator has never touched. This is not an exception to Decision 1 — it keeps the system's own guesses inside the system's own lane. The moment an operator edits a node, it becomes theirs and can only be changed by them.

**Decision 2 — Pre-flight, blocking on declaration only.** Placement fires before the first mutating action. It blocks on a *missing declaration*, never on a *missing domain*. Since the mint path guarantees a declaration always resolves, the gate never actually stops the operator. The only halt is registry-unwritable (HS-4), which is a durability failure, not a taxonomy failure.

**Decision 3 — Identity is separate from position.** The Domain's stable id is the key Placement points at; the dotted `D3.D2.D7` path is a **derived display attribute**, excluded from the content-addressed canonical form. Re-parenting changes display paths and re-mints nothing.

**Decision 4 — Legacy work gets two paths.** Lazy backfill on touch (B21) and a one-time, one-level bulk discovery scan per client (B22). Lazy yields better classifications (the touch is evidence of intent); bulk yields complete coverage and the only honest denominator. They are complementary, so both ship.

**Decision 5 — Descriptive fields auto-derive; promises never do.** A minted Charter gets `title`, `purpose`, `scope_in`, `scope_out` inferred from evidence, and `obligations: []` with a stated reason (satisfying existing invariant I-2). `success_metrics` likewise stays empty. Descriptive fields state what *is* and can be observed. Obligations state what is *promised* and cannot. Auto-writing promises the operator never made would make the whole record untrustworthy.

**Decision 6 — MECE becomes computable.** P5 asserted MECE; nothing checked it. B20 ships a MECE report — pairwise sibling overlap for mutual exclusion, unaddressed-unit count for collective exhaustion — turning P5's falsification test from rhetoric into a runnable check.

## Consequences

| Kind | Effect |
|---|---|
| + | Every unit of work has an authority address; documentation maps mechanically |
| + | Operator is never interrupted for taxonomy work |
| + | B3's phantom-field defect fixed; `Workflow.domain_id` now exists |
| + | B3 line 27's orphaned hole now owned by B19 |
| + | Charter→Domain relationship stored explicitly instead of inferred three contradictory ways |
| + | P5 becomes mechanically checkable for the first time |
| − | The tree drifts without operator attention; bounded but not eliminated by auto-consolidation |
| − | A wrong-but-plausible classification is accepted silently; the cost is a mis-filed row |
| − | Every work unit costs one registry write and one render |
| 0 | ADR-010 (Workflow emergence at k≥4) is untouched — different object, different threshold |

## Peer review

deepseek consult, 2026-07-27, `deepseek-v4-pro`, verdict **CHANGES-REQUIRED**. All findings folded before canon was authored. Log: `.enforcement/deepseek-reviews/gate-log.jsonl`.

| # | Finding | Severity | Fold |
|---|---|---|---|
| 1 | Positional ids + content-addressed rows = write amplification; one re-parent re-mints every Placement in the subtree | P1 | Decision 3; I-P8 |
| 2 | Auto-mint outruns a propose-only consolidation scan; root becomes the de facto catch-all | P1 | Decision 1 corollary; B20 two-tier consolidation |
| 3 | Concurrent sessions mint duplicate siblings under the same parent | P1 | I-P10 atomic check-then-insert |
| 4 | Unbounded registry growth; no retention story | P1 | I-P5 single-current pointer + retention/compaction in placement.md |
| 5 | Pre-flight-only has no drift correction | P2 | I-P9 phase field; post-close superseding row |
| 6 | Always minting even at confidence 0.01 produces semantic garbage | P2 | I-P9 confidence floor → floor-hold at nearest ancestor |
| 7 | MECE asserted, never computed | P2 | Decision 6; B20 MECE report |

Where canon departs from the review: deepseek rated finding 5 as potentially P1 on access-control grounds. Canon keeps it P2 — Placement is an *address*, not an authorization; Charter ACL already governs access. The post-close correction ships regardless.

## Falsification tests

| # | Falsifier | Anchor |
|---|---|---|
| 1 | A work unit executes with no current Placement | I-P1 |
| 2 | Placement resolution halts the operator for any reason other than registry-unwritable | I-P3 |
| 3 | A re-parent operation re-mints any Placement row | I-P8, Decision 3 |
| 4 | Two concurrent sessions produce two Domains for the same unmatched work | I-P10 |
| 5 | A minted Charter contains an obligation no operator authored | Decision 5 |
| 6 | Two sibling Domains overlap and the MECE report does not flag them | Decision 6 |
| 7 | The operator is asked to ratify a Domain | Decision 1 |

## Open questions

- **OQ-028-1**: What is the right similarity threshold for AUTO-tier consolidation? Too low merges distinct areas; too high leaves drift. Needs live data from v1 dogfooding.
- **OQ-028-2**: What is the confidence floor value for I-P9? Same answer — measure before fixing.
- **OQ-028-3**: Retention window for superseded Placement rows before cold-storage archive. Joins §8 OS-14 deferred sink-policy.
- **OQ-028-4**: Should Placement coverage become a north-star-adjacent metric, or stay diagnostic?

## References

- [placement.md](../native/primitives/placement.md) — the primitive.
- [B19](../native/blocks/B19-work-placement.md) · [B20](../native/blocks/B20-domain-restructure.md) · [B21](../native/blocks/B21-backfill-on-touch.md) · [B22](../native/blocks/B22-domain-discovery-scan.md).
- [B3](../native/blocks/B3-domain-hierarchy-mece.md) — the block whose hole this closes.
- [P5](../native/pillars/P5-mece-domains.md) — the constraint now mechanically checked.
- [ADR-010](ADR-010-organic-emergence-propose-approve.md) — distinct: Workflow emergence, untouched here.
- [ADR-006](ADR-006-tenant-isolation-domain-field.md) · [ADR-007](ADR-007-decision-provenance-schema.md).
- Founder direction 2026-07-27 — mandatory self-emergence; system authority; two legacy paths.

## Authoring

Claude-drafted 2026-07-27 under founder direction. deepseek peer review folded pre-authoring. Codex review pending lane availability (2026-08-19).
