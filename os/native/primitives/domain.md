---
part-id: Domain
bucket: primitives
template: L9-primitive-spec
parity-source: §2.1
parity-source-sha256: a66671e5f354493793395a5b93306b4f7a214b55f764312ba4ac13f48774837c
status: DRAFT v1
authored: 2026-05-09
---

# Domain

## Purpose

The Domain primitive partitions Native's governance authority into a tree of D-numbered scopes. Each Domain declares its principles, its accountable role, the kinds of decisions it may make (`authority`), and the Tenant that owns its state. Domains are the authority skeleton: Workflows, Charters, and DecisionProvenance rows reference Domains to anchor which principles apply and which role is accountable. The root Domain `D0` is parent-less; every other Domain hangs off `D0` through a D-pattern parent chain (NATIVE-ENGINE.md §2.1).

## Type signature (TypeScript-style)

```typescript
type Domain = {
  ref: string;           // STABLE id — assigned at mint, NEVER changes (ADR-028)
  id: string;            // D-pattern: 'D0' or 'D<int>(.D<int>)*' — POSITIONAL, changes on restructure
  name: string;          // non-empty
  parent_ref: string | null;  // stable id of parent; null IFF this is the root
  principles: string[];  // append-only — historical principles never overwritten
  accountable: string;   // role identifier (durable role, not person)
  authority: object;     // declarative scope of decisions this Domain may make
  tenant_id: string;     // T-hash; required; references Tenant.id (ADR-006 + I-13)

  // ---- provenance (ADR-028) ----
  origin: 'system-minted' | 'operator';   // who created this node
  touched_by_operator: boolean;           // true once renamed/edited; gates B20 AUTO-tier
  mint_evidence: string[];                // what the classifier matched on (system-minted only)

  // ---- lifecycle (I-D5) ----
  status: 'active' | 'frozen' | 'retired';  // absent reads as 'active'
  successor_refs: string[];                 // ordered; [0] is the primary successor.
                                            //   PLURAL — a dissolution rarely lands in one place.
                                            //   DISPLAY SUMMARY: the disposition record's per-item
                                            //   mapping is authoritative for ref resolution.
  retired_at_ms: number | null;
  retire_reason_code: 'merged' | 'deleted' | 'split' | 'superseded' | 'duplicate'
                    | 'out_of_scope' | 'dormant' | 'abandoned_draft'
                    | 'reconstructed' | null;   // 'reconstructed' is written ONLY
                                            //   by `reconcile`; the operator verb
                                            //   refuses it (see Recovery below)
  retire_note: string | null;               // one line, optional. PRIVATE — never published.
  disposition_event_id: string | null;      // the INDEX.jsonl reorg_id carrying the full mapping
};
```

**`ref` vs `id`** (ADR-028 Decision 3): `ref` is identity, `id` is position. The dotted `D3.D2.D7` encodes where a node sits, so re-parenting rewrites it and every descendant's. Anything that must survive restructure — Placement rows, Charter `domain_ref`, external references — keys on `ref`. `id` is derived from the `parent_ref` chain and used for display and human reference. Before ADR-028 there was only `id`, which made one MOVE invalidate every Placement beneath the moved subtree.

## Invariants (must hold)

