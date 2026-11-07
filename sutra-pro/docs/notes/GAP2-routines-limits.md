# GAP2-routines-limits as built: recurring work, a monthly spending limit, a plan-window guard, quiet hours and an hourly cap

Four verified gaps of the second old-Sutra absorb review (package key `routines-limits`), built on branch `feat/sutra-pro-gap2-routines-limits` from
`3b86117f`. Nothing is pushed. No J2 file, prompt, route or golden is touched (`engine/j2*.py`, `engine/llm.py`, `engine/port.py`, `ui/pages/j2_ui.html`
are as they were). The team page is not changed at all: the Recurring list is a Settings group on Home, not a rider in `node_panel.js` (see Decisions).

Built:
1. **Recurring work**: a team's standing task on a schedule, an in-process tick, ONE catch-up run after an absence, an honest history, a pause after three
   crashes in a row.
2. **A monthly spending limit**: a line from 80 percent, new tasks wait at 100 percent, raising the limit starts them.
3. **A plan-window guard** (one package with 2, one start gate): warn from 70 percent, hold new runs from 80 percent when the owner switched it on, one
   Continue until the window resets, fail open.
4. **Quiet hours and an hourly cap** for what the app pushes at the owner (desktop notices): during quiet hours nothing is pushed and the count stays; a
   notice that a team FINISHED also obeys a rolling-hour cap.

## What the owner sees

