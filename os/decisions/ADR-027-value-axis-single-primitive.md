# ADR-027: value⇄axis is the single primitive — axes are minted, the cross is a runtime product (nothing hard-coded)

**Status**: Accepted — founder direction (2026-06-14, "do both"). Design-forward: renders in canon (this ADR) and website (`platform/flow.html` §H) now; runtime build follows the D54 route with the rest of Native (PLANNED-v2; mirrors ADR-025/026). **Posture note (2026-07-31)**: PLANNED-v2 stands for the axis engine itself (`mint`/`pick` + reflexivity remain theory, FQ1), while ADR-029 shipped mechanical floors adjacent to this spine — floors, not the engine (ADR-029 Decision 6).
**Date**: 2026-06-14
**Context anchor**: founder direction this session — "make it happen in a very generic way so I don't have to hard-code the axis name and we don't have to hard-code the cross product."

## Context

Method (HOW §3) names two recommended axes (Realization, Reflection) plus a lens family (viewpoint · concern · time · ownership · scale · certainty) and a Realization×Reflection cross. A naive render would **hard-code** those axis names and the cross grid into the engine.

That contradicts the canon itself. HOW §3.1: *"a value is just an axis … **this is the only primitive; everything else is this move repeated.**"* HOW §3.3: *"Dimensions are **generated, not listed**. Each dimension = (interrogative × mechanism) — a finite generator mints an open set on demand … the number of Realization levels and Reflection heights is **not fixed**; it is decided per idea."*

So the axes and the cross are **outputs**, not schema. Hard-coding them would cap an explicitly open set and prevent per-idea instantiation.

## Decision

The engine hard-codes exactly **one** primitive and a small generator; everything else is data.

1. **The only built-in primitive: `value ⇄ axis`.** A value is a member of an axis; an axis is a set of values; the role is relative to level (axis seen from below = value seen from above). Formally: `Axis = { values: Value[] }`, `Value = Scalar | Axis` — the recursion **is** the type. No `name` field is part of the type; a name is a label on an instance.

2. **Axes are minted, not enumerated.** `mint(interrogative × mechanism) → Axis`. "Realization", "Reflection", "viewpoint", "certainty" are instances the generator produces — never schema constants.

3. **The cross is a runtime product.** `cross = product(picked_axes)`. The axes picked for an idea are chosen by the **decision test** (keep an axis only if it changes what-you-build or who-reads). The cross is computed over whatever was picked — never a fixed grid.

4. **One primitive, three directions** (all the same `value⇄axis` move):
   - **DOWN** decompose: value → axis of sub-values. Stop: **atomicity** (smallest buildable). [labelled "Realization"]
   - **UP** generalize: value → member of an axis above. Stop: **reflexivity** (describes itself). [labelled "Reflection"]
   - **ACROSS** reframe: classify the same value by a different axis. Stop: **decision test**. [labelled "the lens family"]

5. **Unification with the workflow recursion (flow §G / ADR-026 spine; the numbered modes live in flow §G — ADR-026's text defines the resolution order, not numbered modes).** The recursion modes ARE `value⇄axis`:
   - Mode 2 (step → sub-workflow) = DOWN (decompose).
   - Mode 3 (how-of-how) = UP (generalize / climb to design the method).
   - the lens at each block = ACROSS (reframe).
   There is one generic engine under both the recursion and the Method axes, not two.

## Why not (alternatives)

| Option | Why rejected |
|---|---|
| Hard-code axis names (Realization/Reflection/viewpoint/…) as blocks | Contradicts §3.1 ("the only primitive") + §3.3 ("generated, not listed"); caps an open set; can't add a per-idea axis. |
| Hard-code the Realization×Reflection cross as a fixed grid | The cross is a product over the axes an idea actually instantiates — different arity per idea; a fixed grid is wrong for any idea that needs other axes. |
| Two separate engines (recursion vs axes) | They are the same `value⇄axis` move in different directions; two engines duplicate the primitive. |

## Consequences

- `flow.html` §H renders the inner-engine "lens" as a generic **axis engine** (primitive + mint + pick + product + three stops); Realization + Reflection are offered as default **seeds** only, everything else minted on demand.
- Canon home for the primitive stays HOW §3.1/§3.3 (this ADR records the **unification** + the generic contract; it does not duplicate §3 content).
- Open / unbuilt: the `mint`/`pick` generator and the **reflexivity detector** (when has an axis become self-describing?) are theory (FQ1 PROPOSED, zero-runtime-enforcement). Same halting-family open problem flagged on Work-Atom and flow §G.

## References

- HOW §3.1 (`value⇄axis` — "the only primitive") + §3.3 (generated, not listed; atomicity/reflexivity/decision-test stops) — `holding/website/native/platform/how-methodology.html`.
- `ADR-026` (workflow type / guidance-first spine) — the recursion this unifies with.
- `ADR-025` (FRAME = pick the lens inside SHAPE).
- Website: `holding/website/native/platform/flow.html` §G (recursion) + §H (generic engine).
