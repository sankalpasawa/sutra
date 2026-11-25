# Implementation: the centre panel shows any output, not only websites

Branch: `sut-27-output-agnostic-result`. Commands run from `sutra-pro/`.

## Steps

| step | status | commit |
|---|---|---|
| T1 pure core and fixtures | done | `SUT-27: D450 the pure core of result_view.js and a script-run fixture, not loaded by the page yet` |
| T1 follow-up | done | `SUT-27: D450 the real-run result is read from the receipt row's own result and run_output keys` |
| Q-4 docs | done | `SUT-27: D450 Copy share link is hidden with no main file or a real-run result (Q-4, docs)` |
| T2 tabs, viewers, page line | done | `SUT-27: D450 the page loads result_view.js; every run gets Result, Files, How it was made, and each file opens in its viewer` |
| T3 plan cards and wording | done | `SUT-27: D450 finished plan cards show the builder's line and their files; wording follows the output` |
| T4 finish bar and share link | done | `SUT-27: D450 the finish bar downloads the main result on non-page runs, and a copied link says it opens on this computer only` |
| T5-T6 | not started | |

### T1

| file | what |
|---|---|
| `sutra_app/ui/static/js/result_view.js` (new) | IIFE, one global `ResultView` (node: `module.exports`), avatars.js shape. `isPageRun`, `done`, `realRun`, `named`, `mainResult`, `viewerFor`, `summaryOf`, `filesOfPart`, `table`, `jsonTable`, `label`, `WORDS`, `MAX_ROWS`; `adopt` is a stub returning false. Not in `MODULES`, so the page does not load it yet. |
| `tests/ui/js/result_view.test.js` (new) | 13 node tests over the pure core (AC-5, AC-10, AC-11, FR-7/8 parse, FR-17 wording, FR-20) |
| `tests/ui/fixtures/result_view/state-script.json` (new) | hand-built done script run: output `env_report` (form `agent`, file `env_report/*`), W-1 plan, W-2 with `real_run.result: "report.txt"`, one W-2 message "@Coordination I wrote env_report/report.py. It prints the environment." |
| `tests/ui/fixtures/result_view/artifacts-script.json` (new) | two `env_report` rows (`report.py`, `report.txt`), `workflows: ["W-2"]`, same `name` |
| `tests/ui/fixtures/result_view/real-runs-script.json` (new) | W-2 real_run receipt row in two shapes: `today` (stdout tail in `output`, no `run_output`) and `p45` (the same plus top-level `run_output`, `result`, `created`/`changed`/`deleted`/`files_truncated` and a `dry_run`) |
| `docs/ai/...` | analysis.md and the task folder added; spec.md, architecture.md, plan.md amended for the plan-review decisions (change-log lines in spec and architecture) |

### T2

| file | what |
|---|---|
| `scripts/port_j2_ui.py`, `tests/ui/test_port_edits.py` | `MODULES`: `"result_view"` between `"budget_chip"` and `"dept_ext"` |
| `sutra_app/ui/pages/j2_ui.html` | +1 line, `<script src="/ui/js/result_view.js"></script>` before `dept_ext.js`, written by the port. J2 extracted at the engine's pin (`git archive ee659fb5 prototypes/j2`); `port_j2_ui.py --check` on the base exited 0 ("54 anchors ... 7 committed files equal a fresh port"), then the port ran without `--check`; only j2_ui.html changed |
| `sutra_app/ui/static/js/result_view.js` | `adopt(root)`: checks the page functions (`renderSimple`, `sViews`, `sLoad`, `paint`, `sTeamwork`, `sSkTime`, `sDecorate`) and the page consts (`SV`, `esc`, `runQ`, `isReady`, `sNoun`); adds `#rvpane` (`#rvbody`, empty `#rvlater`) in `#sout` and the stylesheet link; replaces `sViews` (try, else the page's own) and `sGo` (below). Tabs Result / Files / How it was made, default by `done`, pick kept, `file:<path>` with an "All files" back button, unknown picks map to Result. Viewers: site and frame through `sLoad` (the page's sandboxed frames, unchanged); text, code, CSV/TSV, JSON painted escaped into `#rvbody` from `/api/artifact`, cached per `file + sha256`; a failed fetch shows the FR-7 line |
| `sutra_app/ui/static/css/result_view.css` (new) | pane, header bar above a framed file, `<pre>`, numbered code (CSS counters), table with sticky header and its own scroll, `.sframe.rvpane .sprev{visibility:hidden}`; page `--s-*` tokens only |
| `tests/ui/js/result_view.test.js` | 12 glue tests on a vm stub of the page (the module loads after it, as on the page) |

