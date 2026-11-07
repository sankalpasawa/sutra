# QA dept-run: two reported bugs (found on commit 2ae63d11)

Branch `feat/sutra-pro-qa-dept-run`. Both bugs were reproduced first (as a failing test), traced to the root cause and fixed with a
small local change. The J2 engine files were not touched.

## Bug 1 (P1): the engine's prompts leave with no egress audit row, and the Welcome card promises a scrub

**Root cause.** `connectors/factory.py build_router` sets `router.egress = Egress(<data>/connectors/egress.jsonl)` for the app's own router.
The engine process builds a second Router through `connectors/engine_port.py port_from_config` and never did, so
`Router._ask` (the engine's `complete()` path, `router.py` line 566) skipped its observe branch: no row, for any prompt of any team run.
The text itself goes out unchanged on that path by design: D109 says J2's prompts are observed, never edited (the prompt goldens pin them).

**Fix.**
- `engine_port.py`: a live port (not stub-only) gets `Egress(Path(spec.data_dir) / "connectors" / "egress.jsonl")`. `spec.data_dir` is the
  app data folder (the host passes `paths.data_dir`), so the engine process and the app append to the same file. A stub-only port starts
  no process and writes no row, as in the factory.
- `ui/static/js/welcome.js`: the card said "Anything shaped like a key, token or password is removed before a message leaves". That is true for
  chat only. It now says: removed from a chat message; a team's own prompts go out as written, so keep keys out of a brief; Sutra only notes,
  without the text, that one was seen. (The promise and the behaviour had to agree; scrubbing the team prompts is not allowed by D109.)
- Design text: `docs/design/absorb-old-sutra.md` 2.4 says the engine's Router gets the same `Egress`.

**Tests (fail before, pass after).**
- `tests/connectors/test_engine_port.py::test_a_live_engine_port_writes_an_observe_row_and_the_prompt_stays_byte_identical`: a key and a
  `ghp_` token in a prompt reach the fake claude stdin byte for byte, no `[redacted` marker, and exactly one `observe` row with
  `{"openai-key": 1, "github-token": 1}`; the row file does not contain the key.
- `tests/connectors/test_engine_port.py::test_a_stub_only_engine_port_writes_no_egress_file`.
- `tests/ui/js/welcome.test.js`: the copy names chat only and says a team's prompts go out as written.

**Not fixed, on purpose (recorded here).**
- The planted secret is still stored in clear in the run folder (`task.json`, `chat.jsonl`, `events.jsonl`, `summary.json`, `calls.jsonl`,
  `report.*`) and in the team's `memory/playbooks.jsonl` (`brief`, `sutra_app/engine/j2.py` line 9528: `self.request[:300]`). Those files are
  written by J2's engine code, which is frozen, and they sit in the owner's own data folder. A real scrub of a brief before it is stored or sent
  is a design decision (it reverses D109's "observe only for J2") and needs the owner: not taken here.
- The "replace" mode for team prompts stays unused for the same reason. With the audit row, the owner can now see (counts only) that a
  key-shaped string was in a team prompt.

## Bug 2 (P2): "+ New run" shows a blank page but the next brief continues the old run

**Root cause.** `DeptCommands.reset` (engine) stops a waiting team and writes `page.json.since_run`; that marker only makes
`ctx.current_ref` hide the old run from the start page. `TaskService._follow_up` (the path of `POST /api/say` and of a line in the team's
chat) never looked at it: it seeded the new task from the department's latest run folder, set `parent_task_id` to the latest task, and used a
question left open by the reset task as framing. So the engine rehydrated the old run ("Continuing from run ...", the brief judged as a
"Requester change", the old site and conversation on the page). `POST /api/tasks` was not affected (`create` never seeds).

**Fix.** `orchestrator/tasks.py`: `_follow_up` reads the marker (`_reset_marker`, a tolerant reader of `page.json`, the file the engine
writes, located with the engine's own `DataPaths`). When the run it would continue is at or before the marker (the same `run_id <= since_run`
test as `ctx.current_ref`), the new task has no `seed_from`, no parent task and no framing from the old question; the question is still marked
answered by the new brief (the owner moved on). A run made after the reset is continued again. A missing, torn or odd page file changes nothing.
History is untouched (tasks, run folders, the team chat). Design text: `docs/design/engine.md` F9 and `docs/design/orchestrator.md` (reset paragraph).

**Tests (fail before, pass after), all in `tests/orchestrator/test_tasks.py`.**
- `test_a_brief_written_after_a_reset_starts_a_fresh_run_not_a_change_request` (row and `task.json`: seed_from and parent_run_id are None, old run folder kept)
- `test_the_engines_own_reset_command_leaves_the_marker_this_service_reads` (real `DeptCommands.reset` then `DeptCommands.say` over the real service)
- `test_a_reset_by_the_chat_path_starts_fresh_too`
- `test_a_question_left_open_by_a_reset_is_closed_but_not_carried_into_the_fresh_run`
- guards that pass before and after: `test_the_reset_marker_covers_only_the_runs_before_it`, `test_a_page_file_without_a_usable_marker_changes_nothing` (5 shapes).

## Commands run

- `node --test tests/ui/js/*.test.js`: 966 tests, 964 pass, 0 fail (2 skipped).
- `scripts/py -m pytest tests/library tests/connectors tests/orchestrator tests/engine/test_engine_api_commands.py tests/engine/test_engine_api_scope.py tests/test_docs.py tests/test_traceability.py tests/test_ownership.py tests/test_layout.py -q -p no:warnings`: 5337 passed, 10 skipped.
- `tests/ui tests/ops`: 1159 passed, 211 skipped, 1 failed: `tests/ops/test_logsetup.py::test_the_access_log_loses_its_query_string`. It passes alone (12 passed) and fails the same way on the untouched base commit when run after `tests/ui` (order dependence in logging state), so it is not from this change.
- Order dependence worth knowing: `tests/library/test_lib_records.py::test_all_does_not_freeze_the_registry_and_freeze_closes_it` fails when `tests/orchestrator` runs before `tests/library` in one pytest process (also on the base commit); list `tests/library` first.
