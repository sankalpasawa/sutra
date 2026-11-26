# Implementation: SUT-26 (D454) a team-chat line continues an earlier run only when the chat agent says so
Branch: `sut-26-context` (worktree `~/Downloads/sutra-sut26`), from `origin/main` ef69d36b   |   Date: 2026-11-26   |   Not pushed.

## Per step
| Step | Commit | What was built |
|---|---|---|
| T0 | none | `origin/main` = ef69d36b. D452 on main; D453 is only on `live-view` (not merged), so not on main. D454 free on every branch; no P47/E33 needed. All names the plan relies on exist. Baseline: 1 failure (`tests/contracts/test_contract_route_table.py::test_every_path_the_view_scripts_call_is_served_by_some_router`, `/api/appearance`). |
| T1 | 06d425a5 | `templates/follows.md` (new), the FR-5 sentence in `decide.md` and `assign.md`, `prompts.run_lines` (clips brief and question to 1,000 characters), `follows` in `TEMPLATES`/`PLACEHOLDERS`. Tests: AC-7, `run_lines`. |
| T2 | 4a232c73 | `ChatAgent.follows(dept, text, runs)`: one call (`attempts=1`), step `follows`, `assignments` schema, accounting key `follows-<dept>`; `_stage(..., context=None)`. `StageFailed` (bad output, timeout) gives None; `unavailable`/`auth`/`quota` go up. Tests: pick, no pick, bad output, timeout, unreachable model, one call each. |
| T3 | ad1c17d9 | `TaskService.follows_of`, `CONTINUES`, `_open_questions`, `_candidates`, `_pick_follows` (before the transaction; any exception gives a clean start), `_follow_up(..., pick)`. Existing tests updated as the plan says, except `:485` (owner ruling Q-10, below). |
| T4 | 830a1ff7 | AC-1 to AC-6, AC-10 to AC-14 in `tests/orchestrator/test_tasks.py`. The AC-2 test covers the owner's ruling 3 (timeout, unavailable, `asyncio.TimeoutError`, `RuntimeError`, unknown id, another team's id: each starts clean and keeps the line). |
| T5 | a79361a8 | `wiring.py`: `tasks.follows_of = agent.follows`. E2E: scripted picks; AC-9 (`summary.brief` equals the seed's brief, words in `change_requests`); AC-8 on Stop (combined `user_text`, chat line is the words alone, the new `summary.json` brief holds both texts, old folder byte-identical) and on app close (combined `user_text`, old folder byte-identical). |
| T6 | 3a3ed22e | The sweep of the targeted suites found nothing new. The full gate found `tests/live/test_live_app_smoke.py` dry run failing: its follow-up step sent a team-chat line and the fake CLI cannot make the `follows` choice. In `--fakes` mode the step now starts the follow-up with `POST /api/tasks {follows}` (the caller decides, NG-5). The real-model mode still sends the team-chat line and still requires a seed. The test's `seeded is True` assertion is unchanged. |
| T7 | 5f17b5e0 | D454 in `docs/DECISIONS.md` (with an "Amended by D454" line on D21), `docs/diagram/decisions.json`, `docs/design/orchestrator.md` 5.3/5.5; spec.md and plan.md updated for the owner's rulings; the task docs committed. |
| T8 | this commit | Gate, line count, beta, live test, this file. |

## Owner rulings applied
| Ruling | Outcome |
|---|---|
| Q-10: "+ New run" keeps closing what it closes today; an agent-judged clean start leaves questions open | Done. In `_follow_up`, when the agent picks nothing and the reset marker leaves no candidate, the newest open question of an ended task is closed (the same SQL as before), but it is not used as framing. Tests: `test_a_question_left_open_by_a_reset_is_closed_but_not_carried_into_the_fresh_run` (kept, now also asserts no call is made) and `test_another_runs_question_is_never_the_framing_and_stays_open[None]`. |
| R-3: show the owner's line before the decision if that is small | **Not done: it is not small.** The line is posted in the same transaction that creates the task (`task_id` = the new task). Posting it first means two transactions, a `task_id` update on the message, and a line left behind with no task when the second transaction ends in Busy (the race of AC-14). It would also not show the line sooner on the team page: `j2_ui.html` `sendText` waits for `/api/say` and the page draws the run's own chat. The design stands. Measured in the beta: the follows call took 4.7 s (step b), and the whole `/api/say` round trip took about 4 to 5 s (b, c). |
| 3: a failed, erroring or timed-out `follows` call starts clean | Done (`_pick_follows` catches every exception; `ChatAgent.follows` turns a timeout or bad output into None). Tests: T2 and the AC-2 test. |
| 4: live test steps a to d | Added to plan.md T8 and run (below). |

## Deviations from plan and architecture
| # | Deviation | Why |
|---|---|---|
| 1 | A combined task keeps the seed's title (`title=seed.title`) | `one_line_title` collapses the blank line, so the title would have been the brief followed by "The owner now writes: ...". The architecture said the title would be the first brief's line. |
| 2 | `_pick_follows` does not check for a hidden (deleted) team before the call | A deleted project with earlier runs wastes one call before the transaction refuses it with ReadOnly. Missing teams make no call, because there are no candidates. |
| 3 | `:485` test kept, not renamed | Owner ruling Q-10. |
| 4 | `scripts/live_smoke.py` changed (outside the planned file list) | T6, above. |
| 5 | Worked in the existing worktree `~/Downloads/sutra-sut26` | The `sut-26-context` branch was already checked out there (no own commits, clean). It was fast-forwarded to `origin/main`. The main checkout and its uncommitted `analysis.md` edit were not touched. |
| 6 | `run_lines` collapses whitespace and shows `-` for an empty question | As the plan says (like `conversation`). |

## Tests
| Command | Result |
|---|---|
| Baseline (T0) on unchanged `origin/main`: the T6 targeted set | 1 failure: route table `/api/appearance` |
| T6 targeted set after T5 (`tests/orchestrator tests/e2e tests/engine/... tests/integration tests/contracts tests/test_diagram_decisions.py tests/test_ownership.py`) | 1 failed (the baseline one), 3650 passed, 31 skipped |
| `scripts/gate.sh` (full, 15 min) at 5f17b5e0 | 5 failed, 13649 passed, 389 skipped. Checked on a scratch worktree of `origin/main`: `test_workflows_yaml::test_ci_is_named_ci...`, `test_fake_backend::test_the_pages_come_from_the_real_ui_router...`, `test_shared_css::test_each_page_links_its_own_sheet...` fail on main too. The route-table test is the baseline failure. `test_live_app_smoke` dry run was new; it is fixed in 3a3ed22e (`tests/live`: 31 passed, 1 skipped). |
| `tests/test_diagram_decisions.py tests/test_ownership.py` | 5 passed |
| NFR-3 grep (`pulse|bakery|keyword|overlap` in added `sutra_app` lines) | nothing |

New failures against the baseline: 0. The full gate was not rerun after 3a3ed22e. Only `tests/live` was rerun, because that commit touches only `scripts/live_smoke.py`.

## Rebase onto origin/main b5a9bdf9 (live-view, D453, merged)
- The rebase conflicted only in `docs/DECISIONS.md` and `docs/diagram/decisions.json`, both at the end of the file. Resolved by keeping both, in order: D453, then D454. `python -m json.tool` accepts the JSON. No code file conflicted.
- `scripts/gate.sh` after the rebase: 4 failed, 13675 passed, 389 skipped. The 4 failures are exactly the ones that also fail on main: the route table (`/api/appearance`), `test_workflows_yaml::test_ci_is_named_ci...`, `test_fake_backend::test_the_pages_come_from_the_real_ui_router...` and `test_shared_css::test_each_page_links_its_own_sheet...`. The live-smoke dry run now passes.
- Commit hashes in the table above are from before the rebase. The rebased commits are d86f5c26 (T1), 31d208e7 (T2), ae13972f (T3), fc085985 (T4), 5f26ffc7 (T5), 562c1095 (T6), a41b5e4a (T7), 55010547 (T8).

## Size (NFR-4, reported only)
| Part | Added | Deleted | Net |
|---|---|---|---|
| `sutra_app/` Python (agent.py, prompts.py, tasks.py, wiring.py) | 113 | 37 | +76 |
| `sutra_app/**/templates/*.md` | 10 | 2 | +8 |

## Beta and live test (owner's steps, real model, one team)
Beta: Sutra Pro Beta 0.9.0 beta 3a3ed22, installed with `scripts/py scripts/install_app.py beta`, data in `~/.sutra-pro-beta`. The team "Sut26 Live" (`sut26-live`) was added by hand. All text is synthetic.

| Step | Result | Evidence |
|---|---|---|
| a: website brief, let it finish | Done | `tsk_06f1ca6a6999`, run `j2-20261126-113808-cf91`: one info question was answered, then a "keep going / leave out / finish as is" question was answered "Option 3". Ended `done_with_open_items`. Its questions were answered, so **(a) left no open question**. |
| b: "make the header blue" continues (a) | PASS | `tsk_5f049e27a559`, run `j2-20261126-120237-c34e`. task.json: `seed_from` = `parent_run_id` = `j2-20261126-113808-cf91`, framing "", `user_text` "make the header blue". No `upstream/`: it rehydrated. First system line: "Continuing from run j2-20261126-113808-cf91: ...". `summary.json` brief = (a)'s brief. Stopped through `POST /api/tasks/{id}/stop` (owner instruction). |
| c: "write a script that sorts my Downloads folder" starts clean | PASS on the SUT-26 criteria | `tsk_cc83fbbf888c`, run `j2-20261126-120756-f46c`. task.json: `seed_from` None, `parent_run_id` None, framing "", `user_text` = the words alone. No `upstream/`. The first Identity call (calls.jsonl, fn identity) has no "Context from the team lead", no "Earlier the team asked", no `upstream/` and no question from (a). **It does carry (a)'s request**: the D451 project memory under "## Project context" (from `node_context.json`) lists "asked 'Build a one-page website for Juniper Lane Books...'" and "asked 'make the header blue'". This is R-1 (D451 left unchanged by owner decision 3). Stopped through the app. |
| d: answer an open question of (a) | Not run | (a) left no open question (see a). Run (b) was stopped by the owner's instruction before it asked anything. The only open question now in the team is (c)'s own. |

`/api/say` round trip with the follows call: 5 s (b), 4 s (c). The follows call in (b) took 4.7 s and cost $0.059 (claude-opus-5-5, purpose `chat_plan`; the usage row's `step` is empty).

Spend in the beta for this test, from `usage_ledger` (USD at API price, 77 calls): $15.61 in total. That is run (a) $11.28, run (b) $3.81, run (c) $0.44, and the two follows calls $0.077.

## Not verified / known gaps
- The live `follows` prompt was tried on only 2 lines (b: continue, c: clean). An answer to an old question (S-3, S-4) was not tried live, because (a) left no question.
- D451 team memory still puts earlier requests into a clean run's agents (R-1, owner decision 3).
- The `step` field of the follows usage row is empty. The chat agent's other stages behave the same way in this ledger.
- The full gate was not rerun after the T6 fix commit (only `tests/live`).

## Follow-ups
- Owner: decide on R-1 (D451 memory in clean runs) with Kaivan, and on the merge order with Kaivan's `_seed_output` ticket (R-2).
- Try S-3 and S-4 live: Stop a team while it waits on a question, then answer it.

## Fix-up round 1 (review.md round 1)
| Finding | Status | Commit | Change |
|---|---|---|---|
| R1-1 and cuts C-1 to C-6 | fixed | ff493905 | `TaskStore.latest_in` deleted; its 3 test callers read the newest task with one SQL line. Shorter docstrings for `_follow_up`, `_pick_follows`, `_candidates` and `ChatAgent.follows`. The status list in `_candidates` and the combined-brief text are written inline (`CONTINUES` removed). `run_lines` ends with `or "(none)"`. The `context` override in `_stage` is kept (C-7 declined: it keeps per-team accounting). |
| R1-3 | fixed | 32302dd5 | `_pick_follows` checks the team first: active and not deleted, the same SELECT as `_deliver`. A deleted project or inactive team makes no model call. Test: `test_a_deleted_project_is_refused_without_a_model_call`. |
| R1-2 | verified live | none | Beta 0.9.0 beta 32302dd, a new team "Sut26 Answer". Steps: brief "make a page for my shop", Identity asked its question, the run was stopped through the app, then one short line was written in the team chat. The question had no numbered options, so the line was a bare answer to its first part: "A tea shop called Leaf and Co.". The agent picked that run: task.json `seed_from` = `parent_run_id` = `j2-20261126-124802-a3c6`; framing = "Earlier the team asked the owner: <that run's question>"; `user_text` = "make a page for my shop\n\nThe owner now writes: A tea shop called Leaf and Co."; `upstream/j2-20261126-124802-a3c6/` present (fresh start after a stopped seed). The question was marked answered by the line, and the team chat shows the line alone. The continuation run was stopped through the app. Follows call: 4.0 s, $0.020. Spend for the check: $0.58 (7 calls, API price), within the $3 cap. |
| R1-4, R1-5 | declined | none | By the owner's instruction. |

Size after the fix-up: `sutra_app/` Python 102 added, 42 deleted, **net +60** (before: +76); templates +8, unchanged.

Gate after the fix-up (`scripts/gate.sh`, at 32302dd5): 4 failed, 13676 passed, 389 skipped. The 4 failures are the ones main also has: route table `/api/appearance`, `test_workflows_yaml`, `test_fake_backend`, `test_shared_css`.
