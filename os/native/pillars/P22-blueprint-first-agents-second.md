---
part-id: P22
bucket: pillars
template: L1-pov
parity-source: ADR-037 + workflow-engine.html:325-326 (X1, X2) + the-six-layers.html:199-204 (v2)
parity-source-sha256: 67a68d05f7f6b0e8d0bfc9cdc9be144811eb35807427b869204304c77cc4513a
status: DRAFT v1
authored: 2026-09-11
---

# P22: Blueprint first, agents second

Purpose: the doctrine form of ADR-037. Write the workflow before anything runs, put agents on the written thing, let the record correct the blueprint with approval.

## Pillar statement

> Write the workflow before anything runs. Then put agents on the written thing, never on a blank prompt. Every run leaves a record, and the record corrects the blueprint only with approval. The written half (Workflow) is authored; only the grown half (Engine) runs. Rationale in [ADR-037](../../decisions/ADR-037-blueprint-first-agents-second.md); axioms X1 no naked work and X2 no stateless execution per `holding/website/native/platform/model/workflow-engine.html:325-326`.

## What this rules in

- Authoring before dispatch: RESOLVE finds a workflow type and FOLLOWs it, or CONSTRUCTs one; either way the run is engine-backed from run 1 (`workflow-engine.html:291`).
- A single atom is a workflow of one (X1). For trivial work "blueprint first" costs one declared goal and one done-check, not a document.
- The done-check is declared before the run: the Work-Atom's verify template (`../primitives/workflow.md`; atom floor at runtime).
- Agents ask only at real decisions, and those decisions are gates written into the blueprint (`../primitives/approval.md`, ADR-009).
- The record corrects the blueprint through propose-then-approve (ADR-010 organic emergence; `../blocks/B5-*.md` governance).
- Phase sort of the product layers per ADR-037 Decision 3: Ontology, Workflow design and Marketplaces are blueprint; Agents and Tooling are run; Feedback is the loop.

## What this rules out

- Dispatching an agent from a blank prompt with no workflow and no declared done-check.
- Mutating the workflow file at run time. Accumulation lands on the engine; the written half stays a stateless template (`workflow-engine.html:329`).
- Letting the record rewrite the blueprint without approval.
- Treating tool access as a substitute for a workflow. Equipping an agent is not shaping its work.

## Falsification test

**If a run is dispatched to an agent with no workflow (no atom, no declared done-check) and completes without writing to any engine's record slice, P22 is broken.** Newly authored; no section 10.3 row exists. Post-cutover gap-fill under `../MIGRATION-PLAN.md` section 9 limitation 2, the same authority P19 used.

## Doctrine inheritance (from L0)

P22 is not in the section 10.4 doctrine-tension table. Parent: `./P0-customer-focus-first.md`. Nearest kin: `./P1-artifact-first.md` (the blueprint is itself a typed artifact), `./P9-closed-loop-artifact.md` (the record feeds the next run), `./P11-constrained-problem-construction.md` (the blueprint is the constraint), `./P12-deterministic-surface-stochastic-core.md` (the written half is the deterministic surface; agents are the stochastic core). One tension, with the Simple test: an authoring step precedes every run. Resolved by X1: an atom is a workflow of one, so the minimum blueprint is one line.

## References

- [ADR-037](../../decisions/ADR-037-blueprint-first-agents-second.md), decision rationale and the phase sort.
- `holding/website/native/platform/model/workflow-engine.html:75`, `:94`, `:291`, `:325-326`, `:329`, written and grown halves, X1 and X2 (production evidence; prose home).
- `holding/website/native/the-six-layers.html:199-204` (v2, 2026-09-08), the six product layers in time order.
- `holding/website/native/the-system-simply.md:36-45`, SHAPE, RUN, RECORD, GROW (the markdown source, not the HTML render).
- `../primitives/workflow.md`, `../primitives/approval.md`, ADR-009, ADR-010, cross-bucket.
- `./P0-customer-focus-first.md`, `./P1-artifact-first.md`, `./P9-closed-loop-artifact.md`, `./P11-constrained-problem-construction.md`, `./P12-deterministic-surface-stochastic-core.md`, doctrine kin.
- Parity-source deviation: canon GAP. The content did not exist in `NATIVE-ENGINE.md`; parity-source anchors point at ADR-037 and the production site pages per `../MIGRATION-PLAN.md` section 9 limitation 2.

---

provenance: {author: claude, date: 2026-09-11, inputs: [ADR-037, workflow-engine.html, the-six-layers.html v2, the-system-simply.md, artifact da61ccf3 2026-09-10], review: dual-lane, supersedes: none, confidence: high, gaps: [no section 10.3 or 10.4 row; falsification test newly authored; codex round 2 pending at authoring]}
