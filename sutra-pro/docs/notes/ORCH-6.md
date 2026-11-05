# ORCH-6 as built: tasks, run launcher and watcher, projector, fake engine, task routes

Built: `orchestrator/tasks.py` (`TaskRow`, `TaskStore`, `TaskGraph`, `TaskService`), `runs.py` (`child_environment`, `ProcessLauncher`, `RunWatcher`,
`reconcile`, `STOP_GRACE_S` 8 and `TERM_GRACE_S` 4), `projector.py` (`Projector.drain/apply/mark_ended/flag_silent`), `api/tasks.py` (6 routes),
`testing/fake_engine.py` (`FakeLauncher`, `play`, `main`). Tests: `test_tasks.py` (holds `TEnv`, which the other three import), `test_projector.py`,
`test_projector_fnodes.py` (replays `tests/engine/golden/run_events.jsonl`), `test_api_tasks.py`: 130 tests, about 8 s.

## Deviations from the specification
- `FakeLauncher.start` returns distinct fake pids from 2,000,000,000 (not 0): the crash rules need to tell runs apart. `alive(pid)` is true until the script ends or `kill`.
- A follow-up's `seed_from` has no column; it lives in `tasks.settings_json` under the reserved key `_seed_from` (every reader drops underscore keys).
- `RunLauncher` gained optional members the watcher and reconcile read with a fallback: `exit_code(pid)`, `command_of(pid)`; `stop` takes optional `stop_grace`/`term_grace`.
- `TaskService` extras: `start`, `kick`, `bind_loop`, `shutdown`, `_stop`; `TaskStore` is the read/write layer (`insert` takes a Checked `work_task`, the L8 write-path scan), `TaskGraph` (`ensure_step`, not `upsert`: same scan) owns the task step node and `task.updated`.
- `RunWatcher` unwatch/close are graceful (the current database look finishes); a hard cancel mid-thread crashed SQLite in tests.
- `mark_ended(task_id, status, outcome, code=None)` is the one server-made terminal event (crash, stop, shutdown); `code` is not stored (no column).

## Decisions
- A line that is an EARLIER step of an atom already moved on (a replayed file) is a silent no-op; a line that contradicts a final state is refused and noted.
- Notes (skipped line, unknown field, refused atom, failed event) go to Identity's own function session as `note`, idempotent by `src_ref`; each event runs in a savepoint.
- `waiting` without `wait_on` gets `identity`; `waiting_on_you` always `you`; other states clear it. Node tokens are kept when an event carries none.
- Step nodes are created by `node`, `step`, `atom` and `usage` lines alike (the publisher sends `node` before `step`); `team:<role>` refs the library cannot hold are skipped with a note.
- A step edge: `depends_on` from the reader (label reads/revises, rework written last); targets that do not exist yet become placeholder nodes.
- Run end: steps `running|waiting` become `done_unchecked` (done) or `left_open`; `idle` steps `not_made` unless done; functions idle; open function atoms abandoned through `AtomStore.apply_transition`.
- A `done`-style card goes to `cs_org` for every end; a crash also posts "Something went wrong. Try again." (kind error) in the department chat.
- Capacity: `blocked` -> `queued`/`cancelled` is settled in the same transaction that picks work; a department with an unfinished queued task answers 409 busy instead of piling up follow-ups.
- Crash outcome: "the team process stopped unexpectedly", exit code when known, redacted stderr tail (2 KB). Silence over 30 s only flags the step node ("no signal for N s").
- `upstream.files` = top-level regular files of a finished dependency's run folder, minus engine plumbing. Offline setting -> `connector: "stub"` in `task.json`.
- A line over the 2 MB chunk grows the chunk (up to 64 MB, then skipped with a note); `Drained.more` is true only when the read stopped short of the end of the file.

## Known limits and follow-ups
- ORCH-8: set `Services.tasks/projector/watcher/launcher`, `resolve_run`, `deliver_to_department`, `stop_live` from `TaskService`; `service.bind_loop(loop)`; `watcher.after_drain = service.start_ready`;
  run `reconcile(...)` then `start_ready()`; call `service.shutdown()` in the lifespan; `Services.department = departments.row`; `TaskStore.insert` passes the write-path scan with no allowlist line.
- ORCH-7: `create(tx, ..., request='req-<n>', change_id=...)` then `await start_ready()`; the follow-up path is `deliver_to_department`.
- `usage` lines whose `how`/`purpose`/`provider` the connectors' `UsageIn` refuses are noted and not stored (money data is not guessed).
- The real engine-process path is exercised with the fake engine only; no live CLI run.

## Mutation check
21 hand-made mutants (silent threshold, TERM grace, SIGTERM step, silent/recent rule, pid identity, caps, one live per department, folder and file modes, override rules,
retry seed, waiting_user, wait_on fallback, replay rule, rework order, idle settle, crash message, speaks_to count, shorter file): 19 killed first; `SUTRA_TOKEN`
is guarded twice (the secret-name rule too), so that mutant is equivalent; the replay-of-an-earlier-try survivor became a test. No second round.
