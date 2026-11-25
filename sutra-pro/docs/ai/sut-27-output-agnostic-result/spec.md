# Spec: the centre panel shows any output, not only websites
Status: Refined   |   Task: sut-27-output-agnostic-result   |   Date: 2026-11-25

Inputs: request.md (approved, authoritative), impact.md (file:line evidence), docs/ai/analysis.md, the owner's answers of 2026-11-25 (relayed by the coordinator). Paths are under `sutra-pro/`; `j2_ui.html` means `sutra_app/ui/pages/j2_ui.html`.

Design intent (owner): "Keep it simple: one main result, everything else folded or one tab away."

## Problem

| what the user sees on a script run | why | evidence |
|---|---|---|
| an empty "Page" tab | a "Page" tab appears whenever `versions > 0` and the run is not a document | j2_ui.html:1332-1333 |
| one tab for many files | extra deliverables are de-duplicated by name, and all files of one type share a name | j2_ui.html:1335-1336; j2_artifacts.py:159-160 |
| grey bars on finished parts | every card not doing/fixing ends in placeholder bars | j2_ui.html:1613 |
| "The page, version 3", "Open the site" | wording is fixed to a site | j2_ui.html:41, :1302, :1627 |
| Download saves an empty `.html` | the non-document Download always points at `/site/latest` | j2_ui.html:1128 |

The file the run made is not shown as the result anywhere.

## Scope

Request items 1-5, plus one wording change on "Copy share link". Request item 6 (private-data detection) is dropped by the owner.

Not in scope:
- No engine change. Nothing in impact.md §6 is touched; `engine/views.py` and `engine/api/*` are untouched too. The page uses today's routes.
- No screen per project type, no branch on a type name (D241), no main-result guess by file name.
- No zip download. No change to the start page, Home, or the Detailed view.
- The "Later" items (below) are not built.

## Definitions

| term | meaning | evidence |
|---|---|---|
| done | `isReady(s)` or `s.saved` | j2_ui.html:1010, :1337 |
| output file | one row of `/api/artifacts` `deliverables` (one row per file) | j2_artifacts.py:184-194 |
| page run | `s.docset` is non-empty, or `s.types[s.output].form === "page"` | state.json fixture `types.website.form` |
| main result | the one output file Result shows, chosen by FR-3 | |

## Functional requirements

### R1 Tabs (request item 1)
- **FR-1** Every run shows three tabs, in this order: "Result", "Files", "How it was made". No "Page", "Team at work" or per-file tab.
- **FR-2** With no user pick: Result is selected when the run is done; How it was made is selected otherwise.
- **FR-3** A tab the user picked stays selected across polls.
- **FR-4** Before the run is done, Result shows "Your result will appear here when the team finishes." The one exception: a page run with `versions > 0` shows its live site preview while it builds, as today (owner, Q-2).

### R2 Viewers by file type (request item 2)
- **FR-5** The viewer is chosen from the row's `form` (only `page`) and the file's lower-cased extension. Never from a type name or file name.

| row / extension | viewer | route |
|---|---|---|
| `form === "page"` | today's sandboxed site preview | `/site/v<N>` |
| `.html .htm .md .png .jpg .jpeg .gif .webp .svg` | the same sandboxed frame (the server renders markdown and inlines images) | `/view?name=` (views.py:574-598) |
| `.txt .log` | plain text | `/api/artifact?name=` |
| code: `.py .js .mjs .ts .tsx .jsx .sh .rb .go .rs .java .c .h .cpp .css .sql .yaml .yml .toml .ini` | text with line numbers | `/api/artifact?name=` |
| `.csv .tsv` | table, first row as header | `/api/artifact?name=` |
| `.json` | table when it is an array of objects, else numbered text | `/api/artifact?name=` |
| anything else (`.docx .pdf .zip` ...) | file name and a Download link | `/api/artifact?name=` |

