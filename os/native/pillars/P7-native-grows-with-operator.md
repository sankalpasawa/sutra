---
part-id: P7
bucket: pillars
template: L1-pov
parity-source: §10.2 row P7 + §10.3 row P7
parity-source-sha256: ba9757bd526ab87992bc5da738b7a651cfba6fee876db4cade15839fb317fddb
status: DRAFT v1
authored: 2026-05-09
---

# P7: Native grows with operator

## Pillar statement

> Personalization in Native is dynamic, not static. Per §10.2 row P7: "personalization is dynamic, not static." Native at day-180 must behave observably differently from Native at day-1 — it has learned the operator's voice, decision-bias, and cadence. Static personalization (set-once config that never adapts) fails this pillar.

## What this rules in

- Observable adaptation over time in at least three dimensions: voice, decision-bias, cadence (per §10.3 P7 falsification).
- Continuous learning surface — Native consumes operator artifacts (P1) and uses them to adjust future behavior (closed-loop via P9).
- Day-1 vs day-180 behavior diffable — the operator can audit how Native has changed.

## What this rules out

- Day-1-style fixed behavior at day-180 (per §10.3 P7 falsification).
- Static config files as the only personalization surface (the config must be updated by observed operator behavior, not only by manual edits).
- "One-shot setup" personalization that never re-learns.

## Falsification test

**If Native behaves identically at day-1 vs day-180 (no observable adaptation in voice / decision-bias / cadence) → P7 broken; personalization static not dynamic.** (Exact text from §10.3 row P7.)

## Doctrine inheritance (from L0)

Per canon §10.4 doctrine-tension resolution table: P7 has NO direct conflict with the 5 Doctrine tests (Customer Focus First · Dynamic · Flexible · Scalable · Simple · Nuanced) recorded in §10.4. The table only enumerates tensions for P3 (vs Simple), P11 (vs Customer Focus), and P13 (vs Scalable). For P7, no tension is logged; inheritance is via L0 generally (Customer Focus First applies as parent of all pillars).

(If a tension exists in practice but is not in §10.4, this is a gap to surface via future ADR rather than invent inline.)

## References

- NATIVE-ENGINE.md §10.2 row P7 — pillar statement.
- NATIVE-ENGINE.md §10.3 row P7 — falsification test.
- NATIVE-ENGINE.md §10.4 — doctrine inheritance table (P7 not listed; no documented tension).
- `./P1-artifact-first.md` + `./P9-closed-loop-artifact.md` — P7's substrate (typed artifacts + closed-loop consumption are how learning happens).
- Founding Doctrine "Dynamic" test.
