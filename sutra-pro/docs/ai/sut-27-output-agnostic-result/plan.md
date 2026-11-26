# Plan: the centre panel shows any output, not only websites
Branch: sut-27-output-agnostic-result (already cut from origin/main at f21add06)

Inputs: spec.md (Refined), architecture.md. Commands run from `sutra-pro/`.

## Rules for every step

| rule | detail |
|---|---|
| one commit per step | message `SUT-27: D450 <plain sentence>`, repo git identity, no Co-Authored-By trailer |
| stay out | nothing in impact.md §6, no `engine/views.py`, no `engine/api/*`, no `host/`, no `j2.py`, no `j2.css`, no `tests/ui/fixtures/j2/*`, no hand edit of `j2_ui.html` beyond the E12 line |
| tests | targeted only; never `scripts/gate.sh` (the owner frees it); never `scripts/live_smoke.py` |
| beta | never install; ask the owner first |
| push | none |
| paths | no home path, no owner name in any file (`tests/test_ownership.py`) |
| tests first | write each step's tests before its code where practical |

## Steps

| step | goal | Impact | Effort |
|---|---|---|---|
| T1 | pure core and fixtures | high (all choice logic) | ~200 lines, 1-2 h |
| T2 | load the module; three tabs and the viewers | high (request items 1-3) | ~220 lines, 2-3 h |
| T3 | plan cards and wording | medium (items 4-5) | ~120 lines, 1 h |
| T4 | finish bar, share note, browser test | medium (items 2, 5) | ~150 lines, 1-2 h |
| T5 | decision D450 | low (record) | ~15 lines, 15 min |
| T6 | final targeted run; hand over | n/a | 20 min |

- [x] T1: The pure core of `result_view.js` and the script-run fixture, not loaded by the page yet
  - Files: `sutra_app/ui/static/js/result_view.js` (new), `tests/ui/js/result_view.test.js` (new), `tests/ui/fixtures/result_view/state-script.json` (new), `tests/ui/fixtures/result_view/artifacts-script.json` (new)
  - Change: an IIFE with one global `ResultView` (node: `module.exports`), same shape as avatars.js:26-29, :227-229. Functions exactly as architecture.md "Interfaces": `isPageRun`, `done`, `named`, `realRun`, `mainResult`, `viewerFor`, `summaryOf`, `filesOfPart`, `table` (CSV/TSV with quotes; null on an unterminated quote; 1,000-row cap with `total`), `jsonTable`, `label`, and the `WORDS` object (FR-17 strings). `adopt` is a stub returning false. Fixtures hand-built per architecture.md "Data model" (keys copied in shape from `fixtures/j2/state.json` and `artifacts.json`, values invented; no real run).
  - Tests: `isPageRun` (website fixture true, script fixture false, docset true, `output: null` false); `mainResult` (AC-10 cases, incl. a real-run result from the receipt row's own `result` and `run_output/<id>.json` link, a row with `run_output` but no `result` (skipped), the same with only a stdout-tail `output`, a link-shaped `output` but no `run_output`, or no receipt row (skipped), a glob entry file, a name not among outputs, `site/index.html` entry file with two rows); `viewerFor` (AC-5 table); `summaryOf` (AC-11 "@Coordination Wrote the script. It prints env vars." → "Wrote the script."; none → "Finished."; uses the last message of the part's workflows); `filesOfPart`; `table` (quotes, bad CSV → null, 1,500 rows → 1,000 and total 1,500); `jsonTable` (array of objects, object → null, bad → null); `WORDS` values for non-page keys hold no `/\b(site|page|website)\b/i`.
  - Done when: `node --test tests/ui/js/result_view.test.js` and `scripts/py -m pytest tests/ui/test_node_suite.py tests/test_ownership.py -q` pass
  - Covers: FR-5, FR-7 (parse), FR-8, FR-10, FR-11, FR-13 (text), FR-14 (data), FR-20, NFR-5

