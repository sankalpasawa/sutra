# PRD amendment A5: the J2 page for every department, the Shadow graph, and create-or-reuse by an agent

| Field | Value |
|---|---|
| **status** | Proposed, 2026-10-29: amendment A5 to [PRD-FIVE-FUNCTIONS.md](PRD-FIVE-FUNCTIONS.md), to [PRD-FIVE-FUNCTIONS-J2UI.md](PRD-FIVE-FUNCTIONS-J2UI.md) (scope), [A1](PRD-FIVE-FUNCTIONS-A1.md) and [A4](PRD-FIVE-FUNCTIONS-A4.md). Designed and reviewed; not built. The review of 2026-10-29 (two P0, eight P1) is applied in this text (A5.9). |
| Direction | the owner, 2026-10-29, three numbered asks (A5.0); plus the owner's reminder the same day: the workflow follows the hardened pydantic models (A4) |
| Overrides | the ruling of 2026-10-26 that the J2 page serves `website` departments only and every other kind keeps the classic screens ("records mode"); the 2026-09-29 ruling "Root = chat only" as the default of the organisation row is kept until a real Setup conversation has been walked in the page (A5.1.7). The verbatim rule is loosened only by the substitutions S4 and S5 (A5.1.3), each listed in `scripts/sync_j2_ui.py` and pinned by `test_j2ui_verbatim.py` |
| Based on | sutra main with M0 to M12 and A1 to A4 merged, release 2.307.0, the J2 prototype `f9ceba1`, `layer_models/` (A4), `j2ui_*.py`, `static/js/25-j2view.js`, `shadow_*.py`, `static/js/16-shadow-home.js`, `engine_runtime.py`, `founding.py` |
| Build | five developer packages (A5.8): P1 models first, then P2 J2-ALL, P3 DECIDE and P4 GRAPH in parallel on disjoint files, then P5 VERIFY. Local merges only, never push |
| Decision log | the A5 rows of [PRD-FIVE-FUNCTIONS-DECISIONS.md](PRD-FIVE-FUNCTIONS-DECISIONS.md) |
| Pointer for code | `layer_models/a5_types.py`, `a5_words.py`, `a5_graph.py`, `a5_depts.py` (new); `j2ui_words.py`, `dept_read.py`, `dept_list_api.py`, `shadow_dept.py`, `shadow_dept_prompt.py`, `shadow_dept_api.py`, `shadow_graph.py`, `shadow_graph_api.py`, `static/js/27-shadow-graph.js` (new) |

## A5 at a glance

| Question | Answer |
|---|---|
| What changes? | (1) The J2 page serves every department of the engine runtime (website, default, organic, Root, any kind the Library adds), with kind-neutral wording derived from the department. (2) Shadow gets a graph screen of tasks, departments and chats, and a per-task detail screen, reached from Home and from a jump on the active Shadow chat. (3) An agent decides, for any task, to use an existing department, create one, or use none; code covers the decision; the validated record is stored and drawn. |
| Is a website department's page changed? | No. A website department's `words` is empty, every `WD()` default is the prototype's own literal, and a snapshot test diffs the rendered text before and after. |
| Does a task now run in a department instead of a worker? | Not in A5. The decision is recorded and linked; the worker still runs (link-only, the default `SUTRA_SHADOW_DEPT_EXECUTE=0`). The executor swap and `follow()` are a later package, behind an opt-in flag, after a real department has been walked completing a Shadow task (A5.9, finding F1). |
| Pydantic | Every new record is a closed pydantic v2 model in `layer_models`, behind the `layer_schema.py` facade with a DEFS entry, validated at the sink and on every API response, never on a streaming body (A5.4). Schema version 2 with a no-op migration, landed first as its own commit. |
| What needs the owner? | Nothing blocks. Defaults likeliest to change: link-only (A5-9), Root's page not yet the default of the organisation row (A5-6), which Root Shadow uses when there are several (A5-12). |

## A5.0 The direction, and how this reads it

> 1. We should have this kind of UI for all the departments, J2 is the new idea, discard any previous conflicts for this
> 2. Shadow should also show the graph kind of structure
>    1. Either it will use a department or spawn a department, both of this things should be visible.
>    2. Shadow to chat linkages should be graphical representation
>    3. Each node in the graph should allow me to visit the required chat
>    4. Conversely the active shadow chat should have a jump to another screen navigation which will show me everything in detail
> 3. All the above feature are department agnostic, also creation of department / reuse of department is task agnostic and agent decides if needs to be created one or use an existing one. Let's try to build this asap.

| # | Reading | Lands in |
|---|---|---|
| 1 | The page is for every runtime-2 department kind. Earlier rulings that conflict are discarded; the verbatim rule is loosened only as far as kind-neutral wording needs. | A5.1 |
| 2.1 | Graph edges `uses` (existing department) and `spawned` (created by this task) are both drawn, visibly different by dash pattern and tag text, never by colour alone. | A5.2 |
| 2.2, 2.3 | Shadow, task, conversation, task chat, worker and department are nodes; edges are the links; each node opens its chat or page. | A5.2 |
| 2.4 | A "Details" button on the active Shadow chat opens the task's detail screen. | A5.2 |
| 3 | No kind is named in any new code path; the choice is a model step with a typed output; code covers it. | A5.1, A5.3 |
| asap | Three to five packages, disjoint files. The cut line is in A5.9. | A5.8 |

## A5.1 Part 1: the J2 page on every department

### A5.1.1 Scope rule

A department is served by the J2 page when it is on the engine runtime (`runtime == 2`) and its kind is in the Library (`W.KINDS`). There is no kind list anywhere else. The three copies of the website rule are deleted: `KINDS_SUPPORTED` and `is_j2_kind` in `j2ui_common`, the fallback in `j2ui_page._scoped`, and `j2vEligible` in `25-j2view.js`. The server is the one source of truth: `GET /api/native/{ref}/map` gains `"j2": true` when `j2ui_common.need(ref)` passes, and `j2vEligible(ref)` is `m && m.j2 === true`.

`need()` refuses (NotJ2, routes answer `404 {"error":"no such department"}`): unknown ref, path characters in the ref, runtime 1, a kind not in `W.KINDS`. `Ctx.kind` is read from the record.

### A5.1.2 Honest data per kind (no invented content)

