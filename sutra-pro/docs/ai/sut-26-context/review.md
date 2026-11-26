# Review: SUT-26 (D454) a team-chat line continues an earlier run only when the chat agent says so

## Round 1  (2026-11-26, commit 7cb4b268)
Verdict: **Approved**. There are no blocker or major findings. The 3 minor and 2 nit findings below are optional cuts and cleanups.

Scope: `git diff b5a9bdf9...HEAD` in `~/Downloads/sutra-sut26` (worktree of `sut-26-context`). Read against spec.md, architecture.md, plan.md and implementation.md.

### Findings
| ID | Sev | File:line | Finding | Evidence | Suggested fix |
|---|---|---|---|---|---|
| R1-1 | minor | `sutra_app/orchestrator/tasks.py:247-250` | `TaskStore.latest_in` is now dead production code. Its only `sutra_app` caller was the old `_follow_up` (base `tasks.py:1022`). It is still called from 3 tests. | `git grep latest_in b5a9bdf9 -- sutra_app scripts` finds only the def and the old `_follow_up` call. On HEAD, `grep -rn latest_in sutra_app` finds only the def. | Delete the method (-5 lines in `sutra_app/`). In `tests/orchestrator/test_tasks.py:497`, `tests/contracts/test_contract_settings.py:83` and `tests/contracts/test_contract_route_table.py:218`, read the newest task with one SQL line or a local test helper. |
| R1-2 | minor | `docs/ai/sut-26-context/implementation.md` "Not verified" | Synthetic tests cover AC-5 (a deterministic code rule) well. Live, nobody has yet checked whether the model picks the right run for a bare answer to an ended run's question (S-3, S-4, risk R-4). Live step (d) was not run. | `test_another_runs_question_is_never_the_framing_and_stays_open[later/None]` and `test_the_framing_is_the_picked_runs_own_question_only` pass. The beta test (b, c) covered only "continue" and "clean". | Before release, run step (d) in the beta: Stop a team that is waiting on a question, answer "Option 1", and check `seed_from`, framing and `user_text`. Do this as a verification step. It needs no code change. |
| R1-3 | minor | `sutra_app/orchestrator/tasks.py:1044-1059` | (Deviation 2.) `_pick_follows` checks neither `departments.hidden_at` nor `org_nodes.state`. A deleted project, or a team whose graph node and chat outlive its active state, spends 1 model call before the transaction refuses the line (ReadOnly or NotFound). The result is still correct: the line is refused and no task is made. | Read: the precheck at :1053-1055 tests only live and queued tasks. The team check runs only in the transaction, at :931-935. | Accept as recorded, or add the team SELECT from `_deliver:931` to the precheck (+2 lines). Accepting is consistent with the "simpler" goal. |
| R1-4 | nit | `sutra_app/orchestrator/tasks.py:1028`, `:1088` | Each follow-up reads `page.json` 3 times: in `_candidates` from `_pick_follows`, in `_candidates` from `_follow_up`, and again at :1088. | Read. | Optional. No line saving unless `_candidates` also returns the marker. |
| R1-5 | nit | `scripts/live_smoke.py:956-966` | (Deviation 4.) In `--fakes` mode the dry run now starts the follow-up with `POST /api/tasks {follows}`, so it no longer goes through the team-chat path. The real-model mode still does. | Read. The team-chat path is still covered end to end by `tests/e2e/test_scenario_followup.py`, which pushes a `follows` reply into the real `ChatAgent` through `wiring.py:196`. | Accept. Nothing more to do. |

### Owner's question 1: cuts in the +76 net Python lines (113 added, 37 deleted)
No structural block can go without dropping a requirement. The precheck covers NFR-1, the candidate listing covers FR-4, the in-transaction re-validation covers FR-2, and the reset branch covers ruling Q-10. The cuts below add up to about 12 to 15 lines, which brings the net to about +61 to +64.

| # | File:line | Cut | Saves |
|---|---|---|---|
| C-1 | `tasks.py:247-250` | Delete the dead `latest_in` (R1-1) | 5 |
| C-2 | `tasks.py` docstrings of `_follow_up` (6 lines), `_pick_follows` (3), `_candidates` (2) | Shorten to 3, 1 and 1 lines | 6 |
| C-3 | `agent.py:339-341` | `follows` docstring from 3 lines to 1 | 2 |
| C-4 | `prompts.py:103-104` | Remove `if not runs: return "(none)"` and end the function with `return "\n".join(...) or "(none)"` | 2 |
| C-5 | `tasks.py:1031` | Drop the `ended` local and write the status literal inline, as the reset SQL at :1090 already does | 1 |
| C-6 | `tasks.py:83` | `CONTINUES` is used once (:1076). Inline it as an f-string. No test imports it. | 1 |
| C-7 | `agent.py:341`, `:356`, `:358` | Possible but **not recommended**: drop the `context` override and use `call_context(0)`. Usage would then be booked under request 0's overhead atom instead of `follows-<dept>`, which loses per-team accounting. | 3 |

