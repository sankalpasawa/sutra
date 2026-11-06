# map/1: the Map of a run

`runs/<id>/map.json` is written by code (`j2_map.build`) beside `atoms.json`: once with the summary and again after the
report, additive, never changing a run (a failure is only an event). `/api/map` serves the same shape for a live run (drawn
from its live state), a saved run (`map.json`, else rebuilt from the folder) and an old run with no `artifacts.json` or
`atoms.json` (rebuilt from the folder and `workflows.json`). A missing run gives an empty map. No model call is involved.

Version 2 draws the Requester, the Functions row (Identity, Adaptation, Priority, Coordination, Audit) and the Work row.
The Knows row is a later version: its node kind is in the schema, nothing is drawn or invented for it.

## Top level

| Field | Meaning |
|---|---|
| schema | `"map/1"` |
| run | the run folder name |
| live | true when built from a running run |
| status | `{state, state_status, checks: {passed, run}}`: the top line ("Identity running", "Waiting on you", "Done", "Done with open items", "Stopped", "not recorded") and the checks of every work atom that ran |
| nodes, edges | below |
| workflows | presentation only, for the Tree view's circle: `[{id, name, status, box, atoms, checks: {passed, run}, reads}]`, one per workflow in `workflows.json`: the box it sits on (a node id, or null when not placed), the worst status of its atoms, and the workflows it reads (its `dependencies`, then recorded atom edges). Nodes and edges never depend on it. |
| legend | `[{key, label, drawn}]`: what the drawing explains; `drawn: false` for kinds a later version draws |
| built_from | the files the map was built from |
| not_recorded | what the run did not record and the map therefore shows as "not recorded" |

## Nodes: `{id, kind, row, label, status, version, detail, file, workflows, tag, color, lane}`

`lane` (work and step nodes): `"trunk"` for every box but a send, in an order where each box comes after every box it reads (run
order only breaks ties, never draws a line); `"branch"` for a side job (a send deed) and its step. Nodes are listed in drawing
order: each trunk box, the side jobs that read it (step, then deed; a planned side job with no record yet goes after the box before
it in the plan, with no line), then the step to the next trunk box.

