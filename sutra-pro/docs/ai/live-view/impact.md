# Impact: live-view
Commit 6c79a1db (live-view = remove-real-run-gates = origin/main). Line numbers are this worktree's.

Ask: while a run is going, show who is working now (Asha, Mira, Kabir, Dev, Nora) and what they are doing, in one plain line, on the Map and in chat.

## 0. Read first
| Fact | Evidence |
|---|---|
| Every `sutra_app/engine/j2*.py` file (j2.py, j2_map.py, j2_studio.py, j2_realization.py, ...) is GENERATED. A change to one is an `Edit("P<n>", ...)` in `scripts/vendor_j2.py` | vendor_j2.py:46-49 (CODE), :70-75 |
| `ui/pages/j2_ui.html` is GENERATED: a change is an E edit in `scripts/port_j2_ui.py`, mirrored in `tests/ui/test_port_edits.py` | port_j2_ui.py:18 |
| Sutra's own files (no patch needed): views.py, rawchat.py, host/*, capabilities/agents.py, events.py, orchestrator/*, connectors/*, ui/static/js/* | vendor_j2.py:46-49 lists none of them |

## 1. Where "Running" and "Working…" come from
| UI text | Code | Data it reads | How it gets there |
|---|---|---|---|
| Chat line `Working…` | j2_ui.html:1976-1977: `s.thinking ? "<name> is working…" : s.status === "running" ? "Working…"` | `/api/state` keys `thinking`, `status` | `poll()` (j2_ui.html:1965-1967) fetches `/api/state?since=` on a timer; no stream |
| Map pill `Running` | j2_ui.html:3659-3668 `mapChip` shows `m.status.state` | `/api/map` → views.map (views.py:443-445) → j2_map.build → `_state_line` (j2_map.py:127-136) | `_state_line` says `"<lane name> running"` only when a lane is `working` (j2_map.py:133-135); with no working lane it falls back to the bare `"Running"` (:136) |
| Nothing lit on the Map | j2_map.py:166-178 `_functions`: a box is `running` only when its lane is `working` | `snapshot.lanes` | `lanes()` (j2.py:3691-3708) marks a lane `working` only when `thinking == fn` (or `turn == fn`) |
| Simple view crew lines ("Planning the parts", "Checking it on a phone and a laptop") | j2_ui.html:1083-1102 `sCrew`, :1108-1119 `sPhase` | `s.thinking` + `studio.parts[].st` | hard-coded UI text per function: the kind the task should remove |
| Snapshot on disk | host/publisher.py:216-247 writes `snapshot.json` + `live.json` | `views.live_state(run)` = `J2Run.snapshot()` (j2.py:4441-4477) | at most every 250 ms, and every 1 s while running (publisher.py:1-20, :148-160); views.state (views.py:342-356) serves it |

**Root cause**: everything keys on one value, `J2Run.thinking`. It is set only inside `J2Run.call` (j2.py:4822) and cleared in its `finally` (j2.py:4851). The realization planner and judge calls bypass `call`. They go through `j2_realization.ask` → `llm.ask` (j2_realization.py:798-802), reached from the output pick, "What I build" (j2.py:5658), and the realization plan (j2.py:8386). During those calls `thinking` is None, so the run shows `Running`, nothing is lit, and the chat says `Working…`.

Evidence, from the run folder `prototypes/j2/runs/j2-20261117-131753` (main checkout, untracked): wall 874 s, AI 170 s, waiting on the requester 401 s (timing.json). Chat gaps where no logged call runs: 13:18:31 → 13:19:29 (58 s, the output pick) and 13:22:33 → 13:25:50 (3 min 17 s, the realization plan plus judge). Call ids 3-10 are missing from calls.jsonl (it jumps from 2 to 11). About 4 min 15 s of the 5 unaccounted minutes are these calls.

