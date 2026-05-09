---
part-id: P6
bucket: pillars
template: L1-pov
parity-source: §10.2 row P6 + §10.3 row P6
parity-source-sha256: 6511ccb04937abb954d0ce7ce453ac994a170bdbd063ca28a66094eb0f79d7b7
status: DRAFT v1
authored: 2026-05-09
---

# P6: Operator controls explanation

## Pillar statement

> The operator controls how much explanation Native surfaces; the system controls production silently. Per §10.2 row P6: "system controls production silently." Verbosity, trace level, and how much of the machinery the operator sees are operator-tunable. Production noise (runtime internals, intermediate states, hook firings) is suppressed by default — it surfaces only when the operator asks.

## What this rules in

- Operator-tunable explanation level (e.g., trace L0-L3 per output-trace convention).
- Default-quiet runtime: production noise (hook firings, intermediate states) suppressed unless requested.
- Surface inversion is forbidden: production internals do not bubble up to operator surface without operator opt-in.

## What this rules out

- Hardcoded verbosity that the operator cannot tune (per §10.3 P6 falsification, part 1).
- Surfacing raw production noise (internal state changes, debug logs) to the operator without their request (per §10.3 P6 falsification, part 2).
- "Show everything always" as a default — that's inverted surfaces.

## Falsification test

**If operator cannot tune explanation verbosity OR system surfaces raw production noise to operator → P6 broken; control surfaces inverted.** (Exact text from §10.3 row P6.)

## Doctrine inheritance (from L0)

Per canon §10.4 doctrine-tension resolution table: P6 has NO direct conflict with the 5 Doctrine tests (Customer Focus First · Dynamic · Flexible · Scalable · Simple · Nuanced) recorded in §10.4. The table only enumerates tensions for P3 (vs Simple), P11 (vs Customer Focus), and P13 (vs Scalable). For P6, no tension is logged; inheritance is via L0 generally (Customer Focus First applies as parent of all pillars).

(If a tension exists in practice but is not in §10.4, this is a gap to surface via future ADR rather than invent inline.)

## References

- NATIVE-ENGINE.md §10.2 row P6 — pillar statement.
- NATIVE-ENGINE.md §10.3 row P6 — falsification test.
- NATIVE-ENGINE.md §10.4 — doctrine inheritance table (P6 not listed; no documented tension).
- Asawa CLAUDE.md "Execution Trace" + "Readability Gate" sections — operationalize P6 in the current Sutra plugin (founder-tunable trace levels).
