# Plan: A new run in a team starts clean unless the chat agent decides it continues an earlier run
Branch: `sut-26-context` (exists locally, no commits; fast-forward it to `origin/main`; it is checked out in the worktree `~/Downloads/sutra-sut26`, where the work is done)   |   Spec: `spec.md`   |   Design: `architecture.md`

Rules for every step: tests first where practical; one commit per step, message `SUT-26: D454 <plain sentence>`; the step's command must pass before committing (ignoring only tests listed in the T0 baseline file). Do not rely on line numbers in `sutra_app/engine/j2.py`; this plan touches no J2, engine host or page file. Commands run from `sutra-pro/`. Never run `scripts/live_smoke.py`; never touch `~/.sutra-pro`.

Size estimate (Impact/Effort):

| Step | Goal | Impact | Effort (changed lines) |
|---|---|---|---|
| T0 | sync, check numbers, baseline | prerequisite | 0 |
| T1 | prompts | FR-5, FR-4 rendering | ~50 |
| T2 | `ChatAgent.follows` | FR-1, NFR-1 | ~70 |
| T3 | `TaskService` decision point + existing tests | FR-1 to FR-15 core | ~180 |
| T4 | new service tests for the ACs | proof of AC-2 to AC-14 | ~170 |
| T5 | wiring + e2e | AC-8, AC-9, live path | ~90 |
| T6 | sweep other suites | keep green | small, unknown |
| T7 | records and design docs | FR-16 | ~40 |
| T8 | gate, line count, beta | done | 0 |

- [x] T0: Start from the newest `origin/main` that holds D452 and D453; record the tests already failing there
  - Files: none committed. Scratch file `<scratchpad>/sut26-baseline.txt`.
  - Change:
    1. `git fetch origin`; `git show origin/main:sutra-pro/docs/DECISIONS.md | grep -E "^## D45[23] "` must print both D452 and D453. If not, stop and tell the owner (the ticket says they merge first).
    2. `git switch sut-26-context && git merge --ff-only origin/main`. If the switch is refused because of local edits in other files, stop and ask; do not stash or discard someone else's work.
    3. Numbers still free: `git grep -n "^## D454 " $(git for-each-ref --format='%(refname)' refs/remotes/origin) -- sutra-pro/docs/DECISIONS.md` prints nothing. If D454 is taken, use the next free number everywhere this plan says D454 (and update spec/architecture text).
    4. Names this plan relies on still exist: `grep -n "def _follow_up\|def _deliver\|def _answer\|def _run_async\|def _reset_marker" sutra_app/orchestrator/tasks.py`, `grep -n "async def _stage\|async def node_plan" sutra_app/orchestrator/agent/agent.py`, `grep -n "self.request = last_user\|def _metrics" sutra_app/engine/j2.py` (J2 still takes its brief from the first owner line and writes summary.json in `_metrics`/`_save_report`). Any missing: stop and report.
    5. Baseline on unchanged main: `scripts/py -m pytest tests/orchestrator tests/e2e tests/engine/test_engine_paths.py tests/engine/test_engine_api_commands.py tests/engine/test_engine_host.py tests/engine/test_engine_project_followup.py tests/engine/test_engine_rehydrate.py tests/engine/test_rehydrate_any_output.py tests/integration tests/contracts tests/test_diagram_decisions.py tests/test_ownership.py -q 2>&1 | tee <scratchpad>/sut26-baseline-run.txt`, then `grep -E "^(FAILED|ERROR)" <scratchpad>/sut26-baseline-run.txt > <scratchpad>/sut26-baseline.txt`. These are the "already failing on main" tests for every later step.
  - Tests: none.
  - Done when: branch == `origin/main`, D454 free, names found, baseline file written.
  - Covers: R-5.

