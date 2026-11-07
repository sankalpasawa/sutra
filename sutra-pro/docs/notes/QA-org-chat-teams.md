# QA-org-chat-teams as fixed: the org chat, the org chart and the team settings after QA of commit 2ae63d11

QA found 13 bugs in the flow "org chat and teams" (6 at P2, 7 at P3; none at P0 or P1). All 13 are fixed on the branch `feat/sutra-pro-qa-org-chat-teams`, each in its own
commit with a test that failed before the fix and passes after. Four small parts of the P3 reports were left alone, and each is listed with its reason at the end.
No J2 file, prompt, route or golden is touched (nothing under `sutra_app/engine/j2*.py`, `engine/llm.py`, `engine/port.py`, `ui/pages/j2_ui.html`); no bug was in J2's own code.
QA's scripts and screenshots are in the QA scratch folder `qa/org-chat-teams/` (not part of the repo).

## The bugs, their causes and their fixes

| # | Sev | What the owner saw | Root cause | Fix (commit) | Test that failed before |
|---|-----|--------------------|-----------|--------------|-------------------------|
| 1 | P2 | An answered approval or choice card came back open with Yes and No after a reload or restart (a stale Yes gave 409) | The server stored `answered_by` for questions only; Home answered cards from memory (`S.answers`) | `ChatStore` reads `answered_by` of an approval or choice card from the owner line stored as `choice:<card id>`, or from the card itself when its change was decided without a button; `ChatView.answersOf` turns that into "You answered: No" (`17f9bf28`) | `test_turn_runner.py`, `chat_view.test.js`, `test_home.py` |
| 2 | P2 | A line accepted mid-turn stayed `pending` for ever after a stop or kill: no answer, no error, `/retry` said 404 | Nothing at start looked at `pending` owner lines; `retry` only runs a line in state `error` | `TurnRunner.recover`, called from `start_services` before any turn, makes each such line an `error` and posts one template line ("The app stopped before I finished your request. Please try again."), so the bubble offers Retry (`d4f084d2`) | `test_startup.py` |
| 3 | P2 | The change log showed only changes 1 to 50; the newest, a pending approval and the change a card points at never appeared | `GET /api/chart/changes` returns the oldest rows after a cursor, and Home and the org chart asked `limit=50` with no cursor | the route and `ChartStore.history` take `newest=true` (the last `limit` rows, still oldest first); both pages ask for it (`c320cdab`) | `test_chart_store.py`, `test_api_chart.py`, `test_home.py` |
| 4 | P2 | Enter that accepts an input-method candidate sent the half-typed line from the org chat box | `home.js` sent on every Enter keydown; the node panel's box already checked `isComposing` | the keydown ignores `isComposing` and `keyCode 229` (`fe211b9e`) | `test_home.py` (browser) |
| 5 | P2 | Standing rules saved from a stale window dropped the other window's rule | `PUT /api/departments/{id}/rules` replaced the whole list with no revision check | the read carries `rev` (a digest of the list); a save with a stale `rev` is a 422 `validation` (violation `rev`, code `stale_rules`) that stores nothing and returns the current list; the panel shows it again and keeps the typed text. A save without `rev` (a script) replaces as before (`b7232e9f`) | `test_standing_rules.py`, `rules_view.test.js`, `test_rules_notes_page.py` |
| 6 | P2 | Offline demo: with any owner note written, requests went to the wrong team and task titles read "... OWNER NOTES (facts and house" | `demo.py` took the whole `OWNER REQUEST` block as the message, and `decide.md` and `assign.md` put the notes block inside it | the book cuts the notes block (heading and its "- " lines at the end of the captured text) before it reads the message; the same words inside the owner's message stay its own (`69b61e04`) | `test_agent_demo.py` |
| 7 | P3 | The rail and the Needs-you strip kept the old name after a team was renamed in an open page | `chart.changed` refetched the chart and the graph only | it also refetches `/api/departments` and `/api/needs-you` (`3e024bf7`) | `test_home.py` (browser) |
| 8 | P3 | The strip and "Planning..." vanished after reloading during a turn | They came from `chat.turn` events only; `loadAll` ignored `ChatSessionOut.phase` | `syncTurn` maps the server's phase word (reading, planning, building) onto the event words until the first event arrives and reads the session again every 2.5 s while it holds that stand-in, so a turn that ended unseen does not leave the strip up. Events stay the authority once one has arrived (`4ff15d4b`) | `test_home.py` (browser) |
| 9 | P3 | The Needs-you row of an approval began with ": " | `needLine` put an empty team name before the colon | an approval with no team leads with "Approval needed"; a line with neither team nor approval kind is just its words (`3fe66ba9`) | `test_home.py` (browser) |
| 10 | P3 | A message over 8000 characters came back as "The request was refused" and no reason | the 422 lists its violations, and `errorWords` showed the top-level sentence only | a 422 with a violation shows "The request was refused: String should have at most 8000 characters", as the notes and rules views already do; a 5xx is still never shown raw (`706be674`) | `test_home.py` (browser) |
| 11 | P3 | A purpose in Devanagari or Japanese was flagged "only repeats its name" | `thin_purpose` counted a-z words, so such a purpose had none | a purpose with no a-z word that is not plain ASCII is judged by its whole words (any script) against the name's words; Latin text is judged as before (`2905c101`) | `test_chart_health.py` |
| 12 | P3 | Teams named CON or Nul. got the ids and folders `con` and `nul` (Windows cannot make them) | `slug_id` knew no device names | a name that slugs to con, prn, aux, nul, com1-9 or lpt1-9 starts from the kind (`department-con`), as a name with no usable letters already did; `docs/design/library.md` says so (`ab6606a8`) | `test_lib_chart_change.py` (10 cases), `test_chart_store.py` |
| 13 | P3 | "I set up a Event Booking team", "a General Team team", "a Weddings team" for a division | one template, `I set up a {name} team`, for every node | `planner.added(name, kind)` gives "an Event Booking team", "a General Team", "a Weddings division"; the article follows how the first word is said (a University, an Hours, an HR, a UX). `matches_template` keeps its anchors (the line ends in its noun and full stop; `add` ends in "and gave it your request."), so free prose is still not let through (`eb778962`) | `test_chat_agent.py` (15 cases), `test_turn_runner.py` |