**Every workflow is placed.** Each workflow in `workflows.json` sits on one box, decided in this order: a realization decide
workflow (the plan's kind, else an `artifacts/` file with a stage) that wrote its file, or is still unfinished, gets its own spec
box `work:<workflow id>`, labelled from its file (`artifacts/hint-method.md` is "Hint method"), with its stage's `output` from
`agents/j2/stages.json` as `output` (the second line); one that finished with no file sits with its stage-mates; a revision joins the box of the workflow that owns its section; a workflow of a
stage joins the box that holds its stage-mates; a section in `stage-<doc>.json` or `sections.json` names its document (or the
current one); last, the output refs (`artifacts.json`). One that fits none is listed by id in `not_recorded` as "workflows not
placed on the map: W-n, ...", never dropped. The style guide (`style.json`) is `work:style`, made by the workflow with
`style_guide` true; the later build workflows read it, so its line runs into the site.

| kind | row | what it is | built from |
|---|---|---|---|
| person | people | the Requester ("You") | chat (messages from the Requester, a pending question) |
| work | work | the Charter, each deliverable the run built (`types.json`: PRD, HLD, LLD, website), a send deed | `goal.json`, `artifacts.json` (version, workflows, file), atom/1 (status), `types.json` (label, tag, colour) |
| engine | work | the step between two work boxes, named by what its workflows do (Write, Build, Send) | the workflows of the box it leads to: count, and checks passed of those atoms |
| function | functions | Identity, Adaptation, Priority, Coordination, Audit | the live lanes (running run) or the chat (finished run); calls, seconds and tokens from the call log |
| know | | what the work draws on | a later version |

A function node also has `calls`, `seconds`, `tokens {input, output}`, `tab` (the existing tab that shows its work: Identity
Charter, Adaptation Workflows, Priority Conflicts, Coordination Timeline, Audit Audit), `wait_on` (who it waits for) and
`detail` (the one line on what it is doing). An engine node also has `made_by`, `team` (the role of its box's stage from
`stages.json`, or null: the page then names it from the output type) and `unchecked` (the workflows set to done whose atom did
not pass its checks; the page counts them in the team label).

**Function states.** A running run uses `lanes()`: working is `running`, waiting is `waiting` (`wait_on` names who), blocked is
`fault`, idle is `idle` with "last seen: ...". Waiting on the Requester is `waiting_on_you` only while a question to the Requester
is open (the page's Needs you strip reads the same question); otherwise it is `idle`. A finished or old run has no
live state: every function is `idle` with "last seen: <its last message>", never `running`. A question left unanswered
(live `paused`, or the last chat message carries `pause`) puts `waiting_on_you` on Identity and on the Requester node.
Without a chat the line says "no message recorded", and without `calls.jsonl` the counts are 0 and the gap is listed.

Ids are stable: `person:requester`, `work:charter`, `work:prd`, `work:<workflow id>` (a deed), `step:prd>hld`.
`file` is the artifact or record the box opens in the Artifacts tab (`goal.json` for the Charter, `receipts.jsonl` for a
deed). `version` is `null` when the run did not record one: the page says "version not recorded".

## Statuses

| status | from | drawn |
|---|---|---|
| filed | every atom of the box is `closed` (a file with no atoms recorded counts as filed) | solid edge, tinted |
| done_unchecked | a workflow is `done` in `workflows.json` but its atom is `verify_failed` or still `open`: "done · checks did not pass" | thick amber dotted edge |
| running | live run: an atom is `open`, or a function is working | double edge |
| left_open | finished run: an atom is still `open` | dashed edge |
| fault | an atom is `verify_failed` and its workflow is not `done`; a function is blocked | thick red edge and "!" |
| waiting | a function waits for another function | thick amber edge and "?" |
| waiting_on_you | a question to the Requester is pending | thick amber edge and "?" |
| not_made | planned but not built, or every atom `abandoned` | hollow |
| idle | nothing to say | plain |

In a finished run the page says "left open", never "running".

## Edges: `{from, to, kind, label, n, basis, source}`

**No line without a record.** Every edge carries `source`, the record it was drawn from: `{file, workflow, field, value}` (for
example `{"file": "workflows.json", "workflow": "W-4", "field": "dependencies", "value": "copy-guide"}`), and points producer ->
consumer. Nothing is drawn from run order alone, and no rule names a run, a workflow, a file or a stage.

- `handoff` (a read): A -> B when a workflow on B lists a workflow on A in its `dependencies` (workflows.json), its plan's
  `inputs_from` (realization.json) or its atoms' `depends_on` (atoms.json). `label` "given to W-n, ..." names every reader.
- `step`: the Charter -> each team (every workflow is given the charter: `goal.json`); the box just before a team on the trunk ->
  that team, only when the team's box reads it (a send: the box it reads); the team -> its box, from the record that put its
  workflows there (`artifact`, `stage`, `section`, `style_guide`, artifacts.json `workflows`, an atom's send output, or a planned
  stage in summary.json). A step's id names that box before it, else the Charter (`step:charter>W-3`). `n` = workflows of its box.
  The Line view draws a trunk segment only between two nodes such an edge joins; other reads are its "given to" loops.
- `speaks_to`: message counts from the chat: Requester to Identity (their messages), Identity to the Requester (messages
  addressed to them), and function to function (`who` to `next`). Messages to and from workflow agents (W-n) are not drawn.
  Up to three function-to-function pairs are drawn as thin dotted lines with their counts; more go in a small table under
  the row, so lines never cross.
- `speaks_to` from a function to a work box (`to` is `work:...`), from recorded data only, `n` and `label` say what:
  - Identity to the Charter: `label: "wrote the charter"`, `n: null` (from `goal.json`; the run recorded no count).
  - each function to the PRD, HLD and LLD boxes: `label: "calls"`, `n` = its AI calls in the call range `documents.json`
    recorded for that document.
  - Audit to every box that has an audit in `stage-*.json` (documents and website; a plain site run uses `audits.json`):
    `label: "audits"`, `n` = the number of audits, unless the call range already gave Audit a `calls` edge.
  - The website and a deed get only the Audit line. Anything without a line is listed in `not_recorded`
    ("which function worked on X: not recorded", or "which other function worked on X (only Audit is recorded)").
  These replace the earlier `made` edges. A step node still has `made_by` (the same call counts per step) for the
  "Who made each step" table.
- `draws_on`: a later version.

## The page

The Map has two views, chosen by the "Tree" / "Line" toggle next to the status chips (Tree is the default; the choice is kept in the
browser, and `?mapview=line` opens the Line view). Both read the same map.json; at 600px and under both give way to the cards.

**Tree (default).** A top-down layered tree on a dark canvas, drawn from the map's own edges: the Charter on row 0; each deliverable
below every deliverable it reads (a recorded hand-off), so the rows are a lattice; each team (one per persona; steps that share a
workflow are one team) directly above the top deliverable it made. A spec is named from its file (`artifacts/hint-method.md` is
"Hint method"), with its stage's output ("Curriculum") on the second line. A line that skips rows gets a waypoint on each row it
passes, so long lines take their own lanes and are drawn as one smooth curve through them. Each row is ordered by barycentre, then
by sifting (each node tried at every place in its row, kept where the lines cross least), from the start order and from 24 seeded
shuffles; the fewest crossings win. Then a seeded d3-force pass (link, x-centring and collision forces; y fixed per row; a fixed
seed and 240 ticks) moves nodes along their row, kept only if it adds no crossing, and a last sweep keeps every label at least
24px from its neighbours in the chosen order. The same run always draws the same (the layout is worked out once per map);
crossings are allowed but few (the count is on the SVG as `data-crossings`). Lines are smooth curves, thin and faint. On hover or focus a node's lines brighten and dots flow along them,
producer to consumer, about 1.5 s per line: lines into it ("reads") and out of it ("read by") in two calm colours, both in the
Legend; nothing moves at rest, and with prefers-reduced-motion the lit lines get small arrowheads instead. A dot's size is its workflow count, its label is under
it, and its status is on the ring only (the same colours and marks as the Line view).
Clicking a stage moves it to the middle of the view (300 ms, eased; no animation with prefers-reduced-motion) with its workflows
(id, short name, status) evenly round it on a ring stretched to the canvas, joined by curved spokes; every other node fades to
20% with its label hidden (restored on close), so only the stage's and the circle's words show; only the stage's own lines are drawn (the
rest are hidden, not faded), and a workflow's own links show on hover, with the flow. Clicking a workflow there opens its panel
(over the map's right side, inside the map card; below the map when the map is under 720px wide; one panel at a time: a
workflow, a deliverable or the open stage, Esc or Close shuts it; while it is open the view pans down or left, zooming out only
as much as it must, so no workflow or its words sit under it, and goes back when it closes): status, what it delivers, what it reads, what reads it, checks, an Open button
to its card in Workflows, and draws its own "reads" (solid) and "read by" (dashed) links. Esc, Back or a click on empty space
returns. Drag to pan, wheel or pinch to zoom; Fit resets. A deliverable or the Charter opens the same panel and Open button as in
the Line view. The library is d3 7.9.0 (ISC), vendored at `vendor/d3.min.js` and served by the app itself: no CDN.

**Line, wide (900px and up): a metro line.** One horizontal trunk: the Charter, the documents and the site are diamonds on the line,
evenly spaced; the team that made each one (a ring of five dots, "<Persona> · N workflows") sits on the stretch of line leading into
it. Under each diamond (or above, when a line or a side job leaves from below): its name and one fact line ("v6 · 13/13 checks", or
"not recorded"). A side job (a send) leaves its parent diamond on a short branch below the line (above it when a line already
passes under that diamond): its team, then a letter icon with "Test email · dry run, not sent". "Given to" lines that skip a stop
run faintly above the line, flat over the labels, or under it and up to the team that used the document; two that would
interleave go on opposite sides, and the code checks every pair of drawn lines for a crossing. A line that cannot be placed is
drawn round the outside and listed under "Not recorded". The Management layer is one row of chips above: You (with the messages
from you), then Client Lead, Strategist, Prioritiser, Scheduler and Quality Reviewer (each with its AI calls). Lines from a chip to
the work it did, and messages between functions, are shown on hover or in the "Messages between functions" table.

**Narrow (under 900px)** the trunk runs top to bottom with side jobs in a column beside it; at 600px and under the map is a list of
cards.

**Colour means status only:** green = filed and checked, amber = waiting on you, red = fault, grey = not made or idle; a dashed
outline = left open, a double outline = running now; "!" and "?" marks as before. The status chip is green when the checks pass,
amber with "Audit: needs revision" when the latest Audit says the work is not workable yet, and neutral "No checks yet" before any
check ran. The Needs you strip's outcome line names what is left open (for example "1 item left open: test email (dry run)").

Every display label comes from one table in the page (`MAPLABEL`). `renderMap(map)` is one pure function; all text goes through the
Detailed view's plain-words helper.

## Home and navigation

The Detailed view's home is the department name, the Needs you strip (with one plain outcome line and a See report link), the Map and the Chat (docked on the right; stacked below 900px). The left
rail has Map, Chat and one collapsed Internals folder holding every other tab (Preview, Goal, Workflows, Conflicts,
Timeline, Audit, Charter, Documents, Artifacts, Style guide, Lessons, Playbooks, Report, Run details, Run settings). Run settings holds what
to build, the saved-run selector, New run and Back to simple view; the full outcome banner is at the top of the Report. Each internal view
has a "Back to map" link. Needs you lists every open Requester question (the items that make a node "waiting on you"), each
with a button that scrolls to and focuses that question in the Chat.

A click on a node opens its panel; the panel's Open button goes to: a node waiting on you, its question in the Chat; You,
the Needs you strip; Client Lead (Identity), the Chat; Quality Reviewer (Audit), the Audit tab; the other functions, the
two tables under the Map filtered to them; a team persona's step, the Workflows tab filtered to that step's
workflows ("Show all" clears it); the Website, the site preview; the Charter, the Charter tab; any other deliverable, its
document in Artifacts. The page-side state for this (`MAPFILT`, `WFSTEP`) is never stored in map.json.

## The Artifacts tab (artifacts-tree/1)

`/api/artifacts/tree` (and `j2_artifacts.tree(run_dir)`) gives the run's files as a tree, built from the same `j2_map.build` data as
the Map, so makers, readers and statuses always agree; `/api/artifacts` keeps its flat lists. Groups, each collapsible with a count:
**Plan** (the Charter, the realization plan with its zone, stages and plan confidence, the workflows); **Specs** (each spec box: its
file, its team's persona and workflow ids, how many workflows read it); **Deliverables** (each delivered box with its version, team
and workflow count; under it the style guide it reads, its versions, screenshots and exports, and the sends that report it, with
sent / skipped / failed); **Proof** (check results, audits, necessary conditions, stage records); **Records** (collapsed: everything
else the run kept). Every file appears once; each row has its name, who made it (a persona and workflow ids, or the function or code
for a record), status, size and Open. The map supplies the presentation fields the tree and the page share: `persona` on each team
step, `send` on each send box and `readers` on each read.

## Agent view (agent/1) and the website's code

**Agent view.** A function's details panel (on the Map) and a workflow's panel (in a stage's circle) have "See conversation and
thinking"; a function or workflow name in the Chat opens the same view. It is a drawer over the right half of the page (full
screen on phones), closed by Esc or Close; the Map underneath is unchanged (nothing is added to the canvas). `/api/agent?run=&who=`
(`j2_agent.view`) builds it from the run's chat.jsonl and calls.jsonl only, through redact(): a Summary (calls, total time, model,
who it talked to most; tokens small), Conversations (messages sent and received, grouped by counterpart, oldest first, each with
time and step; a message's recipients are its recorded next, audience, to_user and a leading @name) and Thinking (one card per AI
call: step and cycle, Was given (the inputs in plain words), Reason (the agent's stated reason, or a builder's from its reply
record), Reply (sentences, other fields as labelled lines); prompt, system text and raw output only under "Show technical
details"). Reasons are the agent's own; the model's hidden reasoning is not recorded.

**Code.** Under Deliverables > Website the Artifacts tree has "Code": the full page source (site/index.html) and "By section", one
row per entry in sections.json, named from the workflow that created it, with its author, "rewritten by W-n · <name>" when a
later workflow owns it now, and what it holds (lines of HTML, CSS rules, lines of JS). A document's sections (its stage file, or
sections.json while it is the one in work) show the same way as text. `/api/code?run=&deck=&section=` serves the text read-only,
through redact(); the page shows it with line numbers, a monospace font, light colouring and a Copy button.
