<!-- MIRROR (read-only distribution copy). Canonical: sutra/os/decisions/ADR-022-full-loop-six-mechanisms.md. -->
# ADR-022: Full-Loop Six Mechanisms (System-of-Work Science Adoption)

**Status**: Accepted (founder direction 2026-06-12 in-session: "fold the gap map into canon"; dual-lane retro review queued)
**Date**: 2026-06-12
**Context anchor**: research synthesis `holding/research/2026-06-12-unit-work-record-science.md` (asawa commit `8c0e471`; 9-agent workflow, 5 discipline lenses, 0 fact-check flags) + Unit theory at `holding/website/native/index.html` §10.1.

## Context

Vision (already doctrine: P7 native-grows-with-operator · P8 lifecycle-is-unit-of-value · ADR-010 organic emergence): Native creates a system of work backed by a system of record for any operator, situation, industry — growing organically as needs and reality change.

Five independent disciplines (process science, transaction processing, event sourcing/DDD, operations science, cybernetics) converge on the same falsifiable structure: a work system = contracted units + provably-safe composition + an append-only record from which the system can be rebuilt (replay) or rediscovered (mining). The full loop is design → execute → record → compare → redesign, with a formal result guarding each edge.

Native today runs design → execute → record. The record fails both litmus tests: not replayable (state cannot be rebuilt from the log alone) and not regulated (no decision rule reads it in-loop) — so the SoR is telemetry, not yet a system of record. Scale science adds three further requirements: where-used indexing, versioning with drain, retirement.

## Decision

Adopt six mechanisms, dependency-ordered. The loop closes at #5.

| # | Mechanism | Serves | Concretely | Effort |
|---|---|---|---|---|
| 1 | **SoR truth upgrade** | "backed by a system of record" | bracket external effects with attempted/result events · persist LLM outputs AS events · deterministic replay · event schema versioning | M |
| 2 | **Registration-at-birth** | growth without rot | new workflow declares contract + reads/writes (→ where-used index) + version | S |
| 3 | **Workflow authoring engine** | "LLM creates the system of work for any person/situation" | observe situation → Cynefin classify (fixed-sequence vs declarative form) → draft typed Workflow with per-step contracts → machine soundness check → ADR-010 propose/approve | L |
| 4 | **Comparator + admission** | record→system conversion | reference limits per workflow + escalation · open-Execution WIP cap gates new runs | M |
| 5 | **The miner** (organic loop) | "grows organically / as reality changes" | scheduled read of the record: recurrence → propose extraction · spec-vs-actual drift → propose revision · where-used=0 → propose retirement; all via propose/approve | L |
| 6 | **Industry packs** | "any industry" | template workflows + record schemas + reference limits per domain; engine stays domain-free | M/pack |

Sequence: 1 → 2 → 3 → 4 → 5; 6 parallel anytime after 3.

## Consequences

- This ADR fixes scope + order, not internals. Mechanisms #3 and #5 each ship with their own ADR; charter Contract/Primitives edits land when #1/#2 ship (per `updating-native-canon` rule: contract change → charter edit + ADR at ship time).
- SoR contract will gain truth requirements (#1); Workflow registry schema will gain contract/reads-writes/version fields (#2).
- Guard rails adopted with the mechanisms: the 12-pitfall register in the research doc (dual-write divergence, telemetry theater, non-deterministic replay, missing compensators, interaction deadlock, utilization trap, schema rot, et al.).
- Honest boundary (no-sycophancy rule): the LLM intelligence is the host model's. Native's contribution is exactly these mechanisms — typed primitives, contracts, registry, trustworthy record, verifier, propose/approve loop — which turn one-off LLM output into a running, changeable, self-improving system.
- Industry generality is content (#6), not engine: every reference system examined (assembly line, ER, turnaround, loan desk, CI/CD) shares the identical skeleton; domains differ only in templates, schemas, limits.