- [x] T2: The page loads `result_view.js`; every run gets Result, Files, How it was made, and each file opens in its viewer
  - Files: `scripts/port_j2_ui.py` (`MODULES`: `"result_view"` between `"budget_chip"` and `"dept_ext"`), `tests/ui/test_port_edits.py` (its `MODULES` mirror, same place), `sutra_app/ui/pages/j2_ui.html` (one line), `sutra_app/ui/static/js/result_view.js`, `sutra_app/ui/static/css/result_view.css` (new), `tests/ui/js/result_view.test.js`
  - Change:
    1. The page line: extract J2 at the engine's pin (`sutra_app/engine/VENDORED.md` line 3) into a fresh temp folder and run `scripts/py scripts/port_j2_ui.py --j2 "$J2SRC" --commit <pin> --check` on the base first. If it exits 0, run the port without `--check` after the `MODULES` edit. If it does not, add exactly the line E12 writes, `<script src="/ui/js/result_view.js"></script>`, before the `dept_ext.js` tag (what commit fd7bc2f6 did for avatars) and say so in the commit body.
    2. `adopt(root)`: needs `renderSimple`, `sViews`, `sLoad`, `paint`, `sTeamwork`, `sSkTime`, `sDecorate` on `root` and `SV`, `esc`, `runQ`, `isReady`, `sNoun` by bare name (`typeof` guarded); else returns false. Adds `<div id="rvpane" hidden>` with an empty `#rvlater` slot inside `#sout`, and the stylesheet link (avatars.js:220-225 pattern).
    3. Replaces `root.sViews` per architecture.md: tabs `result`/`files`/`team` with `role="tab"` and `aria-selected`; default per FR-2; `SV.pick` kept (FR-3), `file:<path>` opens Files on that file with an "All files" back button, unknown picks map to `result`; Result per FR-4, FR-10, FR-12; Files per FR-9; viewers per architecture.md table (frame viewers through `sLoad`, others painted in `#rvpane` from `/api/artifact` text cached by `file + sha256`; failure line per FR-7); `#sframebox` class `rvpane` hides the frame while `#rvpane` shows; `#surl` from `label`; no toast on non-page runs, today's toast text on page runs; team tab calls `sTeamwork` + `sSkTime` as today.
    4. `result_view.css`: tabs pane, `<pre>`, numbered code (CSS counters), table with sticky header and horizontal scroll inside the pane, the "can't be shown" line, `#sview .sframe.rvpane .sprev{visibility:hidden}`. Uses the page's `--s-*` tokens; no font import.
  - Tests (glue, a vm page stub in the style of avatars.test.js): adopt on a stub with the needed globals; website fixture done → three tabs, Result selected, `sLoad` got `/site/v5?x=1...`; running website → team selected, Result picked loads the live site; running script → placeholder line; done script (two rows) → Files list in Result, Files shows two entries each with Download; one-row variant → `/api/artifact` fetched once over two renders; `.txt` with `<b>x</b>` → escaped; 404 → the FR-7 line; pick `files` kept across renders; saved script → no URL starting `/site/` passed to `sLoad` or fetch; `output: null` → no throw; missing global → `adopt` false and `sViews` untouched.
  - Done when: `node --test tests/ui/js/result_view.test.js tests/ui/js/page_render.test.js` and `scripts/py -m pytest tests/ui/test_port_edits.py tests/ui/test_serve.py tests/ui/test_node_suite.py -q` pass, with no change under `tests/ui/fixtures/j2/`
  - Covers: FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7, FR-9, FR-12, FR-21, FR-22, NFR-1, NFR-2, NFR-3

