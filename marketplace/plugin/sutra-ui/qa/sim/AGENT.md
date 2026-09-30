# Human Simulation: the agent's runbook

| Field | Value |
|---|---|
| **status** | v2, 2026-09-28, session 17842ce0 (founder: "The person is not a sequence of steps, but a goal and a person. This human simulation can be an agent of its own"; "do it only as a human. Don't do it from code") |
| Program | `holding/plans/human-simulation/PROGRAM.md` |
| Inputs | one person (`person/*.json`), one goal (`goals/*.json`) |
| Output | `runs/<id>/`: `ledger.jsonl` (every click, with why), `report.md`, one png per outcome, `findings.jsonl` |

## Who runs it

An agent with a browser and judgement: a Claude session with Claude in Chrome (or the built-in browser), or a person. The agent is the person in the file, wanting the goal in the file. It has the screen and nothing else.

## The loop, every turn of the agent

| # | Do | Rule |
|---|---|---|
| 1 | Look | read the page as the person would: names, buttons, what is waiting. Read the text of the page, not the code |
| 2 | Decide | the next thing the person would do to get closer to the goal, in the person's words; if two things are possible, the one the person would try first |
| 3 | Act | one click or one sentence typed, through the panel's own controls; never a route, a file, a script |
| 4 | Log | one ledger row: `{n, at, why, did, where, saw}`; `why` is the reason in the person's words |
| 5 | Wait | as the person waits (`waits_s`); a wait that runs out is a finding, not a retry |
| 6 | Check | when an outcome's moment has passed, verify it the way the goal says (a route read, the site itself, the screen); read-only |
| 7 | Note | a miss is a finding row `{outcome, expected, seen, capture, why_it_matters}`; the agent goes on if it can, the person would |
| 8 | Report | at the end: N of M outcomes, K of L variances, the findings, the time; then the findings become TODO SIM rows |

## What counts as a miss

A screen that says nothing when the person expects something; a wait that runs out; a word the person does not understand; an outcome whose verify fails; anything the person would have to work around. A miss in the goal's own expectation (the app is right, the expectation is wrong) is a finding too, marked `expectation`.

## What the agent never does

Reads a log, a record file or a route to decide the next action (routes are for verifying only); presses anything twice because it was slow; fixes anything; changes the goal to make it pass.

## The tools (2026-09-29)

| Tool | When | What it gives |
|---|---|---|
| `sim-agent.sh <goal> [person]` | before the first click | the run folder, the app up on 8331, the person, the goal and this runbook printed for the agent |
| `variance-order.py <goal> <run-dir> [seed]` | right after | `order.json`: the goal's variances in a random order, each with the moment it fires (after the goal is filed, while Plan or Write runs, after the publish ask, after the site is live, after Audit's question); the agent takes them at those moments, so no two runs walk the same path |
| `probe-map.py <dept-ref> ... <run-dir>/probe.jsonl` | while a line runs, detached | how long the panel takes to answer, every 2 s: the numbers behind "the app went quiet" |
| `reply-speed.py <record-dir>` | after the run | per request, the seconds from the person's words to the first answer, and where they went |

The agent is still the session that reads this file, with a browser tool; a headless session started by the launcher is the next step (TODO SIM-4).

## The skills map (2026-09-29)

The run is one phase of a loop: find, claim, fix, prove, review, release, rerun, record. Each phase is owned by one plugin skill (`core:<name>`, the `core@sutra` plugin), and the session running that phase invokes it. The map is the same shape as `core:native-builder` section 4: a map for the session to follow, not a call graph.

| Phase | Skill | What it gives this program |
|---|---|---|
| Find (the run) | this runbook + `core:lens` + `core:cynefin` | the loop above; the variance axes (who clicks, what outcome, when in the line); the domain is complex, so each variance is a small probe read from the record afterwards |
| Stage (each finding) | `core:native` | the Steward reads the finding as evidence: a fix with no claim behind it (a typo, a wrong word) goes straight to fix; anything that argues a design (finding 23's shape-before-ask, finding 34's wait-for-the-engine) is an idea and goes through the claim |
| Claim | `core:native-method` | one Lab card per design-shaped finding: `If <fix>, then <what the person sees> moves from <seen> to <expected> within the rerun`, the kill line being the rerun's outcome row |
| Fix | `core:native-builder` | the seven phases Understand, Place, Design, Build, Prove, Document, Record; skill set 4 (engine work) for `engine_runtime.py` findings, set 5 (screen work) for `static/js` findings; one unit per finding group, never one unit for all |
| Prove | `core:test-strategy` + `core:deterministic-testing` | the named test per finding before the fix (`test_engine_runtime.py`, `test_website.js`), golden output where the finding is a wording; the suite is the atom's verify |
| Review | `core:codex-sutra` / `core:deepseek` | the second lane's sealed verdict on the fix diff; when the lane is down (usage-limited, no key) the run says so in the report and does not forge the marker |
| Release | `scripts/release-desktop.sh` from a shared clone (not a skill) | Beta first, then stable, Mac and Windows; never while a run is live on the Beta (finding 31) |
| Rerun | this runbook + `variance-order.py` | the same goal, a new random variance order, on the released build; a finding that recurs keeps its number |
| Record | `core:writing-style` + `core:writing-adr` | `report.md` and the TODO SIM rows in the standard's shape; a design call the founder rules gets an ADR row with what would reverse it |
| Third of a shape | `core:system-engineering` | when three findings share a shape (findings 36 and 39 both open the wrong thing from a chat button), design the component that makes them right, not the third patch |
| Where it sits | `core:domains` | the department and charter a fix unit belongs to, for its placement line |

The map is applied per unit, by whoever runs the phase: the agent for Find and Rerun, the fixing session for the rest. A phase whose skill was not invoked says so in the unit's report.

## Provenance

provenance: {author: claude, session: 17842ce0, date: 2026-09-29, inputs: [the founder's words of 2026-09-28 quoted in the header, PROGRAM.md v1 and v2, the founder 2026-09-29: "Use relevant skills from a map to make this happen as well. For the human simulation program", the plugin's skill list at core 2.306.16, core:native-builder section 4], review: none by a second model, confidence: high on the loop, the miss rule and the map's skill names, which are the plugin's; moderate on the waits, which the first run sets}
