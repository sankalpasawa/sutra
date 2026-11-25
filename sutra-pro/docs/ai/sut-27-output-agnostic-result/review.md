# Review: sut-27-output-agnostic-result

## Round 1  (2026-11-25, commit 3e697d7e)
Verdict: Approve-ready (no P0 or P1 left open; two P2s to fix or accept explicitly)

Scope: `rtk git diff origin/main...HEAD` (10 commits, 9c7664a6 plus the owner follow-up 3e697d7e). No engine files changed (`sutra_app/engine/**` untouched in the diff). No home paths or owner names in `sutra-pro/` (test_ownership passes).

### Findings
| ID | Sev | File:line | Finding | Evidence | Suggested fix |
|---|---|---|---|---|---|
| R1-1 | P2 (resolved by owner, fix in 3e697d7e) | result_view.js:164-179 | In 9c7664a6 the single "Website" card on a website run read "Item 1, Item 2 and 2 more". That breaks FR-16 ("On a page run every visible string stays as today"), and a list of parts does not say what the file is. | Unit test pinned it (result_view.test.js:629 at 9c7664a6). | Fixed by owner decision in 3e697d7e: three or more parts keep the page's own title. Two things still happen under the new rule, and the owner accepted both: (a) a website built from one or two parts is still retitled with part names, not "Website"; (b) on the script fixture both cards still read "Write the report script", so a multi-file type made by one part still shows the same title on every card. Only the second line (the file name) tells them apart. If the goal was distinct titles, (b) is not met. |
| R1-2 | P2 (confirmed by trace, not executed) | result_view.js:357-363, j2_ui.html:1588-1593 | **sGo can call itself every 600 ms forever on a website run.** The wrapper hands website runs to the page's own `sGo`, which picks a tab from the page's `sTabs`. Scenario: a website run with `versions === 0` and a deliverable row whose form is not `page` (an image, data or agent row). Then `sTabs` has no `site` tab, so `sGo` falls back to `tabs.find(t => t.k !== "team")` = `"a:<name>"` and sets `SV.pick = "a:<name>"`. `views()` treats that pick as unknown and maps it to `"result"`, so `SV.view` is never `"a:<name>"`. `sGo` then reschedules itself every 600 ms and calls `renderSimple` each time. implementation.md (Deviations, T2) names this exact loop as the reason for wrapping `sGo`, but the guard lets website runs through. | Lines 1590 and 1593 of j2_ui.html. views() line 291-292 (unknown pick becomes "result"). | In the wrapper, call the page's `go` only when `T.last.versions > 0` (that is when the page's `site` tab exists); otherwise call `sOpenPart(sec)`. Add a unit case on the existing vm stub: a website with versions 0 and one non-page row, `sGo` called, then assert no second `renderSimple` after 600 ms. |
| R1-3 | P3 | result_view.js:190 (team) | **File names on plan cards cannot be reached by keyboard.** Each `.rvfile` is a `<span data-view>` inside the card's `<button data-part>`. It cannot take focus, and a span inside a button is also invalid nesting for an interactive control. Enter on the card opens the part record, not the file. FR-14's "clicking a name opens it in Files" works by mouse only. The same files are reachable by keyboard through the Files tab, so nothing is blocked. | Page delegation j2_ui.html:1855 (`closest` matches the inner span first, so mouse clicks work). | Accept, because the Files tab covers it. Or render the file list after the card's `</button>` as real `<button data-view>` elements. |
| R1-4 | P3 | result_view.js:283 | **A real-run result would show a misleading message.** When the main result is a real-run result, Result shows "This file can't be shown here (it may be over 2 MB)". That is the wrong reason: the route does not exist yet. This never happens today because P45 is not built, and the line is marked `ponytail:`. | | When P45 lands, replace it with the fetched text or a neutral line. |

