---
name: system-engineering
version: 1.0.0
description: >
  Design the layer that makes the thing, not the thing. Use when a capability
  would otherwise be hand-built once per case: instead of building this
  workflow, design the component that builds workflows; instead of adding this
  card, design how cards are added. Works at the architecture rung — finds
  where a component boundary belongs, writes its contract (what it may write,
  what it must ask for, what it returns, how it fails), picks the growth law
  (base and child, registry, template and pick), and proves the design by
  building one real instance through it. Fires on "build the architecture",
  "system engineering", "a component that creates X", "above productization",
  "so we do not build this by hand every time", "make the system able to make
  these". NOT for shaping one system (use core:architect), NOT for building one
  unit (use core:native-builder), NOT for a thing genuinely needed once.
---

# System engineering — designing what builds

Most requests arrive as an instance: build this workflow, add this card, make this department. Sometimes the right answer is to build it. Sometimes the right answer is one rung up: build the thing that makes them, so the next twenty cost nothing and none of them drift.

This skill decides which, and when it is the second, designs the component properly.

Read [ladder.md](references/ladder.md) for the four rungs and how to move on them, [component-contract.md](references/component-contract.md) for what a component owes, and [proving.md](references/proving.md) for the only proof that a generative layer works.

## 1. The ladder

| Rung | What lives there | Example in this system |
|---|---|---|
| 1 Instance | the thing someone asked for | a workflow that checks top-up eligibility |
| 2 Component | the thing that makes instances of that kind | the builder that constructs workflows |
| 3 Architecture | the set of components, their contracts, how they compose | builders, templates, engines, records, and the seams between them |
| 4 Law | what must stay true as the set grows | a derived thing may add or tighten, never drop; every write is an ask |

A request arrives at rung 1. This skill climbs to 3, designs downward, and proves back at 1.

## 2. When to climb, and when not to

Climb when **two or more of these are true**:

| # | Signal |
|---|---|
| 1 | this shape would be hand-built three or more times |
| 2 | the copies would drift, and the drift would be invisible |
| 3 | the thing must be creatable by a person who cannot read the code |
| 4 | the system is supposed to create these for itself later |
| 5 | each instance needs the same guarantees, and forgetting one is silent |

**Do not climb** when the thing is needed once, when the shape is still moving weekly, or when you cannot name three plausible instances. A generator with one instance is a costlier instance, and it hardens the wrong shape.

## 3. The climb — finding the boundary

Work in this order. Each step is a question with an answer you can write down.

| # | Step | The question |
|---|---|---|
| 1 | List three instances | what are three real things this component would make, named, not hypothetical |
| 2 | Diff them | what is the same in all three, and what differs |
| 3 | Cut | the same part is the component; the different part is its input |
| 4 | Name the type and the instance | what is written once, and what is grown by each run |
| 5 | Find the guarantees | what must be true of every instance, whoever made it |
| 6 | Find the seam | what the component may write itself, and what it must ask a person for |

If step 2 shows the three instances differ in what they *guarantee*, stop: that is three components, not one.

## 4. The six parts of a generative layer

Every working generator in this model has all six. A missing one is where it will fail.

| # | Part | Written as |
|---|---|---|
| 1 | **The type** | the shape every instance takes, and the fields it must carry |
| 2 | **The contract** | preconditions, what it may write, what it returns, what it does on failure |
| 3 | **The growth law** | how variants are made: derive from a base, register a kind, or pick a template |
| 4 | **The record** | where an instance lives so that it can be read, versioned and retired |
| 5 | **The surface** | how a person sees, steers and stops it in the app |
| 6 | **The proof** | the check that fails when an instance is malformed |

Two of these get skipped most often, and both are fatal. Without **the record**, instances exist only where they were made. Without **the surface**, the generator can only be driven by whoever wrote it, which makes it infrastructure, not product.

## 5. The growth law — pick one deliberately

| Law | How a variant is made | Good when | Costs |
|---|---|---|---|
| Base and child | every user derives a child that may add or tighten, never drop | the guarantees matter more than the freedom | every child is a record to keep |
| Registry | a kind is registered with a handler | the variants are few and known | the registry becomes the bottleneck |
| Template and pick | ready-made variants, the person picks one | non-technical creation is the point | templates rot unless something keeps them true |
| Free-form | anything goes, validated after | exploration, before the shape settles | drift is invisible until it is expensive |

This model's function templates use base-and-child with a narrowing-only law, and a suite enforces it. That is the reference implementation: read it before choosing a different law.

## 6. The descent — designing down

Having designed rung 3, come back down deliberately:

1. Write the type and the contract before any code.
2. Build the component with the smallest input that could work.
3. Build **one real instance** through it — a real one, not a sample.
4. If that instance needed a special case, the architecture is wrong. Fix the architecture, not the instance.
5. Build the second and third instance. The third is where the design is actually tested.

## 7. Proof

A generative layer is proved by **instantiation, not argument**. The two checks:

| # | Check | Passes when |
|---|---|---|
| 1 | Three real instances, made through the component | none of them needed a change to the component |
| 2 | One malformed instance | the proof from part 6 refuses it |

Then the numbers: make one, make ten, make a hundred, and write down what the hundredth costs to create and to read. An architecture whose read cost grows with the count is a queue with extra steps.

## 8. Where this sits beside the other skills

| Skill | Rung | Answers |
|---|---|---|
| `core:architect` | one system | what is this system's shape, and its decisions |
| **`core:system-engineering`** | **the generative layer** | **what component should exist so we stop hand-building these** |
| `core:native-builder` | one unit | how do I build this piece and prove it |
| `core:incremental-architect` | a live change | how do we get from the old shape to the new one without stopping |

Running order for a real capability: system-engineering designs the component, native-builder builds it and the first instance, architect records the decision if the shape is new.

## 9. The output

This skill's output is a short design, never a document nobody reads:

```
COMPONENT: <name>          what it makes
INSTANCES: <three, named>  the real ones it must make
TYPE:                      the shape every instance takes
CONTRACT:                  may write / must ask / returns / on failure
GROWTH LAW:                base-and-child | registry | template | free-form, and why
RECORD:                    where an instance lives
SURFACE:                   how a person drives it in the app
PROOF:                     the check that refuses a malformed instance
FIRST INSTANCE:            the real thing built through it, to prove it
```

## 10. The self-check

1. Can I name three real instances, or am I generalising from one?
2. Does every instance carry the same guarantees, enforced by something that can fail?
3. Where does an instance live, and who can read it a year from now?
4. Can a person who cannot read the code create one?
5. What does the hundredth instance cost?

---
provenance: {author: claude, date: 2026-09-23, session: 8e2713c3, inputs: [the founder's direction for a systems-engineering skill above productization, the builders law and the function-templates law as already ruled in this model, the life cycle work of 2026-09-23], review: none by a second model, confidence: high on sections 3 to 7, which describe generators already working in this system; moderate on section 5's costs column}
