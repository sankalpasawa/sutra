---
part-id: P1
bucket: pillars
template: L1-pov
parity-source: §10.2 row P1 + §10.3 row P1
parity-source-sha256: c5c270d8a8e8015b46e81aff568567a0281673dc1fb95d36ffa73f91d07894db
status: DRAFT v1
authored: 2026-05-09
---

# P1: Artifact-first

## Pillar statement

> Every Native output is a typed, addressable, logged, reusable, system-readable artifact. Nothing the operator produces is left as ephemeral chat text or untyped scratch — every result of a Native interaction lands as a first-class artifact that the system itself can consume in the next iteration. Per §10.2 row P1: "every Native output is typed, addressable, logged, reusable, system-readable."

## What this rules in

- Outputs of LLM calls, decisions, and operator-confirmed actions are persisted as typed primitives (per cross-ref to `../primitives/`, e.g., ExecutionResult, DecisionProvenance).
- Artifacts are addressable (have stable identifiers) — readable by other Native blocks and by the operator.
- The closed-loop invariant (per P9, `./P9-closed-loop-artifact.md`) — system consumes its own outputs in subsequent iterations.

## What this rules out

- Ephemeral chat-only outputs that vanish at end of turn.
- Untyped or schemaless dumps that cannot be addressed / reused / audited.
- "Memory as separate primitive" — per §10.3 P9 falsification, memory IS the artifact catalog (not specified further in §10.2 row P1 itself; cross-ref).

## Falsification test

**If artifacts are NOT consumed by next iteration → P1 broken; system not closed-loop.** (Exact text from §10.3 row P1.)

## Doctrine inheritance (from L0)

Per canon §10.4 doctrine-tension resolution table: P1 has NO direct conflict with the 5 Doctrine tests (Customer Focus First · Dynamic · Flexible · Scalable · Simple · Nuanced) recorded in §10.4. The table only enumerates tensions for P3 (vs Simple), P11 (vs Customer Focus), and P13 (vs Scalable). For P1, no tension is logged; inheritance is via L0 generally (Customer Focus First applies as parent of all pillars).

(If a tension exists in practice but is not in §10.4, this is a gap to surface via future ADR rather than invent inline.)

## References

- NATIVE-ENGINE.md §10.2 row P1 — pillar statement.
- NATIVE-ENGINE.md §10.3 row P1 — falsification test.
- NATIVE-ENGINE.md §10.4 — doctrine inheritance table (P1 not listed; no documented tension).
- `./P9-closed-loop-artifact.md` — closed-loop pillar (P1's runtime corollary).
- `../primitives/` — typed primitives that artifacts instantiate (cross-bucket; specific files authored in Phase 5).
