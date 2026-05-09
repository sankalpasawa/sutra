---
part-id: Charter
bucket: primitives
template: L9-primitive-spec
parity-source: §2.2
parity-source-sha256: 01ca52956c657e93de6eb5fc65ba5fe87684cee33d17862f803d9900765b0fb2
status: DRAFT v1
authored: 2026-05-09
---

# Charter

## Purpose

The Charter primitive is the content-addressed contract that declares purpose, scope, obligations, invariants, success metrics, constraints, ACL, optional cutover_contract, authority, and termination conditions for a bounded scope of work. Charters are how durable commitments (L4-COMMITMENT) attach to Native: every `commitment_broken` EngineEvent references a Charter obligation id (I-16). Charters are immutable post-mint (content-addressed `C-<hash>`); changes mint new Charters (NATIVE-ENGINE.md §2.2).

## Type signature (TypeScript-style)

```typescript
type Charter = {
  id: string;                 // C-hash — content-addressed (sha256 of canonical form)
  purpose: string;            // non-empty
  scope_in: string[];         // explicit in-scope items
  scope_out: string[];        // explicit out-of-scope items
  obligations: object[];      // ≥1 entry OR explicitly empty + reasoned (I-2)
  invariants: object[];       // typed; machine-checkable per F-10
  success_metrics: object[];  // typed; machine-checkable per F-10
  constraints: object[];      // typed; machine-checkable per F-10
  acl: object[];              // per-tenant access list
  cutover_contract: object | null;  // { rollback gate, behavior_invariants, canary_window } | null
  authority: object;          // declarative — what decisions this Charter can authorize
  termination: object;        // declarative — conditions under which Charter retires
};
```

## Invariants (must hold)

- **Content-addressed id**: `id = sha256(canonical_form(charter))`. Any field change yields a new Charter id (immutable; new mint required). (NATIVE-ENGINE.md §2.2 row `id: content-addressed`.)
- **Non-empty purpose**: `purpose` MUST be non-empty (NATIVE-ENGINE.md §2.2).
- **I-2 (obligations rule)**: `obligations` has ≥1 entry OR is explicitly empty + reasoned. An empty obligations array WITHOUT a reasoning entry is a HARD reject at mint time (NATIVE-ENGINE.md §4 + §2.2).
- **F-10 (machine-checkable typed fields)**: `invariants`, `success_metrics`, `constraints` MUST be typed (not free prose) so terminal_check can evaluate them. (NATIVE-ENGINE.md §2.2 row `typed; machine-checkable per F-10`.)
- **Cutover_contract validity (I-10)**: when `cutover_contract !== null`, its `behavior_invariants` MUST be observed throughout `canary_window` (NATIVE-ENGINE.md §4 I-10).
- **I-16 (commitment_broken referential integrity)**: every `commitment_broken` EngineEvent references a Charter obligation id that resolves in the registry (NATIVE-ENGINE.md §4 I-16; §3.2 event #25).

## Lifecycle (created → terminal states)

1. **Mint**: founder (or governance Workflow) emits Charter JSON; LiteExecutor validates I-2 + F-10 typed fields + content-addressed id; row persisted.
2. **Active**: Charter available for reference by Workflows (via Workflow.interfaces_with, ACL checks, obligation tracking).
3. **Obligation evaluation**: at each Workflow Execution that touches an obligation, the PolicyDispatcher emits DecisionProvenance citing this Charter's obligation id.
4. **Commitment-broken path**: if an obligation is missed by a Workflow Execution that failed, `commitment_broken` event emits (§3.2 #25); does NOT terminate the Charter itself.
5. **Cutover canary (if cutover_contract present)**: canary_window observes behavior_invariants per I-10; cutover_contract is itself a checkable contract.
6. **Terminal**: Charter retires when `termination` condition holds. Specific termination event-type and irreversibility semantics NOT specified in canon §2.2; runtime implementation choice (likely a Charter-retired event in future ADR).

Note on I-14 mapping: Charter is not an Execution; I-14's terminal-event set binds Workflow Executions only — Charter lifecycle does not flow through `workflow_completed`/`workflow_failed`/`approval_requested`.

## Serialization (JSONL row shape)

User-kit registry rows at `~/.sutra-native/user-kit/charters/C-<hash>.json` (single Charter JSON per file):

```jsonl
{"id":"C-<hash>","ts_minted_ms":<unix-ms>,"purpose":"<string>","obligations_count":<int>,"has_cutover":<bool>}
```

Index at `~/.sutra-native/user-kit/charters/INDEX.jsonl` enumerates `{id, ts_minted_ms, has_cutover, obligations_count}` for fast lookup. Canonical form for content-addressing: JSON keys sorted alphabetically, no whitespace, UTF-8 encoded; SHA256 of canonical form = `C-<hex>`.

## Cross-primitive references

- **Domain** (`../primitives/domain.md`): Charter scopes to Domains via `authority` and ACL; Charters inherit principles from the Domain tree they attach to.
- **Workflow** (`../primitives/workflow.md`): Workflows reference Charters through `interfaces_with`; Workflow `stringency` + `on_override_action` are influenced by referenced Charter terms.
- **EngineEvent** (`../primitives/engine-event.md`): `commitment_broken` event (§3.2 #25) references Charter obligation ids; I-16 enforces referential integrity.
- **DecisionProvenance** (`../primitives/decision-provenance.md`): obligation/invariant evaluations emit DecisionProvenance citing the Charter id.
- **Tenant** (`../primitives/tenant.md`): Charter ACL is per-Tenant; cross-tenant access requires explicit ACL entry.

## References

- NATIVE-ENGINE.md §2.2 — canonical Charter field table.
- NATIVE-ENGINE.md §4 — I-2 (obligations), I-10 (cutover canary), I-16 (commitment_broken integrity).
- NATIVE-ENGINE.md §3.2 #25 — `commitment_broken` event.
- ADR-007 — DecisionProvenance schema (Charter reference semantics).
- F-10 — typed machine-checkable fields (forbidden coupling avoidance).
