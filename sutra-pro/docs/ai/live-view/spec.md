# Spec: Show who is working and what, live, on the Map and in chat
Status: Refined   |   Task: live-view   |   Date: 2026-11-26

Inputs: docs/ai/analysis.md, docs/ai/live-view/impact.md (stage 1). Line numbers are at commit 6c79a1db (live-view = remove-real-run-gates = origin/main).

## Problem
The owner, during a run: "I am pretty much in the blind. Who is working on it right now, and what is it working on."
Today the Map says `Running` with no box lit, and chat says `Working…`. Both are driven only by `J2Run.thinking`, which is None during
planner and judge calls (impact.md §1). The Simple view's crew lines are fixed sentences per function, not what the agent does.

## Goals
| # | Goal |
|---|---|
| G-1 | While a run is going, the page names the person working (Asha, Mira, Kabir, Dev, Nora) and what they do, in one plain line |
| G-2 | The Map lights the box of the working agent and its status chip carries that line |
| G-3 | Chat shows short live updates as an agent's call starts and ends |
| G-4 | Every line comes from data the run already records (agent_live.json, snapshot); nothing is invented by the UI |

## Non-goals
| # | Not in this task |
|---|---|
| N-1 | Renaming Map boxes. Box labels stay; the person goes in the status line ("Mira: Reading src/a.py") (founder decision 2) |
| N-2 | Saving live updates as chat messages (founder decision 3) |
| N-3 | Real-run approval, hosts, dry-run code; E28/E29; j2.py real-run blocks (j2.py:236-239, :906-1135, :6058-6412, :10017-10056) |
| N-4 | Any Pulse-specific (or other team-specific) logic |
| N-5 | A new event type, endpoint, poll timer or stored file |
| N-6 | Rewriting `sPhase` (j2_ui.html:1108-1117) (Q-9: out of scope) |
| N-7 | Showing an agent's free text (`text` of an entry, chat message text) as the live "what" (Q-10) |

## User scenarios
| # | Who | Situation | Sees |
|---|---|---|---|
| S-1 | Owner | Adaptation's realization planner runs for 3 min (impact.md §1 sample) | Map: Adaptation box lit, chip "Asha: Adaptation proposes workflows" (the call's step name; no tool line); chat: the same line |
| S-2 | Owner | W-2 (a part) reads a file | Map: W-2's team box lit, chip "<its part's person>: Reading src/a.py"; chat line the same |
| S-3 | Owner | Three builders run at once | One chat line per working agent (at most 3, then "+N"); Map lights all their boxes |
| S-4 | Owner | Between two calls (no live entry) | The last line shown in this page session, never empty or bare `Working…` / `Running` |
| S-5 | Owner | Reloads the page mid-run | No old live rows in chat history; until the next live entry, the line is the run's step name |

## Current behaviour
| What | Where | Behaviour |
|---|---|---|
| Chat line | j2_ui.html:1976-1977 | `<name> is working…` only when `s.thinking`; else `Working…` |
| Map chip | j2_ui.html:3660-3667; j2_map.py:127-136 | bare `Running` when no lane is `working` |
| Map box lit | j2_map.py:144-178 | `running` only when the lane is `working` (`thinking == fn`) |
| Map repaint | j2_ui.html:2019 | `loadMap` only when `total/status/turn/paused` changes; a new tool line alone repaints nothing |
| `thinking` set / cleared | j2.py:4822 / :4851 | only inside `J2Run.call`; planner and judge calls go through `j2_realization.ask` → `llm.ask` and bypass it |
| Crew lines | j2_ui.html:1083-1102 (`sCrew`) | fixed sentences per function ("Planning the parts", "Checking it on a phone and a laptop") and per maker state |
| Live record | capabilities/agents.py:96-215 | agent_live.json, key `tag.function or "agent"` (:155, :166), `text` last 4000 chars (:160), `tool` first 200 chars (:162), **cut before any redaction**; rewritten ≤4/s (:61) |
| Live record in mock mode | agents.py:122-124 | not written (no router) |
| Who reads agent_live today | raw_chat.js:243 via GET /api/agent-live (engine/api/rawchat.py:42); orchestrator/runs.py:121 | the J2 page does not |
| Redaction of API bodies | engine/api/ctx.py:187, engine/api/reply.py:65-73 | every engine GET body (incl. /api/state and /api/agent-live) passes through `services.redact` = orchestrator/redact.py `Redactor` (wiring.py:106) |
| Redaction in the host process | connectors/engine_port.py:136 | none: the host's router gets an `Egress` with no redactor; agent_live.json is written unredacted |
| Snapshot step during "What I build" | j2.py:5606 | the call's tag says `step=2`, but `J2Run.step` (snapshot `step`) is not set to 2 there; the tag's step is the accurate one |

