# J2 sync 4: Sutra Pro takes over the changes of `prototypes/j2` (sync note of record, as built)

_Status: built and merged on `feat/sutra-pro-j2-sync-4` (lanes A, A3, B, C, D1, D2, E1, E2, E3a, E3b, L and V0; lane G wrote the documents and the release) · Date: 2026-11-10 · Ships as: 0.3.0 · Source: the folder `prototypes/j2` of this repository at `025e265c594564f47a2365874cd5a5cc5d0d20a6`, tree `21c67045fe3230c1ab9be381c2f21465ea91849c` (the Studio redesign) · Decisions: D136 to D155 in `docs/DECISIONS.md`_

This note replaces the design and build plan this file held before the work (the plan, the lane table, the verification matrix and the analysis behind them). It says what landed, where the build differs from that plan and why, and what was left out on purpose, in the spirit of `j2-sync-3.md`. Each lane has its own as-built note with the measurements: `docs/notes/J2S4-a.md`, `J2S4-a3.md`, `J2S4-b.md`, `J2S4-c.md`, `J2S4-d1.md`, `J2S4-d2.md`, `J2S4-e1.md`, `J2S4-e2.md`, `J2S4-e3a.md` (with `J2-SYNC-4.md`, the method of the fixtures), `J2S4-e3b.md`, `J2S4-l.md` and `J2S4-v0.md`. The difference between `prototypes/j2` and Sutra Pro is no longer a document written by hand: it is produced by `scripts/j2_diff_of_record.py` and its report is `docs/notes/J2-DIFF-OF-RECORD.md`; the analysis document that stood beside this note (`j2-sync-4-analysis.md`) is removed for that reason.

Paths are relative to `sutra-pro/` unless they start with `prototypes/`. The owner's rules of this sync: one central engine and nothing rerouted around it (R1); every agent works in its own chat session with its own model and effort pick (R2); everything in the copy that Pro lacked is implemented or listed below with its reason (R3); numbered decisions (R4); the page is generated, J2's prompts and code are byte-identical but for numbered patches, goldens move only through recorders, no owner name and no absolute home path in any file, every decision has a pill, traceability is regenerated (R5); and the one J2 reference is `prototypes/j2` of this repository (D154).

## The source and the numbers, as built

