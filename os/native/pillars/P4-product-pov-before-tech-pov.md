---
part-id: P4
bucket: pillars
template: L1-pov
parity-source: §10.2 row P4 + §10.3 row P4
parity-source-sha256: f528f40c30a3b8fe469a20c12ad7b0b89c4b86c622ccae79a1e7b0cd70dceca4
status: DRAFT v1
authored: 2026-05-09
---

# P4: Product-POV before tech-POV

## Pillar statement

> Reverse-engineer voice into core needs first; structure the problem before designing the solution. Per §10.2 row P4: "reverse-engineer voice → core needs; structure problem before solution." Every Native primitive starts from "what does the operator see?" and only then descends to "how does it work technically?" Tech-POV-first is a failure mode — it produces elegant infrastructure with no operator surface.

## What this rules in

- New Native primitives start with operator-observable behavior (UX flow / outcome) before type signature or runtime mechanism.
- Founder-voice rounds + JTBD framing precede architectural decisions.
- Problem-structuring step (Cynefin-style domain framing) gates solution design.

## What this rules out

- Net-new primitives that begin with "how does it work technically?" before "what does the operator see?" (per §10.3 P4 falsification).
- Architecture-first thinking where the operator surface is back-fit onto pre-decided infra.
- Skipping the voice-to-needs step and jumping to implementation patterns.

## Falsification test

**If a new Native primitive starts with "how does it work technically?" before "what does the operator see?" → P4 broken.** (Exact text from §10.3 row P4.)

## Doctrine inheritance (from L0)

Per canon §10.4 doctrine-tension resolution table: P4 has NO direct conflict with the 5 Doctrine tests (Customer Focus First · Dynamic · Flexible · Scalable · Simple · Nuanced) recorded in §10.4. The table only enumerates tensions for P3 (vs Simple), P11 (vs Customer Focus), and P13 (vs Scalable). For P4, no tension is logged; inheritance is via L0 generally (Customer Focus First applies as parent of all pillars).

(If a tension exists in practice but is not in §10.4, this is a gap to surface via future ADR rather than invent inline.)

## References

- NATIVE-ENGINE.md §10.2 row P4 — pillar statement.
- NATIVE-ENGINE.md §10.3 row P4 — falsification test.
- NATIVE-ENGINE.md §10.4 — doctrine inheritance table (P4 not listed; no documented tension).
- `./P14-outcomes-drive-design.md` — P14 is P4's runtime corollary at the architecture level.
- Founding Doctrine Principle 0 — Customer Focus First.
