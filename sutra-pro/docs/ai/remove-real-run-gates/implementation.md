# Implementation: a planned real run runs without approval, a dry run or internet rules
Task: remove-real-run-gates | Branch: remove-real-run-gates (from origin/main 6c79a1db) | Decision: D452 | Patch: P46 | Port edit: E31

Numbers checked after `git fetch origin main` at T1 and again before T12: origin/main is still 6c79a1db; D452, P46 and E31 are free there.
Nothing pushed, no PR, no beta install, no release, no live smoke.

## What was built, per step

| step | commit | what | code lines (j2.py + vendor_j2.py + port_j2_ui.py) | j2.py |
|---|---|---|---|---|
| T1 | a7c23c79 | D452 in DECISIONS.md and decisions.json; the task's impact/spec/architecture/plan committed with it | 0 | 0 |
| T2 | 630cb1f3 | `vendor_j2.py`: a patch's `Edit` may name a vendored data file (`agents/j2/<role file>`, a file of a `TREES` folder); an edit naming any other file still stops the run. Two unit tests on a tiny in-memory source | +23 −8 | 0 |
| T3 | 60a9f1a6 | P44 retired; P46: `HOST`, `HOST_ENTRY`, `real_hosts`, `host_entry_ok`, syntax-only `real_run_hosts_problems(rr)`, hosts stored when listed, `allowedDomains` = the plan's hosts, the two short net rules, `unparsed` moved from P44; E29 deleted; page re-ported | +68 −434 | +26 −184 |
| T4 | ced82eb7 | the folder-argument rule, `_real_path_leak`, `real_paths_in`, `real_folders` and their callers gone (P28, P31, P42 re-anchored); legacy blocks `run_for_real`, `dry_run_real_folders` skipped with a D452 reason | +131 −103 | +37 −89 |
| T5 | e04a3dec | P32 retired; `real_run_dry`, `real_runs_dry`, the `fence` branch, placeholders gone; `_real_run_once` diffs the folder before/after the real run, compares `expect` (mismatch: items NEEDS_REVISION, no Audit call, mismatch in the row's `audit`), else P33's Audit reads the real diff; `_real_run_back` replaces `_dry_run_failed` (`real_run_setup`, no row) | +304 −358 | +86 −175 |
| T6 | c878838f | P42: `_env_install(w, cwd)` installs with no question; `_env_ask`, `_identity_env_install`, `w["resume"]`, the `env:` codes gone; `env_install` row per FR-28; runenv.py docstring | +72 −196 | +35 −94 |
| T7 | 37355d2f | `_real_run_next` / `_ran_real_run` (a `real_run` row in receipts.jsonl, so once per workflow id, follow-ups included); `real_runs_asked`, `REAL_RUN_DECLINE`, `PAUSES["real_run"]`, `real_run` in `AUTO_ASK` and `DECISION_PAUSES`, the dispatch, snapshot `paused.code`, the card and `real_run_env_lines` gone; row keys per FR-27; `_real_run_answer` says ran / did not start; `j2_artifacts` projection drops `approved`; E28 deleted, E31 added; records.py comment | +139 −177 | +41 −76 |
| T8 | 5bd1e9d3 | FR-40: `real_run_why`, `_real_run_open()`; P30's `_goal_done` outcome and `_ship_outcome` use it; `_write_summary` turns a "Done:" outcome into "Done with open items: ..." while one is open | +107 −25 | +50 −12 |
| T9 | 98a23781 | P43 trimmed: the real-run hold and the "Noted. This part is checked ..." line gone; `picked` stays | +2 −37 | +1 −15 |
| T10 | 946ebd48 | P46 data edits: identity.md line 43, real_run.md; `REAL_RUN_EXPECT_RULE`, `REAL_RUN_ENV_RULE`, `_real_run_note`, `real_run` docstring, the SANDBOX_OFF comment; prompt goldens re-recorded (see Deviations) | +59 −27 | +17 −19 |
| T11 | f782a235 | D434, D435, D449 superseded; D447, D448 superseded in part; D436, D438, D446 amended (no earlier text deleted); decisions.json labels; VENDORED intro; stale comments | +11 −7 | +2 −2 |

## Lines (NFR-1, Q-8: no floor)

| measure | value |
|---|---|
| `git diff --shortstat origin/main -- sutra_app/engine/j2.py scripts/vendor_j2.py scripts/port_j2_ui.py` | 3 files changed, 816 insertions(+), 1272 deletions(-): **456 lines net fewer** |
| `wc -l sutra_app/engine/j2.py` | 14001 at 6c79a1db, 13630 now: **371 fewer** |
| `sutra_app` + `scripts` | 11 files, +860 −1320 (460 net fewer) |
| tests | 16 files, +596 −941 (345 net fewer) |
| whole branch (docs included) | 34 files, +2344 −2276 (the four task documents add 856 lines in T1) |

NFR-2 / NFR-3 scan of `git diff origin/main -- sutra_app scripts`: no added `getenv` or new `agent_setting(` name (the one `agent_setting("J2_SANDBOX_CMD")` line moved from `_identity_env_install` into `_env_install`); no host literal outside tests but the existing `api.example.com` example in the planner's rule and pypi.org in P42's note.

## Deviations

| # | what | why |
|---|---|---|
| 1 | T2 kept | T10 needs it: identity.md and real_run.md are data files copied byte for byte, and FR-31 to FR-33 require P46 to change them reproducibly from the extraction (VENDORED.md lists both with P46 and a new sha256). The only alternative was a load-time text replace in code, which is worse |
| 2 | Identity's prompt goldens moved (spec A-4 assumed none would) | identity.md is Identity's system prompt in every run. Re-recorded with `record_engine_golden.py --engine` and `record_fn_golden.py` and compared before/after: only Identity's system digest (and its token count in run_events.jsonl, 19 tokens fewer) differs; every user prompt, outcome, spend and call order is identical. The legacy `DOC_RUN_GOLDEN` is re-recorded with the same note |
| 3 | E31 replaces the phrase instead of deleting it | founder note: `` ` · ${r.ran ? "ran automatically" : "did not start"}` `` |
| 4 | Some patch edits amended in place carry D452 text: P29 (`AUTO_ASK` without `real_run`), P30 (`_goal_done` outcome, `_ship_outcome`, `_item_states` reads `real_run_setup`, the audit path calls `_real_run_next`, the real-run item evidence), P28 (no `leak`), P42 (anchors, `real_runs_done` comment) | each restated J2 text that P46 had to change; an edit's new text must survive to the end, so the restating patch changes in place (architecture's own rule) |
| 5 | `_real_run_back` and `_real_run_once` live in P46 (not P31/P33) | they replace J2's `_ask_real_run`/`_identity_real_run` text, which P46 owns; the P31 and P33 notes say so |
| 6 | `_real_run_open` reads a copied row in a follow-up (`_real_run_row`) | `real_runs_done` is not restored by a follow-up; without it a follow-up of a passed run would say "did not pass" |
| 7 | `_goal_done` keeps J2's "Done with open items" when audits still fail after a real run passed (`rest and self.real_runs_done`), worded "not every done-when item passes." | J2 said "the real run did not pass" there, which was false; dropping the case would have let such a run end "Done:" |
| 8 | AC-25's identity.md scan covers its lines about running | J2's own line 40 names "approval" as a process step a done-when item is not, unrelated to real runs; runenv's docstring keeps J2's branch name `fix-real-run-approval` (excluded from the scan) |
| 9 | AC-29 test copies receipts.jsonl itself instead of calling `rehydrate` | `rehydrate` refuses the folder type's saved run in this fixture depending on test order (its own `_types()`); the property tested is `_ran_real_run` reading the copied file, which is what rehydrate does (rehydrate.py:17-19) |
| 10 | Legacy J2 blocks `run_for_real`, `real_run_checks`, `real_run_order`, `dry_run_real_folders` print "skipped the rest of <name>: D452: ..." (`D452_GONE` in tests/engine/legacy/j2_flow_test.py); EXPECTED.json records the new hash and 4 fewer ok lines (115 / 179) | they test the approval, the dry run or its rules |
| 11 | tests/ui/fixtures/result_view/real-runs-script.json drops `approved` and `dry_run` | founder note |
| 12 | D447 and D448 labels say "(superseded in part)" | only part of each is superseded (FR-36) |