Before any sync-script work, P2 writes the per-kind route matrix (page, state, map, board, artifacts, docs, refs, runs, preview, say) against seeded Root, default, organic and Brief-only records and fixes what fails; the matrix is the gate for the S4 work (finding F4).

| Adapter | Change |
|---|---|
| `j2ui_common` | `EMPTY_DEFAULTS` keeps its keys with neutral defaults (`''`, `'Work'`); `Ctx.kind` from the record |
| `j2ui_state._own` | `output` = the kind id; `output_label` = the capitalised noun of the kind (fallback 'work'); `doc` stays false |
| `j2ui_state.state` | a runtime-2 department with no J2 cycle (Root) keeps cycle 0, step 0, stamped false, outcome null. Never fake one. Pinned by a test on the real Root record |
| `j2ui_state` | 57th key `words` = `j2ui_words.words_for(dept)` (A5.1.4) |
| `j2ui_say` | the `api/output` 409 body names the kind id; the four POSTs are otherwise unchanged |
| `j2ui_map.boxes` | an artifact with no version yet is tagged 'Other', not 'Site' (pass None, not 'index.html'); Open goes to Artifacts. A Brief-only or organic Map is the five functions, the Charter and the Brief, not padded; the panel's 'not recorded' text stays |
| `j2ui_artifacts` | LIVE and PREVIEW names stay. The deliverable is Build/Live site when filed, else the last artifact; pinned per kind; no filler rows; 'Nothing recorded yet.' where empty |
| `j2ui_site.site` | when the previewable artifact has no `index.html`, serve its primary `.md`/`.txt`/data file as a safe text page (escaped text in `<pre>`, existing SAFE_HEADERS: sandbox, no script). The placeholder is words-derived: website keeps 'Your website will appear here once it's built.'; other kinds 'Nothing has been filed here yet.'. `file/` and `shot/` stay 404 |

### A5.1.3 Neutral wording in the page: S4 and S5

The page stays one file, equal to the prototype except for S1 to S5. Two new classes, listed in `scripts/sync_j2_ui.py`, pin schema `j2ui-pin/2`.

**S5** (one inserted line, like S2): directly after `const $ = id => document.getElementById(id);` insert
`const WD = (k, d) => { const w = CTX && CTX.words; return w && w[k] != null ? w[k] : d; };`
Every default argument of `WD` is the exact original literal, so a department with no override sees the same text.

**S4** is a table `WORDS = [(id, original, replacement), ...]`. Each original occurs exactly once in the S1-applied text (guard 7). Any `WD(` inside a template is wrapped in `esc(` or sits in a textContent/attribute-safe position (guard 8). Prototype line numbers:

