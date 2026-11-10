# J2S4-e3b as built: the fake backend, the python UI tests of the studio page

Lane E3, part b of J2 sync 4 (docs/design/j2-sync-4.md 4.8 and its studio addendum). Branch `lane/sync4-e3b`. Files: `tests/ui/fake_backend.py`, `tests/ui/test_fake_backend.py`
(sections 2 to 6; section 1 and 7 are lane e3a's), `tests/ui/test_dept_page.py`, `tests/ui/test_browser_smoke.py`, `tests/ui/test_visual.py`.

## Built

**The fake backend (E3.2).** J2's data routes of the pinned page, each answering a capture or J2's own body: `/api/plan-map`, `/api/activity` (six feeds, `activity-unknown.json`
for any other name), `/api/catalog`, `/api/artifacts/groups`, `/api/runlist` and `/api/changes` (J2's captures now; the derived P13 versions are gone), and the studio's
`/api/record` (`record-<sec>.json`, `record-art-<name>.json`, J2's `no such part` 404), `/doc/<name>` and `/view?name=` (`doc-prd.html`, `view-site.html`, `view-goal.html`, J2's "This
isn't written yet." page otherwise, the page sandbox CSP) and `POST /api/settings {decide_for_me}` (the switch `/api/state` reports back, per team).
`POST /api/ask` is the engine's route in small (D147 to D149): token, team, archived 403, `not a function` and `question too long` 400, J2's records-only answer
(`ask-<who>.json`), and for a function with a session of its own for the run the two lines stored in that session (`ask` is `q`, `records` or `model` on the wire) and announced
as `chat.message`, so the node panel and J2's panel read one transcript; 409 `busy` for a second question to a session being answered. A model answer is booked as one
`agent_chat` call (agent row, `usage.recorded`). `GET /api/engine/settings?dept=` carries `next_run.output` (the start page's pick, else the team's setting: the shape lane b
built), `POST /api/output` stores the pick (a follow-up clears it), `GET /api/teams/{dept}/agents` rows carry `usage.by_purpose`, and `GET /api/usage/summary?by=` groups the
same numbers (the ledger's six and `purpose`). Controls: `/__fake/ask {mode, text, note, delay, fail}` (modes records, offline, model, failed, interrupted) and
`/__fake/output {locked}`. `GET /d/{dept}/library` is the real router's (lane e1). The file runs as a script again: its `main` guard sat above the agent-sessions block, so
`scripts/py tests/ui/fake_backend.py --stage full` died with a NameError (a test runs the file as `__main__`).

**The tests.** `test_fake_backend.py`: 25 new tests (routes and captures, records and pages, the switch, ask in all its cases, usage by purpose and the summary, `next_run` and the locked
pick, running as a script) and the counts and route lists moved to the 30 + studio names. `test_dept_page.py`: `Page.open(view=)` (the page opens in its Simple view; the rail and its strip
are in the Detailed view), both strips, and 14 new browser tests: the rail strip, the output choice (one POST, a reload shows it, a started team keeps it closed), the function chat with
a question asked before and one typed there, Esc with the node panel open, the node panel over the chat panel, the Artifacts flyout, a part's record, Decide for me, the team's library
page. `test_browser_smoke.py`: the walk opens the Detailed view with its own button before the rail's tabs. `test_visual.py`: the 36 shots on the studio page, with one named contrast gap.

## Measured

`scripts/py -m pytest tests/ui`: 896 passed, 271 skipped (the browser tests, without the variable). With `SUTRA_BROWSER=1` (Chrome is here): `test_fake_backend.py`, `test_dept_page.py`,
`test_browser_smoke.py`, `test_chart_insight.py`, `test_visual.py`, `test_agent_chats.py` pass except the one red below.

## Known red, with the cause (not this lane's code)

1. `test_dept_page.py::test_the_attention_pill_does_not_sit_on_the_chat_button`: a real overlap. Sutra's attention pill (`.apillhost`, bottom right, z 50, "1 needs you") sits on
   J2's Chat button (`#chatfab`, bottom right, z 31) in the Detailed view, and a click in the middle of the button lands on the pill, which goes to Home. The fix is in `sutra-panel.css`
   (lane e2: put the pill clear of the button).
2. `tests/ui/test_agent_ask.py` (lane e2) adds its own `/api/ask` only when the fake has none; the fake has one now, and four of its tests assumed the stand-in: its answer text
   ("From the records: <question>"), a 0.5 s think time, and `/__test/ask {fail, note}`. They need the fake's own: the answer of `ask-<who>.json`, `/__fake/ask {"delay": 0.5}`,
   `{"fail": 409}`, `{"note": "..."}`; or `add_ask_route` can go.
3. `tests/ui/js/motion_css.test.js`: lanes e1 and e2 each rewrote rules 1 and 2 for J2's new sheet (e1 records J2's findings exactly, e2 limits the rules to Sutra's sheets and proves
   the replacements by rule 8); merging lane e1's last commit onto lane e2's conflicts there. The integrator picks one.

## Findings kept visible

- `test_visual.py` has one named gap, `KNOWN_STUDIO_GAPS`: the studio's "How the team works" link reads 4.39:1 in the light theme at 1440 px (`j2.css` is J2's; `sutra-panel.css`
  can darken the link). The test checks the gap is still there, so it goes the day the link is fixed.
- The fake serves no `/api/chats/{sid}/providers` (pre-existing): the smoke walk and the visual matrix announce it (`expect_failed("/providers", 404)`); three dept page tests that open
  the department's chat did race that 404 and now announce it.

## Left

- **E3.4, the motion probe**, cut by the coordinator. What it still needs: the five states of design 4.9 as scenarios of `tests/ui/perf/fluid_probe.js` (the Simple landing idle, the
  Map idle, Artifacts, the chat panel in function mode with a 300-line feed, the rail flyout 20 times) on the studio's selectors, a `__seedFeed(who, n)` that posts questions to
  `/api/ask` (a feed is the function's session lines, no longer the org chat's), and a shown browser pane (a hidden one gets no frames); the fake starts by hand again, which was
  the blocker. The numbers for `docs/notes/J2-SYNC-4.md` are not taken.
- Browser tests of the node panel's Ask mode on the real page are lane e2's (`test_agent_ask.py`); the fake's `/__fake/ask` is what they should drive.
- The browser tests of other files (`test_view_graph.py`, `test_view_panel.py`, `test_fluid.py`, `test_home*.py`) were not rerun for this lane.
