---
part-id: commitment_broken
bucket: events
template: L9-event-spec
parity-source: §3.2 row #25
parity-source-sha256: e46026d3d10fdd84d38d31e9b6614348e5de389165f3f93f978a622684f9b10e
status: DRAFT v1
authored: 2026-05-09
---

# commitment_broken

## Purpose

Signals that a Workflow failed AND a Charter L4-COMMITMENT obligation was missed (per §3.2 row #25 + ADR-012). Records the Charter id + obligation id that was un-fulfilled. Per I-16, the obligation id MUST resolve in the Charter registry.

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "commitment_broken",
  "source": "/native/runtime/commitment-evaluator",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "charter_id": "<charter-id>",
    "obligation_id": "<obligation-id>",
    "execution_id": "<uuid>",
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #25: `charter_id`, `obligation_id`. Per I-16, `obligation_id` MUST resolve to an entry in the Charter registry.

## Emitter

Commitment evaluator (exclusive emitter — per ADR-012 typed predicates + Charter obligation binding). Exact emitter binding within the runtime is not enumerated in canon §3.2 — runtime implementation choice; likely binding: post-`workflow_failed` (#4) hook that consults Charter obligations against the failed Workflow id.

## Consumers

- AUDIT surface — persists per ADR-013.
- Charter governance surface — registers the broken commitment for cadence / SLA tracking.
- Founder notification channel — likely consumer for high-severity breaks (runtime implementation choice).
- Telemetry sink (§5.6) — broken-commitment count (alerting signal).
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, Charter governance surface, founder notification.

## Ordering invariants

- Always preceded by `workflow_failed` (#4) for the same `execution_id` (per §3.2 row #25 description: "Workflow failed AND L4-COMMITMENT obligation missed").
- `obligation_id` MUST resolve in the Charter registry per I-16; emission with an unresolvable `obligation_id` is itself a HS-4-adjacent integrity violation.

## Replayability

- **Idempotent on replay**: informational; the broken-commitment state is the durable record on the Charter side.
- **Audit-critical**: required for Charter-level commitment-fulfillment metrics.
- **Fail-closed on emission failure** (per HS-4): no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #25.
- NATIVE-ENGINE.md §2.2 Charter (obligations).
- NATIVE-ENGINE.md §4 I-16 (commitment resolution invariant).
- ADR-012 — typed preconditions/postconditions + Charter binding.
- ADR-013 — 3-channel audit durability.
- ../primitives/charter.md
- ../events/workflow_failed.md
- ../hardstops/HS-4-audit-unwritable.md