## Tests

| command | result |
|---|---|
| `scripts/py scripts/vendor_j2.py --source <extraction of ee659fb5> --commit ee659fb5... --check` (after every step) | `527 files, ok` |
| `scripts/py scripts/port_j2_ui.py --j2 <extraction> --commit ee659fb5... --check` | ok: 57 anchors, the 7 committed files equal a fresh port |
| `scripts/py -m pytest tests/engine/test_engine_patches.py` (after every engine step) | pass |
| `SUTRA_SLOW=1 SUTRA_J2_CHECKOUT=<extraction> scripts/py -m pytest tests/engine/test_engine_vendor.py tests/engine/test_engine_legacy.py` (T4, T5, T7, T10) | pass |
| the same with `tests/engine/test_engine_prompts.py` (T10, slow) | 3 fail, also on origin/main 6c79a1db (checked in a worktree of origin/main): `test_goldens_are_what_j2_does_at_the_baseline[brewlab_fixes0, prd, agent_answer]` (`workflows: golden 'a185d3699c80', got 'c7a38a6f2707'`: since D249 the goldens are the engine's, not J2's). Slow-only; not in the gate |
| `tests/engine/test_engine_views.py tests/ui/test_port_edits.py tests/ui/test_dept_page.py tests/test_diagram_decisions.py tests/test_traceability.py tests/test_docs.py tests/test_ownership.py` | pass |
| `node --test tests/ui/js/page_render.test.js tests/ui/js/result_view.test.js` | 96 tests, 95 pass, 1 skipped |
| `scripts/gate.sh` (full, owner's update; 15m47s) | **4 failed, 13618 passed, 389 skipped**. The 4 fail the same way on origin/main 6c79a1db (rerun there in a worktree of origin/main, then removed), so they are the 4 known main failures: |
| | `tests/contracts/test_contract_route_table.py::test_every_path_the_view_scripts_call_is_served_by_some_router` (`/api/appearance is called by a page script and no router serves it`) |
| | `tests/release/test_workflows_yaml.py::test_ci_is_named_ci_and_runs_on_push_to_main_pull_requests_and_manual_dispatch` (`assert {'workflow_dispatch'} == {'pull_request', 'push', 'workflow_dispatch'}`) |
| | `tests/ui/test_fake_backend.py::test_the_pages_come_from_the_real_ui_router_with_the_fakes_token_and_version` (`Left contains 1 more item: {'avatars': 'classic'}`) |
| | `tests/ui/test_shared_css.py::test_each_page_links_its_own_sheet_and_the_frozen_one_is_for_home_and_the_console_only` (`home.html`: extra `avatars.css`) |
| gate's desktop part (`cd desktop && npm test`), run by hand because `set -e` stops the gate after pytest's exit 1 | 134 tests, 133 pass, 1 skipped; `tests/js/*.mjs`: none exist |

Seen once and not again: `test_p8_the_run_end_hook_fires_after_the_report_is_made_and_the_reviewer_is_running` failed during one T5 run made while a slow legacy run used the machine (`KeyError: 'report'`, the reviewer thread's timing); it passed alone and in every later full run, including the gate.

Tests deleted or rewritten (FR-39): the R1 to R4 tests of impact.md §4 (the P31 question, P32, the P35 and P41 dry-run tests, the P44 naming, asking and offline tests, the P43 hold) are deleted; the KEEP tests pass, renamed where their patch changed (`test_p44_*` that stay are `test_p46_*`). New: AC-1 to AC-5, AC-9 to AC-12, AC-14 to AC-17, AC-20, AC-22, AC-23 (patches and views), AC-25 (vendor and patches), AC-28 (five cases plus the passing and replacement cases), AC-29, and the T2 data-edit mechanism.

## Known gaps and follow-ups

- With the sandbox off (Windows, no srt) a real run is a plain process with full network and no write limit, and nobody is asked (spec A-1, accepted by the founder).
- A mismatch is found after the files changed; nothing reruns or undoes it (by design, FR-16).
- ~~`_tree` raises on an unreadable file in the folder~~: fixed in review round 1 (R1-3).
- P45 (another developer) may want `created`/`changed`/`deleted` in the row; this branch writes none (FR-17).
- Not run: browser tests (`SUTRA_BROWSER=1`), the desktop tests outside the gate, live smoke, a beta install.

## Review round 1 fixes

| finding | status | commit | test (mutation: guard removed, tests that fail) |
|---|---|---|---|
| R1-1 (P2) builder.md promised approval, copies, a refusal | fixed: P46 data edits of `templates/builder.md` (bullet trimmed, folder-path bullet deleted) and `templates/atom_rules.md` ("after the Requester approves the run" gone, found by the grep of every prompt/template/data file); no golden moved (tools-on prompts only) | 12927a31 | AC-25 (`test_d452_the_real_run_texts_promise_no_question_and_no_dry_run`) scans both files, FR34 + "approves", "copies' paths", "refuses a build" |
| R1-2 (P2) "Done:" in chat before the summary net | fixed: `_chain_blocked` (P30, amended in place) lists `_real_run_open()` first, so `_chain_done` and the stage gate's "finish as it is" name it; the net moved from `_write_summary` to just before the closing system line in `_run`, so chat never shows "Done:" | 06e6579d | `test_p46_every_chain_ending_names_the_open_real_run` (5 endings), `test_p46_the_chat_never_says_done_while_a_real_run_is_open` (asserts no system line starts "Done:"). Mutations: net off 1 fail; `rr = []` 5; no-stage branch 4; stage branch 1 |
| R1-3 (P2) unreadable file crashed after the run, no row | fixed: `_tree` records an unreadable file as `"unreadable"`; `_real_run_once` writes the row in `finally` once the command ran (items "not judged: <error>" when a later step raised) | 06e6579d | `..._leaves_an_unreadable_file_still_writes_its_row` (broken symlink + chmod 000), `..._a_step_that_fails_after_the_real_run_still_writes_its_row`. Mutations: `_tree` raise 1 fail; `finally`→`else` 1 fail |
| R1-4 (P2) no real-srt write test | fixed (skips without srt, as the network test) | 30fa953b | `test_p46_real_srt_writes_only_the_plans_folder` (ran here with srt: passes) |
| R1-5 (P3) two endings did not name the reason | fixed with R1-2 (`_chain_blocked`) | 06e6579d | `deeds_fail`, `chain_stages` cases above |
| R1-6 (P3) old approved rows said "ran automatically" | fixed: the projection carries `approved` only when the row has it; E31 says "approved by you" / "not approved" for such a row, else "ran automatically" / "did not start" | 06e6579d | `test_d452_artifacts_list_an_old_real_run_row_and_a_new_one`; node `E31 (D452, review R1-6)` evaluates the page's own expression on 4 rows |
| R1-7 (P3) dead helpers | fixed: `p32_card`, `p35_again` deleted | 30fa953b | n/a |
| R1-8 (P3) checks refusals lost | fixed | 30fa953b | `test_d452_a_real_runs_checks_must_name_done_when_items` (item 9, empty) |
| R1-9 (P3) AC-29 hand copy | fixed: parent saved and summarised, follow-up via `J2Run.rehydrate`; the test points the engine package's `j2`/`j2_types` at this module's copy (the cause of deviation 9: another test module's fresh copy sat there, so rehydrate did not know the folder type) | 30fa953b | `test_p46_a_follow_up_never_reruns_a_parents_real_run`; mutation `_ran_real_run` → False: 1 fail |

Deviation: R1-2's net no longer lives in `_write_summary`; the only other caller (owner override "ship") takes `_ship_outcome`, already guarded. The net replaces a "Done:" outcome by the reasons alone (the old text claimed the work passes).

Results (round 1): `vendor_j2.py --check` 527 files ok, `port_j2_ui.py --check` ok (57 anchors) after each change. `scripts/gate.sh`: 4 failed, 13629 passed, 389 skipped (14m53s); the 4 are the known main failures listed above. Desktop `npm test`: 134, 133 pass, 1 skipped. `node --test tests/ui/js/`: 1750, 1748 pass, 2 skipped.
Lines vs origin/main: sutra_app + scripts without .md +888 −1301 (413 net fewer); tests +716 −944 (228 net fewer). `j2.py` 13641 lines.