- **FR-6** Text, code and table viewers insert file content as text, never as HTML. HTML is only ever shown in the sandboxed frame, which never gets `allow-same-origin` (D83, D153).
- **FR-7** A CSV or JSON file that does not parse falls back to numbered text. A failed fetch shows "This file can't be shown here (it may be over 2 MB)." Nothing is thrown.
- **FR-8** A table shows at most 1,000 rows and then "Showing 1,000 of N rows".
- **FR-9** Files lists every output file once (no de-duplication by name): its name, a Download link, and its viewer one click away.

### R3 Main result (request item 3)
- **FR-10** Rule, first match wins (names confirmed by Kaivan, Q-1; the run_output link of step 1 is P45, not built yet):
  1. real-run result: take the last workflow in plan order whose `real_run.result` (`/api/state` `workflows[].real_run.result`) is a non-empty string. `result` is a path in the user's folder, never one of the run's outputs, so it is not matched against them. Find that workflow's last real_run receipt row (`/api/artifacts/groups` rows' `real_runs`, matched on `workflow`). If that row's `run_output` (P45's key, pending Kaivan's OK) is a string of the exact form `run_output/<id>.json`, Result shows the real-run result: its text comes from that file (up to 64 KB). Otherwise this step is skipped. `output` is never read as a link: it stays today's 1,500-character stdout+stderr tail (j2.py:949-952). Today the step is always skipped: no row has `run_output`, and the `real_runs` projection (j2_artifacts.py:774-793) carries neither it nor `output`;
  2. the output type's entry file (`types[output].entry_file`, else `types[output].file`, which carries the same value today: j2_types.py:435, j2.py:3778) names one concrete file, not a glob such as `<name>/*`, and equals an output file's `file` → that file (a website run: `site/index.html`, shown as the site preview);
  3. exactly one output file → that file;
  4. otherwise → Result shows the Files list ("everything else one tab away").
  A name from step 2 that is not among the output files is skipped.
  Zero output files on a done run → Result and Files read "This run produced no files."
- **FR-11** No step of the rule reads a file name or extension.
- **FR-12** Result shows the main file's name above its viewer, and a Download link.

### R4 Plan cards on How it was made (request item 4)
- **FR-13** A done part card shows no grey bars. It shows the builder's one-line summary: the `human_output` of the last chat message whose `who` is one of the part's workflows, with a leading `@name` removed, first sentence only, kept to one line (clipped with an ellipsis). With no such message it shows "Finished."
- **FR-14** A done card lists the names of the output files whose row `workflows` share a workflow with the part. Clicking a name opens it in Files. A card with no files shows no list.
- **FR-15** Grey bars appear only on cards in progress (`doing`, `fix`) and on the placeholder cards shown before a plan exists. `next`, `bad`, `ask` cards lose the bars and keep the rest of their look.

### R5 Wording follows the output (request item 5)
- **FR-16** On a page run every visible string stays as today.
- **FR-17** On any other run:

| where (j2_ui.html) | today | after |
|---|---|---|
| :41, :1300-1303 top bar `#sopen` | Open the site | hidden (the finish bar has Download, Result is the default tab) |
| :1120 phase | Checking it on a phone and a laptop | Checking the work |
| :1128 finish Download | `/site/latest` as `<output>.html` | the main file through `/api/artifact`, saved under its own name; with no main file, "All files (N)" that opens Files; with no files, no Download |
| :1344 toast | The page is taking shape | no toast |
| :1350 address label | preview / live preview | the main file's name, or "files" |
| :1627 What you got | The page, version N | not shown |
| :1736 part drawer | The part, on the page. | The part, in the result. |

