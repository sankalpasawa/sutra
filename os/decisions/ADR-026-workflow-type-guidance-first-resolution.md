# ADR-026: Workflow shape resolves guidance-first via workflow-type lookup; inner engine always runs

**Status**: Accepted — founder direction (2026-06-14). Design-forward: renders in canon (this ADR + `workflow.md` note) and website (`platform/flow.html` §0) now; runtime build follows the D54 route with the rest of Native (PLANNED-v2 posture, mirrors ADR-025). **Posture note (2026-07-31)**: partially superseded — ADR-029 shipped runtime floors for this spine (workflow-type matcher v0, factors v0, orchestrator mode); PLANNED-v2 stands only for the unshipped remainder.
**Date**: 2026-06-14
**Context anchor**: founder direction this session — "if there is high-level guidance on how the workflow should be, that is how we take it … the high-level guidance can be defined at a platform level and at a child level … if not defined, using the factors and everything we go about how we have done those things"; then the correction — "when you have high-level guidance, within that you also have to run factors, lenses, Cynefin dials … but you have to ensure you follow those steps of the guidance as well."

## Context

Two questions had no canon answer: (1) **how is a workflow's shape chosen** when an input arrives, and (2) **what is the relationship** between a prescribed lifecycle and the factors/lens/Cynefin machinery.

A prior render (June 2026 work-atom.html) framed this as an "adaptive router" emitting "5 dials" — that packaging is unratified and now marked PROPOSED (see `holding/website/native/platform/work-atom.html` §B). The underlying knobs are real canon; the framing was not concluded.

The founder's model names the missing layer: **high-level guidance** = a **workflow type**, which maps exactly onto an existing primitive — a **reusable Workflow** (`reuse_tag=true` → registered as a Skill, minted `W-<hash>`, `return_contract` required per F-13), scoped by `custody_owner` (`primitives/workflow.md`). No new primitive is needed.

Two levels fall out of `custody_owner`:
- **Platform** workflow type: `custody_owner = null` (fleet default, L0).
- **Child** workflow type: `custody_owner = <tenant-id>` (company-specific, L2).

## Decision

Workflow shape resolves in this order:

1. **CLASSIFY** the input by TYPE (Input Routing) + 9-cell (H-Sutra, ADR-001) — Stage 0.
2. **LOOK UP a workflow type** for the work: check **child** custody (`custody_owner = <tenant>`) **first**, then **platform** (`custody_owner = null`). Child-custody wins (more-specific scope).
3. **If a workflow type matches → FOLLOW its steps** (the prescribed skeleton is mandatory).
   **If none matches → CONSTRUCT the steps.**
4. **INNER ENGINE — ALWAYS.** In *both* branches, within every step, run factors (B8) + lens (Method, HOW §3) + Cynefin (+ dials, PROPOSED). Guidance constrains the **outer steps**; it **never** replaces the inner engine.
5. Run the resulting step_graph as Work-Atoms; close via MEASURE → OPERATIONALIZE → LEARN.

**Guidance-first, factors-fallback for the skeleton; inner-engine-always for each step.**

## Why not (alternatives)

| Option | Why rejected |
|---|---|
| FOLLOW **xor** CONSTRUCT (fork) — factors only on the construct branch | Founder correction (2026-06-14): even when a workflow type is followed, factors/lens/Cynefin still shape each step. A prescribed skeleton does not switch the inner engine off. |
| Platform-wins precedence | `custody_owner = <tenant>` is strictly more specific than `null`; child override is the natural config cascade and what the founder described ("defined at platform AND child"). |
| New "workflow-type" primitive | A reusable Workflow (`reuse_tag` + `custody_owner` + `return_contract`) already is this. New primitive duplicates canon. |
| Keep the "adaptive router / 5 dials" as the resolution story | Unratified packaging (now PROPOSED). The dials are an inner-engine detail, not the resolution layer. |

## Consequences

- `primitives/workflow.md` gains a "Workflow-type resolution" WHAT-note pointing here (charter says WHAT, ADR says WHY).
- The Native router model (work-atom.html §B) must gain a **Stage 0** above its tier/certainty/lens axes — it currently assumes TYPE=task with no workflow-type lookup. Flagged on that page.
- `flow.html` §0 renders this as the canonical spine (rename "high-level guidance" → "workflow type"; inner-engine band shown as always-on).
- Open (amended 2026-07-30, narrowed): the **matching** function's deterministic v0 floor shipped per ADR-029 (`bin/workflow-type-match.sh`, fixture f5); the skill-judgment override layer above the floor remains open. The `dials` inside the inner engine remain PROPOSED pending their own ADR.

## References

- `../native/primitives/workflow.md` — `reuse_tag` / `return_contract` (F-13) / `custody_owner` (I-8); the workflow-type substrate.
- `../native/blocks/B8-task-framework-factors.md` — factors (inner engine).
- `ADR-025-shape-frame-then-decompose.md` — FRAME (lens) inside SHAPE.
- `ADR-001-h-sutra-9cell-grid.md` + Input Routing skill — Stage-0 classification.
- `../native/blocks/7d-lifecycle-orchestrator.md` — the task workflow type (8-phase).
- `ADR-027-value-axis-single-primitive.md` — same-day generalization of the inner-engine lens into the generic axis engine (unification: its Decision 5).
- `ADR-029-flow-orchestrator-mode.md` — runtime floors for this spine (matcher v0, factors v0, orchestrator mode).
- Website: `holding/website/native/platform/flow.html` §0 (render).