### T3

| file | what |
|---|---|
| `sutra_app/ui/static/js/result_view.js` | pure `team(html, s, rows)`: on the page's "How it was made" HTML, a `.spart[data-part]` card not `doing`/`fix` loses its `.sl` bars; a `done` one gets `<small class="rvsum">` (`summaryOf`, escaped) and `<span class="rvfiles">` with one `<span class="rvfile" data-view="file:<file>">` per `filesOfPart` row; placeholder cards (no `data-part`) untouched; on a run that is not a page run the "What you got" site line goes, and its section if empty. Wrappers (page's own first, ours adjusts its result; on a throw the page's result): `sTeamwork` (→ `team`), `sPhase` ("Checking it on a phone and a laptop" → "Checking the work"), `sOpenPart` ("The part, on the page." → "The part, in the result." in `#sdbody`), `renderSimple` (`#sopen` hidden). Toasts restored as the page's own on page runs |
| `sutra_app/ui/static/css/result_view.css` | `.rvsum` one line with ellipsis; `.rvfiles` / `.rvfile` |
| `tests/ui/js/result_view.test.js` | 8 tests: cards (AC-11, AC-12, escaping), website vs script "What you got", glue for `sTeamwork`, `#sopen`, `sPhase`, `sOpenPart`, throwing helpers, page-run toasts (website and document set; none on a script), and the FR-18 string scan of `#sviews`, `#surl`, `#steamwork`, `#rvbody` on the done script run over every tab |

### T4

| file | what |
|---|---|
| `sutra_app/ui/static/js/result_view.js` | `sFinish` replaced: a page run (website, document set) gets the page's own, byte for byte; any other run gets the page's phase line, then a Download of the main file (`/api/artifact?name=<file><runQ>`, `download="<basename>"`), or "All files (N)" (`data-view="files"`) when Result is the Files list, or nothing; Copy share link only with a main file (Q-4); Open full view as the page's. The `renderSimple` wrapper redraws `#sfinish` on non-page runs when ready and the bar's HTML changed (`/api/artifacts` arrives after the run turns ready), and clears the hidden `#sopen`'s `/site/latest` href. A capture-phase listener on `#sfinish` handles `[data-share]` on every run: a page run copies `/site/latest` as today, any other run the main file's `/view` link; the button reads "Link copied — opens on this computer only", back to "Copy share link" after 2.5 s; `stopImmediatePropagation` keeps the page's own listener out |
| `tests/ui/js/result_view.test.js` | 6 tests: one file (Download, share), two files, no files, real-run result (through a stubbed `/api/artifacts/groups`), page runs byte for byte, redraw on arrival and no rewrite on an identical render, failed run left to the page, share URLs and note for a script and a website |
| `tests/ui/test_dept_page.py` | new browser test `test_a_script_run_shows_its_files_and_no_site_words` (1280x860, 375x812): the fixture laid over J2's captured snapshot and `/api/artifacts` replaced through the fake's cache; tabs, Result selected, two files with their Download links, finish `["All files (2)"]`, no site/page/website in `#sstage`, `#sopen` not drawn, no `/site/` link or frame in `#sview`, no page-wide horizontal scroll, no console error or failed request. Existing tests unedited |


## Deviations