## 2. What a run records today that could say who and what
| Record | Path / format | Writer | When | Names the agent? | Names step / section? | UI can reach it? |
|---|---|---|---|---|---|---|
| `thinking` | snapshot key, a function or `W-n` | J2Run.call j2.py:4822 | during a `call` only | yes (J2 id) | no | yes, `/api/state` |
| `lanes[]` | snapshot: `{id, name, status, doing, on}` | `lanes()` j2.py:3691-3720 | every publish | yes | `doing`: `"writing section <sec>: <workflow name>"` for a builder, else the STEPS label (j2.py:192-195, :3703), else the last chat text (140 chars) | yes, `/api/state` |
| `studio.parts[]` | `{name, person, st: doing/done/...}` (studio/1) | j2_studio.parts j2_studio.py:96-116 | every snapshot | yes, as a person (mira/kabir/dev via KIND_PERSON :21) | yes, the part name ("Problem", "Menu") | yes, `/api/state.studio` |
| `studio.stream[]` | one line per finished function message | j2_studio.stream j2_studio.py:119-161 | after a message | yes (asha/nora or role) | yes, but text is fixed per act ("planned a fix.") | yes |
| `chat.jsonl` | `{id, t, who, text, act, next, calls}` | J2Run.post | when a turn ends | yes | in its own words ("@W-1 Builder Envelope check for W-1") | yes, `/api/state.chat` |
| `agent_live.json` | `{schema: agent-live/1, at, agents: {<fn or W-n>: {call, since, text, tool, tools}}}`; `text` is the reply so far (last 4000 chars), `tool` is the last tool title ("Reading src/a.py", connectors/tool_kinds.py:61, router.py:1320-1332) | AgentLiveCapability capabilities/agents.py:96-215 | **during** each agent call, about 4 times a second; the entry goes when the call ends | yes: key = `tag.function or "agent"` (:155) | the tool line is what it does right now | yes: `GET /api/agent-live` (api/rawchat.py:5, :42, rawchat.live_tail). Today only the Raw AI chat (raw_chat.js:243) and node-panel partials (orchestrator/runs.py:121-140) read it |
| node events `task.summary` | events.jsonl `node` lines: `"<STEPS label>: <handoff why>"`, running then done | publisher.turn_started/finished publisher.py:164-178 | at each turn's start and end | yes (functions only, not W-n) | the handoff's "why" | indirectly: orchestrator rows, not the J2 page |
| `calls.jsonl` | per call: fn, step, t, seconds, tokens, reply, reason | J2Run.call | after a call ends | yes | step number | yes, `/api/calls`, `/api/call` |
| `receipts.jsonl` | per check: atom, check, pass, evidence, attempt, t | code checks | after each check | atom id (W-n.a1) | the check's name | via artifacts and records |
| `atoms.json`, `map.json`, `timing.json`, `summary.json` | per atom status, map/1, durations | J2 | at saves / the end | yes | yes | `/api/map`, `/api/state` |
| `heartbeat` events | events.jsonl, every 5 s | host/heartbeat.py:1-30 | during the run | no | no | no |

Gaps in the evidence: I read no Sutra Pro host run folder (snapshot.json, live.json, events.jsonl, agent_live.json). They live only under the app data folders, which were off limits. The shapes above come from the code. The sample run above is a plain J2 run with no host files.

## 3. The gap, and the smallest addition
| # | Gap | Evidence |
|---|---|---|
| G1 | Planner and judge calls never set `thinking`, so minutes of a run show nobody | j2_realization.py:798-802; sample run above |
| G2 | In `agent_live.json` those calls are keyed `"agent"`: their tag inherits `function=""` and adds only `role` (planner or judge) | P7 edit vendor_j2.py:3398-3404; agents.py:155. **Inferred from code, not seen at runtime** |
| G3 | The UI's one-liners are fixed text or ids ("W-1 Builder running", `STEPS` labels, sCrew strings), not what the agent does | j2_map.py:134, j2.py:3703, j2_ui.html:1088-1102 |
| G4 | The page never reads the live record that has the agent's own words and tool line | only raw_chat.js:243 calls `/api/agent-live` |
| G5 | Map names (Identity, `W-1 Builder`, persona "Product Analyst" j2_map.py:31) differ from the Simple view's people (Asha, Mira, ...) j2_studio.py:20-21 | two naming tables |

