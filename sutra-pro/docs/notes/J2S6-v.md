# J2 sync 6, lane V: vendoring, patches, goldens, legacy test

_Branch `lane/s6-v` · Design: `docs/design/j2-sync-6.md` sections 5, 7 (lane V) and 11 · Source: J2 main `1adb8ecd8fa8eef47fb7a0fc63a1616f556cdfeb`, tree `9a7cb34c028248de7d3b436647f8baf39be6f77e`_

The decision texts below are in the shape of `docs/DECISIONS.md`; the integrator copies them in number order.

## D176 — The pin moves to J2 main `1adb8ecd`; the source stays the extraction of this repository's `prototypes/j2`
- Sources: D136, D154, D160, `docs/design/j2-sync-5.md`.
- Decided: `scripts/vendor_j2.py` takes `BASELINE = 1adb8ecd8fa8eef47fb7a0fc63a1616f556cdfeb` and tree `9a7cb34c028248de7d3b436647f8baf39be6f77e`; `VENDORED.md` names it "sync 6" (the header says "J2's main, not tagged"); the sync 5 pin (`1d537295`) joins `PREVIOUS_BASELINES`. J2 has not tagged the commit; its maintainers are asked (D189), and the tag name is added as a comment when they do. The tree is 516 files (the design said 514 plus two documents: the two documents are in the 516; `sutra_app/engine/seed` 437, `templates/` 25 with `library-settings.json`, 19 code modules with `j2_artifact_lib.py`). The seven commits labelled "needs owner review" are carried inert behind `J2_RUN_TEMPLATES` and `J2_AUTO_REUSE`.
- Why: the owner's task is "J2 sync 6"; the commit is a fixed point; the flag-off behaviour was measured byte-neutral (seven prompt goldens differ in `j2_commit` only).
- Rejected: waiting for a tag; vendoring a branch tip (D154); carrying only part of the span (the content door, the shelves and the run templates share `j2_template_lib.py`).
- Diagram: label "J2 pin: main 1adb8ecd", pill on band:DEPARTMENT RUNTIME.

## D180 — P1, P7, P8, P9 are re-anchored; P19 is new; the late-judge reserve is P20
- Sources: D13, D136, D145, D162, section 5 of the design.
- Decided: applies P2, P3, P4, P5, P11, P12, P14, P15 (still exactly six home paths), P16, P17, P18; conflict fixed P1 (`CODE` gains `j2_artifact_lib.py`; `P1_COUNTS` `j2.py` 15, `j2_artifact_lib.py` 1: the rule changes **42** lines, not 41 as the design said: 40 + 2), P7 (the planner expression, one statement), P8 (the run-end anchor now includes the `_make_report` line), P9 (`call_delay()` in the delay lines of `call` only); extended P10 (D181); new P19 (the reviewer switch). The reserve of D145 moves from P19 to P20.
- Why: every changed anchor is explained by a J2 change; the reviewer switch is the one place where J2 gives the host no seam.
- Rejected: dropping P8's run-end hook; a regex for P7/P8/P9 (an anchor that stops the run when J2 moves is the safety).
- Diagram: label "patch table P1-P19", pill on band:DEPARTMENT RUNTIME.

## D181 — P10 covers the two runtime writers J2 added: `note_version` and `mark_run_template_used`
- Sources: D26, D142, P10, J2 `j2_template_lib.py`.
- Decided: both are wrappers that take `_library_lock()` around the original, kept as `_note_version` and `_mark_run_template_used`, as `store` and `mark_used` are. `save_run_template`, `move_versions` and the `__main__` commands are developer tools and stay unpatched; `collect` is run by the host under the lock. Tests: `tests/engine/test_engine_library_lock.py` has a static test (over `j2_template_lib.py`) that exactly the four wrappers take the lock and that none of them (and not `collect`) can reach a function that takes it, a guard that no other function writes the index (`_save_index`) outside the lock, a busy-lock test for the two new writers and a two-process test (one run template used 25 times while 25 versions get notes: no row lost).
- Why: both read the index, change it and write it back; two runs adapting templates or using one run template could lose a row.
- Rejected: one lock around the whole of `route` (deadlock for 30 s); a Sutra-side lock in the host.
- Diagram: label "library lock covers 4 writers", pill on Template library.