### Evidence: how planner and judge calls are recorded (Step A)
| Source | Found |
|---|---|
| 34 agent_live.json files under `~/.sutra-pro-beta/departments/*/runs/*/` | all `{"schema":"agent-live/1","agents":{}}`: entries are removed when a call ends (agents.py:164-169) and `close()` empties the file. **No runtime key was observable** |
| calls.jsonl, e.g. `web-design/runs/j2-20261125-130356-6c20` | ids jump 1 → 8: calls 2-7 (the planner/judge calls) are not logged. Rows carry `fn` only, no role/purpose |
| Code: purpose filter | `LIVE_PURPOSES = AGENT_PURPOSES = ("agent_turn", "plan", "judge")` (agents.py:62, hooks.py:37): planner/judge calls **are** recorded; a change-request plan (`purpose="change"`, vendor_j2.py:3398) is not |
| Code: tag nesting | `llm.tagged(**fields)` builds the new tag from `{**current_tag().model_dump(), **fields}` (llm.py:340-350), so P7's `tagged(role=..., purpose=...)` (vendor_j2.py:3398-3404) keeps the enclosing `function`. Enclosing blocks: `tagged(function="adaptation", step=2, ...)` around "What I build" (j2.py:5606) and `tagged(function=fn)` around every turn (j2.py:4582) |
| Conclusion | Planner and judge entries are keyed **`adaptation`**. Confidence: high from code (llm.py:340-350 is a plain dict merge); the FR-1 unit test proves it; one beta read confirms it at runtime (plan.md, live test) |

## Data sources
| Need | Source | Field | Already redacted on the way to the page |
|---|---|---|---|
| Who is live now | agent_live.json via `rawchat.live_tail` (rawchat.py:106-125) | key (`W-n` or function) | yes: written redacted (FR-5) and served through `to_response(..., services.redact)` |
| What they do now | same | `tool` (e.g. "Reading src/a.py") only; `text` is never shown (Q-10) | same |
| Which step the call is in | same | `step` (new: the call's own `tag.step`) | n/a (number) |
| When it started | same | `since` | n/a (number) |
| Person of a `W-n` | /api/state `studio.parts[]` (j2_studio.py:96-116) | `workflows` contains W-n → `person` | yes |
| Person of a function | the page's existing tables: Identity and `BACKSTAGE` (adaptation, priority, coordination, validator) → Asha; audit → Nora (j2_ui.html:1041-1042, today's sCrew :1088-1093) | | n/a |
| Part name fallback | `studio.parts[].name` | | yes |
| Step name fallback | /api/state `steps[<entry step, else snapshot step>]` without its code prefix (as renderSteps j2_ui.html:411 shows it) | | yes |
| Last thing that happened | the last live line this page session showed (page memory, not stored) | | yes |