| Id | Line | Change |
|---|---|---|
| S4.06 | 330 | `examples = s => WD("examples", s.doc ? PRD_EXAMPLES : EXAMPLES)` |
| S4.07, 11 | 927, 955 | `<small>${esc(WD("team","Your website team"))}</small>` |
| S4.08 | 942 | voice label ternary wrapped in `esc(WD("team", ...))` |
| S4.09 | 943 | output select block wrapped in `${WD("pick", true) ? ... : ""}` |
| S4.10 | 944 | sentence wrapped in `esc(WD("start", ...))` |
| S4.12 | 958 | `Your ${s.doc ? "document" : "website"} is ready` becomes `${esc(WD("ready", ...))}` |
| S4.13 | 967 | stitle textContent wrapped in `WD("team", ...)` |
| S4.14 | 724 | `["website"]` becomes `[WD("built","website")]` |
| S4.15 | 959, 960 | 'Open full screen' behind `WD("can_open", true)`, 'Download the HTML file' behind `WD("can_download", true)` |
| S4.16 | 969-971 | the 9-element status array becomes `WD("steps", [same 9])`; the two `.replace(...)` document patches stay |
| S4.17 | 976 | placeholder ternary wrapped in `WD("describe", ...)` |
| S4.18 | 1064 | last branch `WD("describe_long", ...)` |
| S4.19 | 1043 | follow-up array `WD("follow_ups", [...])` |
| S4.20, 21 | 774, 776 | `${s.doc?"document":"site"}` becomes `${esc(WD("noun", ...))}` |
| S4.22 | 770 | `Audit checks the ${esc(WD("noun","site"))} against` |
| S4.23 | 780 | rubric heading ternary wrapped in `WD("rubric", ...)` |
| S4.24 | 374 | `${esc(WD("noun","site"))} v${m.version}` |
| S4.25 | 808 | `WD("noun","site")+" v"+m.version` |
| S4.26 | 785 | `"J2.g checks the "+WD("noun","site")` |
| S4.27 | 1025 | `<dt>${esc(WD("noun","site"))}</dt>` |
| S4.28 | 1136 | 'each version of the site.' as a concatenation with `WD("noun","site")` |
| S4.29 | 851 | Style guide empty text `WD("style_empty", original)` |
| S4.30 | 864, 883 | 'Memory is off...' `WD("memory_off", original)` |
| S4.31 | 1246 | `WD("go_preview", "Open the site preview")` |
| S4.32 | 1086 | `no ${WD("noun","site")} yet` |
| S4.33 | 1075 | after `$("tab-board").hidden = !s.has_board;` append `WD("hide_tabs",[]).forEach(t => { const b = document.querySelector(\`.tabs [data-tab="${t}"]\`); if (b) b.hidden = true; });` (the tab buttons are in `.tabs`, checked in `j2_ui.html`; the ids docs, style, lessons, playbooks, preview exist) |
| S4.34 | legend | the output-type legend is hidden when `WD("pick", true)` is false (the developer locates it; if it cannot be isolated it is exempted from the neutral scan with a written reason in the test) |
| S4.35 | 268 | 'New run' text `WD("new_task","New run")`; the click handler, only when `WD("new_task", null) != null`, focuses `#sbox` instead of POSTing `/api/reset` |
| S4.36 | 962-963, 995 | 'Start over' text `WD("retry","Start over")`; the handler, only when `WD("retry", null) != null`, re-sends the last request instead of POSTing `/api/reset` |
| S4.37 | static | the static markup `Your website team` (l208), `Describe the website you want...` (l215, l293), iframe title `Your website` (l217), `Website preview` (l249) stay verbatim in the file. One applier statement (next to S4.33) rewrites them from `WD("frame_title", null)`, `WD("team", null)` and `WD("describe", null)` only when a word is set (finding F5: a website department's text does not change) |

Because website words are empty, the handlers and the applier do nothing for a website department. Rows S4.35 and S4.36 are behaviour edits and are named as such in the sync script.

**Verbatim machinery.** `restore()` undoes S5, S2, S3, then S4 in reverse, then re-inserts S1 slashes at the pinned columns. `line_problems()` accepts a changed line only if it equals S4(S1(old)) and expects exactly two inserted lines (S5 and S2). Pin schema `j2ui-pin/2` carries `substitutions` S4 (count and items `{id, line, original, replacement}`) and S5 (line, text). STATE_KEYS becomes 57. The size arithmetic adds the S4 length deltas and one line. New tests: `test_hermetic_the_wording_edits_are_neutral` strips every `WD("key", <default>)` default and asserts no website/site/PRD/document word remains outside defaults and the listed static exemptions (S4.37); hand-edit tests (change one byte of a replacement, drop the S5 line, duplicate an S4 line) each fail; `test_j2ui_render.py` gains a words case (the start card has none of 'website', 'PRD', 'document'; a hostile `words.team` of `<img onerror>` comes out escaped); a website snapshot test diffs rendered text before and after.

### A5.1.4 The words

`layer_models/a5_words.py` holds `PageWords` (every field optional; omitted means the prototype's text; only the keys S4 reads), `FALLBACK_WORDS` (separate from the kind map, so a Library kind named `fallback` cannot collide) and `KIND_WORDS = TypeAdapter(dict[Kind, PageWords])` validated once at import (STR-7). `kind_words(kind)` returns the validated entry or the fallback.

`j2ui_words.words_for(dept)` fills department-derived values: `team` = the department's name (trimmed to 80, no 'Your' added); `describe` = 'Describe what you want {name} to do...' (name trimmed to 40); `describe_long`; `start` = 'Tell {name} what you need. It will ask for what it has to know, then get to work.'; `ready` = 'Your {noun} is ready'. `examples` and `follow_ups` are empty for every kind but website. Nouns: website 'site' (no words at all, empty object), default 'result', organic 'work', root 'department', fallback 'work'. Non-website kinds: `pick` false, `can_download` false, `can_open` true, `hide_tabs` docs/style/lessons/playbooks, `go_preview` 'Open the preview', `rubric` 'Quality checks', `memory_off` 'This department keeps its lessons in its own records.', `style_empty` 'No style guide has been filed for this department.', `new_task` 'Give it another task', `retry` 'Try again', `steps` nine neutral strings. Validated once per `ctx.memo['state']`, not per poll.

### A5.1.5 Retiring records mode and the gate

There is no kind-based classic screen. `j2vTab`/`j2vTop` return the classic screen only for runtime-1 departments, an unknown ref, or the explicit per-department switch 'Settings and records' in the page bar (`S.ui.j2off[ref]`, reset on reload). That bar and its classic panes remain as the escape hatch for every kind. In the Org screen and list, any department row opens the J2 frame at `/j2ui/<ref>/` when `j2vOn(ref)` is true, which now means every runtime-2 kind. `19-org2.js` exports `o2OpenDept(ref)` (one window-global line, P2's first commit) for the graph.

### A5.1.6 Tests changed (P2)

`test_j2view.js` (J2 block, J4 blocks, J7 block, header comment, new parity test: `j2vEligible` true for every kind in the map fixture, false for runtime 1; `j2` key); `test_j2ui_common.py` (need() for four kinds, refusals, `is_j2_kind` for every `W.KINDS` key); `test_j2ui_page.py` (param lists, `_scoped` agrees with `need()`); `test_j2ui_api.py` (only unknown and old stay 404; per-kind 200 matrix); `test_j2ui_say.py`, `test_j2ui_site.py`, `test_j2ui_state.py`, `test_j2ui_contract.py` (57 keys); `test_j2ui_verbatim.py`, `test_j2ui_sync.py`, `test_j2ui_render.py`, `test_j2ui_proto.py` (re-pin); the map-shape tests (`test_website_api*`, `test_dept_api.py`) and `test_embed.js`; `qa/walks/j2ui-e2e.sh` (default, organic and root walks). P2 starts with `grep -rn 'KINDS_SUPPORTED\|is_j2_kind\|j2vEligible\|"website"' test_* qa` and lists every hit in the merge note. Existing website expectations pass unchanged: that is the proof.

### A5.1.7 Root

Root's page is served and linked (graph, Org list action). The organisation row keeps the classic Root chat as its default until P5 has walked a real Setup conversation inside the J2 page; the default is one constant in `25-j2view.js` (`J2_ROOT_DEFAULT = false`) flipped by a P2 follow-up commit if the walk passes (finding F10).

## A5.2 Part 2: the Shadow graph

### A5.2.1 Model

Ids are strings with a kind prefix. Nothing is stored as an edge; all are derived from stored ids by `shadow_graph.build()`. P4's first step is a table in `test_shadow_graph_build.py` mapping every node and edge kind to the file, function and field it reads, with one fixture per kind; the fields `conversation.mission_id`, `task_chat_session`, `target_session` are verified there before coding (finding F6).

| Node | Source | Id | Opens |
|---|---|---|---|
| shadow | the single Now session | `shadow:now` | none |
| conversation | `shadow_conversations.list_all()`, unbound only, newest 20 | `conv:shc-...` | conversation |
| goal | `goal_id` of a mission (GoalStore) | `goal:g-...` | goal |
| task | a mission, label = objective trimmed to 80 | `task:m-...` | task |
| task_chat | `task_chat_session` set | `tchat:m-...` | task (alt: raw session) |
| worker | `target_session` (label 'Your chat' when target_mode is 'existing'); not drawn when executor is department | `worker:m-...` | session |
| department | `department_decision.final_ref` | `dept:<ref>` | department page (J2) |

Task status: draft and brief_confirm to draft, queued to waiting, running to working, paused/blocked to waiting/blocked, done, failed, stopped. Department status from `DeptRow.state` (stopped becomes 'off'). A department whose row is missing is drawn with status `off`, label = the ref and tip 'Record not found', never 'idle' (no invented status).

Edges: `has` (shadow to task and to unbound conversation), `opened` (conversation to task), `attempt` (goal to task), `steered_by` (task to task_chat), `driven_by` (task to worker), `uses` (task to an existing department, decision final_action use; solid line, tag 'uses'), `spawned` (task to a department this task's decision created; dashed, '+' start marker, tag 'spawned'). Both carry the decision's reason (at most 300 characters; code overrides appended, e.g. 'Held: X is Off') and confidence. A held decision draws dotted with a 'held' tag. No decision or `none`: no department edge.

Layout is server-computed and deterministic: col 0 shadow; 1 goal/conversation; 2 task; 3 task_chat and department; 4 worker. One row per task in Home order (active first, then recently ended); a department used by several tasks sits at the rounded mean row. Cap: all non-terminal missions plus terminal ones of the last 7 days, at most 60 tasks, newest first; `truncated` flags a cut. `include_done=0` hides terminal missions except those from the last hour. Deleted missions and their chats are never drawn.

### A5.2.2 Read model

`shadow_graph_api.py` (own module, no import of app): `GET /api/shadow/graph?focus=&include_done=` returns ShadowGraph; `GET /api/shadow/graph/task/{mid}` returns ShadowTaskDetail (404 unknown). First line of each: `if not providers.shadow_enabled(): raise HTTPException(403, 'the shadow flag is off')`. The builder does one `MissionStore().list()`, one GoalStore list, one `list_all()`, one `shadow_costs.by_mission()`, one `dept_read.rows(root)`. **Validation happens once inside `build()`, before the memo store; the memo (2 s, keyed by the signature of the missions directory, the conversations directory and the departments signature) holds the validated dict; a hit is returned without re-validating, and the route does not validate again** (finding F11; a test counts validator calls for two polls in one tick). The route returns `JSONResponse(validated)`; no `response_model` (STR-4). A mission file that fails to read is skipped. If `dept_read` is absent or fails, departments come from `mission.department_ref` only.

### A5.2.3 Screen (`static/js/27-shadow-graph.js`, `static/panel.css`)

One screen `shadowgraph`, two modes: overview, and focus mode (`S.shadowGraphFocus` = a mission id), which is the per-task detail screen. Visual language is the J2 Map: metro-style left-to-right lines (orthogonal runs, 45-degree joins, 3 px, round caps), circles on the line, shape by kind, colour for status only; the developer lifts the exact CSS tokens for working/waiting/blocked/done/failed/off/idle/draft from `j2ui_assets/j2_ui.html`. Shapes: shadow large circle with an inner dot; task circle; goal diamond; conversation small circle with a tail; task_chat and worker small circle with a bubble (worker with a gear); department double ring. Status is also text (tip) and a glyph, so colour is never the only channel. Working nodes pulse (not under `prefers-reduced-motion`). Nodes are absolutely positioned `<button>`s over an SVG line layer inside one host, rendered through `shadowPatchInto`/`shadowKeepNode` so a typing box is never reset.

```
 Home  >  Shadow graph                        [ Include finished ] [ Fit ]
 +--------------------------------------------------------------------+
 |  (conv)--+                                +--(chat) Shadow chat    |
 |  (goal)<>+--*Shadow--*Fix login bug-------+--(gear) Worker         |
 |          |                                + - - (o) Billing [uses] |
 |          +----------*Weekly report ---------(o) Reports [+spawned] |
 |  legend: * task  (o) department  <> goal  -- uses  - - spawned  .. held |
 +--------------------------------------------------------------------+
 Focus: left = this task's graph; right = Decision, Departments, Chats,
        Workers, Costs, Timeline.
```

Interaction. Click or Enter runs `sgOpen(node.open)`: task selects it on Home via `shadowRouteDeepLink('sutra://shadow/'+mid)`; conversation sets `S.shadowChat`, `S.shadowTaskSel=SH_NO_TASK`, `lsSet('sutra.shadow.conv', cid)`, then `goDest('focus')` and `openScreen('shadow')`; session `shadowOpenSessionPane(sid)`; dept_page `window.o2OpenDept(ref)` (P2's export; falls back to the Org screen); goal `openGoal(gid)`. Hover/focus shows a tooltip card; the edge tag chip shows reason, confidence and 'decided by agent' or 'by the rule: ...'. Keyboard: roving tabindex; Right = first outgoing neighbour, Left = incoming, Up/Down = siblings in the column; Enter opens; Space or `i` pins the tooltip; `f` enters focus mode; Escape leaves. Host `role="group" aria-label="Shadow graph"`; node `aria-label` is '<kind>: <label>, <status>'. Phone (under 700 px): one indented column list with a left rail, 44 px targets, focus sections stacked under the graph, tooltip shown inline below the node (the bottom sheet is deferred).

States: loading (skeleton, "Reading Shadow's tasks..."), empty ('No tasks yet. Tell Shadow what you need on Home.' with a Home button), dark (403: 'Shadow is not enabled'), error (keeps the last good graph, amber 'Could not refresh. Retrying...' and Retry; plain error with Retry when none), stale ('Updated Ns ago'), working ('N working, N waiting on you').

### A5.2.4 The detail screen and the jump

`GET /api/shadow/graph/task/{mid}` returns: header (objective, state, template, executor, goal, times, turns); the focused graph; Decision (the full `dept.decision`: choice, reason, confidence, overrides, who decided, candidates considered with links to their pages); Departments (DeptRow cards); Chats (ChatLink rows for the Shadow chat, conversation, worker, department page, each with Open and 'Open in Chats'); Costs (per role and total); Timeline (newest last, up to 200 rows, merged from the ledger rows of this mission and the decision record; any further source, such as founder_says or revisions, is added only when P4's source table has verified its field).

Jump: in the chat strip code (`06-render.js`), when the open session id equals some `S.shadowMissions[].task_chat_session` (or its Sutra id) or `target_session`, show a 'Details' button (`data-shdetail="<mid>"`) next to 'Shadow >'. A delegated listener in `27-shadow-graph.js` sets `S.shadowGraphFocus=mid` and `openScreen('shadowgraph')`; if `S.shadowMissions` is empty it calls `loadShadowHome(true)` once first. No server change; no sessions-list or stream is touched (STR-2). Home gets a 'Graph' button (`data-shgraph`) and a per-task 'Details' link (`data-shdetail`).

### A5.2.5 Navigation and live update

No URL router is added. State `S.shadowGraphFocus`, persisted in `localStorage 'sutra.shadow.graph'` (a mission id; dropped if the mission is gone). Deep links `sutra://shadow/graph` and `sutra://shadow/graph/m-...` in `shadowRouteDeepLink`. The screen is in no rail plane (`test_panel.js`, `test_nav.js` untouched); `shadowHomeOnScreen()` and `06-render.js`'s `wide` list gain `'shadowgraph'`. `ensureShadowGraphTicker()` polls every 4000 ms (one GET, plus the detail GET in focus mode), coalesced like `_shHomeRead`, cleared when the screen is not `shadowgraph`; a forced read follows every action. No stream is added.

### A5.2.6 Tests

`test_shadow_graph.js` (vm harness: states; nodes and shapes for the sample; `uses`/`spawned` differ by dash class and tag text and carry the reason; each node's click calls the right open path with the right ids; keyboard; `data-shdetail` sets focus and opens; ticker only on the screen; `shadowPatchInto` keeps a typing box; phone width renders the stacked list; `shadowHomeOnScreen` includes the id); `test_shadow_graph_build.py` (seeded isolated `SUTRA_SHADOW_HOME`; every validator rule; missing department row is 'off'); `test_shadow_graph_api.py` (403 when off, validated body, 404 detail, no `response_model`, no model on a streaming route, validator count over two polls). `fixtures/shadow_graph_sample.json` (owned by P1): shadow; conversation shc-a1b2c3; goal g-000000000001; task m-00000000a001 'Fix the login bug' running with task chat, worker and department Billing (kind default) via `uses`, reason 'Billing already handles invoice and login-token questions'; task m-00000000a002 'Weekly sales report' waiting with Reports (kind organic) via `spawned`, reason 'No department covers recurring reports'; task m-00000000a003 done with no department; one held edge to a stopped department.

## A5.3 Part 3: create or reuse, by an agent, for any task

### A5.3.1 When and inputs

The decision is made once per mission and stored, when the task is about to start (a hook in `app._delegate_spawn`, before provisioning) or earlier on request (`POST /api/shadow/tasks/{mid}/department`). A retry (`clone_for_retry`) copies it. It is task-agnostic: one step for every task and kind.

Inputs (`shadow_dept.py` builds them; `shadow_dept_prompt.py` holds the text): the task text (objective, done_when); up to eight `DeptCandidate` cards from `dept_read.candidates(root_ref, words, limit=8)` (ref, name, kind, goal, done, state, stopped, blocked, last_activity, score; the score is a token-Jaccard prefilter only, never the decision); `engine_runtime.library_kinds()` as (kind, use_case) pairs excluding root; at most ten owner rules tagged always, refuse or ask. The prompt says: reuse the best candidate when its goal covers the task; create only when none does; none when the task needs no department; one sentence of reason; choose a kind by its use_case; return JSON of the `dept.choice` shape only. The three source files `dept_read.py`, `shadow_dept.py`, `shadow_dept_prompt.py` contain none of the words web, site, page, blog (source-scan test); use-case strings are data passed through.

### A5.3.2 Model step

`TaskChat.dept_choice(facts)` with constant `DEPT_ASK` in `shadow_task_chat.py`, the pattern of `brief` and `decide` (no tools, returns text). `shadow_dept.parse_choice()` extracts the JSON and validates it with `dept.choice`. The chooser is injectable: `shadow_dept.CHOOSER = {"fn": None}`; tests stub it. Offline, timeout (45 s) or invalid JSON: `decided_by` 'stub' or 'code', action 'use' only on an exact case-insensitive match of a candidate name in the task words, else 'none', with override `offline` or `bad_output`. It never blocks the task.

### A5.3.3 Code covering (`shadow_dept.cover`, in this order)

Each override is appended to `DeptDecision.overrides` and shown. Each has a passing and a failing example in `test_shadow_dept.py`, named `test_dr1_...` to `test_dr8_...`.

| Rule | Override | Effect |
|---|---|---|
| DR-1 | no_org | no Root or no organisation: none |
| DR-2 | not_a_child | a `use` whose ref is not a candidate under this Root: `create` if the choice carried kind, name and goal, else none |
| DR-3 | bad_kind | a `create` whose kind is not in `library_kinds()` (or is root), or with an empty name or goal: none |
| DR-4 | duplicate | a `create` while a non-stopped child has the same case-insensitive name or token-Jaccard of name+goal at least 0.6: become `use` of that child. `founding.spawn`'s own idempotency (same Root, same name, `existing`) stays authoritative: if `spawn` returns `existing`, the stored record is rewritten as `use` with this override. One duplicate rule, no rename (the Setup path's rename-on-kind-mismatch is Setup's and is not reused here) |
| DR-5 | stopped, blocked | a `use` of a stopped department, or one blocked or with an escalated pending ask, is never silent: the decision stays `use` with `held` true and `held_reason`. In link-only mode (the default) the task is not paused; the edge is dotted and a feed item (informational, new OPTIONAL key `department`) says '<name> is Off. Use it anyway, or create another?'. Stop remains the owner's authority: Shadow never starts a stopped department |
| DR-6 | rate | more than 3 creates under one Root in the last 10 minutes: none. The window is derived from the `created` stamps in the children's `dept.json`; no new store, so a restart does not reset it |
| DR-7 | founder_rule | a `create` while an `ask` rule applies to department birth on Root or an ancestor: `held` with `held_reason` 'founder_rule'; nothing is created and no ask is raised. A feed item names the department and why. The owner approves with `POST /api/native/{root}/departments` carrying `confirmed: true` (an owner act through the panel token); declining is doing nothing. Test: approve creates once, decline creates nothing |
| DR-8 | bad_output | invalid choice JSON: none |

### A5.3.4 Create and use paths (link-only default)

Create: `shadow_dept.apply(decision)` calls `founding.spawn(root_ref, name, kind, goal, owner=..., goal_context=<task text>, done_items=...)`, the builder Root's Setup uses (idempotent per Root and case-insensitive name, returns `{ref, created, existing, operation_id}`). Before spawn it asks `engine_runtime.birth_ask_applies(root_ref)`, a new **public** Root-level helper that evaluates the effective rules of Root and its ancestors with the existing `_rule_applies_to_birth(rule)` predicate (so it means exactly what Setup means; the predicate also matches the words make/create/set up in an ask rule's text, an existing behaviour that is noted in the risks). If it is true, DR-7 holds. If not, no stamp and creation proceeds at once. No new ask kind (ASK_KINDS is frozen). The operation id is stored on the decision and in `dept.json` `founding.decision` (`DepartmentFounding` is open: no Department schema change).

Use: in link-only mode the decision is recorded and linked; the department is not messaged and the worker runs as today. `hand_words`, the executor swap (`executor: 'department'`, no worker) and `shadow_dept.follow()` are **not in A5**. They are a later package (A5-FOLLOW) behind an opt-in `SUTRA_SHADOW_DEPT_EXECUTE=1`, built only after a real department has been walked completing a Shadow task, and after Coordination's who-may-post check has been shown to accept a Shadow-originated post to Identity (finding F1). The model enums already allow `executor: 'department'` and `mode: 'execute'`, so enabling it needs no schema version 3.

### A5.3.5 Records and display

`shadow_dept.record()` validates `dept.decision` and then writes `mission['department_decision']` and `mission['department_ref']` through `MissionStore.save` (`MissionStore.create` gains optional keywords defaulting to None; old records and tests are unchanged; `clone_for_retry` copies them) and appends a ledger row (kind 'actions', field kind 'department'). The graph draws it as `uses`, `spawned` or held; the detail screen shows all of it.

Which Root: the single Root; with several, the shadow setting `dept_root`, else the one with the newest activity; with none, DR-1.

### A5.3.6 Routes

`GET /api/native/_departments?root=` (listing; the leading underscore cannot clash with a ref; registered before the `{ref}` routes; stat-signature cache with a 10 s tick); `POST /api/native/{root}/departments` (body `dept.request`; decide and apply for any caller; 404 unknown Root, 409 not a Root, 422 NOT_IN_SCHEMA on a bad body); `POST /api/shadow/tasks/{mid}/department` (decide and optionally apply for a draft or running task). The three routers are included in `app.py` by P1 (empty routers), so P3 and P4 only fill modules.

## A5.4 Pydantic models (A4 rules)

Everything new follows A4: base `layer_models.base.Closed` (extra forbidden), typed fields, bounded strings and lists (`T(n, m)`, `L(of, mx)` of `layer_models/spec.py`), enums for states and kinds, ids by pattern, no free dicts, TypeAdapters built once at import (STR-7), R1 to R12 (these are leaf records: no extension), registered in `layer_models/defs.py` behind the `layer_schema.py` facade with a DEFS entry and generated JSON Schema (`schemas/layers`, `schemas/models`), validated at the sink that writes it and on every API response that returns it, never on a streaming body. Each model has a contract test and an equivalence test with a passing and a failing example for each keyword (`python qa/a4_equiv.py --check --only <name>`). The Models editor lists them as read-only built-ins (A5.4.2).

Shared constants in `layer_models/a5_types.py`: `TS` (one ISO-8601 pattern, reusing a constant in `types.py` if one exists), `MID` `^m-[0-9a-f]{12}$`, `GID` `^g-[0-9a-f]{12}$`, `REF` (the pattern constant of `department.py`), the node-id alternation.

### A5.4.1 The models

| DEFS name | Class (all extend `Closed`) | File | Fields | Validated at |
|---|---|---|---|---|
| `page.words` | `PageWords` | `a5_words.py` | all optional: team T(80,1); noun pattern `^[a-z][a-z ]{0,38}$`; describe T(120); describe_long T(200); start T(200); ready T(120); built T(40); rubric T(80); style_empty T(200); memory_off T(200); go_preview T(60); new_task T(60); retry T(40); frame_title T(80); steps L(T(80)) exactly 9; examples L(T(160)) max 5; follow_ups L(T(80)) max 4; pick, can_open, can_download Bool; hide_tabs L(enum docs, style, lessons, playbooks, preview) max 5 unique. Also `FALLBACK_WORDS`, `KIND_WORDS = TypeAdapter(dict[Kind, PageWords])`, `kind_words(kind)` | `j2ui_words.words_for` once per `ctx.memo['state']`; import time for the tables; the `words` member of `/j2ui/<ref>/api/state` |
| `shadow.open` | `NodeOpen` | `a5_graph.py` | kind enum task, conversation, session, dept_page, goal, none; ref T(80) pattern `^[A-Za-z0-9._:-]{1,80}$` or null; validator: ref null exactly when kind is none | inside node and ChatLink |
| `shadow.node` | `ShadowGraphNode` | `a5_graph.py` | id (alternation pattern, T(90)); kind enum shadow, conversation, goal, task, task_chat, worker, department; label T(80,1); sub T(120) or null; status enum idle, draft, working, waiting, blocked, done, failed, stopped, off; col I(0,8); row I(0,399); open NodeOpen; since TS or null; cost_usd N(0,1e6) or null; tip T(240). Validators: the id prefix matches kind and the per-kind pattern (`task:m-<12 hex>`, `goal:g-<12 hex>`, `dept:<REF>`, `conv:shc-...`, `tchat:`/`worker:` + MID, `shadow:now`) | inside ShadowGraph |
| `shadow.edge` | `ShadowGraphEdge` | `a5_graph.py` | id T(260); kind enum has, opened, attempt, steered_by, driven_by, uses, spawned; source, target (node-id alternation); reason T(300) or null; confidence enum low, medium, high or null; live Bool; held Bool. Validators: id equals `kind:source>target`; source != target; reason non-empty when kind is uses or spawned or when held | inside ShadowGraph |
| `shadow.graph` | `ShadowGraph` | `a5_graph.py` | nodes L(node) max 400; edges L(edge) max 800; as_of TS; focus MID or null; truncated Bool; shadow_on Bool. Validators: node ids unique; edge ids unique; every endpoint is a node id; exactly one shadow node; `task:<focus>` exists when focus is set | `shadow_graph.build()` once before the memo store; `GET /api/shadow/graph` returns the cached validated dict |
| `shadow.timeline_row` | `TimelineRow` | `a5_graph.py` | at TS; kind enum said, did, asked, decided, state, department, cost, chat; by enum founder, shadow, worker, department, system; text T(300,1); ref T(80) pattern `^[A-Za-z0-9._:-]{1,80}$` or null | inside detail |
| `shadow.chat_link` | `ChatLink` | `a5_graph.py` | role enum shadow_chat, conversation, worker, department_page, now; label T(80,1); live Bool; open NodeOpen; alt_open NodeOpen or null | inside detail |
| `shadow.cost_line` | `CostLine` | `a5_graph.py` | role enum now, shadow, worker, department; usd N(0,1e6); turns I(0,100000) | inside detail |
| `shadow.task_head` | `TaskHead` | `a5_graph.py` | id MID; objective T(400,1); state enum equal to `mission_engine.STATES` (a test asserts set equality); template T(40); executor enum worker, department; goal_id GID or null; created TS; updated TS; turns_used I(0,100000) | inside detail |
| `shadow.task_detail` | `ShadowTaskDetail` | `a5_graph.py` | task TaskHead; graph ShadowGraph; decision DeptDecision or null; departments L(DeptRow) max 8; chats L(ChatLink) max 12; costs L(CostLine) max 6; total_usd N(0,1e6); timeline L(TimelineRow) max 200; as_of TS. Validators: `task.id == graph.focus`; `decision.mission_id` is null or `task.id`; every department ref appears as a `dept:` node in the graph | `shadow_graph.detail()` once; `GET /api/shadow/graph/task/{mid}` |
| `dept.row` | `DeptRow` | `a5_depts.py` | ref REF; name T(200,1); kind pattern `^[a-z][a-z0-9-]*$` max 40 (membership in `W.KINDS` checked at the sink: the Library can add kinds); parent, root REF or null; runtime 1 or 2 (the same integer-enum helper `types.py` uses); stopped Bool; state enum not_started, working, waiting, blocked, stopped, done, idle; waiting_on_you Bool; pending_asks I(0,99); working L(T(40)) max 12; last_activity, created TS or null; goal T(240); done T(160); done_met Bool or null; engines, artifacts L(T(40)) max 32; j2_url T(120) or null | `dept_read.rows`; `GET /api/native/_departments`; detail |
| `dept.listing` | `DeptListing` | `a5_depts.py` | departments L(row) max 500; root_ref REF or null; as_of TS. Validator: refs unique | `GET /api/native/_departments` |
| `dept.candidate` | `DeptCandidate` | `a5_depts.py` | ref; name T(80,1); kind; goal T(240); done T(160); state (as DeptRow); stopped, blocked Bool; last_activity TS or null; score N(0,1) | `dept_read.candidates()` |
| `dept.choice` | `DeptChoice` | `a5_depts.py` | action enum use, create, none; ref or null; kind or null; name T(80) or null; goal T(2000) or null; done_items L(T(200)) max 12; reason T(400,1); confidence enum. Validator: use requires ref and forbids kind/name/goal; create requires kind, name, goal and forbids ref; none forbids all four | `shadow_dept.parse_choice()` |
| `dept.override` | `DeptOverride` | `a5_depts.py` | rule enum stopped, blocked, duplicate, not_a_child, bad_kind, rate, no_org, bad_output, offline, founder_rule; note T(200,1) | inside decision |
| `dept.decision` | `DeptDecision` | `a5_depts.py` | choice DeptChoice; final_action enum use, create, none; final_ref REF or null; overrides L(override) max 6; held Bool; held_reason enum stopped, blocked, founder_rule or null; decided_by enum agent, code, stub; mode enum link, execute; considered L(REF) max 8; candidates_seen I(0,500); root_ref, result_ref REF or null; operation_id T(80) or null; mission_id MID or null; at TS; prompt_version T(20). Validators: use implies final_ref; none implies final_ref null; held implies held_reason; `candidates_seen >= len(considered)`; create with result_ref set only when not held | `shadow_dept.record()` before `MissionStore.save` and before `founding.spawn` writes `dept.json`; both POST routes; detail |
| `dept.request` | `DeptRequest` | `a5_depts.py` | words T(4000,1); mission_id MID or null; apply Bool (default true); confirmed Bool (default false) | the route body, through the sink, so a bad body is 422 NOT_IN_SCHEMA |

### A5.4.2 Schema version 2 and the Models editor

DEFS gains 17 names; that moves `INTERFACE_SHA`, so A5 ships schema version 2 (A1.21): `SCHEMA_VERSION = 2`, `MIGRATIONS[1]` a no-op, `INTERFACE_SHA[2]`, a regenerated `schemas/layers/interface.v2.json`, `INTERFACE_SHA[1]` unchanged. This is P1's first commit, alone, before any model. Tests: a v2 record reads as a no-op; a v1 `dept.json` migrates to 2; extra-forbidden models still hold; `test_x2_the_interface_is_frozen_...` and `test_data_compat.py` move to version 2. The hard-coded `'schema_version': 1` in `layer_models/schema.py` reads `SCHEMA_VERSION`. Rollback note for the release: a build that knows only version 1 cannot cleanly read records written at version 2, so a one-version read shim is named in the release notes.

The editor listing does not use `EXTENSIBLE_CORE` (owners may extend those) or `NESTABLE_CORE` (owners may nest those). A5 adds a third tuple `SEALED_CORE` in `layer_models/spec.py`: listed by `models_api.py` as read-only built-ins, not extensible, not nestable; a `CORE_SAYS` line each in `owner_rules.py`. Tests: no A5 name is in `EXTENSIBLE_CORE` or `NESTABLE_CORE`; an owner model that tries to extend or nest one is refused; `test_models_api.py` asserts all 17 are listed.

## A5.5 Records

| Record | Where | Shape |
|---|---|---|
| `department_decision` | mission record | `dept.decision`, validated before save; null for tasks with no decision, so old records stay valid |
| `department_ref` | mission record | REF or null; the `result_ref` or `final_ref`, copied |
| `executor` | mission record | not written in A5 (default 'worker'); the later package writes it |
| `founding.decision` | `dept.json` of a department a decision created | `dept.decision` without the choice's long goal duplicated (`DepartmentFounding` is open) |
| ledger row | `shadow_ledger` kind 'actions', field kind 'department' | mission_id, final_action, final_ref, reason (300), held |
| feed item key | `shadow_feed.OPTIONAL` gains `department` | REF or absent; `test_shadow_feed.py` updated |
| `sutra.shadow.graph` | localStorage | focus mission id or empty |

## A5.6 APIs

| Route | Purpose | Shape |
|---|---|---|
| `GET /api/shadow/graph?focus=&include_done=` | overview or focused graph | `shadow.graph`; 403 flag off; JSONResponse; plain GET |
| `GET /api/shadow/graph/task/{mid}` | detail | `shadow.task_detail`; 403; 404 |
| `POST /api/shadow/tasks/{mid}/department` | decide, optionally apply | body `dept.request` with `mission_id`; `dept.decision`; 403 flag off; panel token and origin guard |
| `GET /api/native/_departments?root=` | cheap listing | `dept.listing` |
| `POST /api/native/{root}/departments` | decide and apply for any caller | body `dept.request`; `dept.decision`; 404 / 409 / 422 |
| `GET /j2ui/{ref}/api/state` (changed) | 57th key `words` | `page.words` object (empty for website); every kind answers |
| `GET /api/native/{ref}/map` (changed) | adds `j2: bool` | true when `need(ref)` passes |

No route has a `response_model`; none validates a streaming body.

## A5.7 Rules and non-functional requirements

1. Everything new is a closed pydantic model, registered and validated at its sink (A5.4). No free dicts.
2. No code path names a kind: the J2 scope is `kind in W.KINDS`; the decision source files pass the forbidden-words scan; words are derived from the department and a noun table.
3. A website department's page is unchanged (snapshot test).
4. Stop is the owner's authority: Shadow never starts a stopped department.
5. S-18: a stamp only when an `ask` birth rule applies; no new ask kind.
6. A model never writes: the task chat returns text; the app does every write.
7. Old mission records and old `dept.json` load unchanged.
8. Performance: one read per tick, a 2 s memo of the validated graph, a 10 s listing cache; the graph is a plain GET; the 60-task cap applies after the read (measure in P5).
9. Accessibility: colour is never the only channel; keyboard complete; reduced motion respected; 44 px targets on phone.

## A5.8 Packages

| Key | Package | Builds after | Merges after | Owns (summary) |
|---|---|---|---|---|
| a5-models | P1 MODELS | none | none | `layer_models/a5_*.py`, `defs.py`, `spec.py`, `owner_rules.py`, `schema.py`, `models_api.py`, `layer_schema.py`, schemas, fixture, empty routers and three `include_router` lines in `app.py` |
| a5-j2all | P2 J2-ALL | P1 | P1 | `j2ui_*.py`, `website_api.py`, `25-j2view.js`, `19-org2.js`, `22-website.js`, sync script, `j2ui_assets/*`, tests |
| a5-decide | P3 DECIDE | P1 | P1 | `dept_read.py`, `dept_list_api.py`, `shadow_dept*.py`, `shadow_task_chat.py`, `mission_engine.py`, `shadow_feed.py`, `engine_runtime.py` (one helper), `app.py` (the `_delegate_spawn` hook only) |
| a5-graph | P4 GRAPH | P1 | P1, P2, P3 | `shadow_graph*.py`, `27-shadow-graph.js`, `16-shadow-home.js`, `15-shadow-overlay.js`, `06-render.js`, `panel.html`, `static/panel.css` |
| a5-verify | P5 VERIFY | P2, P3, P4 | P2, P3, P4 | `qa/walks/a5-e2e.sh`, `qa/shots/a5/*`, the design documents |

P1 merges first and is announced; P2, P3, P4 rebase. P4 merges after P2 because it calls `o2OpenDept`. The full specs are in the build scratchpad (`waves/A5-specs/<key>.md`). Milestone steps are in PRD-FIVE-FUNCTIONS.md M13.

## A5.9 The review of 2026-10-29 and how it is applied

| Finding | Ruling |
|---|---|
| F1 P0: no path by which a mission drives a department; the cited code is Root's Setup path | Link-only by default. Executor swap, `hand_words`, `follow()` move to a later package behind an opt-in flag (A5.3.4). Decision `mode` is 'link' in A5 |
| F2 P0: EXTENSIBLE/NESTABLE mean something else; schema.py hard-codes version 1 | `SEALED_CORE` tuple; tests that no A5 name is extensible or nestable; `schema.py` reads `SCHEMA_VERSION` (A5.4.2) |
| F3 P1: PageWords over-built | Fallback separate from the kind map; the map is a validated `TypeAdapter`; fields cut to what S4 reads; tab ids verified (selector is `.tabs [data-tab]`) |
| F4 P1: adapters carry website assumptions | The per-kind route matrix is the first P2 gate (A5.1.2) |
| F5 P1: static text changed for website | S4.01 to S4.05 become the S4.37 applier that acts only when a word is set; website words are empty; S4.35 and S4.36 handlers are gated on words; S4.34 done or exempted with a reason; snapshot test |
| F6 P1: graph elements without a verified record | P4's first step is the source table; missing department row is 'off' with tip 'Record not found', not 'idle' |
| F7 P1: loose typing | one `TS` pattern; per-kind id patterns; derived edge id; detail validators; failing example per rule |
| F8 P1: schema version 2 | kept; own commit first; read-shim note in the release notes (A5.4.2) |
| F9 P1: S-18 and DR rules | public `birth_ask_applies`; rate window from `dept.json` stamps; DR-7 is a held decision approved through the route, no ask kind; one duplicate rule with `spawn` authoritative (A5.3.3) |
| F10 P1/P2: package overlap; Root default | P1 owns the three router includes; P4 merges after P2 and uses `o2OpenDept`; `static/panel.css` named; Root's page not the default until walked (A5.1.7) |
| F11 P2: validate per poll | validate once in `build()`, memoise the validated dict (A5.2.2) |
| F12 P2: tests pinned to the gate | the grep step and the extra test files (A5.1.6) |
| F13 P2: scope for asap | cut line: no executor swap, no `follow`, no bottom sheet, timeline limited to verified sources. Kept: the detail screen, ChatLink, CostLine |
| F14 P3: edge cases | edge id derived and checked; `kind` checked against `W.KINDS` at the sink with a failing example |

## A5.10 Open risks

1. The executor swap is deferred and unproven; the link-only default is the safety valve. If the owner wants the swap in A5, it needs the later package and a real department walk.
2. Root's real Setup conversation inside the J2 page is unverified; P5 walks it and the organisation row default flips only after.
3. Several organisations: the Root choice (settings key, else newest activity) is a default.
4. The verbatim hashes re-pin against prototype `f9ceba1`; if the prototype moves, guard 7 fails loudly.
5. `_rule_applies_to_birth` matches loose words in an ask rule's text, so a rule saying 'make' holds a create (DR-7). It holds, it does not block.
6. `MissionStore.list()` reads every file; the cap helps only after the read. Measure in P5.
7. Adding DEFS moves `INTERFACE_SHA`: any branch touching `layer_schema.py` conflicts; P1 merges first.
8. `shadow_feed` consumers that enumerate keys must change together with the new `department` key.
9. The conversation id shape (`shc-...`) and the `Kind`/integer-enum helpers are read from notes; P1 and P4 confirm them first.