## D190 — Goldens and fixtures move only through the recorders; `J2_RUN_BY` is pinned in every recorder
- Sources: D150, D174, R5.
- Decided: the recorders (`record_engine_golden.py`, `record_api_shapes.py`, `record_fn_golden.py`, `capture_j2_fixtures.py`) set `J2_RUN_BY=sutra-pro` and `J2_PUSH_RUNS=0` in the environment they build, and keep both out of the recorded `env` (so a golden is not changed by the pin). Measured: the seven prompt goldens differ from their predecessors in `j2_commit` only; `record_fn_golden --check` is current; `api_shapes.json` changes in `j2_commit` and in the keys of `get.*.catalog`, `library`, `library_item` and `run_templates` (new shelf, artifacts, run template and provenance keys) and nowhere else. The legacy flow test is a three-way merge again (base: J2's file at `1d537295`, ours: the sync 5 copy, theirs: the extraction): 0 conflicts. `change_test.py`, `realization_test.py` and `j2_replay_size.py` did not change upstream. `EXPECTED.json` records the pin, the new hashes and the numbers.
- Why: the goldens are the proof that the pin changed nothing a team can see with the flags off.
- Rejected: re-recording by hand; carrying files without a ruling.
- Diagram: label "goldens by recorder only", pill on band:DEPARTMENT RUNTIME.

## D192 — The diff of record decides every new file; two reference documents and two tests are carried
- Sources: D161, D154, `scripts/j2_diff_of_record.py`.
- Decided: `hardcoding-inventory.md` and `library-reuse-order.md` join `REF_DOCS` (carried, byte copies); `artifact_lib_test.py` and `content_door_test.py` are carried as legacy copies (`tests/engine/legacy/`, `LEGACY_NAMES`) because the merged flow test does not exercise `j2_artifact_lib` (no mention of it; checked by search and by the 77 checks the two scripts add), with the engine imports and J2's committed library read as the engine's seed library; `fixtures/folder-run/**` is excluded (named, with a reason): it is test data of the flow test's `folder_reuse`, read from `SUTRA_J2_CHECKOUT`; `j2_server.py` and `j2_ui.html` stay as before. `j2_diff_of_record.py --check` reports 0 undecided.
- Why: a file without a ruling is how a sync forgets something.
- Rejected: carrying J2's server; skipping the content-door tests (they are the only tests of that module).
- Diagram: none (tooling).

## What I measured

- `vendor_j2.py --check` against the extraction: 516 files, ok. `j2_diff_of_record.py --check`: 0 undecided, 0 stale; its only FAIL line is `port_j2_ui.py --check` (the page is lane U's).
- Prompt goldens (7): each differs from its predecessor in `j2_commit` only (call counts, spend and hashes unchanged: 28/29/24/17/73/24/25 calls). `record_fn_golden.py --check`: current. `api_shapes.json`: `j2_commit` and the keys of `get.idle|live|saved.catalog` (80 to 169), `library` (49 to 51), `library_item` (82 to 134, idle) and `run_templates` (31 to 32, live and saved); 42 routes x 3 modes, 11 POSTs as before.
- Legacy flow test (`--fast`, 98 lines ending " ok" without the extraction, 150 with it; both end "j2 flow checks passed"); `change_test.py` 192 and `realization_test.py` 98 checks as before; the two content-door scripts 33 and 44 checks. J2's own `map_focus`, `graph_map`, `warm_ui` blocks stay pinned as known upstream failures; with the extraction at this pin `warm_ui` and the others print their own lines or their saved-run skip.
- The legacy copy: 11 new J2 blocks arrived by the merge (`auto_reuse`, `delay_setting`, `folder_reuse`, `library_cleanup`, `reuse_display`, `review_after_result`, `run_templates`, `section_checks`, `sutra_library`, helpers `d_facts` and `run_templates_page`); the merge brought J2's own `os.path.dirname(os.path.abspath(__file__))` paths back, so they were redirected to `HERE`/`page_file` (a skip with a reason without the extraction), their bare sibling imports made `sutra_app.engine`, and `sutra_library` (a) (J2's repository layout: a link at the top) prints a skip in an extraction. Eight of the blocks sit in the `skippable` list.
- Reviewer race: `test_p8_a_hooked_run_pairs_every_turn_start_with_its_finish` and `test_p7_the_reviewer_and_the_summariser_are_tagged_and_unlogged` failed intermittently once J2's report writes moved after `waiting` (as the design said); the test helpers now join `review_thread`. `test_engine_patches.py` passed 18 of 19 consecutive runs before that was understood and 12 of 12 after.
- Legacy runs of J2's flow test are slow (about 25 minutes per run) when `git config user.name` is executed per run: `test_engine_legacy.py` now passes `J2_RUN_BY=sutra-pro` and `J2_PUSH_RUNS=0` to its children (D190), as the engine host does.

## For J2's maintainers (design section 11, reported, not patched)

1. The seven "needs owner review" commits of `j2.py` (run templates, auto-reuse) are carried inert; please review, and tag `1adb8ecd`.
2. `GET /api/run-template` reads `J2_RUN_TEMPLATES`/`auto_reuse()` from the server's `os.environ`; a host with per-team settings needs the value as an argument or a callable (`j2_server.py`, the `run-template` route).
3. The reviewer thread (`J2Run._make_report`, `_review_later`) is unnamed and cannot be awaited; a public `join_review(timeout)` and a thread name with the host's prefix would avoid the race. No placeholder text exists for a skipped reviewer (P19 adds one in the copy).
4. `note_version` and `mark_run_template_used` (`j2_template_lib.py`) write the library index without a lock (the copy wraps them, P10); so do `save_run_template` and `move_versions`.
5. `set_run_template` returns `False` silently for a flag-off, an unknown id and a started run (`j2.py`, `J2Run.set_run_template`).
6. `run_author()` runs `git config user.name` at every run start and writes the result into `chat.jsonl`; a personal name goes into run data unless `J2_RUN_BY` is set.
7. `J2_PUSH_RUNS` pushes with the user's credentials; it is the only flag that writes outside the data folder.
8. `catalog_view()` reads Shelf 1 from `J2_RUNS_DIR` while the library is one global store; a host with per-team runs needs a runs-folder argument.
9. `AUTO_MIN` 0.6, `AUTO_WEIGHTS`, `VAGUE_TYPES`, `run_slots`/`_noun` and the `style.json` lookup remain in code; `NOT_CHECKABLE`, `ACTION_GOAL` and the other group-A rows are fixed on `fix-run-blockers` but not in main; the 547-row inventory is carried as `docs/reference/j2/docs/hardcoding-inventory.md`.
10. `j2_template_lib.py` `shelf_view` says "GET /api/shelf: not there yet"; the shelves have no J2 caller but `catalog_view`.
11. (found by lane V) `j2_flow_test.py` blocks added in this span open J2's own files with `os.path.dirname(os.path.abspath(__file__))`; a copy of the script in another folder, or an extraction without `library/`, fails instead of skipping. `content_door_test.py` and `artifact_lib_test.py` import J2's flat modules (fine in J2, needs a port elsewhere).

## Deviations from the design

- P1 changes 42 lines, not 41 (the design's total was 40 + 1; the extra line is the one in `j2_artifact_lib.py`: 40 + 2). `P1_COUNTS` is the script's own count and the vendoring passes with it.
- The seed index has five `/tmp/...` library values (`j2-auto-lib`, `j2-live-library`, `j2-live-library-2` and `j2-rt-lib` twice) next to the six scrubbed ones; the design said P15 finds exactly six home paths, which still holds.
- `scripts/engine_gate.sh` (not a lane V file) runs only the four old scripts; the two new legacy scripts run in `tests/engine/test_engine_legacy.py` only.

## Lane files that other lanes need to know about

- `tests/engine/test_engine_patches.py` and `test_engine_library_lock.py`: `J2_MODULES` lists `j2_artifact_lib`; the run helpers wait for J2's reviewer thread (`review_thread`) before they read the folder, as the host will (D179).
