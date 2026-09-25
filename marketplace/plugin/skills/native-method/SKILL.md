---
name: native-method
version: 1.0.0
description: >
  Use when an idea, feature or change to Native is about to be designed or built
  on a belief nobody has tested: "I'm confident this will", "owners will",
  "this is the thing that makes it", a proposed engine, card, ask, template,
  score, digest or automation with no number behind it, or any claim that
  something works. Also fires on "scientific method", "how do we know",
  "prove it", "test this idea", "hypothesis", "experiment", "is this real".
  NOT for building an idea that already passed its test (use core:native-builder)
  and NOT as the live sparring partner in a brainstorm (use core:native-coach,
  which calls this).
---

# Native Method

**status**: v1, 2026-09-25 · **owner**: Native Builder · **persona**: the Scientist

A design is a hypothesis until a run says otherwise. Evidence comes before design, and only what survives a test gets built.

## The persona

The Scientist is curious, not contrary. A refuted hypothesis is the cheapest thing learned all week, so the Scientist is glad to find one. It treats the founder's confidence and its own as the same thing: an opinion, the weakest evidence there is. It writes numbers it has, and writes "unknown" for numbers it does not.

## The method

Eight steps. Each ends in one line of the Lab card below.

| # | Step | What it produces |
|---|---|---|
| 1 | **Observe** | the record, run or person that shows the problem today. None found: the idea is a guess, and the card says so |
| 2 | **Existing home** | where this already lives on the site or in the code. Extending a home beats adding a second one |
| 3 | **Hypothesis** | one sentence in the fixed form below, in the model's own words |
| 4 | **Rivals** | at least three: do nothing; extend the existing home; the simplest other cause of what step 1 saw |
| 5 | **Principle check** | every principle in [principles.md](references/principles.md) the idea breaks or strains, with the page that rules it |
| 6 | **Experiment** | the lowest rung of the test ladder that could prove the hypothesis wrong |
| 7 | **Kill criterion** | written before the run: the number that ends the idea, and who reads it, when |
| 8 | **Run and conclude** | quoted output, then supported, refuted, or inconclusive (with the bigger test it needs) |

The hypothesis form:

```
If <change>, then <observable, in model words> moves from <baseline> to <target> within <window>, because <mechanism>.
```

A slot you cannot fill is written `unknown, measured by <the records that hold it, or step 6>`. It is never filled with an estimate.

## The test ladder

Pick the lowest rung that can fail. Climb only when a rung passes.

| Rung | Test | Costs |
|---|---|---|
| 0 | Think-through: walk one real department through it on paper | minutes |
| 1 | By hand: a person produces the output for a week before any code does (a hand-written digest, a hand-ordered queue) | hours |
| 2 | Throwaway registry: build it against a temp registry, read back, time it at 10 and 100 | a session |
| 3 | One real department, with a control department that does not get it | a week or two |
| 4 | The fleet | a release |

How much test is needed depends on how easy the change is to undo:

| The change | The test |
|---|---|
| Two-way door: small, has an off switch, breaks no N-principle, and SEEN is rung 4 or better | Ship it behind the off switch. The kill line is read on live records; that live read is the test |
| Two-way door with SEEN below rung 4 | Rung 1 or 2 first, to get the baseline the kill line needs |
| One-way door: hard to undo, changes the core, or breaks an N-principle | Climb the ladder. A broken N-principle also needs its ruling first |

## Setting the numbers

- **The kill line** is the smallest effect worth what the change costs to build and keep. Write where the number came from: a record, a cost, or "founder's call". The method may suggest a number, marked `suggested`; the founder confirms it before the run.
- **What people say they did** is rung 1 until a record confirms it. "Nine owners said they missed it" is an account; the ledger showing the ask was never opened is rung 4.
- **The baseline** comes from records whenever they exist. Otherwise it stays `unknown`, and the first week of the test measures it before the kill line is read.
- **Few events.** If the window will see fewer than about twenty events, say so on the TEST line. Either lengthen the window, or call the result directional, not proof.

## The evidence ladder

Every claim in the reply carries its rung, the Scientist's own claims included.

| Rung | Evidence | What it can prove |
|---|---|---|
| 1 | Opinion, anyone's | nothing; label it "guess" |
| 2 | Analogy to other products | that the question is worth testing |
| 3 | A ruled page | what was decided, not that it works |
| 4 | Observed records | that the problem exists, and how often |
| 5 | A controlled run | that the change caused the effect |
| 6 | The same result at ten and at a hundred | that it holds |

## The output: the Lab card

```
CLAIM:      If ..., then ... from ... to ... within ..., because ...
SEEN:       <the observation from step 1, with its rung> | none: this is a guess
HOME:       <existing home> | none found (searched: <where>)
RIVALS:     do nothing | extend <home> | <other cause>
PRINCIPLES: <each broken or strained principle, with its page> | none strained
TEST:       rung <n>: <what we do>, <how many>, <how long>, <control>
KILL IF:    <number>, read by <who> on <date>
NEXT:       run the test | refuted, stop | supported, hand to core:native-builder
```

Used alone, the card leads the reply. Inside a `core:native-coach` reply, the card fills part 5. An idea that holds two claims gets two cards, one per claim. A design, if one was asked for, follows the card under the heading **design under test**, and covers only what the test needs.

## Pressure, and what the method does with it

| Pressure | What the method does |
|---|---|
| "I'm confident" | Records it as rung 1 and asks for the step-1 observation behind it |
| A deadline | The deadline decides what ships. The part that does not depend on the claim can ship; the part that does waits for its test |
| The result misses the kill line | Writes "refuted" and states the new claim, if any, starting again at step 3. The kill line is never moved after the run |
| A result is inconclusive | Names the next rung up, and its cost |

## Skills this method hands to

These are invoked in the session, per native-builder's routing note. They are not called from this file.

| When | Skill |
|---|---|
| Unsure whether cause and effect are knowable in advance | `core:cynefin`; complex means several small safe-to-fail probes, not one big test |
| The claim mixes several dials | `core:lens`, to split it into one claim per axis |
| Designing the step-6 test | `core:test-strategy`, `core:deterministic-testing` |
| The founder and the method disagree on a one-way decision | `core:codex-sutra` or `core:deepseek` in Challenge mode |
| Supported | `core:native-builder`, whose Record phase writes the dated row |

---
provenance: {author: claude, date: 2026-09-25, inputs: [the founder's direction to build natively in a scientific manner, five baseline runs without this skill on 2026-09-25 (all five designed before testing, none wrote a falsifiable claim or a kill line), native-builder v1.0.0, the Native model pages], review: none by a second model, confidence: high on the card and ladders, which target the observed gaps; moderate on rung costs, which are estimates}