- [x] T3: Finished plan cards show the builder's line and their files; wording follows the output
  - Files: `sutra_app/ui/static/js/result_view.js`, `sutra_app/ui/static/css/result_view.css`, `tests/ui/js/result_view.test.js`
  - Change: wrap `root.renderSimple` (after the original, in `try`): in `#steamwork`, every `.spart[data-part]` that is not `.doing`/`.fix` loses its `.sl`; `.spart.done[data-part]` gains `<small class="rvsum">` (`summaryOf`, one line by CSS ellipsis) and `<span class="rvfiles">` with one `<span data-view="file:<file>">` per `filesOfPart` row (escaped); placeholder cards (no `data-part`) untouched. On non-page runs: remove `#steamwork [data-view="site"]` from "What you got" (and its section if empty); `#sopen` hidden. Wrap `root.sPhase` ("Checking it on a phone and a laptop" → `WORDS.checking` on non-page runs) and `root.sOpenPart` (after it resolves, swap the text "The part, on the page." in `#sdbody` for `WORDS.partDrawer` on non-page runs). Every wrapper falls back to the original on a throw.
  - Tests: painted `sTeamwork` HTML of the script fixture in the stub → done card has `.rvsum` "I wrote env_report/report.py." (the fixture's line, @name stripped), no `.sl`, two file spans; one card per status → `.sl` only on `doing`/`fix` and placeholder; website fixture → cards decorated, "What you got" site line kept, `#sopen` untouched; `sPhase` wrapper on a checking script state → "Checking the work", website unchanged; a wrapper whose helper throws returns the original output; string scan of `#sviews`, `#surl`, `#steamwork`, `#rvpane` text on the done script fixture finds no `/\b(site|page|website)\b/i`.
  - Done when: `node --test tests/ui/js/result_view.test.js` and `scripts/py -m pytest tests/ui/test_node_suite.py -q` pass
  - Covers: FR-13, FR-14, FR-15, FR-16, FR-17, FR-18, NFR-7

- [x] T4: The finish bar downloads the main result on non-page runs, and a copied link says it opens on this computer only
  - Files: `sutra_app/ui/static/js/result_view.js`, `tests/ui/js/result_view.test.js`, `tests/ui/test_dept_page.py`
  - Change: replace `root.sFinish`: page runs (incl. docset) → the original. Others: the `sPhase` message, then a main file → `<a class="pri" href="/api/artifact?name=<enc file><runQ>" download="<basename>">Download</a>`; a list → `<button type="button" data-view="files">All files (N)</button>`; none → nothing; then the page's own `data-share` "Copy share link" (only when the main result is a file, not a list, none or a real-run result: owner, Q-4) and `data-full` "Open full view" buttons, same markup and icons as j2_ui.html:1128-1131. In the `renderSimple` wrapper: when ready and not failed and the main-result key changed, set `#sfinish` innerHTML to `sFinish(s)`. A capture-phase click listener on `#sfinish` for `[data-share]`: copy the main file's `/view` URL (`location.origin + "/view?name=" + <enc file> + runQ`); a page run copies the page's URL (`location.origin + "/site/latest" + runQ` with `?`), set "Link copied — opens on this computer only", reset to "Copy share link" after 2.5 s, `stopImmediatePropagation`. The copied URL is the main file's `/view` link (spec FR-19, Q-3); the button is hidden with no main file or a real-run result (spec Q-4); website runs keep today's behaviour.
  - Tests: unit/glue: done script one-row variant → Download `href` `/api/artifact?name=env_report%2Freport.txt...`, `download="report.txt"`, no `href` starting `/site/`; two rows → "All files (2)" with `data-view="files"` and no `data-share`; zero rows → no Download and no `data-share`; a real-run result → no `data-share`; website and docset → the original `sFinish` output byte for byte; finish repainted when `SV.arts` arrives after the first render; share click → clipboard got the main file's `/view` URL (website: the page's URL), text then reset after the timer, page listener not called. Browser (new): `test_a_script_run_shows_its_files_and_no_site_words` using `finished_team`'s monkeypatch pattern (test_dept_page.py:865-872) to serve `fixtures/result_view/state-script.json` and `artifacts-script.json` through the fake's cache; at 1280x860 and 375x812: tabs Result/Files/How it was made, Result selected, Files list of two, no visible site/page/website, finish `["All files (2)"]` (no Copy share link: Q-4) (Open full view is hidden beside the sidebar, project_rail.css:126), no console error, no page-wide horizontal scroll.
  - Done when: `node --test tests/ui/js/result_view.test.js tests/ui/js/page_render.test.js` passes, and `SUTRA_BROWSER=1 scripts/py -m pytest tests/ui/test_dept_page.py -k "one_way_to_each_thing or opens_its_record or script_run_shows_its_files" -q` passes with the existing two tests unedited
  - Covers: FR-16, FR-17, FR-19, FR-21, FR-22, NFR-2

- [x] T5: Record D450
  - Files: `docs/DECISIONS.md` (append the D450 text from architecture.md D-4), `docs/diagram/decisions.json` (append the D450 entry)
  - Change: `git fetch origin` first and re-check the highest `## D<n>`; if D450 is taken, use the next free number in both files, the module comments and later commit messages.
  - Tests: none new.
  - Done when: `scripts/py -m pytest tests/test_diagram_decisions.py tests/test_ownership.py -q` passes
  - Covers: NFR-6

- [ ] T6: Final targeted run and hand-over (no commit unless a fix is needed)
  - Run: `node --test tests/ui/js/result_view.test.js tests/ui/js/page_render.test.js tests/ui/js/avatars.test.js`; `scripts/py -m pytest tests/ui/test_port_edits.py tests/ui/test_serve.py tests/ui/test_node_suite.py tests/ui/test_fake_backend.py tests/test_ownership.py tests/test_diagram_decisions.py -q`; the T4 browser command; `git diff --stat origin/main` names no file from the "stay out" row.
  - Then: full `scripts/gate.sh` in the foreground when the owner frees it (before any push); ask the owner before installing the beta; no push.
  - Covers: all FRs and NFRs (regression)

## Held for Kaivan

- P45 confirmed by Kaivan (lands after SUT-28): `realRun()` reads the `real_runs` receipt row's own `result` and `run_output` (never `output`, `dry_run.*`, `expect` or `workflows[].real_run.result`); `named()` reads `types[output].entry_file` for runs without a real-run result. Folder changes come from the row's `created`/`changed`/`deleted`/`files_truncated` (Later). Final key list pending once built.
- Later items (folder changes, script output) are not built; architecture.md "Later extension points" names the fields and the `#rvlater` slot.