## Functional requirements
| ID | Requirement | Acceptance check (Given / When / Then) |
|---|---|---|
| FR-1 | While a planner or judge call runs, agent_live.json holds an entry whose key maps to a person. Expected key: `adaptation`. Only if the FR-1 test shows `"agent"`, key = `tag.function or tag.role or "agent"`, the **same** expression in `progress` (agents.py:155) and `finished` (:166) | Given `llm.tagged(function="adaptation")` enclosing `llm.tagged(role="planner", purpose="plan")` (and again with `role="judge", purpose="judge"`), when `AgentLiveCapability.progress(llm.current_tag(), {"tool": "x"})` runs, then `snapshot()["agents"]` has exactly one key and it is `adaptation`; after `finished(tag)` it is empty |
| FR-2 | The page gets the live entries on its existing poll (j2_ui.html:2024, 700 ms) as one additive key `live` of `/api/state` (live mode only), through `services.redact` | Given a live run folder with the fixture agent_live.json, when `GET /api/state?dept=web` is fetched, then `body["live"]` holds each fixture key with its `tool`, `since` and `step`; a saved run's state has no `live` key |
| FR-3 | Each live key resolves to a person from existing data only: `W-n` → the `studio.parts[]` whose `workflows` holds it → `person`; `identity` or a `BACKSTAGE` function → Asha; `audit` → Nora (Q-2: the judge, keyed `adaptation`, is Asha). No person → the key itself is the who (Q-3), e.g. "agent: …" | Given fixture keys `W-2` (a part of Mira in the fixture state), `adaptation`, `audit`, `agent`, when the lines are built, then the whos are Mira, Asha, Nora, `agent` |
| FR-4 | The "what" is, in order: `tool`; else the part name (`W-n`); else the step name of the entry's `step`, else of the snapshot's `step`. Never the entry's `text` or any chat text (Q-10). Cut to 120 characters. A line with no what is the who alone, never "Name: " | One fixture entry per branch yields the expected string; the fixture's `text` values appear in no output; a 300-char tool line shows 120 chars |
| FR-5 | The line never shows a secret value. The writer redacts **first, then cuts** (`text` tail 4000, `tool` 200), with the existing `Redactor` class (orchestrator/redact.py:24-90) built from the same `.env` file as the server's (`default_env_file()`). In the host it knows **`.env` values only**: the host is started without secret-named environment variables (orchestrator/runs.py `child_environment`) and without the launch token or override key. Environment-only secrets are redacted only whole, by the API pass on the body (reply.py:73, ctx.py:187); a secret of that kind split by the writer's cut is a known limit, accepted (Q-7, review R1-2). Secrets are not passed into the host to close it. No second redactor implementation, no secret list in the browser. Paths stay visible. Other accepted limits (Q-7): whole values only | (a) Given a `Redactor` that knows `fake-token-0123456789`, when a `tool` of 195 chars + that value and a `text` of that value + 3995 chars are recorded, then neither the snapshot's `tool` nor `text` holds any 5-char piece of the value (fails on today's cut-then-redact). (b) Given the fixture with that value in a `tool` and `svc.secrets` holding it, when `/api/state` is fetched, then the body has `[redacted]` and not the value; `src/a.py` is unchanged |
| FR-6 | Chat: while ≥1 entry is live, `#typing` shows one line per live agent, "<Who>: <what>", ordered by `since`, at most 3, then "+N" (Q-6), instead of `Working…` | Given 1 live entry, then `#typing` text equals "Mira: Reading src/a.py"; given the 4-entry fixture, then 3 lines ordered by `since` and "+1" |
| FR-7 | Chat updates are live only: a line appears when an entry appears and is replaced when it goes. Nothing is written to chat.jsonl or returned in `state.chat`; nothing survives a reload | Given the live fixture, `state.chat` length equals the chat.jsonl line count without it; the page code that builds the line never calls `addMsg` |
| FR-8 | Map: the box of each live agent (`fn:<key>` for a function, the team box (`kind: "engine"`) whose `workflows` holds a `W-n`) shows the existing `running` state; the chip shows the line of the most recent entry (largest `since`) instead of `Running`. Box labels unchanged. The Map repaints when the live lines change, on the same poll | Given fixture keys `adaptation` and `W-2`, then `fn:adaptation` and W-2's team box have status `running`, their labels equal today's, and the chip text is the line of the entry that started last; with no live entries no node is changed |
| FR-9 | Never blank: when the run is running and nothing is live, the chat line and the Map chip show the last live line of this page session; on a fresh load (none yet), the step name of the snapshot's `step` (not the last chat message: Q-10) | Given status running and `live: {}` after a live line was shown, then the line equals that last line; given a fresh page with the same state, then it equals the step name |
| FR-10 | Delete the fixed crew status lines in `sCrew` (j2_ui.html:1088-1095 and :1097-1100, removed by the E32 edit in scripts/port_j2_ui.py), and the helpers only they use (`sNum`, `sCap`, :1082). A live person's crew line is its FR-4 "what" through `plain()`, and it is busy. An idle person's line is their last live "what" of this page session (Q-5), else empty. Kept (Q-4): :1087 (needs you), :1096 (parked on your answer), :1101 (handoff) | In the regenerated page, none of "Planning the parts", "Deciding what comes first", "Lining up who goes next", "Making sure each part is ready to start", "Talking it through with the team", "Keeping things on track", "Checks each part as it finishes", "Free for the next part", "Waiting for the plan", "Nothing for this project", "Hit a problem", "Wrapped up", "Ready when you are", "Checked the work" is anywhere in the page (each occurs once today, only in sCrew), and "coming up" is not in `sCrew` (it occurs 4 times elsewhere); with the fixture, Asha's crew line is the plain step name and Mira's is "Reading src/a.py"; after the entries go, both keep those lines and are not busy |
| FR-11 | One fixture holds agent_live entries (mock runs write none, agents.py:122-124): a `W-n`, `adaptation` (the FR-1 key), `audit` with a fake secret in its `tool`, and `agent` with free `text` and no tool | `tests/ui/fixtures/live/agent_live.json` exists; the Python (FR-2, FR-5b, FR-7) and JS (FR-3, FR-4, FR-6, FR-8, FR-9, FR-10) tests read it; removing `liveLines` or the `live` key fails at least one |
| FR-12 | The decision is D453 in docs/DECISIONS.md and docs/diagram/decisions.json; the page edit is E32; the comment patch is P47. All rechecked on `origin/main` before commit and renumbered to the next free if taken (Q-8) | `tests/test_diagram_decisions.py` passes; `git grep -n '## D453' origin/main`, `git grep -n '"E32' origin/main`, `git grep -n 'Edit("P47"' origin/main` show nothing before the first commit |
| FR-13 | Order: remove-real-run-gates lands first; live-view rebases onto it and regenerates j2_ui.html with scripts/port_j2_ui.py (never a hand merge) | `port_j2_ui.py --check` is clean; tests/ui/test_port_edits.py passes; `git merge-base --is-ancestor <removal commit> HEAD` succeeds |
| FR-14 | The rule comment at j2_studio.py:8-9 says exactly: tool lines may be shown; the agents' free text still may not (Q-10). j2_studio.py is generated, so this is a comment-only patch P47 in scripts/vendor_j2.py | `grep -n "P47 (D453)" sutra_app/engine/j2_studio.py` shows the sentence; `vendor_j2.py --check` is clean; no line of j2_studio.py other than the docstring changes |