- [x] T1: The decision prompt and the FR-5 sentence
  - Files: `sutra_app/orchestrator/agent/templates/follows.md` (new), `templates/decide.md`, `templates/assign.md`, `sutra_app/orchestrator/agent/prompts.py`, `tests/orchestrator/test_chat_agent.py`.
  - Tests first (in `test_chat_agent.py`, prompts section):
    - extend `test_the_templates_say_what_the_design_says`: for `decide`, `assign`, `follows` the template contains "when not sure, leave it empty" (AC-7); `follows` contains `{runs}` and no "reply" (same check as decide/assign).
    - new `test_run_lines_lists_each_run_and_clips`: 2 runs → two blocks in order with id, title, status, "brief:", "open question:" (`-` when empty); a 3,000-char brief and question are clipped to 1,000 each; `run_lines([]) == "(none)"`.
    - `test_each_template_file_holds_exactly_its_placeholders` covers `follows` once it is in `TEMPLATES`.
  - Change: write `follows.md` as in architecture.md "Interfaces"; add the FR-5 sentence in `decide.md` and `assign.md` (replace "`follows` only with a task id listed for that team" with the longer sentence); `TEMPLATES += ("follows",)`, `PLACEHOLDERS["follows"] = {"dept", "runs", "message", "schema"}`; `run_lines(runs, *, width=1000)` next to `pending_lines`, using `clip` and collapsing whitespace as `conversation` does; add it to `__all__` and the module docstring list.
  - Done when: `scripts/py -m pytest tests/orchestrator/test_chat_agent.py -q` passes.
  - Covers: FR-5, FR-4 (rendering), NFR-5, AC-7.

