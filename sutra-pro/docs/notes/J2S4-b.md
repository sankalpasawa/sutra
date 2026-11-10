# J2 sync 4, lane B (routes): as built

Branch `lane/sync4-b`. Design: `docs/design/j2-sync-4.md` 3.1 to 3.3, 3.5; the re-pin to `prototypes/j2` @ `025e265c` (tree `21c67045`) added the studio routes. The only J2 reference is an extraction of `prototypes/j2`.

## Built

| Package | What | Where |
|---|---|---|
| B1 | five views `plan_map`, `activity`, `catalog`, `artifacts_groups` (live view), `ask`; the studio views `record`, `doc`, `view`, `settings`; `view_page` (J2's lives in its server file, which is not vendored); `HANDLER_COUNT` 41 (`VIEWS` 40, 34 GET rows, 7 POST rows); `PATCH_VIEWS` gone; adapter rows in `engine/api/{run_views,library,files,commands}.py`; stdlib rows (`/library` as the page, a records-only `ask`, `settings` on `RUN.set_auto`); `build_traceability` counts every view | `engine/views.py`, `engine/api/*`, `engine/j2_server.py`, `scripts/build_traceability.py` |
| B1 | the library views read `<data>/library`: `RunCtx.library` (set by `build_ctx`) and `views._library`, which sets `J2_LIBRARY_DIR` for one call under a lock and puts it back (the server never sets it, only the engine host does) | `engine/views.py`, `engine/api/ctx.py` |
| B2 | `Capability.documents`, `capabilities.documents`, and the merge in `artifacts_groups`; `project.py` and `workspace.py` are untouched | `engine/capabilities/{base,__init__}.py` |
| B3 | `Commands.ask`, `DeptCommands.ask`, `AgentChatTurn` and `AskFailed` in `ports.py` (`agent_chat` optional); `next_run` in `settings_view` | `engine/api/{commands,ports,settings}.py` |
| B4 | the recorder's route list (36 to 42 routes, 11 POSTs; no `patched` section; takes an extraction only), the golden recorded from J2's own server, the route-table and settings contracts | `scripts/record_api_shapes.py`, `tests/engine/golden/api_shapes.json`, `tests/contracts/*` |

## Decide for me (decided here; the addendum was cancelled): for lane G's `DECISIONS.md`

J2's switch is `J2Run.auto`, set by `POST /api/settings {decide_for_me}`. In the app the live run is another process, so:

1. **The setting.** `EngineSettings.decide_for_me: bool = False` (env `J2_DECIDE_FOR_ME`, exported by the host before J2 is imported; the host's `settings.json` carries the field name) and the eighth task key `J2_DECIDE_FOR_ME` (`"0"`/`"1"`: `TASK_SETTING_KEYS` and `TaskSettings` agree). A run started with the key has the switch on from its first question.
2. **The command.** `POST /api/settings` is `views.settings` and `DeptCommands.settings(on)` (`None` only reads). A live run gets the inbox line `{"kind": "setting", "decide_for_me": bool}`, written by the task service (`TaskService.send_setting`, wired as `services.send_setting`, optional) and applied by the host with `J2Run.set_auto` (J2 persists it; lane A's P16 keeps the host's `settings.json`). The host (`engine/host/inbox.py`) applies a `setting` line at once, ahead of the FIFO, whatever the run is doing.
3. **The team's choice** is also kept in `page.json` `next_settings.J2_DECIDE_FOR_ME`, so a team with no run, and every later run, start with it. Unlike the output choice it is not cleared by a delivery (J2's switch stays through Start over and follow-ups).
4. **The state.** `/api/state.decide_for_me` is J2's own snapshot field while a process holds it; the idle snapshot takes it from the effective settings (the page's choice included); a run whose process has gone shows the latest choice.

Other decisions: the stdlib adapter answers a question from the records only (no `llm.ask` on any answer path, tested by an AST scan); `view_page` is the app's own copy of J2's function; the recorder no longer accepts a git repository as `--source`.

## Edits outside lane B's table (each small, all for the settings above or the library fix)

`engine/spec.py` (field, task key), `orchestrator/models.py` (`TaskSettings` key), `engine/host/inbox.py` (kind `setting`), `orchestrator/tasks.py` (`send_setting`), `orchestrator/wiring.py` (the `send_setting` slot, beside lane C's `agent_chat`), `engine/api/ctx.py` (`build_ctx`: library folder and pending choice), `tests/engine/test_engine_spec.py` and `tests/contracts/test_contract_settings.py` (the new field and the eight keys).

## Measured

`tests/engine` 2223 passed, 11 skipped; `tests/orchestrator` 1573 passed, 1 skipped; `tests/contracts` and `tests/integration/test_agent_ask_e2e.py` 147 passed. `scripts/record_api_shapes.py --source <extraction> --check`: up to date. New tests: `test_engine_inbox_setting.py` (11, three of them whole host runs), `tests/orchestrator/test_task_setting.py` (8), 77 in the views (30), scope (4), commands (28), settings (4), registry (8) and project (3) tests (the report row proved on runs the host made, with `project.json` as the agent tab).

## Left, and for others

- **Lane G.** `docs/ENVIRONMENT.md` needs the row `| `J2_DECIDE_FOR_ME` | `decide_for_me` | `0` | no | yes | the team answers its own questions with the suggested option and keeps going (the Simple view's Decide for me); `1` turns it on |`; `tests/test_docs.py` is red until it is there. `tests/test_traceability.py` and `scripts/build_traceability.py` still say 30 endpoints; the real count is 41, and the committed `TRACEABILITY.md` and `traceability.json` must be regenerated. The task keys are eight, not seven (D18, S1-contracts-03 text).
- **Lane E3.** The fake backend must serve `/api/record`, `/doc/<name>`, `/view`, `POST /api/settings` (J2's shapes are in the golden) and `next_run`. The page's list (33 exact names, 5 prefixes) equals the engine's table.
- The golden pins `plan_map` as `{found}` and `changes` as `{changes}` only: the recorded scenario has realization off and no change plan. J2's own `plan_map_view` block and `test_plan_map_of_a_run_with_a_plan...` carry the richer shape.
- Seen, not from this sync: the library's record gate (log mode) refuses the project output's condition and rubric ids (`PJ1`, `PJ-1`); strict mode would reject `conditions.json` and `audits.json` of a project run.
