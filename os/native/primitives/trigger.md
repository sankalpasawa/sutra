---
part-id: TriggerSpec
bucket: primitives
template: L9-primitive-spec
parity-source: §2.5
parity-source-sha256: f68e7db6e527d93a011c7b02f5023d0450274398db2ca067a08612b852b39afc
status: DRAFT v1
authored: 2026-05-09
---

# Trigger

## Purpose

The TriggerSpec primitive declares WHEN a Workflow fires. Each Trigger has a `pattern` (one of `preprocessor`, `observer`, `gate`, `fan_out`, `negotiation`), a typed `predicate` (match-all / match-any / cron — NEVER free prose), a `target_workflow_id` that MUST resolve in the registry, and an optional `cadence` object (tick/cron spec per ADR-017). The Router uses TriggerSpecs to map operator utterances (and cadence ticks) to target Workflows (NATIVE-ENGINE.md §2.5).

## Type signature (TypeScript-style)

```typescript
type TriggerSpec = {
  id: string;                          // unique per registry
  pattern: 'preprocessor' | 'observer' | 'gate' | 'fan_out' | 'negotiation';
  predicate: TypedPredicate;           // match-all / match-any / cron; ADR-012 PNC parser
  target_workflow_id: string;          // MUST resolve in user-kit/workflows registry
  cadence: CadenceSpec | null;         // tick/cron spec per ADR-017; null for utterance-driven Triggers
};
```

## Invariants (must hold)

- **Unique id**: `id` is unique across the user-kit Triggers registry. Mint-time reject if collision.
- **Pattern enum**: `pattern` MUST be one of the 5-set `{preprocessor, observer, gate, fan_out, negotiation}` (NATIVE-ENGINE.md §2.5).
- **Typed predicate (ADR-012)**: `predicate` MUST parse as a typed PNC predicate (match-all / match-any / cron). Free prose is HARD rejected at mint-time (NATIVE-ENGINE.md §2.5 row `not free prose`).
- **Target resolution**: `target_workflow_id` MUST resolve to an existing Workflow in the user-kit registry. Mint-time HARD reject if unresolved; runtime HARD reject (no firing) if target later deprecated.
- **Cadence rules (ADR-017)**: when `cadence !== null`, CadenceScheduler fires within ±5 min of the scheduled time (I-12).

## Lifecycle (created → terminal states)

1. **Mint**: founder (or governance Workflow) emits TriggerSpec JSON; LiteExecutor validates id uniqueness + pattern enum + typed predicate (PNC parse) + target_workflow_id resolution; row persisted to user-kit Triggers registry.
2. **Active (utterance-driven)**: Router consults Triggers for every HSutraEvent (operator utterance); on match, emits `routing_decision` (§3.2 #1) and dispatches `NativeEngine.run(target_workflow_id, ctx)`.
3. **Active (cadence-driven)**: CadenceScheduler.tick() generates TriggerEvents per cadence spec (ADR-017); each TriggerEvent fires the target Workflow within ±5 min (I-12).
4. **Match miss**: when predicate does NOT match, Router emits `routing_decision` with no `matched_workflow_id` (or routes to pattern-proposal flow per ADR-010 if k≥4 unmatched utterances accumulate).
5. **Terminal**: NOT specified in canon §2.5. Triggers are effectively permanent once minted in v1.0; runtime implementation may add a `deprecated` flag (future ADR). When target Workflow is deprecated, the Trigger becomes non-firing but the TriggerSpec row remains.

Note on I-14: Trigger is not an Execution; I-14's terminal-event set does NOT apply to Trigger lifecycle.

## Serialization (JSONL row shape)

User-kit registry rows at `~/.sutra-native/user-kit/triggers/<id>.json` (single TriggerSpec per file):

```jsonl
{"id":"<unique-id>","pattern":"observer","predicate":{"kind":"match-all","clauses":[...]},"target_workflow_id":"W-<hash>","cadence":null,"ts_minted_ms":<unix-ms>}
```

Index at `~/.sutra-native/user-kit/triggers/INDEX.jsonl` enumerates `{id, pattern, target_workflow_id, has_cadence, ts_minted_ms}` for Router fast-path lookup. Cadence-driven Triggers carry a `cadence` object per ADR-017 (cron string + tick interval).

## Cross-primitive references

- **Workflow** (`../primitives/workflow.md`): `target_workflow_id` references a registered Workflow; Trigger's pattern enum aligns with Workflow's intent (preprocessor vs observer vs gate vs fan_out vs negotiation).
- **EngineEvent** (`../primitives/engine-event.md`): every Trigger match emits `routing_decision` (§3.2 #1) carrying `matched_workflow_id`, `predicate_id`, `score`.
- **ExecutionResult** (`../primitives/execution-result.md`): when a Trigger fires, the resulting Execution carries the originating `trigger_event` per ExecutionResult.trigger_event.
- **DecisionProvenance** (`../primitives/decision-provenance.md`): Router emits DecisionProvenance for every match/miss decision per I-7.

## References

- NATIVE-ENGINE.md §2.5 — canonical TriggerSpec field table.
- NATIVE-ENGINE.md §4 — I-12 (CadenceScheduler ±5 min).
- NATIVE-ENGINE.md §3.2 #1 — `routing_decision` event.
- NATIVE-ENGINE.md §3.1 — `Router.route` / `Router.routeAsync` signatures.
- ADR-010 — pattern-proposal flow (k≥4 unmatched utterances).
- ADR-012 — typed predicates (PNC parser).
- ADR-017 — CadenceScheduler tick/cron semantics.
