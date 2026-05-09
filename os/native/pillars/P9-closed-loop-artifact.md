---
part-id: P9
bucket: pillars
template: L1-pov
parity-source: §10.2 row P9 + §10.3 row P9
parity-source-sha256: f26efd2b422b3bd670d501766b560962e5a889a72c3fcd277f1e54cbf2953378
status: DRAFT v1
authored: 2026-05-09
---

# P9: Closed-loop artifact

## Pillar statement

> Both input AND output of every Native interaction are stored as artifacts; the system consumes its own outputs in the next iteration. Per §10.2 row P9: "input + output both stored; system consumes own outputs next iteration." Memory is not a separate primitive — memory IS the artifact catalog. The closed-loop discipline is what turns artifact-first (P1) from a storage convention into a self-improving system.

## What this rules in

- Both input AND output sides of an interaction are persisted as artifacts.
- The next iteration's input set includes prior-iteration outputs by default.
- The artifact catalog is the memory primitive — no separate "memory" abstraction.

## What this rules out

- Treating memory as a separate primitive distinct from the artifact catalog (per §10.3 P9 falsification).
- One-way storage where outputs land but never feed back as inputs.
- Bespoke memory systems running parallel to the artifact catalog.

## Falsification test

**If memory is treated as a separate primitive (not the artifact catalog) → P9 broken.** (Exact text from §10.3 row P9.)

## Doctrine inheritance (from L0)

Per canon §10.4 doctrine-tension resolution table: P9 has NO direct conflict with the 5 Doctrine tests (Customer Focus First · Dynamic · Flexible · Scalable · Simple · Nuanced) recorded in §10.4. The table only enumerates tensions for P3 (vs Simple), P11 (vs Customer Focus), and P13 (vs Scalable). For P9, no tension is logged; inheritance is via L0 generally (Customer Focus First applies as parent of all pillars).

(If a tension exists in practice but is not in §10.4, this is a gap to surface via future ADR rather than invent inline.)

## References

- NATIVE-ENGINE.md §10.2 row P9 — pillar statement.
- NATIVE-ENGINE.md §10.3 row P9 — falsification test.
- NATIVE-ENGINE.md §10.4 — doctrine inheritance table (P9 not listed; no documented tension).
- `./P1-artifact-first.md` — P9's storage prerequisite.
- `./P7-native-grows-with-operator.md` — P9's behavioral payoff.
