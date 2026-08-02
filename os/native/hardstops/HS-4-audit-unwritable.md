---
part-id: HS-4
bucket: hardstops
template: ADR-style-invariant
parity-source: §6.9 row HS-4 + §7 STRIDE row "Audit-trail loss" + §4 I-7 + §4 I-9 + §4 I-17
parity-source-sha256: 801eda60c364349a671d891a6cf367b571027d23fbba0f97e0fd2f7e657b2e50
status: ACTIVE
authored: 2026-05-09
---

# HS-4: DecisionProvenance log unwritable across all 3 channels

## Status

ACTIVE (v1.0 — shipped with Native runtime).

## Context (when this fires)

HS-4 fires when the DecisionProvenance JSONL audit log is unwritable across all 3 fallback channels.

Trigger conditions (per canon §6.9 row HS-4 + §7 STRIDE "Audit-trail loss" + ADR-013):
1. A consequential decision occurs that per §4 I-7 must emit a DecisionProvenance row.
2. AND the primary JSONL append fails (per ADR-013 — `fsync` per append).
3. AND the stderr beacon fallback fails.
4. AND the dual fallback to `/tmp` fails.
5. Hence all 3 channels (primary, stderr beacon, /tmp) are simultaneously unavailable.

Observable state at trigger time (per §7 STRIDE mitigation column for "Audit-trail loss"):
- Primary `user-kit/decision-provenance.jsonl` append errored.
- Stderr beacon emit errored.
- `/tmp` dual-fallback path errored.

(The exact identity of "the 3 channels" beyond what §7 names — primary JSONL + stderr beacon + /tmp dual-fallback — is NOT further specified in canon §6.9 row HS-4. Runtime implementation chooses concrete paths; future ADR may codify the channel-set contract.)

## Decision (fail-mode)

**Block all governance hooks; stderr beacon** (per canon §6.9 row HS-4).

- All governance hooks are blocked from continuing.
- A stderr beacon is emitted (the surface-of-last-resort even when the audit log itself is unwritable).
- Per §4 I-7 + I-9 + I-17: governance cannot proceed without a writable provenance surface — every consequential decision is required to carry `policy_id` + `policy_version` to a durable sink.

(Whether "all governance hooks" means session-wide or process-wide, whether in-flight Executions are paused vs aborted, and the specific blocking mechanism are NOT specified in canon §6.9. Runtime implementation choice; future ADR may codify.)

## Recovery path

Per canon §6.9 row HS-4, the canonical signal is the stderr beacon — operator observes the beacon and restores at least one of the 3 channels (primary path, beacon path, /tmp path) before governance hooks resume.

Specific restore procedures (operator commands, automatic retry intervals, partial-recovery semantics if 1-of-3 channels comes back) are NOT specified in canon; runtime implementation choice; future ADR may codify.

## Downstream effects

Per canon §6.9 + §7 + §4 I-7/I-9/I-17 + ADR-013, the directly canon-specified downstream effects are:
- All governance hooks stop emitting decisions (audit-trail integrity preserved by blocking, not by writing without trace).
- Stderr beacon is the only surface guaranteed to fire.
- Any in-flight consequential decisions that require provenance (per I-7) cannot proceed.

Cross-effects on the cadence scheduler, on Workflow Executions mid-step, and on the cutover engine are NOT specified in canon §6.9 row HS-4; runtime implementation may choose; future ADR may codify.

## STRIDE relevance

**Repudiation** (per canon §7 STRIDE row "Audit-trail loss"). HS-4 guards against the audit-trail-loss class — a Repudiation attack where a consequential decision occurs but no provenance is durably recorded, leaving no trace for replay or accountability.

Per §7 row, the mitigation column cites: "fsync per append (ADR-013); stderr beacon fallback; dual fallback to `/tmp`". HS-4 is the terminal "all-channels-down" guard; ADR-013 is the per-append durability mechanism; I-7 + I-9 + I-17 are the structural invariants that make audit-trail completeness a contract.

## References

- NATIVE-ENGINE.md §6.9 row HS-4 (canonical hardstop definition).
- NATIVE-ENGINE.md §4 I-7 — invariant: every consequential decision emits DecisionProvenance.
- NATIVE-ENGINE.md §4 I-9 — invariant: every governance hook emits DecisionProvenance carrying `policy_id` + `policy_version`.
- NATIVE-ENGINE.md §4 I-17 — invariant: every DecisionProvenance carries `policy_id` + `policy_version` (F-8).
- NATIVE-ENGINE.md §7 STRIDE row — Repudiation / Audit-trail loss.
- NATIVE-ENGINE.md §2.9 — DecisionProvenance primitive.
- NATIVE-ENGINE.md §5.6 — Telemetry sink (JSONL append-only, fsync per append).
- ADR-013 — DecisionProvenance durability (fsync + fallback chain).