- **I-1 (D-pattern)**: `id` MUST match the regex `^D0$|^D[0-9]+(\.D[0-9]+)*$`. Mint-time validation per NATIVE-ENGINE.md §4.
- **Parent integrity**: `parent_id === null` IFF `id === 'D0'`. For all other Domains, `parent_id` MUST resolve to an existing Domain in the registry (NATIVE-ENGINE.md §2.1).
- **Append-only principles**: `principles` is monotonically growing — never edit, never delete. New principle = new array entry with its own ratification ts. (NATIVE-ENGINE.md §2.1 row `principles: append-only`.)
- **I-13 (Tenant ownership)**: every Domain is owned by exactly one Tenant via `tenant_id`; the field is required and non-null (NATIVE-ENGINE.md §4 + ADR-006).
- **Accountable role durability**: `accountable` is a role identifier (e.g. `founder`, `tenant_owner`), not a person id — survives identity rotation. (Canon implies durability via I-13 + ADR-015 agent_identity chain; specific durability semantics NOT specified in canon beyond "role identifier", runtime implementation choice.)
- **I-D1 (stable ref immutability, ADR-028)**: `ref` is assigned once at mint and MUST NEVER change — not on rename, not on move, not on merge. `id` (the positional D-path) MAY change under restructure. Nothing outside the Domain registry may key on `id`.
- **I-D2 (atomic mint, ADR-028)**: minting a Domain under a given `parent_ref` MUST be an atomic check-then-insert. Two concurrent sessions resolving the same unmatched work MUST NOT produce duplicate siblings; the loser adopts the winner's `ref` and emits `domain_minted` with `race_adopted: true`. Without this, concurrency shreds MECE at the moment of creation (placement.md I-P10).
- **I-D3 (system mint authority, ADR-028)**: Domains may be minted by the system without operator approval, and `origin` records which path created the node. `touched_by_operator` flips to true the first time an operator renames or edits it, and never flips back — it is what makes a node ineligible for B20's AUTO-tier consolidation forever after.
- **I-D4 (mint evidence, ADR-028)**: a `system-minted` Domain MUST carry non-empty `mint_evidence`. System authority without a recorded rationale is unauditable, and B20's sibling-overlap computation reads this field.
- **I-D5 (no destruction)**: a minted Domain's row is NEVER removed from `domains/`. The terminal state is `status='retired'` with `successor_refs` populated — never an unlink. MERGE, DELETE and the `retire` verb all stamp the lifecycle fields and leave the file in place. Deleting the file strands every Placement row, Charter `domain_ref` and INDEX event that cites the ref, because all of them key on `ref` and nothing back-references them; the registry then fails its own groundedness lint by construction. Corollaries:
  - **Read-path rule.** `load_domains()` returns ALL Domains and carries no default filter. Filtering happens at render and choice surfaces only, through `live_refs(domains)` (excludes `retired` ONLY): the classifier's candidate set, the tree, search, the MECE report and consolidation candidates. Every other consumer — the Placement write boundary's I-P2 check, the groundedness lint, adjacency votes, `domain_path()`, and every Charter consumer — MUST receive the unfiltered map, or the retire path fails on its own happy path and every just-retired ref reads as newly unresolvable.
  - **`frozen` is excluded from nothing at read time.** The resolver mints a new sibling whenever classification finds no candidate, so a frozen Domain hidden from the classifier manufactures the duplicate the freeze exists to prevent. `frozen` is enforced at the WRITE boundary: no new child mints, placements accepted only as pre-flight rows.
  - **D-number permanence.** `domain_path()` always derives the positional `D<n>` over the FULL sibling set. A retired sibling keeps its ordinal permanently and the number is never reused. `live_refs()` decides what is RENDERED, never how anything is NUMBERED; passing a filtered map into `domain_path()` is a bug.
  - **Name reuse.** `ref`s are never reused; NAMES are. The mint-time sibling dedupe therefore matches `active` siblings only — otherwise I-D5 turns it into tombstone adoption, and the new mint returns a retired ref that refuses placements.
  - **Succession liveness.** A successor must be `active` at apply time (`ORG-016`). `successor_refs` is never rewritten after the fact; a chain of retirements resolves transitively at render, never at write.
  - **Recovery.** `retire` writes a pre-mutation manifest to `plans/retire-<ref>-<ts>.json` before touching anything; `unretire <ref> --from <manifest>` is the ONLY transition back to `active`. It is append-only: it cannot delete the successor Charters the retire minted (I-D5 and content addressing both forbid it), so each is marked `lifecycle='reverted'` in its sidecar instead. Reverted successors staying visible is the honest trace.
  - **Damage already done (`reconcile` / `repair`).** I-D5 stops NEW destruction; it cannot undo the rows the pre-I-D5 `os.remove()` path already unlinked. Two idempotent one-time sweeps close that, and neither is part of the steady-state lifecycle (`B20-domain-restructure.md` §Damage recovery):
    - **`reconcile`** mints one **tombstone** per `domain_ref` that Placement history cites but `domains/` no longer holds: `{name: '[unrecovered] <ref>', status: 'retired', retire_reason_code: 'reconstructed', successor_refs: [], recovered: true, mint_evidence: ['recovered']}`. The name says *unrecovered*, not *recovered*, because name, principles and evidence are gone for good and a row that reads as restored data is worse than the dangling ref it replaces. `ts_minted_ms` is the reconcile's own clock, never the recovered one — back-dating a tombstone would slot it into the middle of its parent's ts-ordered sibling list and renumber every live sibling after it, breaking D-number permanence, the property this whole invariant exists to protect. The recovered timestamp survives as `recovered_ts_minted_ms`. `reconstructed` is refused by the `retire` verb: it asserts the row was never authored, only inferred, and no operator is in a position to assert that.
    - **`repair`** re-homes every Charter whose `domain_ref` has no LIVE Domain — the DELETE branch never had a Charter loop, unlike MERGE, so those Charters are already unreachable through `charters_for()`. Destination is the first live node along `successor_refs`, else the nearest live ancestor, else the root (recorded as `lifecycle='orphaned'` on the successor). Re-homing mints a successor with `supersedes` set; the original body is immutable and stays put. Anything already superseded is skipped, so a legitimately merged Domain's Charters are never re-homed a second time.
    - Both are verified by **`lint --full`**, which scans every `CURRENT.jsonl` row, every Placement body and every Charter body and exits 2 on any ref with no row in `domains/`. A ref resolving to a tombstone is GROUNDED — that is the point of I-D5 — so a legitimate `retire` never turns it red. The sampled `lint` lane is unchanged and still exits 0.
  - **One write path.** Every mutation of a `domains/<ref>.json` row goes through `_save_domain()` under `_lock('RESTRUCTURE')`, and every one of them appends `domain_updated {ref, before, after, ts_ms}` with the changed fields only. The ONE suppression is the write on the ref a `domain_restructured` row is already about — that event carries its before/after, so a second row is duplicate history. It carries only THAT ref, so a restructure's writes to other rows (the surviving target's `principles` on MERGE, every child re-parent) are audited on their own rows; they were previously invisible on every log. An unlocked read-modify-write anywhere else loses updates against a concurrent restructure and leaves no audit row — which is what `domains_pipeline._set_field` did.

