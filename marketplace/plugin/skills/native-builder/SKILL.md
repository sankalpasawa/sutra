---
name: native-builder
version: 1.0.0
description: >
  Build any part of Native — a record, an ask, an engine, a screen, a page, a
  journey — through one loop that ends every phase on a check a machine can run.
  Use when the work is building or changing the Sutra system itself: a new
  department capability, a proposal kind, an engine, a department-screen card, a
  Native model page, a runnable walk, or a piece of the root department. Also
  fires on "build native", "native builder", "system build", "add this to the
  model", "make the system do X itself". Names which of the ten skill sets the
  work needs, takes that set's own check as the unit's verify, and refuses to
  call a phase done on a check that cannot run. NOT for ordinary repo work with
  no Native record behind it, for writing prose (use core:writing-style), or for
  deciding whether a thing should exist (use core:architect first).
---

# Native Builder

Native is built out of four homes and ten muscles. Most build sessions fail the same way: the work is done in the wrong home, or proved with a check weaker than the claim. This skill fixes the order and fixes the bar.

Read [native-map.md](references/native-map.md) for where everything lives, [skillsets.md](references/skillsets.md) for the ten muscles and what each one is proved by, [build-loop.md](references/build-loop.md) for the seven phases, and [best-practice.md](references/best-practice.md) for how a skill itself is written.

## 1. The contract, in four lines

1. Name the skill set before the first tool call. One unit, one set; three sets means three units.
2. The set's own check is this unit's verify. Never soften it, never restate it after a fail.
3. Nothing lands undocumented. The page that owns the subject is part of the build, not a follow-up.
4. Every decision gets a dated row and deletes the hedges it closes in the same commit.

## 2. The loop

```
Understand -> Place -> Design -> Build -> Prove -> Document -> Record
```

| Phase | Ends when |
|---|---|
| Understand | one sentence, in the model's words, that a stranger could test |
| Place | the skill set is named and the target path exists or its parent does |
| Design | a table of what changes, and one line on what this makes harder |
| Build | each file exists and reads back the thing it claims |
| Prove | named output, quoted, from the strongest lane available |
| Document | both site guards pass and the page renders |
| Record | a dated decision row, with what would reverse it |

Full detail, and why each phase gets skipped: [build-loop.md](references/build-loop.md).

## 3. The ten skill sets

| # | Set | Proved by |
|---|---|---|
| 1 | Model literacy | the word exists in the model, or a new kind is routed |
| 2 | Record work | a read-back on a throwaway registry |
| 3 | Ask work | refused for a bad argument; applied only after a stamp |
| 4 | Engine work | one run writes a row and its check flips |
| 5 | Screen work | the suite passes and a live walk shows real records |
| 6 | Documentation work | both guards pass; the page renders headlessly |
| 7 | Journey work | the walk runs and prints what it reached |
| 8 | Review work | a test that fails when the claim is false, or a sealed verdict |
| 9 | Scale work | the same number at ten and at a hundred |
| 10 | Growth work | a change the system proposed, a person stamped, that stuck |

Each set names the existing skill it delegates to: [skillsets.md](references/skillsets.md).

## 4. The routing map

One skill invoking another is **not a documented capability** (checked 2026-09-23, see [best-practice.md](references/best-practice.md) item 5). So this table is a map for the session to follow, not a call graph: when a phase needs one of these, invoke it in the session.

| Phase | Call | For |
|---|---|---|
| Understand | `core:domains` | where a thing sits in the tree |
| Understand | `core:architect` | whether the thing should exist at all, and its shape |
| Place | `core:input-routing`, `core:blueprint` | the route and the per-step checks |
| Design | `core:incremental-architect` | when a live thing must change shape under traffic |
| Build | `core:writing-style` | every file's shape, every turn's output |
| Prove | `core:test-strategy`, `core:deterministic-testing` | the suite before the code |
| Prove | `core:codex-sutra`, `core:deepseek` | the second lane, when one is configured |
| Document | `core:native-author-part`, `core:updating-canon` | the page, and where a new fact belongs |
| Record | `core:writing-adr` | the decision that outlives the session |

Fan-out is allowed and often right: dispatch one agent per independent read (the registry, the app, the site) and synthesise. Never dispatch two agents that write the same file.

## 5. The three checks before anything ships

```bash
cd holding/website/native && python3 _sidebar.py --check && python3 _manifest-check.py
python3 holding/plans/department-lifecycle/run-journey.py
# and the named suite for whatever was touched — named, never "the tests"
```

The middle one is the model's own smoke test: it walks a department through its eight states on a throwaway registry. If a build broke the model, that walk stops reaching a state it used to reach.

## 6. The documentation duty

A build is finished when someone who was not here can read it. That means, for every unit:

| # | Rule |
|---|---|
| 1 | One home per subject. Extend the page that owns it; never start a second page about the same thing |
| 2 | Built, designed and proposed are three different words, and the page says which |
| 3 | A new page brings its manifest row, its sidebar entry, and both guards green |
| 4 | The page's claims name the record or the run behind them; a claim with no record is a proposal |
| 5 | Quote a run's output rather than describing it |

## 7. Scale, before it arrives

Ten of anything hides what a hundred will show. When the unit adds a kind of thing the system will have many of, do the cheap measurement in the same session: build a hundred on a throwaway registry, time the read that draws the screen, and write both numbers down. Architecture opinions about scale are worth less than one timing at a hundred.

## 8. Growth, with brakes

The system is meant to improve itself: Adaptation proposes engines from what repeated, templates carry what worked into the next department, the root department makes the next one. Every growth path must end at a stamp. When building one, write down in the same unit what stops it: the budget it spends against, the rule that refuses it, the person who says yes.

## 9. When this skill does not apply

| Situation | Use instead |
|---|---|
| ordinary repo work with no Native record behind it | nothing; just do it |
| deciding whether a thing should exist | `core:architect` |
| writing prose or a document's shape | `core:writing-style` |
| a one-line fix to a page's typo | nothing; fix it |
| running the governance stack for a turn | `core:flow`, `core:blueprint` |

## 10. Changing this skill

It ships inside a plugin that declares a version, so a change reaches anyone only on a version bump; locally, reload the plugins to pick it up in-session. Keep the body under 500 lines, keep references one level deep, and test a change in a **fresh session**, never the one that wrote it. The eval suite under `evals/` is the floor: a case that fires the skill on natural phrasing, and a grader on what it produced.

## 11. The self-check

Before closing a unit built with this skill, answer these five in the turn's output. Any "no" is unfinished work, not a caveat.

1. Which skill set was this, and did I use its check?
2. Does the claim name a record, a run or a test?
3. Is the page that owns this subject updated?
4. Is the decision dated, with what would reverse it?
5. What did this make harder, and is that written down?

---
provenance: {author: claude, date: 2026-09-23, session: 8e2713c3, inputs: [the founder's direction to build a Native Builder skill, this plugin's own skill conventions, the life cycle and screen work of 2026-09-22 and 2026-09-23], review: none by a second model; the skill's own section 10 is its checklist, confidence: high on the loop and the sets, which describe work that actually ran this week}
