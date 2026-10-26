# The department as the J2 prototype's page, inside the Sutra app: the design of record

| Field | Value |
|---|---|
| **status** | Built and merged on main in four packages (core, work, views, shell); the verification package (`j2ui-verify`) is the branch `prd/j2ui-verify`, written 2026-10-27. **No release until the owner has seen the screenshots with the sign-off list in section 7** (decision D-SIGNOFF). |
| **owner's instruction** | "Take latest pull from J2 prototype and implement UI in the exact same fashion, no change." (2026-10-26) |
| **the prototype** | `J2_Prototype` at commit `f9ceba15192bbd6f62047cb7288d0f291b2fbc4f`; its page `j2_ui.html` has sha256 `23549799903e98485f404872670c49e5735c7cc9962c19b42037b1bde5ebad0d` (1724 lines) |
| **where it lives** | the page and its pin in `j2ui_assets/`; the adapter in `j2ui_*.py`; the frame in `static/js/25-j2view.js`; the proof in `test_j2ui_*.py`, `test_fixtures/j2ui/`, `qa/walks/`; the pictures in [`design/j2ui/`](j2ui/) |
| **this file does not change** | `PRD-FIVE-FUNCTIONS.md`, `PRD-FIVE-FUNCTIONS-A1.md`, `PRD-FIVE-FUNCTIONS-DECISIONS.md`; the integrator adds the pointers and the supersession of the decision rows (section 10) |

## 1. What the owner asked for, and how it is read