## Lifecycle (created → terminal states)

0. **System mint (ADR-028)**: the placement resolver finds no matching Domain for a unit of work and mints one as a child of the deepest matching ancestor, via atomic check-then-insert (I-D2). `origin='system-minted'`, `mint_evidence` populated, `domain_minted` emitted. No operator approval; no waiting. This is now the dominant creation path — the founder/governance path below is the exception, not the rule.
1. **Mint**: founder (or governance Workflow) emits Domain JSON; LiteExecutor validates I-1 D-pattern + parent resolution + non-null tenant_id; row persisted to user-kit registry. `origin='operator'`.
2. **Active**: Domain available for reference by Workflows / Charters / DecisionProvenance. Principles may be appended (never overwritten).
3. **Subdomain mint**: child Domains may be minted with this Domain's id as `parent_id` — extends the authority tree.
4. **Freeze (optional, reversible)**: `status='frozen'`. Still rendered, still classified against, still resolvable, still keeps its D-number — but accepts no new child mints, and placements only as pre-flight rows swept by the next apply. A holding state during a cutover, not a terminal one.
5. **Terminal — `status='retired'` (I-D5)**. The row is stamped, never removed. `retire <ref> --successor <ref2>` is the operator path; MERGE and DELETE reach the same state with `retire_reason_code` `merged` / `deleted`. The verb refuses (exit 2) with a disposition report while any Charter, child Domain or current Placement on the node has no successor mapping. On success: every Charter gets a successor mint homed to its mapped target with `supersedes` set (the original body is immutable and stays put), every child Domain re-parents to its mapped target, every current Placement gets a superseding row with `phase='post-close'`, and `domain_restructured` carries the full per-item disposition. A retired Domain is still resolvable by `ref` forever, still accepts the superseding rows `retire`/`unretire` write, and keeps its D-number permanently — it is simply not a candidate for new work.