| what | why |
|---|---|
| Main-result step 1 rebuilt as `realRun(s, runs)`; `mainResult` takes a third argument `runs` and can return `{kind: "real-run", workflow, result, link}` | owner decision at plan review (Q-1): `real_run.result` is a path in the user's folder, never matched against outputs; its text comes from P45's `run_output/<id>.json`, linked as the receipt row's `run_output` (owner update; `output`, today's 1,500-char stdout tail, is never read as a link). Strict link regex `^run_output/\w[\w.-]*\.json$`. The workflow's last receipt row decides (a later tail row hides an earlier link). `named(s)` now returns only the concrete entry file (string), not a list. |
| Owner update during T1: the link key is `run_output` on the receipt row, not `output` | `realRun` reads only `run_output`; a unit case pins that a link-shaped `output` is ignored; spec, architecture, request (plan-review section) and plan updated. Folded into the single T1 commit (unpushed, amended) |
| P45 confirmed (second commit): step 1 reads the receipt row's own `result` and `run_output`; each workflow's last row, the last in plan order, rows for workflows not in the plan ignored; `workflows[].real_run.result` no longer read | owner update. Confirmed keys: `run_output` (`run_output/<receipt-id>.json`), `result` (from the proposal, else the entry_file fallback, resolved by the engine), and the real run's own `created` / `changed` / `deleted` / `files_truncated` in the `dry_run.*` format; `output` stays the 1,500-char tail (pending Kaivan's final key list once built) |
| No `folderChanges(row)` reader | the coordinator preferred documenting; architecture.md Later names the keys. The "dry_run has created, top level none" case is covered by `realRun` returning only `{workflow, result, link}` and a unit case where `dry_run`/`expect` carry a `result` that is not read |
| `files_truncated: false` in the p45 fixture | `dry_run` has no such key today (j2.py:974-977, `_tree_diff` gives only created/deleted/changed); a boolean is assumed |
| Third fixture `real-runs-script.json` (plan named two) | the coordinator asked for fixtures holding both receipt-row shapes (today's and P45's) |
| `label` returns "result" before done on a non-page run, "no files" when done with zero outputs | the spec names only "the main file's name, or files"; these two cases had no string |
| `WORDS.showing(n, total)` is a function | the row counts are part of the string |
| request.md: "Approved by <name>" → "Approved by the owner" | no owner names in committed files |
| plan.md T4 text: share URL is now the main file's `/view` link | Q-3 answered at plan review; plan said "unchanged" |
| T2: `sGo` wrapped (not in the plan's list) | the page's `sGo` looks for a J2 tab per document (`sTabs`); with the three tabs an unknown tab key never becomes the view, so `sGo` would re-call itself every 600 ms forever. On a run that is not a website it now opens the part's record (`sOpenPart`); a website keeps the page's own (the module sets `SV.view = "site"` while the site shows, so `sGo` and `sDecorate` work as today) |
| T2: a website run (page run, no docset, `versions > 0`) always shows its site in Result | same as the main-result rule's answer for a website (entry file `site/index.html`), without waiting for `/api/artifacts`; avoids a flicker to "no files" before the rows arrive |
| T2: a real-run result shows its name and the FR-7 line | P45's route does not exist; marked `ponytail:` in the code |
| T2: `/api/artifacts/groups` fetched only when the run is done and its plan has a real run, once per `SV.akey` | the hook costs no request on other runs |
| T2: docset toasts ("The X is being written") dropped | reverted in T3 (coordinator): page runs get the page's own toasts again, computed with the page's `sTabs` (a website's "taking shape", a document set's "being written"); other runs none |
| T2: two short strings with no spec text: "Opening…" (fetch in flight) and "No preview for this kind of file." (download viewer) | needed a body; no site/page word |
| T3: cards decorated as an HTML string by wrapping `sTeamwork`, not DOM decoration after `renderSimple` | the page `paint`s `sTeamwork`'s string and skips an unchanged one, so decorating the string is idempotent (no duplicate lines on a skipped paint) and testable without a DOM; the page's own render is still not copied |
| Owner, during T2: the "Link copied" note shows on website runs too (FR-19 stands) | resolved in T4: built so, spec.md FR-19 says so |
| T4: the browser test's state is the script fixture laid over J2's captured snapshot (not the fixture alone) | the page reads many keys the hand-built fixture does not carry (budget, agents, ...); the fixture's keys win |
| T4: `#sopen`'s href set to `#` on non-page runs | it is hidden, but its `/site/latest` href was the one `/site/` link left in the panel (AC-13) |
| T4: a real-run result has no Download in the finish bar | P45's route does not exist; the result is a file in the user's folder |

## Tests

| command | result |
|---|---|
| `node --test tests/ui/js/result_view.test.js` | 13 tests, 13 pass, 0 fail |
| `scripts/py -m pytest tests/test_ownership.py tests/ui/test_node_suite.py -q` | 10 passed (the node suite runs every `tests/ui/js/*.test.js`, the new file included) |

T2:

| command | result |
|---|---|
| `node --test tests/ui/js/result_view.test.js` | 25 tests, 25 pass |
| `node --test tests/ui/js/page_render.test.js` | 54 tests, 53 pass, 1 skipped (needs `SUTRA_J2_CHECKOUT`); with `SUTRA_J2_CHECKOUT=<the extraction>`: 54 pass. Goldens and `tests/ui/fixtures/j2/` unchanged |
| `scripts/py -m pytest tests/ui/test_port_edits.py tests/ui/test_serve.py tests/test_ownership.py tests/ui/test_node_suite.py -q` | exit 0; 363 passed, 5 skipped (1 needs `SUTRA_J2_CHECKOUT`, 4 need `SUTRA_BROWSER=1`) |
| `SUTRA_J2_CHECKOUT=<extraction> scripts/py -m pytest tests/ui/test_port_edits.py -k fresh_port_of_the_real_j2` | 1 passed |
| `SUTRA_BROWSER=1 scripts/py -m pytest tests/ui/test_dept_page.py -k "one_way_to_each_thing or opens_its_record"` | 3 passed (website finish bar and part record unchanged; plan names no new browser test for T2) |

T3:

| command | result |
|---|---|
| `node --test tests/ui/js/result_view.test.js` | 33 tests, 33 pass |
| `SUTRA_J2_CHECKOUT=<extraction> node --test tests/ui/js/page_render.test.js` | 54 pass; goldens unchanged |
| `scripts/py -m pytest tests/ui/test_port_edits.py tests/ui/test_serve.py tests/test_ownership.py tests/ui/test_node_suite.py -q` | exit 0; 363 passed, 5 skipped (as T2) |
| `SUTRA_BROWSER=1 scripts/py -m pytest tests/ui/test_dept_page.py -q -k "one_way_to_each_thing or opens_its_record"` | exit 0 (3 tests; plan names no new browser test for T3) |

T4:

| command | result |
|---|---|
| `node --test tests/ui/js/result_view.test.js` | 39 tests, 39 pass |
| `SUTRA_J2_CHECKOUT=<extraction> node --test tests/ui/js/page_render.test.js` | 54 pass; goldens unchanged (E4 at :292-302 unedited) |
| `scripts/py -m pytest tests/ui/test_port_edits.py tests/ui/test_serve.py tests/test_ownership.py tests/ui/test_node_suite.py -q` | exit 0; 363 passed, 5 skipped (as T2) |
| `SUTRA_BROWSER=1 scripts/py -m pytest tests/ui/test_dept_page.py -q -k "one_way_to_each_thing or opens_its_record or script_run_shows_its_files"` | 5 passed (the website finish test at :886-899 unedited) |

Not run (owner rule): `scripts/gate.sh`, `scripts/live_smoke.py`, browser tests, beta install.

## Known gaps

- `realRun` never hits today: the `/api/artifacts/groups` `real_runs` projection (j2_artifacts.py:774-793) carries none of the P45 keys, and P45 lands after SUT-28. Hook only; how the text is fetched from `run_output/<id>.json` is decided when P45 lands.
- Q-4 answered by the owner (docs commit): Copy share link is hidden with no main file or a real-run result; built in T4.