| Item | Value |
|---|---|
| Source | the folder `prototypes/j2` of this repository, nothing else (D154) |
| Pin | commit `025e265c594564f47a2365874cd5a5cc5d0d20a6`, tree `21c67045fe3230c1ab9be381c2f21465ea91849c` (`git rev-parse <commit>:prototypes/j2`). The pin moved once while the lanes ran, from `00efb179` to this one, which holds the Studio redesign of the Simple view (D153) |
| Extraction | `git archive <commit> prototypes/j2 \| tar -x --strip-components=2 -C <new, empty folder>`; the folder goes to every script with `--source` (or `--j2`) and `--commit`; the working tree is never read |
| Engine | 208 files (207 rows in `VENDORED.md`: the files minus itself), 17 code modules (new: `j2_agent_models.py`, `j2_agent_views.py`, `j2_studio.py`); `vendor_j2.py --check`: `208 files, ok` |
| Patches | P1 to P5, P7 to P12, P14, P15 and P16; there is no P6 and no P13 (P13 is retired into `engine/runlist.py`); 55 text edits and the one data patch P15 (D136, D140, D152); a late-judge switch, if live numbers ask for one, would be P17 (D145) |
| Seed library | 157 files, 32 templates, 39 versions (26 `mock: true`), 8 `runs` rows |
| Page | 33 edits, 7 generated files; `port_j2_ui.py --check`: `ok: the 33 anchors ... and the 7 committed files equal a fresh port` |
| Routes | 41 handlers (`HANDLER_COUNT`; 34 GET rows and 7 POST rows of J2's table, `VIEWS` has 40 entries), `J2_EXACT` 33 names and five prefixes |
| Decisions | D136 to D155 (D135 belongs to the 0.2.1 fix); D91 and D18 carry an Amended line |
| Difference of record | `scripts/py scripts/j2_diff_of_record.py --check` exits 0: 284 files of the pin, 207 vendored (196 identical, 11 patched), 6 page files (3 verbatim, 3 patched), 4 legacy test copies, 67 excluded each with a reason, 0 undecided |

## Landed, by lane

| Lane | What landed | Where | Decisions |
|---|---|---|---|
| A (foundation) | `vendor_j2.py` from the extraction (constants, header, `CODE`, the P1 counts, P15, P16, `--commit`); the first vendoring and the re-pin to the Studio tip; `engine/runlist.py`; records that strict mode needs (`judge`, `auto_label`, `LateEntry`, `RealizationDoc.late`, `settings.json` as an open run object, `RegisteredWorkflow.version` 0); the three schemas re-exported | `scripts/vendor_j2.py`, `sutra_app/engine/{j2*.py,runlist.py,VENDORED.md,seed,templates}`, `sutra_app/library/{chat,wire}.py`, `docs/schemas/` | D136, D140, D143, D145, D152 |
| A3 (recorders) | `MAPS` gains `enums` so the shape golden stops depending on the seed; the seventh prompt scenario `agent_answer`; every golden recorded from the extraction with `--source` and `--commit` (no default folder); the Studio delta moved none of the seven prompt goldens and none of the function-node goldens, only the `state` shapes | `scripts/record_{api_shapes,engine_golden,fn_golden}.py`, `tests/engine/golden/` | D150 |
| B (routes) | `plan_map`, `activity`, `catalog`, `artifacts_groups`, `ask` and the Studio's `record`, `doc`, `view`, `settings` as views on the one `RunCtx`; adapters and stdlib rows; the report row of an output (`Capability.documents`); the library views read `<data>/library` (`RunCtx.library`); Decide for me end to end; `next_run` in the engine settings view; the shape golden recorded from J2's own server | `sutra_app/engine/{views,j2_server}.py`, `engine/api/*`, `engine/capabilities/{base,__init__}.py`, `engine/spec.py`, `engine/host/inbox.py`, `orchestrator/tasks.py`, `tests/contracts/` | D140, D141, D146, D147, D152, D153 |
| C (ask port) | `RouteContext.pick`, `agent_chat` in `PICK_PURPOSES`; `orchestrator/agent_ask.py` (`AgentAsk`, `AskTurn`); `ChatMessageOut.ask`; the end-to-end test over the real router and fake CLIs | `sutra_app/connectors/{router,models}.py`, `sutra_app/orchestrator/{agent_ask,chats,models,wiring}.py`, `tests/integration/test_agent_ask_e2e.py` | D147, D148, D149 |
| D1 (seed sync) | `sync_seed_library` (add only, under the library lock, nothing renumbered), `missing_seed_versions`, `sync_seed_once` at start, `config sync-library`, the doctor check | `sutra_app/ops/{doctor,cli}.py`, `orchestrator/wiring.py` (`start_services`) | D144 |
| D2 (finish steps) | `engine/host/finish.py`: the guarded steps `agent_views` and `catalog` at the end of a run, one call in `Host._conclude` | `sutra_app/engine/host/{finish,loop}.py` | D142, D143 |
| E1 (page port) | `port_j2_ui.py` with 33 edits; the frozen `j2-shell.css` for Home and the console; `SutraCtx` (`pagePath`, `libraryPath`, `onLibrary()`, 33 names); `GET /d/{dept}/library` | `scripts/port_j2_ui.py`, `sutra_app/ui/{pages,routes.py,static/css/{j2,j2-shell}.css,static/js/sutra_ctx.js}` | D137, D138, D141, D153 |
| E2 (modules and sheet) | `output_pick.js`, `function_chat.js`; the node panel's Note and Ask modes; the ask lines in the chat view; both team chips; `sutra-panel.css` (strips, Ask box, the node panel's own bubbles, motion overrides for the Studio sheet) | `sutra_app/ui/static/{js,css}/` | D139, D148, D155 |
| E3a, E3b (UI tooling) | `capture_j2_fixtures.py` (80 fixtures, deterministic, R5 scrub); `page_render.test.js` (53 tests, J2's own harness equal to the ported page with an extraction); the fake backend with every new route and the Python UI tests of the Studio page | `scripts/capture_j2_fixtures.py`, `tests/ui/` | D150 |
| L (legacy test) | J2's flow test brought to the pin in two merges; J2's new blocks run on the vendored engine; `EXPECTED.json` | `tests/engine/legacy/`, `tests/engine/test_engine_legacy.py` | D150 |
| V0 (difference of record) | `scripts/j2_diff_of_record.py` with its exclusion table; `docs/notes/J2-DIFF-OF-RECORD.md` before and after | `scripts/`, `tests/engine/test_j2_scope.py` | D91, D154 |
| G (docs and release) | D136 to D155 and the D91 and D18 amendments; the pills and the key of the diagram (`gen.py` now sizes its key from `decisions.json`); `docs/ENVIRONMENT.md` (the `J2_DECIDE_FOR_ME` row, eight task keys); the traceability matrix at 41 endpoints and 155 decisions; the design and operator documents; this note; version 0.3.0 | `docs/` | all |

What the owner gets, in one list: the Studio page (Simple view, icon rail, chat panel, Adaptation Map, Artifacts groups and tabs, native Run settings, the shared library page at `/d/{dept}/library`); Decide for me; a function's answer as a turn of its own session (own model and effort pick, scrubbed, limited, booked, never offline); the late judge on by default as in J2; the agent-readable JSON and the catalog entry at the end of every finished run; the project report in Artifacts' Documents group; new seed versions delivered to an existing install without overwriting anything.

## Deviations from the plan, and why

| # | Plan | Built | Why |
|---|---|---|---|
| 1 | pin `00efb179`, 207 files, 16 modules, patches P1 to P15 | pin `025e265c`, 208 files, 17 modules, P16 added | the owner asked for the latest `prototypes/j2` while the lanes ran: the Studio commits add `j2_studio.py`, Decide for me (which rewrote `settings.json`: P16) and the Studio routes (D152, D153) |
| 2 | the header of `VENDORED.md` and a constant of the script name a second source | the header names the sutra commit, the tree id and the extraction command only; there is no such constant | one source only (D136, D154) |
| 3 | 37 handlers, 30 names in `J2_EXACT`, 28 page edits | 41 handlers, 33 names, 33 edits | the Studio routes and edits (D140, D137) |
| 4 | strict mode needs `judge` and `late` | it also needed `auto_label`, `settings.json` as a catalogued file and `RegisteredWorkflow.version` 0 | J2 gives the Plan workflow of a realization run version 0 and the model demanded 1: strict mode refused `workflows.json` of every run with realization on, the default (D145) |
| 5 | the user text of an ask goes through `scrubbed` with an audit row | the router's egress in replace mode first (that writes the audit row and replaces the app's secrets), then `scrubbed`; J2's system text through `scrubbed` only; the stored lines are scrubbed too | `scrubbed` writes no audit row (D149) |
| 6 | D145: usage by purpose, the Agents tab line and a live-smoke scenario for the late judge | not built; the ledger already holds the purpose | Sutra-side extras cut by the owner to finish sooner (below) |
| 7 | the legacy flow test merged from a composite folder with saved runs | merged in two steps from the history of this repository; `SUTRA_J2_CHECKOUT` is the plain extraction, so the blocks that need saved runs or Chrome print why they did not run | the only J2 source is `prototypes/j2`, which holds no saved runs (D150) |
| 8 | the start page's output choice before the chips | the first child of the row of options, beside Decide for me; nothing is built for an archived team | the Studio's start page has no select and its chips are examples (D139) |
| 9 | preview frames: unspecified | the frames keep Sutra's sandbox; the Studio's decoration of frames stays off | D83 (D153) |
| 10 | the node panel asks in any function chat | in a live function chat only; a past run's chat is read, and J2's panel asks about a past run | the Agents tab opens a past run's chat read-only (D148) |
| 11 | the Studio sheet is taken as it comes | `sutra-panel.css` restores the node panel's bubbles and overrides the sheet's motion; J2's sheet is not edited | the sheet scopes the bubbles to `#sview` and breaks D122 (D155) |
| 12 | `gen.py` untouched | the decisions key is sized from `decisions.json` | the key was a fixed 396 px for 109 entries; with 124 entries the last rows were outside the figure, and D136 to D155 would have been the clipped ones |