Checked and found sound (no finding):
- **Main-result rule.** It reads only the receipt row's `result` and `run_output`, with a strict link regex (line 36). It never reads `output`, `dry_run` or `expect`. Step 2 drops glob entry files (`*`), and nothing reads a file name or extension. Matches FR-10/11 and the owner's P45 note.
- **Escaping.**
  - Everything that reaches innerHTML is escaped with `esc`/`escape`: file names, text, CSV/JSON cells, builder lines, part names, `main.result` and the URL label.
  - URLs use `encodeURIComponent`, and `download=` uses the escaped basename.
  - HTML, markdown and images open only through `sLoad`, in the page's frames, which have `sandbox="allow-scripts allow-forms allow-popups"` and no `allow-same-origin` (j2_ui.html:59).
  - No inline script: test_serve passes.
- **Capture-phase share listener.** It is on `#sfinish` and acts only when `closest("[data-share]")` matches. `stopImmediatePropagation` at that point keeps the page's own `#sfinish` and `#sview` handlers away from the share button only. Retry, Open full view and All files (`data-view`) still reach the page.
- **Re-render loops.** A text fetch re-renders once per file+sha. The groups fetch happens once per `SV.akey`, and only for done runs with a `real_run`. The finish-bar redraw writes only when its HTML changes. None of these loop.
- **Fallbacks.** Every replaced global falls back to the page's own on a throw. Page runs get the page's `sFinish` unchanged.
- **Contrast.** `--s-accent` measures 6.7 to 7.5:1 in both themes, and a unit test pins the token.

Pre-existing, not introduced here: `/api/artifact` serves `.html` as `text/html` on the app's own origin (views.py:559-570). The new Download links carry `download`, so a normal click saves the file. Opening one in a new tab would render it unsandboxed, but the page's "The file itself" link (j2_ui.html:1751) already did that before this change.

### Spec coverage
| Requirement | Covered by | Status |
|---|---|---|
| FR-1..4 tabs, defaults, pick kept, placeholder, live site on website | views(), unit glue tests, browser script test | Met |
| FR-5..9 viewers, escaping, parse fallback, 1,000-row cap, Files list | viewerFor, bodyOf, table/jsonTable, unit tests AC-5..9 | Met |
| FR-10/11 main result | realRun/named/mainResult, AC-10 cases | Met (step 1 is a hook only, as agreed) |
| FR-12 name + Download | stage() head | Met |
| FR-13..15 plan cards | team(), browser docset tests | Met (keyboard: R1-3) |
| FR-16 page-run strings unchanged | sFinish passthrough, toasts | Met after 3e697d7e (R1-1). One exception: a website built by one or two parts still gets part-name card titles, by owner rule |
| FR-17/18 wording on other runs | sPhase/sOpenPart/renderSimple wrappers, FR-18 scan | Met |
| FR-19 share link | share(), finish() | Met |
| FR-20..22 | unit + browser (375 px) | Met |
| NFR-1..7 | port_edits, serve, ownership, goldens (per implementation.md), wrappers | Met. NFR-7 has a gap: R1-2 |

### Tests run
- `node --test tests/ui/js/result_view.test.js`: 41 tests, 41 pass, both before and after 3e697d7e.
- `scripts/py -m pytest tests/test_ownership.py tests/ui/test_port_edits.py tests/ui/test_serve.py -q`: pass (5 skipped, which need the browser or `SUTRA_J2_CHECKOUT`).
- `SUTRA_BROWSER=1 scripts/py -m pytest tests/ui/test_dept_page.py -q -k "script_run_shows_its_files or document_set or one_way_to_each_thing"`: 6 passed.
- Not run (per instructions): `scripts/gate.sh`, the beta install.

Test quality:
- The glue tests run against a vm stub of the page, not the real page.
- The browser tests do exercise the real page for the script fixture, the document-set fixture and the website finish bar.
- Missing: a unit case for the website `sGo` path when `versions === 0` (R1-2).

### Earlier findings
None (first round).
