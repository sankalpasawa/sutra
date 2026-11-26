# Implementation: Files and earlier context stay with a project (D451)
_Branch feat/project-files-context, base origin/main e59d3ea0 · nothing pushed, no PR, versions not bumped (0.9.0 is named only in the release note)_

## What was built (per plan step)
| Step | Result |
|---|---|
| T1 | failing tests first (red for the stated reasons: no module, no route, no column) |
| T2 | spike: `channel-spike.md` + 3 characterisation tests. Finding: a run's framing line reaches the five function agents, never a builder in a real run (`J2_SLIM`), and a long chat summarises it away. Decision: the project block goes through the host's `system_addendum` (`node_context.json["*"]`) |
| T3 | schema v10 (`project_files`, `tasks.input_files_json`), `ProjectFiles` |
| T4 | `project_context.py`: pure composition, budgets, whole or excerpts, receipt, signature |
| T5 | files on `/api/say`, `/api/tasks`, team chat messages; `run_inputs.py` (snapshot, copy to `inputs/`, context file); `hooks.py` `"*"` entry; retry keeps files; export ignores `inputs/` |
| T6 | chat path: stable block in the system text, excerpts in the message, `context.sig` and the Codex thread rule, 202 `context` receipt |
| T7 | routes in `api/project_context.py` (files, promote, attachments, instructions, memory, `/context` preview), body limit |
| T8 | `attach_bar.js` extracted from the composer; `TEAM_FILES` removed |
| T9 | `start_files.js`, port edits E30a-d (E25c amended), page regenerated with `port_j2_ui.py` |
| T10 | composer and Attention send team messages with files; the owner's line shows "Given to the team" |
| T11 | panel `project_context_view.js`, project menu entry |
| T12 | Create project: files after create, partial failure kept |
| T13/T14 | instructions and memory (`project_memory.py`), writers in `Projector._finish` and `ChatArchive.archive`, lazy seed |
| T15 | org chat files: planner digest, each task given the files |
| T16 | D451 (+ decisions.json), release note 0.9.0, ENVIRONMENT row, troubleshooting |
| T17 | mutation proof (below), sharded suite |

## Deviations from the architecture
1. Project block goes to `node_context.json["*"]` (system addendum), not the framing (T2 outcome, the architecture's own fallback). The framing carries a pointer line only.
2. New modules not in the plan: `run_inputs.py` (materialiser, snapshot, context file; kept out of the pure `project_context.py`) and `project_delivery.py` (shared read of rows for chat and preview).
3. Stale save is 409 code `busy` with `details.stale` (a new error code would change the pinned list in `test_records`).
4. Contract tests: `tests/contracts/test_contract_world.py` mounts the new router; `tests/engine/test_engine_spec.py` lists `inputs`; `chat_composer`/`front_door`/`project_pick`/`chat_ask` tests that encoded the old refusal or exact menu were replaced (4 composer tests) or amended.
5. E25c was amended (not only E30 added) because port edits may not anchor on each other's output.
6. A file sent with an answer to a waiting team is refused with a sentence (OQ-6: not silently dropped).

## Not done / not exercised
- The chip "3 files · memory on" under the start box and the "Using N files" line (`usingLine` exists and is tested; not placed in a page).
- No browser or desktop run: page behaviour is proven by node tests with stand-ins, source pins, and the regenerated page; `tests/e2e/test_browser_chat_composer.py` was edited to follow the new behaviour and not run (opt-in). The beta checklist and a real builder obeying the block (PRD 9) are the owner's.
- Files on `POST /api/projects` (deferred by decision).

## Tests added
Python: `tests/orchestrator/` test_project_files (17), test_project_context_compose (17), test_project_memory (23), test_task_inputs (14), test_chat_project_files (11), test_api_project_context (13), test_runner_files (4), test_project_context_golden (2 guards); `tests/engine/` test_say_files (18), test_project_context_channel (6), test_run_export_inputs (2); `tests/connectors/test_chat_context_sig.py` (6); a v9 to v10 migration test in test_schema. JS (node): attach_bar (8), start_files (9), project_context_view (15), plus new tests in chat_composer, chat_view, create_project, front_door, project_pick. Fixture: `tests/fixtures/project_context/chat_system.txt` (written by the pre-change code).

## Commands run and results (sharded in parallel, no real model, no SUTRA_LIVE/SLOW)
| Shard | Result |
|---|---|
| tests/orchestrator (3 shards) | 1336 passed; 817 passed 1 failed; 986 passed 1 failed. The 2 failures (test_team_admin version pin, test_api_steer node_context equality) were mine, fixed (33 passed on rerun) |
| tests/engine | 3330 passed, 18 skipped |
| tests/connectors + tests/contracts | 2233 passed, 1 failed, 5 skipped |
| tests/library ops integration release fakes e2e top-level | 3907 passed, 1 failed, 43 skipped |
| tests/ui (python, includes node suite) | rerun after the last edits: 1104 passed, 2 failed, 327 skipped |
| node --test tests/ui/js | 1749 tests, 1747 pass, 0 fail (2 skipped-by-design counted by node) |
Failures identical on origin/main e59d3ea0 (verified in a second worktree): `test_contract_route_table::test_every_path_the_view_scripts_call_is_served_by_some_router` (/api/appearance), `test_workflows_yaml::test_ci_is_named_ci...` (pull_request trigger), `test_fake_backend::test_the_pages_come_from_the_real_ui_router...` and `test_shared_css::test_each_page_links_its_own_sheet...` (avatars.css / avatars key).

## Mutation proof (T17)
33 single-line mutations of the code, each run against its covering tests: all 33 went red (the table is the list below, ids M01-M25, J01-J08): export forgets inputs, Codex ignores the signature, carry-over counts excerpts, bytes never released, release ignores chat lines, context file not written, host ignores `"*"`, run end / archive not remembered, say drops files, no scrub in chat, switch at 20,000 gone, stale save overwrites, memory keeps secrets, retry loses files, answer takes files silently, half-made inputs left, kill switch inert, hidden project writable, duplicate rule gone, planner not shown files, org tasks not given files, body limit, team route drops files, excerpts stored on the line; JS: team send ignores files, chip does not hold a send, words not put back, create box forgets files, panel text differs, stale not said, front door sends no files, bar accepts a refused type. Two were first green (M20 duplicate pre-check, M21 planner digest also arrived via the resumed request): two assertions were added and both then went red.
Against pre-change code (origin/main source, new tests copied in): every new test file errors or fails except the by-design guards: test_project_context_golden (2), the 4 characterisation/guard tests in test_project_context_channel, 1 in test_run_export_inputs.

## Known limits and follow-ups
Files in an answer to a team's question and on `POST /api/projects`; the start-box chip and "Using N files" line; real-browser and beta checks; deleting a chat does not delete its stored files; the scratch worktree used for the base comparison was removed.
