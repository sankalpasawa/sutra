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

## Lifecycle (created → terminal states)

0. **System mint (ADR-028)**: the placement resolver finds no matching Domain for a unit of work and mints one as a child of the deepest matching ancestor, via atomic check-then-insert (I-D2). `origin='system-minted'`, `mint_evidence` populated, `domain_minted` emitted. No operator approval; no waiting. This is now the dominant creation path — the founder/governance path below is the exception, not the rule.
1. **Mint**: founder (or governance Workflow) emits Domain JSON; LiteExecutor validates I-1 D-pattern + parent resolution + non-null tenant_id; row persisted to user-kit registry. `origin='operator'`.
2. **Active**: Domain available for reference by Workflows / Charters / DecisionProvenance. Principles may be appended (never overwritten).
3. **Subdomain mint**: child Domains may be minted with this Domain's id as `parent_id` — extends the authority tree.
4. **Terminal**: NOT specified in canon. Canon §2.1 does not define a `deprecated` field for Domain. Domains are effectively permanent once minted in v1.0; future ADR may codify decommission semantics. (Runtime implementation choice; future ADR may codify.)

Note on terminal-event mapping: Domain is not an Execution and therefore I-14's terminal-event set (`workflow_completed` | `workflow_failed` | `approval_requested`) does NOT apply to Domain lifecycle. I-14 binds Workflow Executions only.

## Serialization (JSONL row shape)

User-kit registry rows at `~/.sutra-native/user-kit/domains/<id>.json` (one Domain per file; D-pattern id is the filename):

```jsonl
{"id":"D<pattern>","name":"<string>","parent_id":"D<pattern>|null","principles":["<p1>","<p2>"],"accountable":"<role-id>","authority":{...},"tenant_id":"T-<hash>","ts_minted_ms":<unix-ms>}
```

Index at `~/.sutra-native/user-kit/domains/INDEX.jsonl` enumerates `{id, parent_id, tenant_id, ts_minted_ms}` for fast tree traversal.

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
