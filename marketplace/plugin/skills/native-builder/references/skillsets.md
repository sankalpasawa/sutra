# The ten skill sets building on Native needs

**status**: v1, 2026-09-23 · **owner**: Native Builder · **read when**: you are about to build any part of Native and want to know which muscle the work needs, what it touches, and what proves it.

Building Native is not one skill. It is ten, and most sessions that go wrong go wrong because they used the wrong one: a screen change made as a record change, a record change made as a document, a document written as if it were a build. Name the set first, then work.

## The map

| # | Skill set | The question it answers | Touches | Proved by |
|---|---|---|---|---|
| 1 | **Model literacy** | what is this thing called, and is it a thing the model already has | nothing; it is reading | the word you use appears in the model pages, or you stop and route a new kind |
| 2 | **Record work** | what must exist in the registry for this to be true | the registry: domains, charters, placements | a read-back on a throwaway registry shows the row you claim |
| 3 | **Ask work** | how does a change get permission | the proposal kinds, their checks, summaries and appliers | a proposal is filed, refused for a bad argument, and applied only after a stamp |
| 4 | **Engine work** | what makes this run without a person | routine records, schedules, folders, checks, the calendar jobs | one run writes a row and its check flips |
| 5 | **Screen work** | what does the person see, and is it honest | the app's readers, cards, styles and their suites | the suite passes and a live walk shows the card with real records behind it |
| 6 | **Documentation work** | where does this become readable to someone who was not here | the Native site: the page, the manifest, the sidebar, the guards | both site guards pass and the page renders headlessly |
| 7 | **Journey work** | can a person, or a script, actually walk this end to end | a runnable walk and its output | the walk runs and prints which states it reached |
| 8 | **Review work** | why should anyone believe this works | tests, evals, the verify lane, a second model | a named test runs green, or a sealed verdict exists |
| 9 | **Scale work** | what breaks at a hundred of these | reads per screen, locks, tree shape, naming, the budget of words | a measurement at ten and at a hundred, not an opinion |
| 10 | **Growth work** | how does the system get better without being told | Adaptation's proposals, templates, the root department, the life cycle | a change the system proposed, that a person stamped, that stuck |

## Each set, in one page

### 1. Model literacy
The vocabulary is closed on purpose: department, function, engine, work item, filed work, ask, stamp, owner, rules, budget, folder, placement. Before building, check the word you are using is one of these or a customer's own word for one of these. A new kind that fits nothing is an event, not a silent addition: route it through the new-thing protocol instead of inventing a word in code.
**Delegates to**: `core:domains` for where a thing sits; `core:updating-canon` for where a new fact belongs.

### 2. Record work
Everything true about a department is a row. The engine mints domains, charters and placements; nothing else may. Two rules save whole days: the desktop's own back end may never mint or retire (a test proves the negative), and a retire is a re-homing, refused until every child, rule and filed item has a successor.
**Check**: point the registry at a temp folder, write the row, read it back, and delete the folder.

### 3. Ask work
A proposal applies nothing. A stamp applies it. To add a change kind you touch four places: the kind list, its check, its one-line summary in the operator's words, and its applier. Miss the applier and the ask can be stamped and still fail; that exact gap shipped once.
**Check**: file the ask with a bad argument and see it refused; file it correctly, stamp, and read the record.

### 4. Engine work
An engine is a record with a folder, a moment, one instruction and a check. It fires from a calendar job outside the app, because the app stops its own back end when the last window closes. Anything an engine may do without asking is written on it, and its runs are rows.
**Check**: one run appends a row whose outcome and cost can be read back.

### 5. Screen work
The app is a projection: every card is a record read, never a second source of truth. A card with no record behind it must show the quiet empty line, not a plausible blank. The suites are the contract; a screen change with no test is a screen change that will regress.
**Delegates to**: `core:deterministic-testing` for the suite; `core:test-strategy` when the surface is new.

### 6. Documentation work
A build that nobody can read is half a build. The Native site is the home: one page owns a subject, others link to it. A new page needs its manifest row, its sidebar entry, both guards green, and a render before it is published. The page says what is built, what is designed and what is proposed, and never blurs them.
**Delegates to**: `core:native-author-part`, `core:writing-style` (file shape), `core:updating-canon`.

### 7. Journey work
The strongest proof that a model is real is a walk: a script that drives it end to end and prints what it reached. A journey that cannot run is a story. Where a state cannot be reached, the walk says so and continues, and that line becomes the next piece of work.
**Check**: the walk runs on a throwaway registry and its output is quoted, unedited, wherever it is described.

### 8. Review work
Three lanes, in falling order of strength: a test that fails when the claim is false, a second model's sealed verdict, a human reading it. Use the strongest available. A claim shipped with none of the three is a guess with a commit hash.
**Delegates to**: `core:codex-sutra` or `core:deepseek` for the second lane; `core:blueprint` for the per-step checks.

### 9. Scale work
Ten departments hide every problem a hundred will expose: a tree nobody can read, screens that read the whole registry to draw one card, locks taken in different orders, names that collide, and documentation that grows faster than anyone reads it. Scale work is measurement, not architecture talk: build the hundred, time the read, then decide.
**Check**: a number at ten and the same number at a hundred, in the same run.

### 10. Growth work
The system is supposed to get better on its own: Adaptation watches what repeated and proposes the engine, templates carry what worked into the next department, the root department makes the next one. Growth work is building those loops and, more importantly, the brakes on them: every growth path ends at a stamp.
**Delegates to**: `core:architect` for the shape; `core:incremental-architect` when a live thing must change shape.

## How to use this map

1. Name the set before the first tool call. If the work needs three, it is three units, not one.
2. Take the set's check as the unit's verify. Do not invent a softer one.
3. If a set has no delegate named above, that is the next skill worth writing.

---
provenance: {author: claude, date: 2026-09-23, session: 8e2713c3, inputs: [the department life cycle work of 2026-09-23, the engine and app code read the same day, the founder's direction on a Native Builder skill], review: none by a second model, confidence: high on sets 2 to 7 (each built this week), moderate on 9 and 10 (designed, not yet measured)}
