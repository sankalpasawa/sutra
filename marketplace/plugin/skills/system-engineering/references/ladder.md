# The ladder — instance, component, architecture, law

**status**: v1, 2026-09-23 · **owner**: System engineering · **read when**: a request arrived as one thing and you suspect it is really a kind of thing.

## The four rungs

| Rung | What lives there | Who changes it | How often |
|---|---|---|---|
| 1 Instance | the thing someone asked for | anyone with permission | daily |
| 2 Component | what makes instances of that kind | a builder, deliberately | monthly |
| 3 Architecture | the set of components and the seams between them | a design decision | quarterly |
| 4 Law | what must stay true however the set grows | the founder | rarely, and never by accident |

Two mistakes cost the most, and they are mirrors of each other.

**Building at rung 1 what belongs at rung 2.** The twentieth workflow is hand-made, each slightly different, and no two carry the same guarantees. The cost is invisible until someone asks "do all of these check their input" and the answer takes a week.

**Building at rung 2 what belongs at rung 1.** A generator is built for a thing needed once. It costs three times the instance, hardens a shape nobody has tested, and the second instance never comes.

## Which rung is this request on

Ask in this order, and stop at the first yes.

| # | Question | If yes |
|---|---|---|
| 1 | Would this be hand-built three or more times? | rung 2 |
| 2 | Would copies drift invisibly? | rung 2 |
| 3 | Must a non-coder be able to make one? | rung 2 |
| 4 | Does it change what may exist at all? | rung 4, and it is the founder's |
| 5 | None of the above | rung 1: build it and move on |

## Climbing

Climbing is finding the boundary between what repeats and what varies.

1. **Name three real instances.** Real, with their own names. If you cannot, you are generalising from one, which is how the wrong abstraction gets built.
2. **Write them side by side.** Literally: three columns.
3. **Mark every row same or different.** The same rows are the component. The different rows are its input.
4. **Look at the guarantees separately.** If the three differ in what they *promise*, they are three components wearing one name.
5. **Cut where the marks change**, not where the code happens to be split today.

## Descending

Design down one rung at a time, and let each rung constrain the next.

| From | To | What carries down |
|---|---|---|
| Law | Architecture | the invariants every component must preserve |
| Architecture | Component | the contract, the seams, the growth law |
| Component | Instance | the type, the defaults, the proof that refuses a bad one |

The descent is where a design is falsified: build one real instance and see whether it fits. A special case at this stage is not a detail, it is the architecture telling you it is wrong.

## Standing on the ladder in this system

| Rung | In Native |
|---|---|
| 1 | a workflow, a department, an engine, a card, a page |
| 2 | the builders, the function templates, the start-a-department engine |
| 3 | the four homes and the seams: records, asks, engines, screens |
| 4 | every write is an ask; a derived thing may add or tighten, never drop; nothing is deleted |

---
provenance: {author: claude, date: 2026-09-23, session: 8e2713c3, inputs: [the builders law, the function-templates law, the department life cycle work of the same week], review: none by a second model, confidence: high; every example named here exists in the repository}