- **FR-18** No visible text on the panel of a non-page run uses "site", "page" or "website" for the result. Checked by a string scan of the script-run fixture.
- **FR-19** On every run, after "Copy share link" copies, the button reads "Link copied — opens on this computer only" for 2.5 s. The server listens on loopback only (main.py:20), so this is true. The copied URL is the main file's `/view` link instead of `/site/latest` (owner, Q-3). A page run whose main file is the site keeps `/site/latest` (FR-16); a run with no main file (Files list, no files, or a real-run result, which has no `/view` route) keeps today's URL (T4 detail; see Q-4).

### Edge cases
- **FR-20** `output == null` (D165): not a page run; noun "result"; three tabs; no console error.
- **FR-21** A saved run follows the same rules, and Result never loads `/site/latest` on a non-page run.
- **FR-22** Phone width: tabs and viewers fit without horizontal page scroll.

## Non-functional requirements

| id | requirement | check |
|---|---|---|
| NFR-1 | `j2_ui.html` changes only by the port script's own output (one module tag); new behaviour is a Sutra module (D439) | `scripts/py -m pytest tests/ui/test_port_edits.py -q` |
| NFR-2 | J2 parity goldens unchanged | `node --test tests/ui/js/page_render.test.js` with no fixture change |
| NFR-3 | no inline script, CDN, web font or new dependency (D82, D74, D138) | `scripts/py -m pytest tests/ui/test_serve.py -q` |
| NFR-4 | no file of impact.md §6, `engine/views.py` or `engine/api/*` changes | `git diff --stat origin/main` |
| NFR-5 | no home path or owner name in any changed file (D99) | `scripts/py -m pytest tests/test_ownership.py -q` |
| NFR-6 | decision D450 in DECISIONS.md and decisions.json | `scripts/py -m pytest tests/test_diagram_decisions.py -q` |
| NFR-7 | the page still works if the module fails to load or throws (wrappers fall back to the page's own function) | unit test |

## Acceptance criteria

A new hand-built fixture for a script (folder-form `agent`) run is needed (impact.md §7).

| id | Given | Then | covers |
|---|---|---|---|
| AC-1 | the done website fixture | tabs are Result, Files, How it was made; Result selected; it holds the sandboxed frame on `/site/v<N>`; finish shows Download (`/site/latest`) and Copy share link as today | FR-1, FR-2, FR-10, FR-16 |
| AC-2 | the running website fixture | How it was made selected; Result, when picked, shows the live site preview | FR-2, FR-4 |
| AC-3 | the running script fixture, Result picked | Result reads "Your result will appear here when the team finishes." | FR-4 |
| AC-4 | the user picked Files; another poll arrives | Files is still selected | FR-3 |
| AC-5 | rows `a.md, b.txt, c.py, d.csv, e.json, f.png, g.html, h.docx` | viewer is frame, text, numbered, table, table, frame, frame, download | FR-5 |
| AC-6 | a `.txt` holding `<b>x</b>` | the literal text shows; no `<b>` element is created | FR-6 |
| AC-7 | a bad CSV, a bad JSON, a 404 | numbered text, numbered text, the "can't be shown" line; no throw | FR-7 |
| AC-8 | a 1,500-row CSV | 1,000 rows and "Showing 1,000 of 1,500 rows" | FR-8 |
| AC-9 | three rows of one multi-file type | Files shows three entries, each with Download | FR-9 |
| AC-10 | one output `out.txt` / two outputs `index.html` + `report.txt` / the same plus `real_run.result: "report.txt"` and its receipt row with only the stdout tail in `output` (today) / the same with `run_output: "run_output/R-1.json"` (P45) / the same with `output: "run_output/R-1.json"` and no `run_output` / the same with no receipt row / a type file `env_report/*` with two outputs / a type file `site/index.html` with two outputs / `real_run.result` set, one output, no link / zero outputs | `out.txt` / the Files list / the Files list / the real-run result from `run_output/R-1.json` / the Files list / the Files list / the Files list / `site/index.html` / the one output / "This run produced no files." | FR-10, FR-11 |
| AC-11 | a done part whose last `W-n` message is "@Coordination Wrote the script. It prints env vars." | the card reads "Wrote the script.", has no `.sl` bars, lists its files | FR-13, FR-14 |
| AC-12 | a done part with no `W-n` message; parts in each status | "Finished."; bars only on `doing`, `fix` and placeholder cards | FR-13, FR-15 |
| AC-13 | the done script fixture | no visible "site/page/website"; `#sopen` hidden; Download `href` is `/api/artifact?name=<main>...` with `download="<basename>"`; no `href` starts with `/site/` | FR-17, FR-18, FR-21 |
| AC-14 | any done run; Copy share link clicked | the button reads "Link copied — opens on this computer only", then "Copy share link" after 2.5 s | FR-19 |
| AC-15 | state with `output: null` | three tabs, noun "result", no throw | FR-20 |
| AC-16 | the change set | the NFR commands pass | NFR-1..7 |

Existing tests that pin today's strings are reviewed in architecture.md ("Existing tests").

## Later (planned, not built)

Built once SUT-28 / SUT-23 add a route. Nothing below ships now.

| item | source today | where it goes | interface the UI expects |
|---|---|---|---|
| "What changed in your folder" | real_run receipt row `created` / `changed` / `deleted` (planned, pending Kaivan) | Result, below the viewer, folded | `/api/artifacts/groups` `real_runs[]` rows (inside the documents group rows, j2_artifacts.py:774-793): `created`, `changed`, `deleted`, paths relative to the folder |
| "What the script printed" | the same receipt row's `stdout` / `stderr` tails (P42, D447; planned, pending Kaivan) | Result, folded, last line as the hint | the same `real_runs[]` rows: `stdout`, `stderr`, `exit`, `workflow`, `t`; shown with the text viewer. Today `real_runs` omits stdout (engine-side gap, not this change) |
| a file written into the user's folder as the main result | `run_output/<receipt-id>.json` (P45, not built) linked as the receipt row's `run_output` | Result, via FR-10 step 1 (hook built now, skipped until P45) | the `real_runs[]` rows carry `workflow` and `run_output` (the projection, j2_artifacts.py:774-793, must add it; engine-side) |

When a route is absent nothing is drawn (no empty heading).

## Assumptions

| # | assumption | basis |
|---|---|---|
| A-1 | `types[output].form` tells a page run apart | state.json fixture; types.json forms page/document/agent |
| A-2 | rows carry no size; a file over 2 MB answers 404 | j2_artifacts.py:208; views.py:559-562 |
| A-3 | a plain `<a href="/api/artifact?..." download>` works without the page token | the page already links `/api/artifact` this way (j2_ui.html:1751) |
| A-4 | `function` page globals can be replaced from a module; `const` ones can be read | impact.md §0; avatars.js:190-205 |
| A-5 | `s.allChat` holds every chat message, with `who` and `human_output` | j2_ui.html:1969; state.json fixture |
| A-6 | deliverable rows carry `workflows` for type rows | j2_artifacts.py:141-151, :155-160 |

## Open questions

| # | question | who | default |
|---|---|---|---|
| Q-1 | Planned names: `workflows[].real_run.result` for the main result and `types[output].entry_file` as fallback; is `result` a path relative to the run folder (so it can equal a row's `file`)? | Kaivan (SUT-23) | answered: names confirmed; `result` is a path in the user's folder, not the run folder, so it is never matched against outputs; its text comes from `run_output/<receipt-id>.json` (P45, not built), linked as the receipt row's `run_output` (FR-10 step 1) |
| Q-2 | Should a page run's Result keep the live site preview while running (FR-4 exception)? | owner | answered yes (plan review, 2026-11-25) |
| Q-3 | On a non-page run "Copy share link" still copies `/site/latest`, which answers "No site in this run." Copy the main file's `/view` URL instead? | owner | answered yes (plan review, 2026-11-25): the main file's `/view` link (FR-19) |
| Q-4 | What does "Copy share link" copy on a run with no main file (Files list, no files) or a real-run result (no `/view` route)? | owner | today's URL; revisit at T4 |
| Q-5 | P45's link key on the real_run receipt row is `run_output` (owner), since `output` already holds the stdout+stderr tail | Kaivan | answered by the owner, pending Kaivan's OK: the UI reads only `run_output`, never `output`, as the link |

Answered: builder summary (owner, item 3 of 2026-11-25), per-file download with no zip, `engine/views.py` untouched with CSV/JSON parsed in the page, keep the name "Copy share link", How it was made as the default before done, the site preview for a website run, the "opens on this computer only" note.

## Decision to record

D450, one decision for the whole change. SUT-28 is expected to take D449; re-check the next free number after fetching.

## Change log

| date | change |
|---|---|
| 2026-11-25 | First draft from request.md and impact.md |
| 2026-11-25 solution-architect | Status Refined. Cut 41 FRs to 22 and 32 ACs to 16 by merging duplicates (FR-1.4/1.6/8.4/8.6 into FR-1..4; FR-2.4/2.5/8.2 into FR-7; FR-7.x into the FR-17 table). Dropped R6 privacy (FR-6.1-6.6, 6.8; AC-18-23), Q-2, Q-3 and D451 per the owner's decision; kept only the "opens on this computer only" wording (FR-19). |
| 2026-11-25 solution-architect | Docset runs: dropped the special Result chooser (old FR-3.4, AC-30); their documents are output files, so the general rule (Files list) covers them, and their finish bar stays the page's own. Reason: fewer cases, same reach. |
| 2026-11-25 solution-architect | Main-result rule step 3 (site preview) merged into step 2: a website run's only output row is the site with `form: page` (artifacts.json fixture). |
| 2026-11-25 solution-architect | FR-4 exception: a page run keeps its live preview while running (today's behaviour; Q-2). |
| 2026-11-25 solution-architect | Plan-card files come from deliverable rows' `workflows` (servable `file` paths, A-6) instead of `workflows[].outputs` (bare names such as `index.html` that `/api/artifact` does not serve). |
| 2026-11-25 solution-architect | Builder summary: strip a leading `@name` (owner). Clipping to one line is done in CSS. |
| 2026-11-25 solution-architect | `#sopen` is hidden on non-page runs instead of becoming "Open result" (the finish bar and the default tab already cover it). Group heading "Page" removed from the wording table: it only shows on docset runs, which are page runs. |
| 2026-11-25 solution-architect | Removed NFR-6 (manual 1 s timing check) and NFR-9; FR-8 (1,000-row cap) bounds the table, and text is set with `textContent`. |
| 2026-11-25 solution-architect | `.markdown` removed from the viewer table: `view_page` renders only `.md` (views.py:591). |
| 2026-11-25 solution-architect | Main-result rule rebuilt on the owner's planned names (pending Kaivan): `workflows[].real_run.result`, then a concrete type entry file, then the single output, then the Files list. Later items name the `real_runs` receipt fields. |
| 2026-11-25 solution-architect | Q-3 added: the share URL on a non-page run points at a page that says "No site in this run." |
| 2026-11-25 developer (T1) | Owner decisions at plan review: Q-1 answered (FR-10 step 1 rebuilt: `real_run.result` is a path in the user's folder, never matched against outputs; the real-run result shows only when the workflow's last receipt row's `output` is a `run_output/<id>.json` link, P45; skipped today). Q-2 yes (FR-4). Q-3 yes: Copy share link copies the main file's `/view` link (FR-19). AC-10 cases updated; Q-4, Q-5 added; Later row for a folder file points at P45. |
| 2026-11-25 developer (T1) | Owner update: the P45 link key is `run_output` on the receipt row (pending Kaivan's OK); `output` stays the stdout+stderr tail and is never read as a link. FR-10 step 1, AC-10, Later, Q-1, Q-5 updated. |
