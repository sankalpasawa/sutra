# J2S4-l as built: the legacy flow test follows prototypes/j2 (lane L)

Owns `tests/engine/legacy/*`, `tests/engine/test_engine_legacy.py`, the comment of `scripts/engine_gate.sh`, this note.
Spec: `docs/design/j2-sync-4.md` 2.8 and 5.3 (L1, L2); D150. The J2 source is the folder `prototypes/j2` of this repository, extracted with
`git archive <commit> prototypes/j2 | tar -x --strip-components=2 -C <empty folder>`. The pin moved while the lane ran, from `00efb179` to
`025e265c594564f47a2365874cd5a5cc5d0d20a6` (the studio redesign); everything below is at the new pin.

## What was built

- **The flow test, merged in two steps inside this repository's history.** No commit of this repository holds the file the port was made from: the
  closest of the 42 versions of `prototypes/j2/j2_flow_test.py` in any ref is 1,242 changed lines from the port, whose own edits are 164 lines, so no
  history file is a merge base.
  Step 1 (to `00efb179`) was therefore built from the difference between the pinned file and the committed port, hunk by hunk (190 hunks: 82 are the
  port's own mechanical edits and stay, 10 are J2 additions, 77 are J2 edits of existing lines and are taken through the port's rewrites, 17 sit next
  to a guard and were merged by hand, 4 are guards of the port that stay). Step 2 (to `025e265c`) is a clean three-way merge: base = the file of
  `prototypes/j2` at `00efb179`, ours = step 1, theirs = the file at `025e265c`; no conflict. The proof, by multisets of lines, for each step: against the
  pinned file the result differs only by the port's 126 added lines and 38 J2 lines the port replaces (`REAL_MEMORY` and its fingerprint, `get("/")`,
  the git and `claude` CLI comparisons, `run_list`, `view_page`); against the step before, every added line is J2's text.
- **Port edits beyond the old ones** (all in `j2_flow_test.py`): `server_run_list()` for J2's `j2_server.run_list()` (the stdlib adapter has none;
  `engine/runlist.py` holds the logic, D140); `views.view_page` for J2's `j2_server.view_page` (the engine's one implementation, D25); the `skippable`
  wrap list gains the blocks that read the page, Chrome or saved runs (`simple_redesign`, `plan_map_view`, `chat_panel`, `function_chat`, `view_kept`,
  `run_settings`, `artifacts_groups`, `agent_views`, `agent_views_page`, `studio_views`); `map_tab` compares the two mock runs when the checkout has no
  saved run at all (still failing when only one of J2's two is there); `left_bar` skips with a reason when there is none. `realization_test.py` takes
  J2's one new check (merged cleanly); `change_test.py` and `j2_replay_size.py` did not change.
- **`EXPECTED.json`**: the pin, the sha256 of the pinned flow test, the minimums (flow 70 `ok` lines without a checkout, 109 with an extraction;
  change 192; realization 98) and `skip_lines_with_extraction` (the 14 lines the saved-run blocks print against an extraction; no line that depends on
  whether Chrome is installed).
- **`test_engine_legacy.py`**: the pin test asserts the new commit and that `VENDORED.md` names the same one; the list of twelve J2 blocks is checked
  statically (defined, called by the main flow, the ten that need the page in the wrap list) and by running the flow (`SUTRA_J2_CHECKOUT` an extraction
  whose flow test has the recorded sha256): every block prints its line and none stops at the page, and the skip lines appear. `engine_gate.sh`
  says what the checkout is.

## Measured

| Run | Result |
|---|---|
| `j2_flow_test.py --fast`, no checkout | `j2 flow checks passed`, 70 lines ending ` ok`, 63 s |
| the same, `SUTRA_J2_CHECKOUT` = a fresh extraction of the pin | `j2 flow checks passed`, 109 lines ending ` ok`, 106 s |
| `SUTRA_SLOW=1 SUTRA_J2_CHECKOUT=<extraction>` on `tests/engine/test_engine_legacy.py` | 28 passed, 1 skipped (the browser run, `SUTRA_BROWSER=1`), 185 s |
| `change_test.py`, `realization_test.py` | 192 and 98 checks |

These ran on the integration branch plus lane B's tip (built with `git merge-tree`, nothing merged into this branch): lane B's tip merged into this
branch conflicts in `scripts/record_api_shapes.py`, the file lanes A3 and B share, which is the integrator's to resolve. On this branch alone the flow
fails at exactly two blocks, `decide_for_me` (`POST /api/settings`) and `studio_views` (`GET /view`, `/doc/<kind>`, `/api/record`, `views.view_page`):
J2's server answers them, the engine adapter does not until lane B is merged.

## What J2's blocks need, and what is guarded (extraction of the pin: page and harness yes, saved runs no, Chrome no)

| Block | Needs | With the extraction |
|---|---|---|
| `late_judge_run`, `decide_for_me`, `studio_model` | the engine only (`decide_for_me`: lane B's `/api/settings`) | runs through |
| `plan_map_view`, `simple_redesign` | the page and its render harness; `simple_redesign` also loops over saved runs and Chrome (`--browser`) | runs through (0 saved runs, 7 live states) |
| `studio_views` | HTTP on the adapter (lane B's routes), then the render harness | runs through |
| `chat_panel`, `function_chat`, `view_kept`, `run_settings` | the page; their real-page steps need Chrome, `--browser` and saved runs (`run_settings`: 50 or more) | the static checks run, the rest prints why it did not |
| `artifacts_groups` | the page for its static checks; run `j2-20261103-132506` for the rest | static checks; skip line |
| `agent_views`, `agent_views_page` | three saved test runs; Chrome for the page helper | skipped (the producer is proved on this tree's own mock runs by other lanes) |
| `left_bar`, `graph_map`, `map_shapes`, `map_tree`, `map_every_workflow`, `replay_size`, `rules_split` | saved runs | skip lines (listed in `EXPECTED.json`) |

## Deviations from the design, and what is left

- The merge base and the saved-run folder of design 2.8 are not used (owner instruction: the only J2 source is `prototypes/j2`): the base is built from the
  diff, then the old pin's file; `SUTRA_J2_CHECKOUT` is the pure extraction, not a composite with `runs/`.
- Design 6.2 step 7 expects an ` ok` line for each of eight named blocks; `late_judge_run` and `plan_map_view` print J2's lines without the ` ok`, so the check
  is the first words of each block's line, for twelve blocks. `flow_fast_ok_lines` is the no-checkout count (the number the gate and the default test meet);
  the extraction count is its own key.
- Not run here: `--browser` (Chrome and the real page steps), a Windows run. `j2_flow_test.py` still ends `j2 flow checks passed`; its saved-run and Chrome parts
  are exactly the skips above, so a J2 saved-run corpus brought into the copy later turns them on without a change of this file.