Proposal: the smallest version needs no new state, no status list and no J2 patch.
| Step | Change | File (owner) | Why this one |
|---|---|---|---|
| A | Key a live entry by `tag.function or tag.role or "agent"` (planner, judge) | capabilities/agents.py:155 (Sutra) | fixes G1 and G2 in the record that already runs during every call, keyed by the call's own tag |
| B | Put the live agents into `/api/state` as one additive key (`live: rawchat.live_tail(dir).agents`), so the page's one poll carries it | views.state views.py:342-356 (Sutra) | no second poll and no new endpoint; `live_tail` already exists |
| C | Who: a `W-n` key → `studio.parts[].person` (already in the snapshot); a function → PEOPLE (asha, nora; Planner and so on behind Asha). What: the entry's `tool` line, else the first line of its `text`, else the part's name ("Mira: Problem") | one E edit in port_j2_ui.py: `#typing` (j2_ui.html:1976-1977), `mapChip` (:3666) and the Map node of that agent | the line comes from what the agent does, not fixed text |
| D | Delete the hard-coded function lines in `sCrew` (j2_ui.html:1088-1091, :1094) in favour of C's line | same E edit | simplifies (D55 Restructure-on-Add); the goldens move |
| E (optional) | Chat updates as steps start and finish: show the start from an `agent_live` entry appearing (`since`); the finish is already the posted chat message | no new stored message | avoids a ninth event type (events.py:7, the list is closed) |

Not proposed: a J2 patch that makes `j2_realization` set `run.thinking`. It has no run reference, so it would need a new P patch through the hot file vendor_j2.py, and it still gives no plain line.

## 4. Files likely to change, and the overlap with remove-real-run-gates
remove-real-run-gates has **no commits**: it equals origin/main (6c79a1db). `git diff main...remove-real-run-gates --stat` shows 201 files only because local `main` is 164 commits behind origin/main; it is not the branch's work. The removal exists as an uncommitted plan in the main checkout (`sutra-pro/docs/ai/remove-real-run-gates/impact.md`, untracked, plus an edit to `sutra-pro/docs/ai/analysis.md`).

| File | live-view | remove-real-run-gates (per its impact.md) | Conflict risk |
|---|---|---|---|
| sutra_app/engine/capabilities/agents.py | A | no | none |
| sutra_app/engine/views.py | B | no | low |
| scripts/port_j2_ui.py | C, D (new E) | E28 and E29 removed (port_j2_ui.py:310-323) | medium: different blocks, same edit list and E header line :18 |
| tests/ui/test_port_edits.py | E mirror | E28 and E29 mirror (:71, :181-187) | medium: line :71 is a shared list |
| sutra_app/ui/pages/j2_ui.html | regenerated | regenerated | high: regenerate after rebasing, never merge by hand |
| tests/ui/fixtures/j2/golden-*.json | shift from D | maybe | medium |
| docs/DECISIONS.md, docs/diagram/decisions.json | 1 D | 1 D (D452) | number clash, see 5 |
| scripts/vendor_j2.py, j2*.py, VENDORED.md, test_engine_patches.py, agents/j2/identity.md, artifacts/real_run.md | **not touched** by this proposal | the removal's main surface | none if the proposal holds |
| docs/ai/analysis.md | edited (this stage) | edited, uncommitted, in the main checkout | **text conflict when both land**: merge by hand |

Off limits for live-view: j2.py real-run code (j2.py:236-239, :906-1135, :6058-6412, :10017-10056), E28, E29, and anything that reads `paused.code`.

