---
part-id: pattern_proposed
bucket: events
template: L9-event-spec
parity-source: §3.2 row #12
parity-source-sha256: d5edb512c00294496fac1da126337ce261949c6ca5da6380c979d32c373c635f
status: DRAFT v1
authored: 2026-05-09
---

# pattern_proposed

## Purpose

Signals that the pattern detector reached the emergence threshold k≥4 (per §3.2 row #12 + ADR-010). A candidate Workflow is proposed for founder approval — closing the loop between observed repetition and structured automation.

## Schema (CloudEvents 1.0 form)

```json
{
  "specversion": "1.0",
  "type": "pattern_proposed",
  "source": "/native/runtime/pattern-detector",
  "id": "<uuidv7>",
  "time": "<rfc3339>",
  "data": {
    "pattern_hash": "<hash>",
    "k": 4,
    "sample_utterances": ["<utterance>", "..."],
    "agent_identity": "<claude | codex | operator>",
    "ts_ms": 1778336529000
  }
}
```

Required payload fields per §3.2 row #12: `pattern_hash`, `k`, `sample_utterances`.

## Emitter

Pattern detector (EMERGE surface; exclusive emitter) per ADR-010. Fires when k (count of matching utterances/events) reaches the configured threshold. The exact threshold value (≥4 noted in §3.2 row #12) and the precise matching rule are runtime implementation choices — canon §3.2 specifies the threshold as k≥4 but does not enumerate the matching predicate (Q4-pattern-emergence-k open question).

## Consumers

- AUDIT surface — persists per ADR-013.
- Founder approval channel — receives the proposal for `approve P-<id>` / `reject P-<id>` utterance per §3.4 approval utterances.
- Telemetry sink (§5.6) — emergence-detection telemetry.
- Consumer set not enumerated in canon §3.2; runtime implementation choice — likely consumers: AUDIT surface, founder approval surface.

## Ordering invariants

- Not bound to a specific Execution; emitted asynchronously when the detector window crosses k.
- Causal predecessor of either `proposal_approved` (#13) or `proposal_rejected` (#14) for the same `pattern_hash`.

## Replayability

- **Idempotent on replay**: informational; the durable record is the proposal entry in user-kit/proposals/ (path not specified in §3.2 — runtime implementation choice).
- **Audit-critical**: required to reconstruct founder approval flow.
- **Fail-closed on emission failure** (per HS-4): no fail-open.

## References

- NATIVE-ENGINE.md §3.2 row #12.
- NATIVE-ENGINE.md §3.4 Approval utterances (`approve P-<id>`).
- NATIVE-ENGINE.md §14.10 open questions — Q4 pattern emergence k.
- ADR-010 — pattern emergence detection.
- ADR-013 — 3-channel audit durability.
- ../open-questions/Q4-pattern-emergence-k.md
- ../events/proposal_approved.md
- ../events/proposal_rejected.md
- ../hardstops/HS-4-audit-unwritable.md