Legal transitions: `active ↔ frozen`; `active | frozen → retired`; `retired → active` ONLY via `unretire --from <manifest>`, never by editing the file.

Note on terminal-event mapping: Domain is not an Execution and therefore I-14's terminal-event set (`workflow_completed` | `workflow_failed` | `approval_requested`) does NOT apply to Domain lifecycle. I-14 binds Workflow Executions only.

## Serialization (JSONL row shape)

User-kit registry rows at `~/.sutra-native/user-kit/domains/<id>.json` (one Domain per file; D-pattern id is the filename):

```jsonl
{"id":"D<pattern>","name":"<string>","parent_id":"D<pattern>|null","principles":["<p1>","<p2>"],"accountable":"<role-id>","authority":{...},"tenant_id":"T-<hash>","ts_minted_ms":<unix-ms>}
```

Lifecycle fields are written on every mint (`status:'active'`, `successor_refs:[]`, the rest `null`) and stamped in place on retirement. A row that predates I-D5 and carries no `status` key reads as `active`.

Index at `~/.sutra-native/user-kit/domains/INDEX.jsonl` enumerates `{id, parent_id, tenant_id, ts_minted_ms}` for fast tree traversal. `domain_restructured` rows on the same log carry `{reorg_id, tenant_id, op, ref, target, retire_reason_code, before, after, disposition{charters[], children[]}, ts_ms}`; `before`/`after` cover the changed mutable fields plus `d_path`, which is RECORDED rather than recomputed at replay time because sibling ordinals depend on the tree's membership at that instant.

Two further event kinds share the log:

- `domain_updated {ref, tenant_id, before, after, ts_ms}` — every field write except the one on a `domain_restructured` row's own subject ref, emitted by the single locked `_save_domain()` path. That includes the writes a restructure makes to OTHER rows, which its narrower `before`/`after` never covered. `before`/`after` here are the changed keys of the WHOLE row, not the restructure event's replay set, because what an operator touches (`description`, `design`, `touched_by_operator`) is mostly outside it. A no-op write emits nothing.
- `domain_reconstructed {ref, parent_ref, resolution, tenant_id, cited_by{current_rows, placements}, recovered_name, retire_reason_code, ts_ms}` — one per tombstone minted by `reconcile`. `resolution` is `index-parent` when the parent was recovered from this log and still resolves, `root-fallback` otherwise; `recovered_name` is what the log remembers of the destroyed row, recorded as history and deliberately NOT used as the tombstone's `name`.

## Cross-primitive references

- **Tenant** (`../primitives/tenant.md`): `tenant_id` field; I-13 binds every Domain to exactly one Tenant.
- **Charter** (`../primitives/charter.md`): Charters scope to Domains via Charter `authority` and ACLs (§2.2).
- **Workflow** (`../primitives/workflow.md`): Workflows reference Domains transitively through Charters and through Domain principles cited in DecisionProvenance.
- **DecisionProvenance** (`../primitives/decision-provenance.md`): every consequential decision (I-7) cites the Domain whose principles authorized the outcome; `policy_id` may carry a Domain anchor.

## References

- NATIVE-ENGINE.md §2.1 — canonical Domain field table.
- NATIVE-ENGINE.md §4 — I-1 (D-pattern), I-13 (Tenant ownership).
- ADR-006 — multi-tenant isolation; Tenant ownership of Domains.
- ADR-007 — DecisionProvenance schema; Domain reference semantics.
- ADR-015 — agent_identity chain; accountable-role durability context.
