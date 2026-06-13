# ADR-025: SHAPE phase = Frame → Decompose

**Status**: Accepted — founder direction (2026-06-13). Design-forward: renders in canon (this ADR + 7d citation) and website now; runtime build follows the D54 route with the rest of Native (mirrors maturation / work-atom PLANNED-v2 posture).
**Date**: 2026-06-13
**Context anchor**: founder direction this session ("we have to think about the framing of the problem … which might be in the shape part of the life cycle"). TODO captured in `holding/website/native/platform/work-atom.html` founder queue + `holding/TODO.md` (commit `4673c34`).

## Context

The 8-phase task lifecycle (D30a: OBJECTIVE → OBSERVE → SHAPE → PLAN → EXECUTE → MEASURE → OPERATIONALIZE → LEARN) renders SHAPE as a single move: decompose (per B2). See `7d-lifecycle-orchestrator.md` UX-flow step 4 ("Phase SHAPE decomposes per B2") and its Blocks dependency ("B2 — SHAPE phase consumes B2 Decomposition").

This is incomplete. Shaping a problem is two moves:

1. **FRAME** — choose the point(s) of view that matter for THIS problem ("how do you look at the situation that really matters").
2. **DECOMPOSE** — break it up ALONG that frame (B2).

Frame precedes and drives decompose: the lens decides the cut lines. The same problem framed three ways decomposes three ways:

| POV (founder examples) | Canon lens family (HOW §3) | Decomposition shape |
|---|---|---|
| History | TIME | by-epoch — precedent, evolution, trajectory |
| Product | CONCERN (value) / VIEWPOINT (operator) | by-deliverable — what the operator gets |
| Technical | CONCERN (structure) / VIEWPOINT (builder) | by-component / by-risk |

(The three POVs are concrete lenses drawn from the canon family — they are not new lens names. History is a TIME lens; product and technical are two CONCERN lenses, value-vs-structure, optionally split by VIEWPOINT.)

Framing is not a new idea — it is one we **had and dropped**:

- The retired v1.2.1 lifecycle (`sutra/archive/package-v1.2.1-retired/os-core/TASK-LIFECYCLE.md`) named SHAPE explicitly as **"Framing: what's the right approach? what are the constraints?"** + **"Option evaluation,"** depth-scaled D1→D5.
- The Native migration collapsed SHAPE to bare B2 decompose.
- Framing now survives ONLY as the adaptive router's implicit **AXIS 3 (LENS)** in HOW §3 — present in the router diagram, absent from the phase the lifecycle actually walks.

The lens machinery already exists in canon (HOW §3): the Lens primitive, the lens family (viewpoint · concern · time · ownership · scale · certainty), the 6 HOW dimensions (Approach · Mindset · Structure · Detailing · Decomposition · Cascading), and a 6-step decision procedure. B2 already exists for decompose. The gap is purely the **wiring** — making the lens an explicit FIRST sub-step of SHAPE, feeding B2.

## Decision

SHAPE becomes two ordered sub-steps inside the one phase:

```
SHAPE = FRAME  ->  DECOMPOSE
  FRAME      pick the lens(es)/POV per HOW §3 (Lens primitive; family
             viewpoint/concern/time/ownership/scale/certainty); record
             chosen lenses + why in DecisionProvenance.
  DECOMPOSE  B2 splits intent into sub-intents ALONG the chosen frame;
             the frame sets the HOW §3 Decomposition dimension
             (by-epoch / by-deliverable / by-component / by-risk / ...).
```

- FRAME **reuses** HOW §3's Lens primitive + decision procedure — no new primitive (honors the work-atom "no new invention" rule).
- The frame's output (chosen lens set) is an **input to B2**, carried as context via B11 PromptBuilder into the decompose call. B2's `Decomposition` gains no new field in v1. A typed `frame_lens[]` on `Decomposition` is a v2 option (OPEN).
- **Provenance**: chosen lens(es) + rationale persist via the existing DecisionProvenance primitive, so "why this cut" is auditable.
- Sequence stays **within** SHAPE — no change to the 8-phase roster or the §4.2 state machine.

## Why not (alternatives)

| Option | Why rejected |
|---|---|
| Leave SHAPE = decompose; framing stays an implicit router axis | The thing that decides the decomposition cut lines is invisible in the phase that cuts. Builders + operators cannot see or record the frame. The retired lifecycle proved framing deserves to be explicit. |
| New FRAME phase between OBSERVE and SHAPE (→ 9 phases) | Bloats the canonical roster (D30a is 8; master §10.1's extra ORIENT station is already flagged as a reconcile-down gap). Framing is part of shaping, not a separate station. |
| New Lens/Frame primitive | HOW §3 already has the Lens primitive; a new one duplicates canon. |

## Consequences

- **Positive**: the decision that drives every decomposition is explicit, recorded, and auditable; HOW §3 (the IP) is wired into the lifecycle instead of floating beside it; restores a capability the v1.2.1 lifecycle had.
- **Cost**: 7d block + work-atom diagram updated now; `how-methodology.html` cross-ref + B2 lens-as-context input contract are follow-ups.
- **Design-forward**: nothing is built — renders in canon + website now; runtime follows the D54 route with the rest of Native.
- **OPEN**: (1) typed `frame_lens[]` on `Decomposition` (v1 context-only vs v2 field); (2) whether FRAME is a gated step (`requires_approval`) for high-stakes/irreversible work or always implicit; (3) reconcile master §10.1 ORIENT station while here.

## References

- `../native/blocks/7d-lifecycle-orchestrator.md` (SHAPE phase — amended to cite this ADR).
- `../native/blocks/B2-decomposition.md` (the DECOMPOSE half).
- `holding/website/native/platform/how-methodology.html` — HOW §3 (Lens primitive, lens family, 6 HOW dimensions, decision procedure, AXIS 3 LENS).
- `holding/website/native/platform/work-atom.html` (renders SHAPE = frame → decompose; founder-queue TODO resolved by this ADR).
- `sutra/archive/package-v1.2.1-retired/os-core/TASK-LIFECYCLE.md` (retired SHAPE = Framing + Option-evaluation — the dropped capability restored here).
- `sutra/archive/package-v1.2.1-retired/os-core/d-engines/ADAPTIVE-PROTOCOL.md` (Cynefin shapes + 5 depths — certainty-lens prior art).
- `holding/research/ADAPTIVE-PROTOCOL-RESEARCH.md` (Cynefin / Wardley / Military RoE / Agile — the framing research that fed v1).
- D30a (8-phase lifecycle). HOW §3 AXIS 3 (LENS).