One existing test encoded bug 13: `test_a_new_division_with_work_for_it` expected "I set up a Blog team" for the division Blog. It now expects "I set up a Blog division". The
generic `test_every_line_has_a_matching_pattern_and_no_free_prose_matches` gives the new field `what` a sample that is a phrase ("a X team") instead of "X", and it gained
three more negative and positive cases. No test was deleted or made weaker.

## Skipped, and why

- **Bug 11, the rest of the report: the same ASCII-only tokenizer drops non-Latin text from reuse matching, and `slug_id` gives such a team the id `department`, `department-2`.**
  By design today: `textutil.slugify` says non-ASCII letters are dropped, not transliterated, and `test_slug_id_examples` pins `("department", "销售") -> "department"`. A wider
  tokenizer changes which team a request is given to (it shares `JACCARD_REUSE` and the keyword fallback with the library), so it is not a one-line guard. Follow-up for a
  design decision: Unicode-aware tokens for reuse matching.
- **Bug 13, the change-log row of a pending or rejected merge keeps the past-tense summary "Merged Corporate into Weddings".** The row already ends with a status word
  ("waiting for your yes or no", "not applied", `chart_marks.js statusNote`), so it reads correctly; the stored `summary` is part of the `chart_changes` row and the
  change record, so rewording it for a state it has not reached is a data change, not a wording fix.
- **Bug 12 on Windows itself:** the fix was proved by the id and the folder name the app now makes (a test lists the folder names and does not probe `con`, which "exists" in
  every folder on Windows). It was not run on a Windows machine.

## Tests

- New or changed this round: `tests/ui/test_home.py` +4 browser tests (rename refresh, approval label, refusal reason, reload mid-turn), `tests/orchestrator/test_chart_health.py` +1,
  `tests/library/test_lib_chart_change.py` +10 cases, `tests/orchestrator/test_chart_store.py` +1, `tests/orchestrator/test_chat_agent.py` +15 cases and 3 assertions,
  `tests/orchestrator/test_turn_runner.py` +1 and 1 corrected expectation. Before the fix each of these failed for the reason in the table.
- Results on the branch tip (commands from the repository's gate):
  - `node --test tests/ui/js/*.test.js`: 969 tests, 967 passed, 2 skipped, 0 failed.
  - `scripts/py -m pytest tests/orchestrator tests/integration tests/ui tests/test_docs.py tests/test_traceability.py tests/test_ownership.py tests/test_layout.py -p no:warnings`:
    2208 passed, 219 skipped (the skipped are the browser tests, which need `SUTRA_BROWSER=1`).
  - `scripts/py -m pytest tests/library -p no:warnings` (on its own): 2357 passed, 4 skipped.
  - With `SUTRA_BROWSER=1` on `tests/ui/test_home.py`, `test_view_graph.py` and `test_rules_notes_page.py`: 112 passed, 9 failed, 41 errors; the base commit 2ae63d11 gives 105 passed,
    9 failed, 41 errors. See the next paragraph.
- **Known and not from this branch:** in this environment most of `tests/ui/test_home.py` already fails or errors at 2ae63d11 because the fake backend answers 404 to
  `GET /api/chats/cs_org/providers` and a test that does not announce it with `browser.expect_failed` fails at teardown (9 failures and 41 errors across those three files at the base commit).
  The tests added here announce it, as their siblings do. `test_the_first_graph_after_a_turn_takes_the_right_pane_and_the_task_card_links_to_the_team` and
  `test_a_click_on_a_sliver_of_a_box_at_the_edge_opens_it_without_moving_it_from_under_the_pointer` pass or fail from run to run at the base commit as well (timing).
