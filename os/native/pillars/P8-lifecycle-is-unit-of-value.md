---
part-id: P8
bucket: pillars
template: L1-pov
parity-source: §10.2 row P8 + §10.3 row P8
parity-source-sha256: 71fe5ab3a214a65e7ad4e6d2751b0892e98330ac17a0942454d88d8400f2702f
status: DRAFT v1
authored: 2026-05-09
---

# P8: Lifecycle is unit of value

## Pillar statement

> The unit of value Native delivers is a complete lifecycle, not an isolated task. Per §10.2 row P8: "analysis → decide → build → operationalize → auto-run." Picked work must traverse the full five-phase lifecycle as ONE addressable thing — the operator does not have to manually re-pick up the work at each phase transition. A single-phase tool ("just analyze" or "just build") fails this pillar.

## What this rules in

- The five lifecycle phases (analysis → decide → build → operationalize → auto-run) are one addressable lifecycle artifact per picked work.
- Phase transitions are automatic from the operator's POV — no manual re-pickup required.
- Native value is measured at lifecycle completion (operator-hours saved across the full arc), not per-phase.

## What this rules out

- Picked work that requires manual re-pickup at every phase boundary (per §10.3 P8 falsification, part 2).
- Single-phase Native (analysis-only, build-only) that breaks the lifecycle into disconnected tools (per §10.3 P8 falsification, part 1).
- Measuring success at phase boundaries rather than lifecycle completion.

## Falsification test

**If picked work cannot traverse analysis → decide → build → operationalize → auto-run as ONE addressable lifecycle, OR phase transitions require manual re-pickup → P8 broken.** (Exact text from §10.3 row P8.)

## Doctrine inheritance (from L0)

Per canon §10.4 doctrine-tension resolution table: P8 has NO direct conflict with the 5 Doctrine tests (Customer Focus First · Dynamic · Flexible · Scalable · Simple · Nuanced) recorded in §10.4. The table only enumerates tensions for P3 (vs Simple), P11 (vs Customer Focus), and P13 (vs Scalable). For P8, no tension is logged; inheritance is via L0 generally (Customer Focus First applies as parent of all pillars).

(If a tension exists in practice but is not in §10.4, this is a gap to surface via future ADR rather than invent inline.)

## References

- NATIVE-ENGINE.md §10.2 row P8 — pillar statement.
- NATIVE-ENGINE.md §10.3 row P8 — falsification test.
- NATIVE-ENGINE.md §10.4 — doctrine inheritance table (P8 not listed; no documented tension).
- `./P14-outcomes-drive-design.md` — lifecycle completion is the outcome P14 anchors on.
- NATIVE-ENGINE.md §11.2 — North Star metric (Operator-Hours-Saved per Week) measures lifecycle-level value.
