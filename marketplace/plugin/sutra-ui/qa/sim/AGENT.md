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

## Productionizing

`sim-agent.sh <goal.json>` starts a headless Claude session with this runbook, the person, the goal and a browser tool, and ends with the run folder; until that launcher exists (SIM-2), the agent is the session that reads this file.

## Provenance

provenance: {author: claude, session: 17842ce0, date: 2026-09-28, inputs: [the founder's words of 2026-09-28 quoted in the header, PROGRAM.md v1 and v2], review: none by a second model, confidence: high on the loop and the miss rule; moderate on the waits, which the first run sets}