## Non-functional requirements
| ID | Requirement | Check |
|---|---|---|
| NFR-1 | A new `tool` line is visible on the page ≤2 s after the agent's tool call (file ≤4/s, poll 700 ms, Map repaint on the same poll) | manual check in the beta: time from the Raw AI chat showing a tool line to the Map/chat showing it |
| NFR-2 | No new endpoint, poll timer, event type (events.py:7 list unchanged), or stored file. The only J2 patch is P47, comment only. The only change to the agent_live record is one added field, `step` | `git diff --stat`: sutra_app/engine/j2*.py changes only j2_studio.py's docstring; events.py unchanged; no new route in engine/api |
| NFR-3 | No new hard-coded status sentence or status list in the UI; no team-specific branch | review of E32: its string literals are separators (": ", "<br>", "+"), the 120 cut, and existing table names (BACKSTAGE, PEOPLE) |
| NFR-4 | It simplifies the page: the regenerated `sCrew` plus the removed `sNum`/`sCap` line is shorter than today's 22 lines (j2_ui.html:1082-1103) | line count of that block in the regenerated page |
| NFR-5 | Off-limits code unchanged: real-run approval, hosts, dry-run, E28, E29, anything reading `paused.code` | `git diff` against the rebased base touches none of them |
| NFR-6 | With no live entries, a saved or finished run renders as today except FR-10's deleted crew lines; a running mock run's chat line is the step name (FR-9) instead of `Working…` / `<name> is working…` | page render goldens: every golden key equal; `team` equal once the crew `<small>` texts are blanked on both sides; plus FR-10's own test |

## Edge cases
| Case | Expected |
|---|---|
| Several `W-n` live at once | one chat line each, at most 3 then "+N" (FR-6); all boxes lit; chip = latest `since` (FR-8) |
| Key `"agent"` (a call outside any function tag) | who is `agent` (Q-3); what is its step name; no crew line (no person) |
| `text` is JSON or prose, no `tool` yet | never shown; part name / step name (FR-4) |
| Entry with empty `tool`, no part, no step | the who alone |
| agent_live.json left with entries after a crash (only a clean end empties it, agents.py:136-145) | ignored: `live` is used only while `status === "running"` |
| Saved run | no `live` key; today's behaviour minus FR-10 lines |
| A secret straddling the 200-char `tool` cut or the 4000-char `text` cut | redacted whole before the cut (FR-5) |
| A secret still streaming (the reply so far ends with part of it) | not a whole value yet, so not redacted; accepted (Q-7; live_redact.py:13 treats a partial prefix the same) |
| A secret the agent read from a file, not in the env or `.env` | `Redactor` does not know it (redact.py:1-6); accepted (Q-7) |
| `W-n` not in any `studio.parts[].workflows` (the style section, j2_studio.py:98) | who is the key (`W-3`), Agent view only; no crew line |
| A change-request plan call (`purpose="change"`) | not in agent_live (LIVE_PURPOSES); FR-9 line shows. Out of scope |

