---
part-id: P19
bucket: pillars
template: L1-pov
parity-source: FOUNDER-DIRECTIONS.md §D24 + PARALLELIZATION-ARCHITECTURE.md (Bernstein/BSP) + GATE-PARALLEL method
parity-source-sha256: 81d2bc3d444c17836ab5f7083d521986a0c5756228b704788e18a61e982c862b
status: DRAFT v1
authored: 2026-06-12
---

# P19: Parallelization while evolving is its own project

## Pillar statement

> The system is built while it is used — infra agents and product agents run simultaneously, and making that safe is a first-class project, not an emergent property. Per FOUNDER-DIRECTIONS.md D24 (founder verbatim): *"How can we parallelize it? That is also a project of its own when the system is still evolving."* Concurrent work is admitted only when tasks pairwise satisfy Bernstein conditions over declared read/write sets; conflicting tasks queue for the next wave/cycle instead of running.

## What this rules in

- The formal independence test, ported verbatim from PARALLELIZATION-ARCHITECTURE.md: tasks A and B may run concurrently only if write_set(A) ∩ read_set(B) = ∅, read_set(A) ∩ write_set(B) = ∅, and write_set(A) ∩ write_set(B) = ∅ — with shared external state (e.g., deploy targets) counted in both sets.
- Conflict-graph construction over enumerated read/write sets + Bulk Synchronous Parallel (BSP) wave dispatch: each workflow step declares its read/write sets, the engine derives the conflict graph, overlap means queue-don't-run.
- The evolve-while-in-use clause explicitly: self-mutation/infra work queues downstream actions for the next cycle rather than mutating mid-wave — composes with `../blocks/7e-mid-exec-mutation.md` mid-exec mutation rules.
- The origin incident as rationale: 2026-04-05 — 15 agents across 4 planned waves collapsed after wave 1 for lack of structural enforcement; the formal test was written down because informal coordination failed at scale.
- GATE-PARALLEL as a registered, per-instance-enabled method (os/method-registry.jsonl + SUTRA-CONFIG enabled_methods) — the gate is switchable infrastructure, not prose.

## What this rules out

- Treating execution-time parallelism as sufficient: `../blocks/B13-multi-runtime-concurrency.md` (artifact locks, runtime concurrency) and 7e (mid-exec mutation) cover EXECUTION; P19 covers concurrent EVOLUTION — infra agents mutating the system while product agents use it. Per the parity gap analysis, B13 + 7e are explicitly insufficient for this; neither states the Bernstein/BSP discipline or the queue-for-next-cycle rule.
- Dispatching concurrent agents without declared read/write sets.
- Mutating shared infrastructure mid-wave instead of queueing for the next cycle.
- Informal "they probably don't conflict" judgments in place of the pairwise formal test.

## Falsification test

**If two concurrent agents/Executions are dispatched whose declared (or undeclared) write sets overlap — or one mutates infrastructure the other reads mid-wave — without being serialized into successive waves → P19 broken.** (Falsification test newly authored from the production behavior contract — no §10.3 row exists; P19 is a post-cutover gap-fill.)

## Doctrine inheritance (from L0)

P19 is not in the §10.4 doctrine-tension table (authored post-cutover as a canon gap-fill); no tension is logged. Inheritance via L0 generally — Customer Focus First (`./P0-customer-focus-first.md`); strongest alignment is with the Dynamic and Scalable tests: the system stays usable while it evolves, and concurrency scales by formal structure rather than luck.

(If a tension exists in practice but is not in §10.4, this is a gap to surface via future ADR rather than invent inline.)

## References

- holding/FOUNDER-DIRECTIONS.md §D24 — doctrine + founder verbatim (production evidence).
- holding/DIRECTION-ENFORCEMENT.md row D24 — SOFT, STATUS ACTIVE (production evidence).
- sutra/layer2-operating-system/PARALLELIZATION-ARCHITECTURE.md — Bernstein conditions, read/write set rules, conflict graph, BSP wave model; born from the 2026-04-05 15-agent collapse (production evidence).
- sutra/layer2-operating-system/TASK-LIFECYCLE.md — Parallelization Gate (production evidence).
- os/SUTRA-CONFIG.md + os/method-registry.jsonl — GATE-PARALLEL registered + enabled (production evidence).
- `../blocks/B13-multi-runtime-concurrency.md` + `../blocks/7e-mid-exec-mutation.md` — execution-time parallelism only; explicitly insufficient for concurrent evolution (cross-bucket).
- `./P0-customer-focus-first.md` — doctrine parent.
- Parity-source deviation: canon GAP — content does not exist in NATIVE-ENGINE.md; parity-source anchors point at the production source docs per MIGRATION-PLAN §9 limitation #2.