## 5. Numbers
| Series | Highest on origin/main and every ref | Owned or planned | Proposed for live-view |
|---|---|---|---|
| D | D451 (DECISIONS.md, decisions.json; commit 6e1351ca, project files) | removal plans D452; the caller says Kaivan owns D451 and up | **D453** if the D451+ reservation is not literal. If it is literal, nothing at or above D451 is free: then **D442** (unused gap D442-D445; D441 is a renumbered Kaivan number, so it is avoided). Ask before taking either |
| P | P44 (VENDORED.md, vendor_j2.py) | P45 Kaivan (DECISIONS.md:3161, not landed); removal plans P46 | **none needed**; if a J2 patch turns out to be necessary, **P47** |
| E | E30 (port_j2_ui.py:324, D451) | removal: E31 only if it needs one | **E32** |

Check: `git grep` over every local and remote ref found no `## D45[2-9]`, `Edit("P4[5-9]`, or `"E3[1-9]`, and `git log --all` names none of them. The removal's own numbers are only in its uncommitted impact.md (§5).

## 6. Tests
| Area | Tests | State |
|---|---|---|
| agent_live.json writer | tests/engine/test_engine_agent_live.py | ran: pass |
| /api/agent-live reader | tests/engine/test_engine_rawchat.py | ran: pass |
| chat.partial from agent_live | tests/orchestrator/test_runs_watcher_partials.py | ran: pass (41 passed in all, 1.0 s) |
| publisher, snapshot, lanes, node events | tests/engine/test_engine_publisher.py, test_engine_host.py, test_engine_views.py | not run |
| Map pill, `#typing`, sCrew render | tests/ui/js/page_render.test.js + fixtures/j2/golden-*.json (simple, team, teamwork, plan) | not run; D changes the goldens |
| E edits | tests/ui/test_port_edits.py | not run |
| **Gap** | no test covers `thinking` during a realization call, or the Map or chat line while an agent is mid-call | |

Commands (from sutra-pro/):
| Purpose | Command |
|---|---|
| the targeted Python tests above | `scripts/py -m pytest tests/engine/test_engine_agent_live.py tests/engine/test_engine_rawchat.py tests/orchestrator/test_runs_watcher_partials.py -q` |
| page render goldens | `node --test tests/ui/js/page_render.test.js` |
| re-port the page | `scripts/py scripts/port_j2_ui.py --j2 "$J2SRC" --commit <c> [--check]` |
| full gate (about 15 min, foreground) | `scripts/gate.sh` |
| try it live | `scripts/py scripts/install_app.py beta`, then start a run in Sutra Pro Beta (data `~/.sutra-pro-beta`) and watch the team page: Map tab, Agent view chat (`#typing`), Simple view crew; compare with Settings & logs → Raw AI chat (`/d/<team>/raw`), which already shows `/api/agent-live` |
| status of both apps | `scripts/py scripts/install_app.py status` |
| never | `scripts/live_smoke.py`; anything under `~/.sutra-pro` |

## 7. Risks and open questions
| # | Item | Confidence |
|---|---|---|
| R1 | G2 is inferred from code. Confirm by looking at `agent_live.json` during a beta run's "What I build" phase | moderate |
| R2 | `agent_live` exists only when a router is installed (agents.py:122-124). Mock runs and the browser tests have no entries, so a fixture is needed | high |
| R3 | `text` is the model's raw reply (JSON for a function turn). The plain line must prefer `tool`, else the part name. agent_chats.js:29 already says "writing its reply" for text that starts with `{`: reuse that rule | high |
| R4 | j2_ui.html conflicts with the removal's E28/E29 deletion: land one first and re-port the other | high |
| R5 | analysis.md is edited on both lines of work | high |
| Q1 | On the Map, should a function box show the person (Asha, Nora) or the function (Identity, Audit)? Today it shows the function (j2_map.py:25) | open |
| Q2 | Kaivan's D range: is "D451 and up" literal? D451 is already the project-files decision | open |
| Q3 | Should chat updates be stored as messages, or shown only live? The proposal shows them live only | open |