### Owner's question 2: does a failed follows call always start clean?
The decision has 1 caller: `_deliver` (tasks.py:929). `_deliver` is reached from `deliver_to_department` (engine `/api/say`, `commands.py:120`, worker thread), from `deliver` (`api/agent.py:92`, `run_blocking`) and from `answer_waiting` (`answer_only=True`, which makes no call). Both callers that can make the call run in worker threads, so `_run_async` uses `anyio.from_thread.run` and cannot deadlock the loop.

| Path | Where it ends | Result |
|---|---|---|
| Model returns no `follows`, or no assignments | `agent.py` `build` → None | clean |
| `follows` fails the `^tsk_[0-9a-f]{12}$` pattern, the gate rejects the reply, or the JSON is bad | `_stage` → `StageFailed` → `follows` returns None | clean |
| Timeout (`wait_for` at `chat_timeout` + 10 s grace) | retry-kind failure; with `attempts=1` → `StageFailed` → None | clean |
| Unreachable model, auth or quota (`NO_RETRY_KINDS`) | `ConnectorFailure` is raised out of `follows` and caught by `except Exception` at `tasks.py:1060` → None | clean |
| Any other exception, including a test double's `RuntimeError` | `tasks.py:1060` | clean |
| DB or chat lookup fails before the call (e.g. `NotFound` from `_dept_session`) | `tasks.py:1060` → None. The transaction then raises its own NotFound or ReadOnly. | no task (correct) |
| The pick is unknown, from another team, or became stale during the call (reset, folder gone) | re-validated in the transaction: `next(...)` over `_candidates` at :1074 → `seed=None` | clean: no seed, no parent, no framing, no question closed |
| The team became live or queued during the call | the existing answer or Busy branches win and `pick` is ignored | as before |

Inside the transaction, nothing after the pick can raise because of the pick itself: `next` has a default, and `CONTINUES.format` takes the owner's words as an argument, not as a template. `_candidates` can fail only on the same folder and page reads the old code already did. The `asyncio.CancelledError` from a loop shutdown is a `BaseException` and would propagate, but that happens only while the app is closing, so it is not a finding. Tests: `test_a_failed_or_foreign_pick_starts_clean_and_keeps_the_line` (6 cases) and the T2 tests in `test_chat_agent.py` (pick, none, bad output, timeout, unreachable).

### Owner's question 3: "+ New run" and closing open questions, compared with b5a9bdf9
| Case | b5a9bdf9 | HEAD | Same? |
|---|---|---|---|
| Reset, no run after the marker | Newest orphan of an ended task closed, no framing | `not found and marker` → same SQL → closed, no framing, **no call** | yes |
| Reset, 2 orphans | Only the newest closed | Same SQL (`ORDER BY m.id DESC LIMIT 1`) | yes |
| Reset, then a later run ended, agent picks none | Newest orphan closed **and** used as framing | Nothing closed, no framing | intended change (Q-10: an agent-judged clean start leaves questions open) |
| No reset, agent picks none | Newest orphan closed and used as framing | Nothing closed | intended (FR-7) |
| No marker, no candidate (e.g. folders gone) | Orphan closed and used as framing | Nothing closed | intended (FR-7, no agent pick) |

Tests: `test_a_question_left_open_by_a_reset_is_closed_but_not_carried_into_the_fresh_run` (closed, `calls == []`) and `test_another_runs_question_is_never_the_framing_and_stays_open[None]` (left open).

### Known risk (not a finding)
R-1: D451 project memory (`run_inputs.py` `given_for`) still shows earlier requests under "## Project context" in a clean run's Identity prompt. Beta step (c) confirmed this. The owner is checking it with Kaivan. It is out of scope for SUT-26.

### Deviations
| # | Deviation | Judgement |
|---|---|---|
| 1 | A continuation of a stopped, crashed or cancelled seed keeps `seed.title` | Accept. `one_line_title` of the combined text would have been the old brief run together with "The owner now writes". The owner's words ("Option 1") make a worse title. Tested in `test_orphaned_question_framing`. |
| 2 | No deleted-team check before the call | Accept (R1-3) |
| 4 | `live_smoke.py` fake mode uses `POST /api/tasks {follows}` | Accept (R1-5) |

