---
part-id: P12
bucket: pillars
template: L1-pov
parity-source: §10.2 row P12 + §10.3 row P12
parity-source-sha256: 9afde4041aef665f2c2197eae1ff730da46a067a61588c79e666ae6d6a4e45de
status: DRAFT v1
authored: 2026-05-09
---

# P12: Deterministic surface, stochastic core

## Pillar statement

> Only LLM reasoning and action are stochastic; everything else in Native is tested, deterministic code. Per §10.2 row P12: "only LLM reasoning + action are stochastic; everything else is tested code." The Native runtime — routing, primitive serialization, event emission, audit logging, hook firing — is engineered code with tests. The stochastic core (the LLM call itself) is enveloped on both sides by deterministic surfaces.

## What this rules in

- All non-LLM-non-action Native code has tests (per §10.3 P12 falsification).
- Routing, primitive (de)serialization, event emission, hook firing, audit logging are deterministic and covered.
- Coverage discipline cross-referenced in §14.16.8 [G6] — coverage gate ≥80% per build.

## What this rules out

- Untested non-LLM code paths in Native (per §10.3 P12 falsification).
- "It's hard to test so we'll skip it" for deterministic code.
- Treating non-LLM Native code as low-rigor because the LLM core is fuzzy.

## Falsification test

**If non-LLM-non-action code lacks tests → P12 broken.** (Exact text from §10.3 row P12.)

## Doctrine inheritance (from L0)

Per canon §10.4 doctrine-tension resolution table: P12 has NO direct conflict with the 5 Doctrine tests (Customer Focus First · Dynamic · Flexible · Scalable · Simple · Nuanced) recorded in §10.4. The table only enumerates tensions for P3 (vs Simple), P11 (vs Customer Focus), and P13 (vs Scalable). For P12, no tension is logged; inheritance is via L0 generally (Customer Focus First applies as parent of all pillars).

(If a tension exists in practice but is not in §10.4, this is a gap to surface via future ADR rather than invent inline.)

## References

- NATIVE-ENGINE.md §10.2 row P12 — pillar statement.
- NATIVE-ENGINE.md §10.3 row P12 — falsification test.
- NATIVE-ENGINE.md §10.4 — doctrine inheritance table (P12 not listed; no documented tension).
- NATIVE-ENGINE.md §14.16.8 [G6] — coverage gate ≥80% per build is P12's operational lever.
- `./P2-pre-post-llm-validation.md` — deterministic-surface envelope on the post-LLM side.
- `./P11-constrained-problem-construction.md` — deterministic-surface envelope on the pre-LLM side.