- **Settings, Recurring work** (rail: "Recurring work"). A row per standing task: the team, its words, "Every weekday at 9:00 AM (local)", On or Paused (and why),
  "Next: tomorrow 9:00 AM", the last run in words ("Wed 4 Nov, 9:00 AM: started on schedule, done" / "... skipped, the team is waiting for your answer" / "...
  started as a catch-up (2 earlier times folded in), working"), a note when only a manual run ever happened ("it has not fired on its own yet: a run you
  started by hand does not prove the schedule works"), and Run now, Pause or Switch on, History (five runs), Remove (asks twice). Under the rows an add
  form: team, how often (hour, day, weekday, week; nothing below an hour is offered), the time in the owner's local time, the words. A run is an ordinary
  task titled "... (scheduled)" and a system note in the team's chat says it was scheduled and why it started (late, folded).
- **Settings, Limits** (rail: "Limits"). The monthly limit (a field; empty or 0 means none; "$10", "12.50", "$1,250" read), "About $8.20 of your $10 monthly
  limit" with a meter, one honest sentence that the dollars are an estimate at Claude's list price, known dollars only, and that Codex calls carry no
  dollar figure so on a subscription the real limit is the plan's quota (the number of calls this month without a dollar figure is said out loud). The
  plan-window guard: a switch (default off), what the windows say ("Claude weekly window is at 83%, resets Fri 09:00"), and Continue only while work is held.
- **The Needs strip** (Home) gains one line each when the monthly limit is at 80 percent or more and when a plan window is at 70 percent or more; with the guard
  on and a window at 80 percent or more the line says "New team runs wait." and carries Continue. These lines are not counted on the badge, the strip's count
  or the tab title (they are a state, not a question).
- **Settings, Notifications** (rail: "Notifications"). Quiet hours (two times, the owner's local time, wraps midnight; "No quiet hours") and the cap on
  finished-work notices per hour (default 3, 0 means never unasked, at most 10).
- **A held task** stays queued and its waiting detail reads "waiting: this month's spending limit is used up; raise it to continue (about $10.20 of $10)" or
  "waiting: Claude weekly window is at 83%, resets Fri 09:00 (press Continue to run anyway)". It starts by itself when the reason ends: the limit is
  raised or cleared, Continue is pressed, the month turns, the window resets (the scheduler's 30-second tick looks for queued work and calls `start_ready`).
- **Desktop notices.** During quiet hours none is sent (the count in the tab title, the strip and the pill stays). A question, an approval and a problem
  obey quiet hours only. A new kind, "Web finished "Menu"", is sent for finished work in the Heads up lane's finished rows, only inside the hourly cap, only
  outside quiet hours, never counted in the title. A notice that fell due while quiet or over the cap is settled silently: no catch-up notice when quiet ends.

## Where

Python (all under `sutra_app/`):
- `orchestrator/schedule.py` (new, pure): the closed `Schedule` (hour, day, weekdays, week; a sub-hourly word or a free cron line is a 422 with the sentence
  "A schedule runs at most once an hour: choose hour, day, weekdays or week."), `next_due`, `latest_due`, `owed` (the latest due time since a cursor and how many
  were folded in, capped at 2000), `human` (always says local). Wall-clock times for day, weekdays and week (a time that does not exist runs just after the gap, a
  time that happens twice runs on its first pass: once per local day); the hourly preset keeps its minute on the real clock.
- `orchestrator/recurring.py` (new): `Recurring` (store, service, ticker in one class), `RecurringOut`, `RunOut`. A due time is dealt with exactly once: the row of
  `recurring_runs` is UNIQUE on (recurring_id, due_at) and is written in the same transaction as the task and the new cursor (`recurring.cursor_at`), so a restart,
  a second tick or a stale cursor cannot start a slot twice. What a due time becomes: a task through `TaskService.create_scheduled` (then `start_ready`, so the
  caps, one live task per team, the spending limit and the guard all apply unchanged); or a skip row with the reason (still working, waiting for you, work already
  waiting to start); or, after three crashes in a row, a pause with a reason (and a note in the team's chat). A run's outcome is never stored: it is read by joining
  `tasks.status` (`done` and `done_with_open_items` are never both called success). The first tick is awaited at app start (the catch-up), then one every 30 s.
- `orchestrator/limits.py` (new): `Limits` (the owner's choices in `<data>/limits.json`, mode 0600, atomic, never raises on a bad file; the two readings; the
  start gate), `spend_status`, `guard_reading`, `LimitsStore`. UTC month like the console; stub rows left out; a Continue is stored with its window's reset time.
- `orchestrator/api/recurring.py`, `orchestrator/api/limits.py` (new routers) and `ops/attention_api.py` (new router).
- `ops/attention_prefs.py` (new): the old app's pure rules to the letter (zero-padded HH:MM, start == end refused, inclusive start, exclusive end, wraps midnight,
  a rate of 0 to 10 where booleans are junk), `<data>/attention.json` mode 0600, read never raises and degrades toward speaking.

Routes (reads need no token; every write depends on `require_token`, D81):

    GET    /api/recurring                  PUT /api/recurring/{id}   {text?, schedule?, enabled?}
    POST   /api/recurring                  DELETE /api/recurring/{id}
           {dept_id, text, schedule}       POST /api/recurring/{id}/run          GET /api/recurring/{id}/runs?limit=
    GET    /api/limits                     PUT /api/limits {monthly_usd?: number|null, guard_enabled?: bool}      POST /api/limits/continue
    GET    /api/ops/attention              PUT /api/ops/attention {quiet_hours?: {start, end}|null, nudges_per_hour?: int}

UI (all under `sutra_app/ui/`): `static/js/limits_view.js`, `static/js/recurring_view.js` (pure string modules, one global each, every wire word escaped, the
checks run before any request); `static/js/chat_attention.js` (additive: `windowActive`, `cleanQuiet`, `nudgeAllowed`, `plan()` takes `quiet`,
`nudgesPerHour`, `history`, `itemsOf(..., {finished: true})`, `create({prefs})`); `static/js/home.js` (the controller block at the end of the Settings section,
`fetchLimits`, the strip line, the prefs handed to `ChatAttention`); `pages/home.html` (three paint targets, three rail entries, two script tags);
`static/css/sutra-shell.css` (one block at the end, J2's tokens only; the contrast test passes).

## Riders in shared files (kept small and local, for the merge)

- `orchestrator/schema.py`: `DDL_V3_RECURRING` (tables `recurring`, `recurring_runs`), appended to `MIGRATIONS`, and the two names in `TABLES`. **Merge note:
  `rules-notes` also appends a migration (`owner_notes`).** Order them (`MIGRATIONS = (DDL_V1, _v2, <one>, <the other>)`), `SCHEMA_VERSION` follows `len()`.
  The tests that pinned the version number now read `SCHEMA_VERSION` instead (`tests/orchestrator/test_schema.py`, `test_startup.py`, `tests/ops/test_api_ops.py`,
  `test_backup.py`, `test_doctor.py`, `tests/e2e/test_cli_boot.py`), so a merge only has to keep the constant.
- `orchestrator/tasks.py`: `TaskService.create_scheduled`, `TaskService.post_note` (one system note in a team's chat), the attribute `start_gate` and two lines in
  `_prepare_next` (`if not waiting and self.start_gate is not None: waiting = self.start_gate(tx.conn, tx.now(), row.dept_id)`).
- `orchestrator/wiring.py`: `AppServices.recurring` and `.limits`, built in `build_services` (`tasks.start_gate = limits.gate`), `recurring.start()` after the
  reconcile and before `start_ready`, `recurring.stop()` first in `stop_services`.
- `main.py`: `recurring`, `limits` and `attention_api` in `ROUTERS` (an import line and the tuple).
- `ops/backup.py`: `limits.json` and `attention.json` join `_ROOT_FILES` (the owner's own choices are in the backup); `tests/ops/test_backup.py` lists them.
- Tests that pinned the settings rail (`tests/ui/test_home.py`), the write routes of the fake backend (`tests/ui/test_fake_backend.py`: seven new writes) and the
  route world (`tests/contracts/test_contract_world.py`: three more routers). `tests/ui/fake_backend.py` serves the new routes and two control routes
  (`/__fake/limits`, `/__fake/recurring`).

## Tests

- `tests/orchestrator/test_schedule.py` 20 (presets, strictly-after, zone, the hourly floor as a 422 sentence, a long absence owes one run and counts the rest,
  both daylight-saving days in New York: skipped with no tz database).
- `tests/orchestrator/test_recurring.py` 27 on `TEnv` (one due slot makes exactly one task with the stored words; 3 days down then start makes ONE task and a row
  that says 2 slots were folded in; a team waiting for you, working, or with work waiting gives a skip row with its reason and no task; two restarts and a stale
  cursor add no second row for the same due time; 3 crashes in a row set enabled=0 with a reason and a note in the team's chat; 2 crashes and a success do not;
  switching on again starts a new streak; run now is `manual`, never moves the cursor and says "has not fired on its own yet"; a busy team refuses a manual run;
  a task the team cannot take is skipped once with the reason; one broken schedule does not keep the others from running; the real lifespan makes the catch-up
  at start and ends the loop at stop; the tick starts work a limit was holding once the limit lifts).
- `tests/orchestrator/test_api_recurring.py` 13, `test_api_limits.py` 17, `test_limits.py` 36 (levels and their edges, the words, only known dollars of the UTC
  month, Codex rows with no dollar and stub rows not counted, a queued task waits with the reason and starts when the limit is raised, a manual start is held, a
  running task is never touched, the new month releases, a broken gate fails open, the guard at 69/70/79/80/100, hold only when enabled, Continue until the reset,
  a stale snapshot holds nothing, a pinned team is judged by its own provider, offline is not gated, the file).
- `tests/ops/test_attention_prefs.py` 55 (the shared case table, junk refused, start == end refused, clear deletes the key, 0 stays 0, restart in a subprocess,
  the routes).
- `tests/orchestrator/test_schema.py` +2 (a database at version 2 gets the tables and keeps its rows; the unique due time and the cascade).
- `tests/ui/js/attention_prefs.test.js` 16 (the SAME case table `tests/fixtures/quiet_hours_cases.json`, copied unchanged from the old app, on Dates and minutes;
  the rolling hour; a question at 02:00 inside the window pushes nothing and the title still counts; finished notices obey the cap, a reload does not refund it,
  an unknown rate suppresses), `limits_view.test.js` 17, `recurring_view.test.js` 16.
- `tests/ui/test_home_limits.py` 1 + 7 browser (`SUTRA_BROWSER=1`): the strip line, Continue with the token, the limit, a refused amount sends nothing, the
  guard switch, quiet hours and the cap, the whole life of a standing task.

## Decisions

- **No scheduler outside the app.** The browser is the window (D12), so the server runs with no page open; an in-process tick covers "the owner is away", and the
  one uncovered case (the app quit, the machine asleep) is the single catch-up at the next start, which is what launchd's coalescing did. No launchd, no cron file.
- **Presets, not cron.** Four cadences; the old single-minute rule becomes structural. A catch-up is a run started more than 5 minutes after its due time or one that
  folds earlier due times; it is labelled `catch_up`, otherwise `schedule`.
- **A busy team skips, it does not queue.** A due time with the team working, waiting for the owner or with work already waiting writes a skip row. A manual Run now
  on a busy team is refused (409) instead, because the owner's own click deserves an answer, not a quiet skip.
- **Per-fire ceiling.** A scheduled run has the engine's own per-run budget (Settings, Engine: 100 work credits, cap 200 by default), the old app's "an unattended
  run with no ceiling is how a schedule becomes a bill"; the monthly limit is the second guard. No new budget field.
- **Limits gate starts only.** The engine process is J2's, so a run in flight cannot be paused (the old app paused before the next step): this is weaker on purpose,
  and the Settings words say a running task finishes. A held task is a waiting reason, not an error.
- **Dollars are known dollars.** UTC month like the console, stub rows left out, Codex rows (no dollar) not counted and said so; the words say "about".
- **The guard fails open** and is off by default. Pinned team: only the pinned provider's windows count for that team. A window with no reset time is trusted
  for 6 hours after it was seen. A Continue with no reset time lasts an hour. Offline (stub) is never gated.
- **Quiet hours: no catch-up notice when quiet ends** (not in the old app; recorded here as asked). The count was never hidden, so nothing is lost.
- **Finished notices are new in Pro** and are the only thing the hourly cap governs (questions, approvals and crashes were already pushed by the attention
  package and obey quiet hours only). They are never counted in the title and never offered the permission prompt.
- **Routes**: one `/api/limits` for both guards (not `/api/ops/spend` and `/api/guard`), `/api/ops/attention` for the owner's two notification choices, so the
  page asks two questions.

## Not done, and why

- **A Recurring list inside the team panel (`node_panel.js`)**: the Settings group lists every team's schedules in one place (the old app's Routines page);
  `node_panel.js` is a file other packages edit, and a Details-tab block belongs to `rules-notes`.
- **A launcher notification while no tab is open** (G26's other half) and **a macOS login item that starts the app at a schedule**: the app has to be running;
  the catch-up covers the time it was not.
- **A per-schedule budget or model choice**, **a monthly or every-N-hours cadence**, **a calendar of firings**: not in the old evidence.
- **Pausing a run already in flight at the limit**: the engine process is J2's.
- **Editing a standing task in the page** (its words, time or team): `PUT /api/recurring/{id}` takes `{text?, schedule?, enabled?}` and works, but the row has no
  edit control; the owner removes it and adds it again (its history goes with it). A schedule paused because its team left the chart cannot be re-pointed to
  another team: the route has no `dept_id` either. Found by QA (docs/notes/QA-recurring-limits.md).
- **docs**: `docs/design/gaps.md` G23 should now say the dollar guard exists and is separate from the calls-per-hour idea; absorb rows 35 and 36 and D107's LATER
  triggers are answered; the docs package records the routes. Nothing under `docs/design` or `docs/DECISIONS.md` is edited here.

## Known limits

- A schedule's `next_due_at` is the next due time after "now"; while the app was away and a catch-up is owed it reads the next ordinary slot (the catch-up starts
  within 30 seconds of the app opening).
- The hourly preset keeps its minute on the real clock, which differs from a wall clock only in a zone whose daylight-saving change is not a whole hour.
- The browser suites of `test_home.py` (48 of its tests) and `test_dept_page.py` (2) already fail on the base commit (the fake backend has no
  `GET /api/chats/{sid}/providers`); the set of failing tests is the same with this branch (compared in a worktree at `3b86117f`), and
  `test_the_first_graph_after_a_turn_takes_the_right_pane_and_the_task_card_links_to_the_team` flakes at about the same rate on both (1 in 14).
  `tests/ops/test_logsetup.py::test_the_access_log_loses_its_query_string` fails when `tests/orchestrator` runs before `tests/ops` in one session, also on the base.