### Spec coverage
| Requirement | Covered by | Status |
|---|---|---|
| FR-1, FR-2, FR-3 | `_pick_follows`, `_follow_up` re-validation; AC-1, AC-2 tests | met |
| FR-4, NFR-5 | `_candidates` (5, ended, folder, after marker), `run_lines` clip; `test_the_agent_sees_the_newest_five...`, `test_run_lines_lists_each_run_and_clips` | met |
| FR-5 | 3 templates; AC-7 test | met |
| FR-6, FR-7, FR-8 | framing and closing in `_follow_up`; AC-4, AC-5, :485 | met |
| FR-9, FR-10, FR-11, FR-12, FR-15 | `CONTINUES`; e2e AC-8 (Stop and app close, `tree_sha`), AC-9, chain test | met |
| FR-13, FR-14 | marker filter, early return; reset tests assert `calls == []` | met |
| FR-16 | D454 in DECISIONS.md and decisions.json; `test_diagram_decisions` | met |
| NFR-1, NFR-2, NFR-8 | `attempts=1`, `_Budget(1)`, call before `db.tx()`; AC-13, AC-14 | met |
| NFR-3 | no subject or keyword literals in the added `sutra_app` lines (read) | met |
| NFR-4 | +76 net reported | reported; cuts above |
| NFR-6, NFR-7 | `test_ownership`, run-spec goldens (in `tests/orchestrator`) | met |

### Tests run
`scripts/py -m pytest -q tests/orchestrator tests/e2e/test_scenario_followup.py tests/e2e/test_scenario_restart_stop.py tests/live tests/test_diagram_decisions.py tests/test_ownership.py`
Exit 0: 3210 passed, 3 skipped, 0 failed. The full gate was not rerun. The developer reports 13675 passed and 4 failed, and all 4 also fail on main.

### Earlier findings
None (round 1).

## Fix-up round 1 response (developer, 2026-11-26)
| ID | Response |
|---|---|
| R1-1 | Fixed in ff493905, together with cuts C-1 to C-6. C-7 was declined: the `context` override is kept. |
| R1-2 | Verified live in beta 32302dd. A bare answer to a stopped run's question continued that run with its framing and the combined brief. Evidence is in implementation.md, "Fix-up round 1". |
| R1-3 | Fixed in 32302dd5: the team check now runs before the call, with a test. |
| R1-4 | Declined (owner). |
| R1-5 | Declined (owner). |

## Round 2  (2026-11-26, commit 10fbbfc8)
Verdict: **Approved**. This round re-checked only the lines changed in `7cb4b268..10fbbfc8`. There are no new findings.

### Findings
None.

### Checks
| Check | Result | Evidence |
|---|---|---|
| The trims change no behaviour | Confirmed | The f-string at `tasks.py` `_follow_up` builds the same text as the old `CONTINUES.format` (test_tasks asserts the exact text). `run_lines(...) or "(none)"`: joining an empty list gives "", so the result is "(none)" as before. The literal status list in `_candidates` equals `GOOD_END + BAD_END`. The other changes are docstrings only. |
| `latest_in` fully gone | Confirmed | `grep -rn latest_in sutra_app tests scripts` finds nothing. The 3 tests now query `ORDER BY created_at DESC, rowid DESC`, the same order the old method used. |
| R1-3 check comes before any model call and uses the same rule as `_deliver` | Confirmed | `_pick_follows` runs the team query (`departments JOIN org_nodes`, `state = 'active'`, `hidden_at IS NULL`) first inside its `try`, before the live/queued checks, `_candidates` and `_run_async`. `_deliver:931-935` applies the same two conditions and refuses with NotFound or ReadOnly; this check returns None for both, so the transaction still gives the same refusal. |
| The new test is meaningful | Confirmed (by reading) | In `test_a_deleted_project_is_refused_without_a_model_call`, the team has an ended run with a folder, so without the new check `_candidates` would be non-empty, the double would be called, and `calls == []` would fail. It also asserts ReadOnly. |

### Open item from round 1
R1-2 is closed for S-3: a run was stopped while it waited, then answered with a bare line. The agent picked that run, and framing, combined `user_text`, `upstream/` and the closed question are all recorded in implementation.md. This covers it adequately: stopping first is the only way to reach the `follows` path (a live waiting task takes the answer directly, NG-4), and a free-text answer is a fair stand-in for "Option 1". The live test did not cover S-4 (the right run chosen among several, with a newer unrelated run present), because the team had only 1 candidate. That stays under spec risk R-4 (model judgement). It is not a code defect and not a blocker.

### Tests run
`scripts/py -m pytest -q tests/orchestrator tests/contracts/test_contract_settings.py tests/contracts/test_contract_route_table.py tests/e2e/test_scenario_followup.py tests/e2e/test_scenario_restart_stop.py`
Result: 3220 passed, 2 skipped, 1 failed. The failure, `test_contract_route_table.py::test_every_path_the_view_scripts_call_is_served_by_some_router` (`/api/appearance`), also fails on main. The edited test in the same file passes.

### Earlier findings
R1-1: fixed. R1-2: fixed for S-3 (S-4 stays under R-4). R1-3: fixed. R1-4, R1-5: declined by the owner. That is acceptable for both, since both are nits.
