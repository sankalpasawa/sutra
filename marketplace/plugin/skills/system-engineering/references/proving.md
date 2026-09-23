# Proving a generative layer

**status**: v1, 2026-09-23 · **owner**: System engineering · **read when**: the component is built and you are about to say it works.

An architecture cannot be proved by describing it. It is proved by making things with it and watching what happens. Three proofs, in order of how much they tell you.

## Proof 1 — three real instances

Make three, named, real, wanted by someone.

| Outcome | What it means |
|---|---|
| all three went through unchanged | the boundary is right |
| one needed a special case | the boundary is wrong; fix the component, not the instance |
| one needed a special case and you added it to the instance | the architecture is now a lie, and the next person will not know |

The third instance matters most. One proves nothing, two can be a coincidence of similarity, three is where a bad cut shows.

## Proof 2 — one malformed instance

Hand-write an instance that breaks a guarantee, and run the proof against it.

| Outcome | What it means |
|---|---|
| refused, naming the broken line | the guarantee is real |
| accepted | the guarantee is a comment; the component is a suggestion |

This is the check most often skipped, because everything made by the component is well-formed by construction. The risk is never the things the component makes. It is the things made beside it.

## Proof 3 — the numbers at one, ten and a hundred

Generate one, ten, a hundred, on a throwaway store. Write down two numbers at each: what it costs to **make** one more, and what it costs to **read** the whole set.

| Shape | Reading |
|---|---|
| make flat, read flat | the layer scales |
| make flat, read growing | there is a missing index or a missing summary; it will hurt at the screen |
| make growing | something is scanning everything on every write; fix it now, it never gets cheaper |

Opinions about scale are worth nothing next to these two numbers. Take them in the same session as the build, while the throwaway store is already there.

## What to record

Whatever the proofs say, one block goes into the decision record:

```
COMPONENT:   <name>, version
INSTANCES:   the three, named
SPECIAL CASES NEEDED: none | <what, and what changed because of it>
MALFORMED:   refused | accepted (and what that means)
NUMBERS:     make at 1 / 10 / 100, read at 1 / 10 / 100
REVERSES IF: <the observation that would make this the wrong design>
```

The last line is the one that makes it a decision rather than a preference: name in advance what you would have to see to call this wrong.

## The honest failure modes of generators

| # | Mode | Symptom |
|---|---|---|
| 1 | Built too early | one instance, and the component changes every time a second is attempted |
| 2 | Cut in the wrong place | every instance passes an option to switch off something the component does |
| 3 | No surface | only its author can make an instance |
| 4 | No record | instances exist, and nobody can list them |
| 5 | Proof inside | hand-made instances bypass the guarantee silently |
| 6 | Grown past its law | variants that add nothing, because deriving was easier than deciding |

Mode 6 is the one that arrives last and hurts longest: forty templates where four would do. The cure is a periodic read of the set, not a stricter law.

---
provenance: {author: claude, date: 2026-09-23, session: 8e2713c3, inputs: [the function-templates suite and its instrument check, the eight-state runner built the same day, the department screen's card layer], review: none by a second model, confidence: high on proofs 1 and 2, which this system has run; proof 3's thresholds are unmeasured here and are stated as a method, not a number}