## Assumptions
| # | Assumption |
|---|---|
| A-1 | FR-1's code reading holds at runtime (key `adaptation`); the unit test plus one beta read confirm it (Q-1) |
| A-2 | Tool titles ("Reading src/a.py", connectors/tool_kinds.py:61) are plain enough to show as they are |
| A-3 | remove-real-run-gates has no commits yet (both branches at 6c79a1db on 2026-11-26); it lands before live-view |
| A-4 | The host process sees the same `.env` (`config.default_env_file`, honours `SUTRA_ENV_FILE`) but not the server's secret-named environment variables (child_environment removes them), nor the launch token or override key (server-only `extra`, wiring.py:100-106); the API pass covers those, whole values only (review R1-2) |

## Open questions
| # | Question | Who answers | Answer |
|---|---|---|---|
| Q-1 | Is the planner/judge key `adaptation` at runtime? | owner, 2026-11-26 | Trust the FR-1 unit test; add `tag.role` only if it shows `"agent"`. Keep one live check: read agent_live.json during a beta run's "What I build" phase. Stage 3: high confidence from llm.py:340-350 |
| Q-2 | The judge is keyed `adaptation`, so it shows as Asha. Nora instead? | owner | Whoever the existing person mapping gives: Asha. No special case, no data change |
| Q-3 | For key `"agent"` or an unmapped `W-n`? | owner | Show the key as the who, e.g. "adaptation: …" style (differs from the draft's "what alone") |
| Q-4 | Keep the question/handoff crew lines (j2_ui.html:1087, :1096, :1101)? | owner | Keep |
| Q-5 | An idle person's crew line after FR-10? | owner | Their last live line (consistent with FR-9), not a fixed text. Stage 3: the page session's memory of that person's last "what" (no stored data, N-5); empty before any |
| Q-6 | Cap on chat live lines | owner | 3 lines, then "+N" |
| Q-7 | Redactor limits | owner | Redact FIRST, then truncate; reuse orchestrator/redact.py `Redactor`, no second redactor; otherwise accept its limits |
| Q-8 | D453 / E32 provisional | owner | Developer rechecks origin/main before committing; renumber to the next free if taken (P47 too) |
| Q-9 | `sPhase` in scope? | owner | Out of scope |
| Q-10 | The live line vs j2_studio.py:8-9 ("never the agents' own words") | owner, APPROVED | Tool lines may be shown; the agents' free text still may not. Update the comment at j2_studio.py:8-9 to say exactly that (FR-14). The what comes from the tool line, else the part or step name, never free text |

No open question blocks the design.

## Change log
| Date | Change |
|---|---|
| 2026-11-26 | First draft from impact.md and founder decisions 1-3; Step A evidence recorded |
| 2026-11-26 | solution-architect: Status Refined. Owner answers Q-1..Q-10 recorded. FR-3: unmapped who is the key (Q-3; was "what alone"); W-2 example is Mira (the fixture state's parts are all Mira's, tests/ui/fixtures/j2/state.json). FR-4: `text` removed as a source, lane `doing` replaced by the step name of the call's own step (Q-10; lane `doing` is the last chat text when not working, j2.py:3700). FR-5: redact before the cut in the writer (Q-7), because today the cut happens first (agents.py:160-162) and the host has no redactor (engine_port.py:136). FR-6: cap 3 + "+N" (Q-6). FR-8: names which boxes light and adds the repaint, because the Map reloads only on total/status/turn/paused (j2_ui.html:2019). FR-9: fresh-load fallback is the step name, not the last chat message (Q-10). FR-10: idle line = last live what (Q-5); deleted range made exact; `sNum`/`sCap` go with it. New FR-14 (Q-10 comment, P47) and N-7. NFR-2 relaxed on purpose: one comment-only J2 patch (owner asked for FR-14) and one added agent_live field `step` (so "What I build" shows step 2, not the stale snapshot step, j2.py:5606). NFR-6 tightened into a concrete golden check, and states the mock-run chat line change |
