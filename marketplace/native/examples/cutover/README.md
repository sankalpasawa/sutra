# examples/cutover — reference cutover_contract fixtures

Two reference fixtures for the Core → Native cutover playbook. Both validate against `createCutoverContract` from [`../../src/schemas/cutover-contract.ts`](../../src/schemas/cutover-contract.ts).

| Fixture | Tier | canary_window | Use case |
|---|---|---|---|
| [`asawa-dogfood-cutover-contract.json`](asawa-dogfood-cutover-contract.json) | T0 | `60s` | Asawa runs Native against its own session (M11 dogfood) |
| [`dayflow-cutover-contract.json`](dayflow-cutover-contract.json) | T2-1 | `7d` | DayFlow first T2 cutover (Phase 3) |

## Usage (operator workflow)

```
1. Pick the fixture matching your Tenant's tier (or write a fresh one)
2. Strip the `_comment_*` fields (these are documentation, not part of the schema)
3. Substitute Tenant-specific values:
   - source_engine: your current engine id (e.g. "sutra-core-v2.9.1")
   - target_engine: "sutra-native-v1.0"
   - behavior_invariants: required 3 + per-Tenant additions (see MIGRATION.md §5)
   - rollback_gate: required predicates + per-Tenant tightenings (see MIGRATION.md §6)
   - canary_window: per-tier default OR tuned (see MIGRATION.md §7)
4. Validate via `createCutoverContract(JSON.parse(fixture))` — should not throw
5. Attach to your Charter as `cutover_contract` field
6. Invoke cutover engine (M11+) per MIGRATION.md §4 sequence
```

## Schema reference

The 5 required fields per [`cutover-contract.ts`](../../src/schemas/cutover-contract.ts):

| Field | Type | Required | Notes |
|---|---|---|---|
| `source_engine` | `string`, min length 1 | Yes | Engine.id currently active for the Tenant |
| `target_engine` | `string`, min length 1 | Yes | Engine.id being cut over to (parallel-canary) |
| `behavior_invariants` | `string[]`, min length 1 | Yes | Predicates that MUST hold across cutover (≥3 recommended) |
| `rollback_gate` | `string`, min length 1 | Yes | Single predicate; when true → abort cutover + rollback |
| `canary_window` | `string`, min length 1 | Yes | Observation window (e.g. `"7d"`, `"PT72H"`, `"60s"`) |

`null` is also valid — represents a Charter that does not require cutover (greenfield).

## Notes

- `_comment_*` fields in the JSON fixtures are ignored by JSON.parse + Zod schema validation; they exist purely as inline documentation. Strip before production use.
- Per-Tenant invariants and tightenings should be added on top of the required defaults; see MIGRATION.md §5 + §6 for how-to.
- These fixtures are NOT executable directly — the cutover engine (P-B1) ships at M11+. Until then, fixtures are valid-shape templates for operator-driven cutover.
- D1 §11.1 research doc shows an older 6-field schema with `canary_window_seconds` + `success_metrics`. Ignore that drift — `cutover-contract.ts` is canonical.

## Cross-references

- [MIGRATION.md](../../MIGRATION.md) — full cutover playbook (the doc these fixtures support)
- [src/schemas/cutover-contract.ts](../../src/schemas/cutover-contract.ts) — canonical schema
- [holding/plans/native-v1.0/M10-migration-doc.md](https://github.com/sankalpasawa/asawa-holding/blob/main/holding/plans/native-v1.0/M10-migration-doc.md) — milestone plan