## Not done, and why (skipped on purpose; each item is recorded where it is explained)

| Item | Reason | When it comes back |
|---|---|---|
| Usage by purpose: `GET /api/usage/summary?by=purpose`, `usage.by_purpose` on the Agents rows, "judging N calls, $x" and "questions N calls, $x" under an agent's usage (lane D3, E2.2) | a Sutra-side extra, cut by the owner to finish sooner; the ledger already has `purpose`, `fn`, `session_id` and `atom_id`, so the numbers can be read there | a package of its own: `UsageStore.summary(by="purpose")`, the `by` literal, `team_agents` rows, the modules and tests (D145) |
| The console's table of usage by purpose (`console_view.js`) | the same cut | with the item above |
| Live-smoke scenarios `--scenario late-judge` and `--scenario ask` of `scripts/live_smoke.py` | the late-judge one was cut with D4; the ask one had no owner in the plan; both need the real CLIs and a spend | on the owner's word for a live run; facts for the first are in `J2S4-d2.md` (a forced audit failure goes into the team's `engine.json`; stub rows are left out unless `include_stub=1`) |
| A live run with the real `claude` CLI on a scratch copy of a data folder, with `template_library` on and its row in the catalog's "By run" | no live call was made in any lane | the integrator's live step |
| The motion probe of D122 on the Studio page (five states, `tests/ui/perf/fluid_probe.js`) and its table in `docs/notes/J2-SYNC-4.md` | cut by the coordinator; it needs a shown browser pane (a hidden one gets no frames); the rules are met by overrides and proved by `motion_css.test.js` | with a probe run |
| The Studio's decoration of the preview frames (tags on parts, glow on a new version, scroll restore, link interception) | it reads the frames' documents, which the sandbox forbids (D83); the code is guarded | never, unless D83 changes |
| The steps of J2's flow test that need saved runs or Chrome (`--browser`); a Windows run | the copy holds no saved runs; no Chrome run and no Windows here; the skip lines are listed in `tests/engine/legacy/EXPECTED.json` | a corpus of saved runs in the copy turns the blocks on without a change of the test; the Windows CI job |
| Closed library models for `plan-map/1`, `activity/1`, `artifacts-groups/1` and the catalog | J2's Artifacts rows still move often; the shape goldens fail on any key that appears or goes (D151) | W-WIRE |
| Home and the console in J2's new look | a design pass with its own risk; they keep the frozen sheet (D138); J2's page paints light first and Home dark, so a viewer who never chose sees two looks | a Home design package |
| Asking a workflow builder (`W-n`) or the validator; Ask in a past run's chat inside the node panel | J2's `answer` serves six functions; the validator is code with no session; the port can serve a builder's step session once J2's `answer` covers builders | when J2's feed and answer cover builders |
| Live typing of an answer (`chat.partial`); server-side repair of an interrupted question | an answer is one short call; the page says "No answer was stored." and the question stays | when the owner asks |
| The Settings text of the `template_library` flag does not say that the catalog's "By run" lists J2's eight development runs only while it is off | text in `settings_view.js`, found while writing D142 | with the next Settings pass |
| A switch for the late judge | no live number yet (D145) | P17 on the measured cost |
| The HTML mocks, the explainer pages, the flow picture, screenshots, diagram pictures, `docs/build-on-run-design.md` (a design with no code), the older studio, the budget demo, `llm.py` and `j2_server.py` | not engine or page code, or replaced by Sutra's own files (`engine/llm.py`, `engine/views.py`, `engine/j2_server.py`); D91 was wrong about the explainer pages, the flow picture and the solar mock being kept under `docs/reference/j2/`: they are not carried (amended) | the exclusion table of `scripts/j2_diff_of_record.py` (67 files, each with its reason) is the record; its `--check` fails on a J2 file that is neither carried nor excluded (its "also written in" column still words the D91 disagreement as open: that is lane V0's data and was left alone) |
| Dead references in the byte copies of J2's `README.md` and `realization-axis.md` (`docs/ui-studio-*.png`, `docs/j2-flow.jpg`, `docs/realization-axis.dot`) | the copies are J2's words; the three pictures are not carried | the vendor script's reference list can take the three small pictures |
| `docs/reference/j2/SETUP.md` tells the reader to clone a separate repository (J2's own two lines, copied byte for byte) | a copy of J2's setup guide | stop vendoring `SETUP.md` (`REF_TOP`), the owner's call |

## Findings the plan did not have

- The seed library index held six absolute home-folder paths of a J2 developer's machine (`runs[].library`); patch P15 makes them `not recorded`, and the fixture capture applies the same rule (R5).
- Home and the console were built on J2's old Simple skeleton and five classes that only the old stylesheet defines; they keep a frozen copy of it (D138).
- The server process never set `J2_LIBRARY_DIR` (only the engine host does), so `library`, `library_item` and `run_templates` read a folder that does not exist; the views now read `<data>/library` (`RunCtx.library`, D141). Until then nobody saw the synced templates in the app.
- Decide for me wrote `settings.json` over the file the host had written (P16, D152); a task setting `J2_DECIDE_FOR_ME` never reached J2 because the host exports only the settings it knows (the eighth task key).
- The Studio sheet scopes the chat bubbles to `#sview` and breaks D122 (three `transition: all` rules, thirty layout properties, six keyframes); the node panel and the motion rules are restored in Sutra's own sheet (D155).
- `j2_agent_views.build` raises `SystemExit` for a folder that is not there; the finish steps catch it (D142).
- The attention pill sat on J2's Chat button in the Detailed view; the integration commit lifts it, and darkens the Studio's team-rail link whose contrast gap `test_visual.py` had named.
- Strict record mode would also reject the project output's condition and rubric ids (`PJ1`, `PJ-1`) in `conditions.json` and `audits.json` of a project run (log mode only traces it); not from this sync, not changed.
- J2's live snapshot has 59 keys (`decide_for_me`, `auto_answers`, `studio` are new).

## What was checked, and what was not
Each lane's results are in its own note, measured on that lane's tip. Lane G ran, serially, on the merged tree: `docs check: ok (4 documents)`; `build_traceability.py --check` ok (two regenerations are byte equal); `tests/test_docs.py`, `test_traceability.py`, `test_layout.py`, `test_ownership.py` and `test_markers.py`: 110 passed; `scripts/j2_diff_of_record.py --check`: PASS; `check_release_tag.py sutra-pro-v0.3.0` passes; `tests/release` and `tests/test_packaging.py`: 590 passed, 9 skipped; `tests/ops`, `tests/test_smoke.py`, `tests/test_build_plan.py`, `tests/orchestrator/test_startup.py` and two UI files that read the version: 1,127 passed, 19 skipped; the vendor, scope, runlist and contract tests: 292 passed, 1 skipped; the desktop tests that need no installed package: 117 passed, 1 skipped (`package.test.js` needs `@electron/packager`, which that checkout does not have); `docs/diagram/gen.py` builds with all 144 key rows inside the figure. The integrator's gate is still the proof for the whole tree: `scripts/gate.sh`, `node --test tests/ui/js/*.test.js`, the slow engine suite with an extraction, the browser suite, and CI on Windows. No lane ran a live model call, a Windows run, `--browser` of J2's flow test or the motion probe.

## What to run

```
export J2SRC="$(mktemp -d)"                 # a new, empty folder, never inside the repository
PIN=025e265c594564f47a2365874cd5a5cc5d0d20a6
git archive $PIN prototypes/j2 | tar -x --strip-components=2 -C "$J2SRC"        # from the repository root
test "$(git rev-parse $PIN:prototypes/j2)" = 21c67045fe3230c1ab9be381c2f21465ea91849c
cd sutra-pro
scripts/py scripts/vendor_j2.py --source "$J2SRC" --commit $PIN --check          # 208 files, ok
scripts/py scripts/port_j2_ui.py --j2 "$J2SRC" --commit $PIN --check             # ok: the 33 anchors ... 7 committed files
scripts/py scripts/record_api_shapes.py --source "$J2SRC" --commit $PIN --check  # up to date (and record_engine_golden.py, record_fn_golden.py)
scripts/py scripts/capture_j2_fixtures.py --j2 "$J2SRC" --commit $PIN --check    # ok: 80 files
scripts/py scripts/j2_diff_of_record.py --check                                  # PASS: both checks pass and every file is decided
SUTRA_J2_CHECKOUT="$J2SRC" SUTRA_SLOW=1 scripts/py -m pytest tests/engine/test_engine_legacy.py tests/engine/test_engine_prompts.py
scripts/gate.sh                                                                  # pytest and the node tests; then: node --test tests/ui/js/*.test.js
SUTRA_BROWSER=1 scripts/py -m pytest tests/ui                                    # the browser tests (Chrome)
```

## Compatibility and rollback

Existing data folders need nothing: there is no database migration (`SCHEMA_VERSION` is unchanged; `ChatMessageOut.ask` is derived from `src_ref`); settings files take no new key; old run folders are read as they are (their rows have no `stage_from` or `judge`, their Artifacts tab falls back to the run's own JSON); a run in flight at the upgrade ends as before in its own process (no finish steps for that run); the library gains templates, versions and provenance only, under its lock, with the marker `.seed-sync`. Every API change is additive (new routes, `next_run`, `ChatMessageOut.ask`); `PATCH_VIEWS` and `J2_PATHS.patched` were internal names. Rollback: revert the merge of the integration branch; nothing in a data folder needs undoing (the library additions and `.seed-sync` are additive files, the ask lines are plain chat lines, the agent JSON files are extra files in run folders). A release is never "Latest" (D100), so 0.2.1 stays installable beside 0.3.0.