The department's screen in the Sutra desktop app is the J2 prototype's UI: the Simple view, the Detailed view with its rail, the Map drawn as a metro line, the Board tab, the cards, the phone-width layout, the colours, the fonts and the wording, reproduced exactly, with no redesign, no restyle and no re-worded label. The data comes from Sutra's runtime (the five functions, `dept.json`, runs, versions, asks, the J2 ledger) instead of the prototype's run folders. Screens the prototype has no version of (Settings > Instructions as typed fields, Root's Settings > Standards) stay in the app's own style.

`j2ui` means "the J2 prototype's UI". It has nothing to do with the user journeys J1 to J4 of amendment A3 (data only, no screen) or with the department's running cycle (`j2_runtime`).

## 2. What is built, in one page

1. The prototype's single file `j2_ui.html` is copied into `j2ui_assets/` by one script, `scripts/sync_j2_ui.py`, which applies three documented substitutions only (section 3), pins the source commit and hashes, and copies two helper files byte for byte (`j2_schema.py`, the prototype's atom adapter, and `j2_ui_render.js`, its node render harness).
2. `GET /j2ui/{ref}/` serves that file for a department of the engine runtime whose kind is `website`, with a content security policy. The page calls relative URLs, so a router under the same base (`j2ui_api.py`) answers every endpoint it uses, in the prototype's own JSON shapes, built from Sutra's records (section 4).
3. In the department screen the page runs in one same-origin, unsandboxed iframe, laid over a placeholder by a mount-once frame host, under a slim native bar (the department's On/Off switch and `Settings and records`), with the list column hidden so the page has its desktop width. `Settings and records` shows the classic list and panes, including the typed Instructions and Root's Standards, so nothing Sutra-only is lost.
4. Departments of kind `default` and `organic`, a Root, and a department of the first build keep the classic screens: the page's vocabulary is a website team's, and presenting another kind as one would be false.
5. The adapter invents nothing. Where Sutra has no record the page shows its own "not recorded" or empty text. The Audit tab claims no item-by-item result and no code check that nobody made.

## 3. Embedding, and the three substitutions (the only differences from the prototype's bytes)

The page lives in `j2ui_assets/`, not in `static/`: nothing under `/static` is the page, so it is never reachable at a broken relative base, and only `j2ui_page.py` reads it. It is shown in a same-origin iframe with **no `sandbox` attribute**: a sandbox without `allow-same-origin` could not fetch, keep its view in `localStorage` or send the panel token. Rejected: inlining the page into `panel.html` (its global CSS and listeners would collide with the app's, and both UIs would change), Sutra's sandboxed page-module mechanism (`default-src 'none'`: the page could not fetch), navigating the whole window (loses the rail and the tree), static files at the root (`/api/state` collides with Sutra's own), a native port (a rewrite: "no change" could not be guaranteed).

| | Substitution | Why |
|---|---|---|
| **S1** | a quote, apostrophe or backtick followed by `/api/`, `/site/`, `/file/` or `/shot/` loses that first slash (34 places on 31 lines at the pin) | the page is served at a directory-style URL, so every URL is relative to `/j2ui/{ref}/` |
| **S2** | `<script src="j2host.js"></script>` inserted directly after the viewport meta line | the page's writes need the app's panel token; `j2host.js` (a short fetch wrapper that names one URL, `/api/panel-token`) gives a non-GET `fetch` the `X-Sutra-Panel` header and retries once on a 403 |
| **S3** | the one external stylesheet's `href` becomes `fonts/fonts.css` | **not applied in the pin written now** (`local_fonts` is false): the fonts were not vendored, so the page keeps the prototype's Google Fonts link and the policy allows those two hosts. Run `scripts/fetch_j2_fonts.py` with a network, then the sync script, to switch it on (veto point D-FONTS) |

Nothing else is patched: not the title, the `j2view` localStorage key, a CSS rule or a label. The test that proves it (`test_j2ui_verbatim.py`) reverses S1 and S2 from the pin's recorded positions and compares the hash with the prototype's, always; and, when the prototype is on the machine, compares the copy with the **git objects** at the pinned commit (never the working tree, which moves) with an independent difflib check that allows only S1 lines, the S3 line and one inserted S2 line. `test_j2ui_render.py` (T2) adds the proof by behaviour: the copy and the prototype's own page draw **every pane identically** on the prototype's own real runs.

**Syncing after the prototype moves** (one command, then the three proofs):

```
cd marketplace/plugin/sutra-ui
J2_PROTOTYPE=<the prototype's checkout> python3 scripts/sync_j2_ui.py              # copy and pin
J2_PROTOTYPE=<...> python3 scripts/sync_j2_ui.py --check                            # exit 1 if the copy differs from the pin
J2_PROTOTYPE=<...> python3 scripts/sync_j2_ui.py --check-latest                     # report only: has the prototype moved?
J2_PROTOTYPE=<...> python3 scripts/capture_j2_fixtures.py                           # new captured runs (section 8)
./run-tests.sh test_j2ui_verbatim.py test_j2ui_contract.py test_j2ui_render.py test_j2ui_xss.py
bash qa/walks/j2ui-e2e.sh                                                           # Chrome: the screenshots and the structure
```

## 4. The routes

Every route is under `/j2ui/{ref}/`. `{ref}` must be a department of the engine runtime whose kind is `website` (`j2ui_common.need`, the one place that decides); anything else is `404 {"error": "no such department"}` on every route, the page included. JSON is cleaned (`j2ui_common.clean`: no private key, no path of this machine; **not** `functions_view._clean`, whose path rule turns `build/v1/index.html` into `buildindex.html` and `5/6/2026` into `52026`) and sent no-store. Reads write nothing. A route that cannot build its answer sends the page's own empty shape, because a wrong shape blanks the page.

| Route | Answer |
|---|---|
| `GET /` and `index.html` | the page, with its security policy (own origin, inline script and style, `frame-ancestors 'self'`), `nosniff`, no-store; a request without the slash is redirected to it |
| `GET j2host.js`, `fonts/{name}` | the fetch wrapper; the vendored font files the pin lists (none while S3 is off) |
| `GET api/state?since=N` | the 56 keys of the prototype's snapshot, each always present; `since` slices the adapter's own chat list; `run` other than the live one is 404 |
| `GET api/runs` | `{live, runs: []}`: one live cycle per department, so the picker shows only "Live run" |
| `GET api/map` | `map/1`: the person, the five functions, the Charter, the work boxes and step nodes, with the 14-row legend and the nine statuses |
| `GET api/board` | `board/1`; entries only once `questions.json` exists (the engines' questions to each other); the tab is hidden until then |
| `GET api/artifacts`, `api/artifact?name=` | the deliverables and records in the prototype's 17-key rows; one file, only one the listing names, at most 2,000,000 bytes, with the `SAFE` headers; a path out of the folder is 404 |
| `GET api/docs`, `api/audits`, `api/refs`, `api/preview?atom=`, `api/call?id=` | the empty documents ("Not asked for in this run."), no earlier stage's audits, the conditions' texts, an empty preview, and 404 for a call (Sutra stores no prompt or reply) |
| `GET site/{key}[/{path}]` | `latest`, `vN` or `N` redirect to `<key>/index.html`; a file of that version, css inlined; nothing built yet is a fixed line; every body carries the `SAFE` headers (`sandbox; script-src 'none'`: shown, never run) |
| `GET file/{name}`, `shot/{n}` | always 404 (a website team has no document and records no screenshot), with the `SAFE` headers |
| `POST api/say` | the owner's words, routed to the writers that already exist: `Option k` through the options the owner was shown (`choose_option`, `decide_ask`), free words to Identity's open question or the Chat's own path (`owner_ask`); never refused because work is running |
| `POST api/reset`, `output`, `playbooks/clear`, `lessons/clear` | `409`, nothing changes |

Writes pass `app.py`'s origin guard unchanged: a POST that carries an `Origin` without the `X-Sutra-Panel` token is 403 (tested through the full app).

## 5. What each thing in the page is in Sutra (the mapping rules)

| # | The prototype | Sutra | Rule |
|---|---|---|---|
| 1 | A run (one conversation; `?run=`) | the department's cycle (`j2-state.json` `cycle_id`) | live id = the cycle id; `api/runs` lists no saved run; `?run=` equal to the live id is live, any other is 404; `api/reset` is 409 |
| 2 | The Requester | the owner | their words are `user` messages, taken from `chat_view` (Root's board filtered on the department, plus the department's own turns); only Identity ever has `to_user` true; the adapter never speaks and never posts |
| 3 | Identity, Adaptation, Priority, Coordination, Audit | the same five | lower-case ids; node state working, waiting, waiting_on_you (only while an ask is open), fault, quiet maps to running, waiting, waiting_on_you, fault, idle |
| 4 | The Validator | Root's check | its messages come only from the ledger events `workflow.validated`, `workflow.registered`, `workflow.blocked`; Root is not one of the five and has no Map node |
| 5 | A builder agent `W-n` and its workflow | an engine of the registered line | `W-k` by position in the line, then left-out engines continue the numbering; none before a plan is registered; a left-out engine is a hollow branch box, not a workflow |
| 6 | A work atom `W-n.aK` and `atoms_v1` | one slot step of the engine, with its rows | `atoms_v1` is the prototype's own `run_views` (vendored byte for byte); gates and rules are decisions, not atoms; check ids appear only in `target` |
| 7 | The Charter | Identity's goal, done-when items and rules | the page keeps its own word "Charter" (no re-worded labels); the PRD's "never charter" binds the adapter's own prose only |
| 8 | Budget and work credits | calls and USD in Priority's envelopes | one credit is one model call; `budget` is the calls limit, `spent` the calls used today; no other rescale |
| 9 | Playbooks and lessons | none | `memory` false, arrays empty; the page says "Memory is off" |
| 10 | `board/1` entries | `questions.json` rows | empty and the tab hidden until the file exists; Sutra's own board posts are not `board/1` |
| 11 | Deeds and sends | none | no Send nodes |
| 12 | `site/vN`, the Preview tab | versions of the previewable artifact (`Build`) | `versions` is the count; scripts do not run in the preview |
| 13 | The Documents tab | none | three entries with `asked` false |
| 14 | Audit results, rubric, conditions | Audit's readings and the Check engine's recorded check | a clean reading is **one `read` line** and no per-item PASS; `workable` None until readings carry per-item verdicts; a reading that was not read is no entry; conditions are named for who recorded them (the Check engine, Root's check); no rubric, no screenshots |
| 15 | Conflicts (Adaptation against Priority, up to four attempts) | bargain threads where Priority asked for less or said no, plus `conflict` posts and Identity's rulings | one conflict for each; a straight yes is not one |
| 16 | Message `id` and the `since` cursor | an arrival-ordered, in-memory registry of the owner-facing turns, internal posts, ask messages and ledger messages | ids are 1-based positions and never move while the process lives; the adapter writes no file of its own |
| 17 | `status`, `outcome`, `paused`, `done` | the cycle state, `j2_runtime.open_question`, pending asks | `status` is `waiting` whenever something waits on the owner, so the composer and the option buttons stay live while an engine runs; `outcome` is only `Done` or `Done with open items` |
| 18 | `Option N` answers | `choose_option`, `decide_ask`, `j2_runtime.answer`, `owner_ask` | `k` is mapped through the option ids the owner was shown |
| 19 | Stop, pause, resume (the prototype has none) | the department's On/Off switch | a native control in a slim bar above the page |
| 20 | Lanes, `call_log`, report, style guide, write lock, test switches | mostly no record | lanes from function nodes and engine states; `call_log` only from step rows that made calls; the rest None |
| 21 | A function-to-function message's text | the act, in the owner's words | `functions_view._did` plus the carried words; the Detailed chat, the Timeline and Conflicts agree |
| 22 | Output types `website`, `prd`, `hld`, `lld` | department kinds | only `website` has a mapping |
| 23 | Message time `t` | the record's `at` | `HH:MM:SS` |
| 24 | "Written by code, no AI call" | step rows with `calls > 0` | a message is linked to a call only on an unambiguous time match |

## 6. What became of every earlier UI step of the PRD and amendment A1

"Superseded" means the page does the job and the classic code and its tests stay (reachable in `Settings and records`, or for departments of the other kinds) until the owner signs off a deletion.

| Step | Disposition | Note |
|---|---|---|
| S1 Map: NOW line and five function boxes | Superseded | the page's Map (state pill, checks pill, function chips, metro work row) |
| S2 All five overview | Superseded | the Map's chips, the Needs you strip and the Run details lanes; the All five row folds into the page |
| S3 List column with function state dots | Changed | hidden while the page is open (it needs the width); present in `Settings and records` |
| S4 NOW pill, strip line, round dots | Changed | the Map's state pill replaces the pill; the strip's progress line stays in the shell and opens the page |
| S5 Identity's pane | Superseded | Goal, Charter, Chat and Needs you; the pane stays in records mode |
| S6 Identity's question card | Superseded | the Simple view's question bubble with option buttons and the Needs you strip; the server rules (`choose_option`, `UNKNOWN_OPTION`, `ALREADY_HANDLED`) stay |
| S7 Coordination's pane and timetable | Superseded | Workflows (limits, status) and the Map's step nodes; accepted loss: the timetable's start times are not in the page |
| S8 Adaptation's pane with S11's dots | Superseded | Workflows, Conflicts, Timeline and the Validator messages; S11's dots survive in the classic pane |
| S9 Priority's pane | Superseded | Conflicts and the Workflows limits; envelope editing stays in records mode |
| S10 Limit or blocked card | Superseded | a blocked or limit ask reaches the page as a paused question with option buttons |
| S12 Audit's pane | Superseded | the Audit tab shows recorded readings and findings only |
| S13 Internal messages and `GET /messages` | Superseded | the Detailed chat, the Timeline and the Map's speaks-to lines |
| S14 Ready card | Superseded | the page's "Your website is ready" card |
| S15 Chat, the department's one voice | Superseded | the Simple view and the Detailed chat; the one-voice rule stays as an adapter rule with a test |
| S16 Settings > Instructions as typed fields | **Kept** | reached through `Settings and records`, a function row, Settings |
| S17 Engine card | Superseded | the Map's step node panel and the Workflows row |
| S18 Root settings > Standards | **Kept** | on the organisation's Root settings button, unchanged |
| `W1-UI` V6: S11's dots | Changed | built, but only in the classic Adaptation pane |
| `W2-SCREENS` H1 to H6 | Changed | screen growth for S8, S9, S10, S12, S13 and S14 is superseded; the word tests on the classic panes stay |
| `W3-MAP` M1 to M2 | Superseded | the prototype's Map is the metro line |
| A1.28 rail navigation | Changed | adopted inside the page; the app's own rail is unchanged |
| A1.28 and M10.4 phone-width check | Changed | a real Chrome test at 390 and 1280 px (`design/j2ui`); at the 900 px minimum window the frame is narrow and the page draws its phone layout, as the prototype does |
| M1.6, M1.7, M1.10 read models | Kept | they are the adapter's sources |
| M10.2 one API family | Changed | the adapter reads the same runtime functions and never calls the legacy `/api/dept` routes |
| M10.3 words pass | Changed | applied to the adapter's output; the word "charter" and the page's own labels are waived inside the page |
| M4.9 and `W3-BOARD` board/1 between engines | Kept | `questions.json` feeds the Board tab and the Map's asks and uses edges |
| M8.7 spot checks, M9 pursue rounds | Kept | server side, untouched; rounds show as the cycle number |
| A1.28 emails as dry-run deeds, Sends | Kept (not adopted) | no send engine, no Send nodes |
| Departments of kind `default` and `organic` | Kept classic | `is_j2_kind` and the shell's `j2vOn` both say `website` only |
| User-journey templates J1 to J4 (A3) | Data only | no screen, no adapter field |
| Base and child classes, function templates (A2, A3) | No screens | if A2 adds kinds that extend `website`, change `is_j2_kind` and the one JS test of `kind` together |

## 7. The owner's sign-off list: what the owner will see that is not the prototype's data

"No change" is kept for the page. These are the places where what the owner sees is not what the prototype would show on its own data, with the picture that shows each. **The owner reviews this list with the pictures before a release.**

### A. Controls the page draws that the adapter can only answer with 409 or with nothing

They stay on screen, unchanged, because the page is not edited.

| # | The control | What happens | Picture |
|---|---|---|---|
| A1 | `New run` | calls `api/reset`, which is 409; the page reloads to the same department | [Run settings](j2ui/detail-runsettings-1280.png) |
| A2 | `What to build` | offers Website and the PRD document type, but `api/output` is 409; it is disabled once the department has any message, which is the normal case | [Run settings](j2ui/detail-runsettings-1280.png), [the start screen](j2ui/simple-start-1280.png) |
| A3 | `Saved runs` | lists only "Live run" | [Run settings](j2ui/detail-runsettings-1280.png) |
| A4 | `Start over` | never shown: `error` is None and `outcome` is never Stopped or Crashed (tested) | none: it cannot appear |
| A5 | `Clear memory`, `Clear playbooks` | hidden, because `memory` is false; the clear routes are 409 and tested to change nothing | [Playbooks](j2ui/detail-playbooks-1280.png), [Lessons](j2ui/detail-lessons-1280.png) |

### B. Strings and tabs that print a prototype setting, or an empty state, that Sutra does not have

| # | What the owner sees | Why | Picture |
|---|---|---|---|
| B1 | in Run details: `mock functions` (or `model: not recorded`) `· N AI calls · cycle N`, `J2_FIXES=1 (fixes)`, `memory off` | the page prints one of two fixed strings for `fixes` and neither is true of Sutra (D-FIXES: `1` is the prototype's own default; a one-line substitution S4 that hides it is available on request); Sutra records no model name; memory is off | [Run details](j2ui/detail-rundetails-1280.png) |
| B2 | the Style guide, Lessons, Playbooks and Report tabs stay at their own empty texts | no style guide, lesson, playbook or run report is recorded | [Style guide](j2ui/detail-style-1280.png), [Lessons](j2ui/detail-lessons-1280.png), [Playbooks](j2ui/detail-playbooks-1280.png), [Report](j2ui/detail-report-1280.png) |
| B3 | the Documents tab: "Not asked for in this run." | a website team writes no design document | [Documents](j2ui/detail-docs-1280.png) |
| B4 | the Board tab is hidden until the engines have asked each other something | `board/1` entries come from `questions.json`, which a wave-3 package writes | none on the finished department; shown by the contract test (`with_board`) |
| B5 | an opened work atom has no `Prompt sent`, `Reply received`, `Reason given` or tokens | Sutra stores no prompt, reply or token count | [an opened atom](j2ui/detail-atoms-1280.png) |
| B6 | the message dialog says `Written by code, no AI call` for a message that cannot be linked to exactly one recorded call, and `Full text of what it was given` says `Not found.` | a link is made only on an unambiguous time match (D-DIALOG) | [the dialog](j2ui/detail-chat-1280.png) |
| B7 | the Artifacts and Conflicts tabs show only what was recorded (a straight yes is no conflict) | no invention | [Artifacts](j2ui/detail-artifacts-1280.png), [Conflicts](j2ui/detail-conflicts-1280.png) |

### C. Words that are the page's, not the PRD's

`Charter`, `Requester (you)`, `Builder`, `work credits` (one credit is one model call), `Validator`, the J2 step codes `J2.a` to `J2.h`, `Your website team`, `site v1`, and the page's own names for the five functions on the Map (Client Lead, Strategist, Prioritiser, Scheduler, Quality Reviewer). The PRD's wording rules (never "charter", said yes / asked for less / said no) bind the adapter's own prose and the classic screens; inside the page the owner's no-change rule wins (D-PRD). Pictures: [Charter](j2ui/detail-charter-1280.png), [Workflows with work credits](j2ui/detail-workflows-1280.png), [the Map](j2ui/detail-map-1280.png), [the chat with the Requester and the Validator](j2ui/detail-chat-1280.png), [Run details with J2.a to J2.h](j2ui/detail-rundetails-1280.png).

### D. Behaviour that differs from the prototype because Sutra is long-lived and local-first

| # | What differs | Picture |
|---|---|---|
| D1 | the department's On/Off switch and `Settings and records` sit in a native bar above the page (D-BAR) | [in the app](j2ui/app-j2view-1440.png) |
| D2 | the organisation tree, the strip and the rail of the app frame the page | [in the app](j2ui/app-j2view-1440.png) |
| D3 | `Settings and records` opens a second, classic UI (the old list and panes, including the typed Instructions and Root's Standards) | [records](j2ui/app-records-1440.png) |
| D4 | the composer is disabled while work runs **and nothing waits on the owner**, as in the prototype; with an ask pending it stays live (D-LOCK) | [building](j2ui/simple-building-1280.png), [a question](j2ui/simple-question-1280.png) |
| D5 | a built site's own JavaScript does not run in the preview (`SAFE`: shown, never run) | [Preview](j2ui/detail-preview-1280.png) |
| D6 | the page follows `prefers-color-scheme` only (in Electron the panel's theme drives it) | every picture is the dark scheme |
| D7 | at the 900 px minimum window the frame is narrow and the page draws its phone layout (the layout follows the frame's width) | [phone: question](j2ui/simple-question-390.png), [Map](j2ui/detail-map-390.png) |
| D8 | links that open a new window (`Open full screen`, `View in site`) open the system browser at the app's local address in Electron; not testable headlessly here | none |
| D9 | the fonts are the prototype's Google Fonts link while S3 is off; online it is identical, offline the page falls back to system fonts (D-FONTS) | none |
| D10 | the page is only used for departments of kind `website` (D-SCOPE) | none |

### E. Found by this package's own walk (for the owner and the integrator)

| # | Observation | Picture |
|---|---|---|
| E1 | The Audit tab's table "Necessary conditions (checked by code, site v1)" also lists Root's check of the plan (R-1 to R-14, evidence "Root's check: ..."). They are recorded checks by code and each says who recorded it, but they check the plan and the page heads them with "site v1". No per-item PASS and no "Workable (checked by code)" line appear; the contract test pins both. Decide whether Root's check belongs under that heading. | [Audit](j2ui/detail-audit-1280.png) |
| E2 | The page's status line reads "Building your check..." while the Check engine runs: it prints the running workflow's name lower-cased. | [building](j2ui/simple-building-1280.png) |
| E3 | The seeded departments are offline drafts: the built site's text is the Library's template text ("who the hospital is and how to get care"), whatever the owner asked. | [the preview](j2ui/detail-preview-1280.png) |

## 8. How it is proved

| Proof | Where | What it says |
|---|---|---|
| Verbatim | `test_j2ui_verbatim.py`, `test_j2ui_sync.py` | the copy is the prototype's file at the pin, changed by S1 to S3 only; the sync guards fire on synthetic bad inputs |
| Same page, real data | `test_j2ui_render.py`, `test_fixtures/j2ui/poll_harness.js`, `test_fixtures/j2ui/captured/` | four real runs of the prototype (a small website run, a run with a conflict and three audits, a crashed run with `atoms_v1`, the large documents run) and the idle start screen, captured from the prototype's own server at the pin by `scripts/capture_j2_fixtures.py`, drawn by the pinned page and by the copy through a node stub DOM: every pane identical after S1, no `undefined`, `NaN` or `null`; a state with a key missing, a hand edit of the copy and a poll that stops early each turn it red |
| Adapter contract | `test_j2ui_contract.py` (the whole app, 17 cycle states and 9 more departments, seeded by `test_fixtures/j2ui/seed.py`) | the 56 state keys, `atoms_v1` against the vendored `run_views`, the Map's keys, statuses, kinds, legend and golden invariants against the prototype's own map, the artifact and board rows, the words (no GRANT, COUNTER, REFUSE, act id, path of this machine or private key), only Identity speaks to the owner, the P1 cases (a follow-up through Root is one more user message and none is the Validator's; two publish asks are two messages; `Option k` through the options the owner was shown), the honest Audit, scope (404), the origin guard, traversal, the `SAFE` headers; and every state's real answers through the page harness: the page is never blanked |
| Hostile strings | `test_j2ui_xss.py` | a department whose 78 fields are all attacks (the spec's three payloads in a row, then an svg, a `javascript:` link and a template placeholder), rendered in every pane and every agent's message dialog: no script, no `on*` attribute, no foreign image, no `javascript:` link, no unsandboxed frame, no raw `</script>`; the owner's own words come back as text; a temp copy of the page with one field printed raw turns the check red. The page's `esc()` ignores `'`, but it has no single-quoted attribute that prints a field, so nothing breaks out today; the check stays the guard |
| Browser, end to end | `qa/walks/j2ui-e2e.sh`, `qa/walks/shot-j2.js` (headless Chrome, raw CDP) | the page directly at 1280x900 and 390x844: zero exceptions, zero console errors, no Content Security Policy violation, the rail walked, every tab shown, the Map's cards on the phone; in the app: exactly one iframe at `/j2ui/{ref}/`, no sandbox, titled J2 Department, the bar, the records mode and the typed Instructions, the way back; the hostile department leaves `window.__xss` undefined in the page and the host; the page's DOM skeleton equals the prototype's own ([`STRUCTURE.md`](j2ui/STRUCTURE.md)) |
| Branches | `qa/walks/j2ui-against.sh <branch>` | the contract, render, chat and audit tests on a temporary merge of main and the branch; run before each wave-1 merge and again after |
| The gate | `bash qa/walks/suites.sh` | five j2ui lanes and `test_j2view.js` join the existing ones |

How to run: `./run-tests.sh test_j2ui_verbatim.py test_j2ui_contract.py test_j2ui_render.py test_j2ui_xss.py`; `node test_j2view.js`; `bash qa/walks/j2ui-e2e.sh` (needs Chrome and the ports 8362 and 8763; without Chrome it says so and exits 0).

## 9. Decisions (each with its veto point)

| Id | Decision | Reason | Veto |
|---|---|---|---|
| D-HOST | host the page in a same-origin, unsandboxed iframe at `/j2ui/{ref}/`, adapter routes under the same base | the alternatives collide with the app's CSS, listeners and routes (section 3) | model-written bodies carry `SAFE` on every route (tested) |
| D-DIR | the vendored page in `j2ui_assets/`, read only by `j2ui_page.py` | not reachable at a broken base; no `static/**` capture per sync; ships with the plugin tree | none |
| D-PIN | compare with git objects at the pinned commit; the hash check always runs; "moved" is a report | the prototype moved 20 commits in 6 days | none |
| D-SCOPE | the page is for `kind == 'website'` only | `default` and `organic` have Brief and Result or Brief only | ask for a document mapping as a later package |
| D-FONTS | vendor the three font families (S3) | local-first: identical typography offline | `--no-local-fonts` restores the prototype's line; **not yet applied** (needs one network fetch) |
| D-LOCK | `status` is `waiting` whenever something waits on the owner | otherwise a pending stamp could not be answered while an engine runs | never report `running` (loses "Building your ...") |
| D-BAR | a slim native bar: On/Off switch and `Settings and records` | the prototype has no run controls; Sutra needs Stop and the way to the typed Instructions and Standards | drop the bar and reach Stop from the strip |
| D-SIGNOFF | no release until the owner has seen the screenshots and section 7 | "no change" is the owner's, so the visible differences are the owner's to accept | none |
| D-CHAT | the owner's side of the chat from `chat_view`, internal posts from the department's board, the Validator from the ledger | the owner's follow-ups are on Root's board | registry keys carry the board |
| D-CLEAN | an own `clean()` with `ABS_PATH`, not `functions_view._clean` | `_clean` rewrites relative paths and dates | tested |
| D-SCHEMA | vendor `j2_schema.py` byte for byte | `atoms_v1` is then the prototype's code, not a copy of its logic | changes only with the sync |
| D-HONEST | a clean Audit reading is one `read` line; `workable` None until per-item readings exist | no invented item-by-item results or code check | none |
| D-FIXES | `fixes` is 1 | the page prints one of two fixed strings | S4 hides the line on request |
| D-DIALOG | link a message to a call only on an unambiguous time match | no guessing | none |
| D-REG | the chat id registry is in memory | the adapter writes no file of its own | after a restart ids are rebuilt by the same sort; an open page may show option buttons as not live until reloaded |
| D-PRD | the PRD's "never charter" is waived inside the page only | the owner: no re-worded labels | the adapter's own prose still avoids it |
| D-WALK | the Chrome walk starts the app with the motor off (`SUTRA_MOTOR_OFF=1`), offline functions, on its own record directory and port, and keeps its Chrome profile in a temp folder | no record moves under the browser; nothing is committed but the pictures | none |

## 10. Open risks and what the integrator adds

- **The page is a moving target.** The sync guards, the verbatim test, the page-key scan, the list of raw interpolations and the render tests on real fixtures make an update fail loudly; a change in the shape of a state key still needs adapter work. Refresh the fixtures with `scripts/capture_j2_fixtures.py`.
- **Naming collision.** `j2ui` is the prototype's UI; J1 to J4 are user journeys (A3); J2 is also the department's running cycle. Keep the prefix; never reuse the word for the journeys.
- **Wave-1 changes move sources.** The adapter calls only public functions of the records; a few private helpers (`functions_view._did`, `_said`, `_short`, `_cap`) are pinned by a contract test. `qa/walks/j2ui-against.sh <branch>` names the function a branch moved.
- **Polling cost.** The page polls every 700 ms; mitigated by the signature cache, a one-second rebuild floor and incremental journal tails (tested at 5,000 board, 20,000 step and 20,000 ledger rows).
- **Not testable headlessly here:** the Electron shell's handling of `target=_blank` and `download` links, and the browser-mode gateway (SameSite=Strict cookie).
- **Fonts need a network once** (S3 is off in the pin).
- **The page's `esc()` ignores `'`.** Guarded by the hostile-string tests; a breakout through a prototype interpolation is reported, never patched in the page.
- **Scope by kind** may need revisiting when A2 adds child kinds (`is_j2_kind` and the shell's `kind === "website"` are the two places).
- **The seeded departments are offline drafts.** Chrome sees what the offline functions make; a department run by a real model has richer panes. The captured prototype runs cover the page's richer data.

The integrator, in one docs commit: (1) marks `W1-UI.md` as carried by `j2ui-shell`; (2) records the owner's UI-port instruction as the settlement of `PRD-FIVE-FUNCTIONS-DECISIONS.md` rows MK-5, MK-6, MK-8 and A1-P2, P3, P4, P6, keeping the pinned commit `f9ceba1` in the A1.28 table; (3) adds a pointer to this file from `PRD-FIVE-FUNCTIONS.md` and `-A1.md`; (4) runs `qa/walks/j2ui-against.sh <branch>` for any wave-1 branch still to merge. Before a release the owner sees section 7 with the pictures.

## 11. Status

| Package | State | Evidence |
|---|---|---|
| `j2ui-core` (scope, the one read, chat, state, say, routes) | merged on main | `a74a1f91`, fix round `07dd46c7` |
| `j2ui-work` (workflows, atoms, lanes, honest audits, conflicts, docs, call log) | merged on main | `1e235350`, fix `d24cad63` |
| `j2ui-views` (Map, board, artifacts, site, file, shot) | merged on main | `e13a89d3`, fix round `61debd38`, `10e5b6ec` |
| `j2ui-shell` (verbatim copy and sync, page route, frame and bar, records mode, typed Instructions and Standards) | merged on main | `16c75bc6`, fix `0d9f2c84` |
| `j2ui-verify` (this: fixtures, same-page proof, contract, hostile strings, Chrome, gate lanes, branch check, this record) | **built on `prd/j2ui-verify`, T1 to T6 done; awaiting the integrator's merge** | the commits `PRD UIPORT T1` to `T6`; the gate green on its last commit |

| Wave-1 rerun | Merged on main | The contract, render, chat and audit tests on it |
|---|---|---|
| `a1-coord-2` Coordination | yes (`c5ae944a`) | pass |
| `a1-identity-2` Identity | yes (`5d7c54ec`) | pass |
| `a1-priority-2` Priority | yes (`827fe38f`); its fix branch `prd/a1-priority-fix1` is not yet merged | pass on main; `j2ui-against.sh prd/a1-priority-fix1` also passes |
| `a1-audit-2` Audit | yes (`cbb61740`) | pass |
| `a1-adapt-2` Adaptation | yes (`1d2a310e`, fix round `a660b5a2`) | pass |
| `a1-core-k2` core K2 (typed values, the API, views through the layers) | yes (`e4b227c5`) | pass |

Every row passed on the tree this record was written on: main at `dc7f8e9c` with `prd/j2ui-verify` rebased onto it. `qa/walks/j2ui-against.sh main prd/j2ui-verify` runs the four files (contract, render, chat, audit) green, and `qa/walks/j2ui-against.sh prd/a1-priority-fix1 prd/j2ui-verify` (the one wave-1 fix branch not yet merged) is green too. Run it again after each merge.

What ran on that tree, 2026-10-27:

| Run | Result |
|---|---|
| `bash qa/walks/suites.sh` (with the five j2ui lanes and `test_j2view.js`) | exit 0 |
| the five j2ui lanes | core 175 passed (1 skipped), work and audits 169, map, board, artifacts and site 229, the copy and its route 54, contract, render and hostile strings 78 |
| `test_j2.py test_j2_api.py test_j1.py test_dept_api.py test_function_templates.py test_org2_api.py test_forbidden_calls.py` | 303 passed |
| `node test_panel.js`, `node test_nav.js`, `node test_j2view.js` | 408 passed, 81 passed, 30 passed |
| `bash qa/walks/j2ui-e2e.sh` (Chrome 155) | start 12 of 12, question 12 of 12, building 12 of 12, ready 73 of 73, hostile 72 of 72 claims; the skeleton of both views is the prototype's own |

## 12. The pictures

Every picture is of the finished or seeded department in the app's dark scheme, taken by `qa/walks/j2ui-e2e.sh` (the page itself is at the same address the app's iframe uses). Names follow the prototype's `docs/ui-simple-*`.

| | 1280 px | 390 px (phone) |
|---|---|---|
| Start | [simple-start-1280](j2ui/simple-start-1280.png) | [simple-start-390](j2ui/simple-start-390.png) |
| Question (Stamp, Say no) | [simple-question-1280](j2ui/simple-question-1280.png) | [simple-question-390](j2ui/simple-question-390.png) |
| Building (composer locked) | [simple-building-1280](j2ui/simple-building-1280.png) | [simple-building-390](j2ui/simple-building-390.png) |
| Ready | [simple-ready-1280](j2ui/simple-ready-1280.png) | [simple-ready-390](j2ui/simple-ready-390.png) |
| Detailed: Map | [detail-map-1280](j2ui/detail-map-1280.png) | [detail-map-390](j2ui/detail-map-390.png) |
| Detailed: Workflows | [detail-workflows-1280](j2ui/detail-workflows-1280.png) | [detail-workflows-390](j2ui/detail-workflows-390.png) |
| Detailed: a message's dialog | [detail-chat-1280](j2ui/detail-chat-1280.png) | [detail-chat-390](j2ui/detail-chat-390.png) |

In the app at 1440 px: [the page under the native bar](j2ui/app-j2view-1440.png) and [Settings and records](j2ui/app-records-1440.png). The tabs the sign-off list points at, at 1280 px: [Run settings](j2ui/detail-runsettings-1280.png), [Run details](j2ui/detail-rundetails-1280.png), [Report](j2ui/detail-report-1280.png), [Style guide](j2ui/detail-style-1280.png), [Lessons](j2ui/detail-lessons-1280.png), [Playbooks](j2ui/detail-playbooks-1280.png), [Charter](j2ui/detail-charter-1280.png), [Preview](j2ui/detail-preview-1280.png), [Audit](j2ui/detail-audit-1280.png), [Documents](j2ui/detail-docs-1280.png), [Artifacts](j2ui/detail-artifacts-1280.png), [Conflicts](j2ui/detail-conflicts-1280.png), [an opened atom](j2ui/detail-atoms-1280.png). The page's structure against the prototype's own: [`STRUCTURE.md`](j2ui/STRUCTURE.md).

Looking at them against the prototype's own `docs/ui-simple-*.png` (taken at an earlier commit of the prototype): the differences are data (the department's own words, the built site, the rail and the page's own newer controls that those older pictures predate), not the adapter's. The structure test above is the proof that the markup is the prototype's.