- [x] T2: `ChatAgent.follows`, one call
  - Files: `sutra_app/orchestrator/agent/agent.py`, `tests/orchestrator/test_chat_agent.py`.
  - Tests first (new section "follows", using `ScriptedConnector` and the file's existing env fixture):
    - reply `{"kind": "assignments", "assignments": [{ref a1, dept web, title, brief, follows "tsk_000000000001"}]}` → returns that id; exactly 1 call; `calls[0].step == "follows"`; the prompt holds the owner's words and each run's id, title, status, brief and question; `calls[0].context["atom_id"]` equals `overhead_atom_id("follows-web")`.
    - reply with `follows: null` → None.
    - reply `{"x": 1}` (bad output) → None and still exactly 1 call (no retry).
    - a `ConnectorFailure("unavailable")` scripted → raises (the service catches it; T4 proves the clean start).
  - Change: `_stage(..., attempts=None, context=None)`: `context = context if context is not None else call_context(request.message_id, request.node_id)`. Add `follows(...)` per architecture.md: render `follows` with `dept=dept_id`, `runs=prompts.run_lines(runs)`, `message=text`, `schema=_dump(REGISTRY.transport_schema("chat_turn", kind="assignments"))`; `build` returns `model.assignments[0].follows` with no violations; call `_stage("follows", "chat_turn", "assignments", prompt, schema, PlanRequest(text=text, message_id=0), _Budget(1), build, attempts=1, context=...)`; `except StageFailed: return None`. Docstring line in the module header ("follows(dept, text, runs) one call, D454").
  - Done when: `scripts/py -m pytest tests/orchestrator/test_chat_agent.py tests/orchestrator/test_node_plan.py -q` passes.
  - Covers: FR-1, FR-4, NFR-1, D-1.

- [x] T3: One decision point in `TaskService`; update the tests that encode the old rule
  - Files: `sutra_app/orchestrator/tasks.py`, `tests/orchestrator/test_tasks.py`.
  - Tests first, in `test_tasks.py`:
    - add a helper `pick(tenv, task_id_or_None)` that sets `tenv.service.follows_of` to an `async def` recording `(dept_id, text, runs)` into a list and returning the given id.
    - `:387` `test_no_live_task_makes_a_follow_up_that_continues_from_the_old_run`: call `pick(tenv, first)` first; assertions unchanged (done seed → `user_text` stays the owner's words, title unchanged).
    - `:403` rename to `test_a_run_without_a_folder_is_not_a_candidate`: `pick(tenv, second.id)` after deleting its folder → task is clean; the recorded `runs` hold `first` only.
    - `:444` and `:478`: `pick(tenv, <the run that should continue>)`; assert as today.
    - `:431`, `:455`, `:462`: no picker set or one set → still clean; add an assertion that the recorder saw no call (FR-13/FR-14: the reset leaves no candidate).
    - `:485` (owner ruling Q-10, replaces the rename): unchanged, the reset still closes its question; add that the agent was not asked.
    - `:519` `test_orphaned_question_framing`: `pick(tenv, task)`; framing unchanged text; `row.user_text == "Build a landing page for my cafe\n\nThe owner now writes: Green please"` (stopped seed → combined, FR-9); title is the first brief's title; the team chat line is "Green please" alone (FR-15); question marked answered.
  - Change (tasks.py), per architecture.md:
    - `self.follows_of = None` in `__init__` with a one-line comment (D454).
    - `CONTINUES` constant near `GOOD_END`/`BAD_END`.
    - `_open_questions(conn, sid, task_id)`; `_answer` uses it (same SQL as today, `tasks.py` `_answer`).
    - `_candidates(conn, dept_id, sid)`: tasks of the team with `run_id IS NOT NULL` and status in `GOOD_END + BAD_END`, `ORDER BY created_at DESC, rowid DESC`; skip a run without a folder or with `run_id <= marker` (same comparison as today); stop at 5; pair each with the text of its newest open question (`_open_questions(...)[-1]["text"]` or "").
    - `_pick_follows(dept_id, said)`: early returns listed in architecture.md "Interfaces"; builds `runs` as `(id, title, status, user_text, question)`; `try: return self._run_async(lambda: self.follows_of(dept_id, said, runs)) except Exception: log.info(...); return None`.
    - `_deliver`: `pick = None if answer_only or self._override_command(body) is not None else self._pick_follows(dept_id, said)` before `with self.db.tx()`; pass `pick=pick` to `_follow_up`.
    - `_follow_up`: drop the recency scan, `latest_in`, the any-task orphan query; `seed = next((r, q) for r, q in self._candidates(...) if r.id == pick)` or None; seed → `seed_run`, `parent_task_id = seed.id`, framing `clip(f"Earlier the team asked the owner: {q}", 20_000)` when `q`, `text = CONTINUES.format(brief=clip(seed.user_text, 20_000), words=body)` when `seed.status in BAD_END` else `body`; post `body` (unchanged code); after posting, mark every `_open_questions(conn, sid, seed.id)` answered. Rewrite its docstring (agent decides; D454 amends D21).
  - Done when: `scripts/py -m pytest tests/orchestrator/test_tasks.py tests/orchestrator/test_attempts.py tests/orchestrator/test_task_inputs.py tests/orchestrator/test_task_setting.py tests/orchestrator/test_run_spec_golden.py tests/orchestrator/test_project_context_golden.py tests/contracts -q` passes (goldens unchanged: NFR-7).
  - Covers: FR-1, FR-2, FR-3, FR-6, FR-7, FR-8, FR-9, FR-11, FR-13, FR-14, FR-15, NFR-7, NFR-8.

- [x] T4: Tests for the remaining acceptance criteria
  - Files: `tests/orchestrator/test_tasks.py` only.
  - Tests (each synthetic, scripted picker):

    | Test | AC |
    |---|---|
    | unrelated brief after a done run, picker returns None → no seed, parent, framing; after `start_ready`, `task.json` has `seed_from`/`parent_run_id` None and the run folder has no `upstream/` | AC-1 |
    | picker raises `ConnectorFailure("timeout")`, raises `RuntimeError`, returns a task id of another team, returns `"tsk_000000000999"` → clean, owner line stored, recorder saw exactly 1 call | AC-2 |
    | done run, no question, picker picks it → seed, parent, framing "", `user_text` == words | AC-3 |
    | R1 stopped with Q1, R2 stopped with Q2; pick R1 → framing has Q1 only; Q1 answered, Q2 open | AC-4 |
    | R1 stopped with Q1, R2 done; pick R2 (and, parametrized, pick None) → framing never has Q1; Q1 open | AC-5 |
    | 6 ended runs (one with a 3,000-char brief and question) → recorder's `runs` has the newest 5, newest first, with id, title, status, brief, own question; nothing from run files | AC-6 |
    | R1 stopped; R2 continues R1 (picked) and stops; R3 picks R2 → R3 `user_text` contains R1's brief text | AC-10 |
    | reset marker at R1 → no call, clean | AC-11 |
    | team with no task → no call, clean | AC-12 |
    | team waiting on the owner → answer delivered, no call | AC-13 |
    | picker that, while "in flight", creates a queued task of the team (`tenv.new(...)`) and returns R1 → `Busy`; no second follow-up row | AC-14 |
  - Change: none in `sutra_app/`.
  - Done when: `scripts/py -m pytest tests/orchestrator/test_tasks.py -q` passes.
  - Covers: AC-1 to AC-6, AC-10 to AC-14; NFR-1, NFR-2, NFR-5, NFR-8.

- [x] T5: Wire the agent into the app; end-to-end proof
  - Files: `sutra_app/orchestrator/wiring.py`, `tests/e2e/test_scenario_followup.py`, `tests/e2e/test_scenario_restart_stop.py`.
  - Tests first:
    - `test_scenario_followup.py` `chain_of_tasks` (:47): before `live.write(live.session_of("web"), FOLLOW_UP)` push `{"kind": "assignments", "assignments": [draft("a1", "web", follows=second)]}` onto `live.connector`. Existing assertions stand (`user_text == FOLLOW_UP`, `change_requests == [FOLLOW_UP]`, `tree_sha`).
    - `test_the_follow_up_run_holds_the_old_runs_files_and_the_old_folder_is_untouched` (:105): add `summary["brief"] == json.loads((old / "summary.json").read_text())["brief"]` (AC-9: seed brief recorded, words in `change_requests`, old folder byte-identical).
    - document chain (:142): push the pick of `first` before the write.
    - stopped run (:166): push the pick of `first`; take `tree_sha` of the old folder before the write; add: `task_row(second)["user_text"]` starts with the first brief and ends with the owner's words; the team chat's newest owner line is the owner's words alone; once `summary.json` exists in the new folder (`live.until`), its `brief` contains both texts; old `tree_sha` unchanged (AC-8, Stop).
    - `test_scenario_restart_stop.py:127`: push the pick of `task` before "Never mind the question, start again"; assertion on `answered_by` stands.
    - `test_closing_the_app_runs_the_ladder_on_a_waiting_team_and_the_next_start_finds_nothing_to_fix` (:149): after the restart, push the pick of the stopped task, write `ANSWER` in the team chat, assert the new task's `user_text` holds the first brief and `ANSWER`, and the old folder's `tree_sha` is unchanged (AC-8, app close).
  - Change: in `wiring.py`, right after `agent = ChatAgent(...)`: `tasks.follows_of = agent.follows` with a comment citing D454.
  - Done when: `scripts/py -m pytest tests/e2e/test_scenario_followup.py tests/e2e/test_scenario_restart_stop.py -q` passes.
  - Covers: AC-8, AC-9, FR-9, FR-10, FR-12, FR-15.

- [x] T6: Sweep the suites that send team-chat lines
  - Files: only tests that fail because a team-chat follow-up now starts clean where the test means a continuation (candidates from reading: `tests/e2e/test_dept_chats.py`, `tests/engine/test_engine_paths.py`, `tests/orchestrator/test_attempts.py`, `tests/orchestrator/test_task_inputs.py`, `tests/orchestrator/test_task_setting.py`, `tests/integration/test_offline_demo.py`).
  - Change: for each new failure (not in the T0 baseline), push a scripted pick or set `follows_of`, never weaken an assertion about clean starts. If a failure shows a behaviour the spec did not foresee, stop and report instead of editing.
  - Done when: `scripts/py -m pytest tests/orchestrator tests/e2e tests/engine/test_engine_paths.py tests/engine/test_engine_api_commands.py tests/engine/test_engine_host.py tests/engine/test_engine_project_followup.py tests/engine/test_engine_rehydrate.py tests/engine/test_rehydrate_any_output.py tests/integration tests/contracts -q` shows no failure outside the T0 baseline. No commit if nothing changed.
  - Covers: R-7.

- [x] T7: Records and design docs
  - Files: `docs/DECISIONS.md`, `docs/diagram/decisions.json`, `docs/design/orchestrator.md`.
  - Change:
    - `## D454 — A team-chat line continues an earlier run only when the chat agent says so; framing is that run's own question and its brief comes along (amends D21)` after D453, with Sources (SUT-26, `docs/ai/sut-26-context/`), Decided (architecture D-1 to D-5 in plain words), Why (the two observed cases, generic), Rejected (architecture A-1 to A-5), Diagram label.
    - `decisions.json`: `{"id": "D454", "label": "team chat: the chat agent decides whether a line continues an earlier run; else a clean run", "anchor": "<same anchor D21 uses>"}` (read D21's entry for the anchor).
    - `orchestrator.md` :398: the decide text copy gets the FR-5 sentence; :421 "No live task" paragraph and the orphaned-question rule describe the agent's pick, seed-only framing, the combined brief and "a clean start closes no question" (cite D454). Do not edit `docs/design/settlements/*` (history).
  - Tests: `tests/test_diagram_decisions.py` (existing) is the test.
  - Done when: `scripts/py -m pytest tests/test_diagram_decisions.py tests/test_ownership.py -q` passes.
  - Covers: FR-16, AC-15, NFR-6.

- [x] T8: Full gate, line count, beta
  - Files: `docs/ai/sut-26-context/implementation.md` (developer's report, committed with this step).
  - Change / checks:
    1. Targeted set (the T6 command plus `tests/orchestrator/test_chat_agent.py tests/test_diagram_decisions.py tests/test_ownership.py`) → no failure outside the T0 baseline.
    2. `scripts/gate.sh` in the foreground (about 15 min). Any failure: compare with the T0 baseline; a test outside the baseline set that fails is checked on `origin/main` too (`git worktree add <scratchpad>/main origin/main`, run that one test there with this checkout's `scripts/py`; never stash); only failures also seen on main may be ignored, and they are listed in implementation.md.
    3. NFR-3: `git diff origin/main -- sutra_app | grep -inE "pulse|bakery|keyword|overlap"` prints nothing new.
    4. NFR-4 report (not a gate): `git diff --numstat origin/main -- sutra_app ':(exclude)sutra_app/**/templates/*.md'` summed (added minus deleted) and, separately, the template lines; write both numbers in implementation.md.
    6. Live test (owner ruling), in the beta app, ONE team, real model, each step once; a failed step stops the test (no retry), with evidence: (a) a website brief, let it finish; (b) "make the header blue" continues run (a); (c) "write a script that sorts my Downloads folder" starts clean, nothing from (a) (first Identity prompt / task.json: no seed, no upstream, no team-lead framing); (d) an answer to an open question of (a) continues (a) with its brief (if (a) left no open question, say so). Report the spend.
    5. Beta (AGENTS.md step 3, the change shows as server behaviour): `scripts/py scripts/install_app.py beta`; if it exits 3 the app is busy: wait or ask, never `--force`. Tell the owner the version and commit, and what to try: (a) a team that finished one site, write an unrelated brief → clean run, no "Context from the team lead"; (b) "make the header blue" → continues; (c) Stop a team while it waits on a question, answer it → the new run shows the first brief; (d) note how long the line takes to appear (R-3).
  - Done when: gate green apart from main's own failures, implementation.md lists what ran, what was skipped (live model behaviour of the `follows` prompt is not verified by any test), the two line counts and the beta build.
  - Covers: all; NFR-3, NFR-4.

Push and landing on `main` follow AGENTS.md step 4 after code-reviewer, not in this plan.
