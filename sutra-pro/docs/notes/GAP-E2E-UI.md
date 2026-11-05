# GAP-E2E-UI as built: the browser walk against the real app (G06)

## Built (`tests/e2e/`, 4 browser tests, about 31 s; all skip unless `SUTRA_BROWSER=1`, so the gate never runs them)
- `test_browser_real_app.py`: (1) the first-day walk in ONE document, with zero console errors and zero failed requests checked after every step: Home start page (4 briefs,
  `● live`), the brief, progress, `chart_change` and `task` cards, chart mark "added", Detail graph with the five function nodes, a read-only function node (Adaptation: note, no composer,
  goal/task/context/atoms/constraints/hands), Identity's chat, Identity's question card answered in the card (the answer lands in the department's session), the steps turning green
  in the same document (`window.__sameDocument`) from `atom.updated` + `graph.updated`, the `Done` card, Identity's atoms against the database, Open the team (`/d/web/`: offline, Detailed view, Map,
  Library with the run's routing decisions and template copies "from this run", the template viewer in both modes), Workflow graph, Org chart, then Home Settings (Engine `max_cycles` edit read
  back from `/api/engine/settings`, Connectors Test of the stub). (2) the same Settings Test through the real router over the fake `claude` ("Worked in ... s", one process call).
- `test_browser_resync.py`: (3) stop the app, `○ polling`, start it again on the same folder and port, the second `server.hello` becomes a resync, the graph (a team made meanwhile) and the org chat
  (a line written meanwhile) appear without a reload; the page's `/api/health` read count rises (only `loadAll` asks for it, polling never does). (4) the restarted app has a new token: the old page's write is 401,
  the banner says "This page was opened without its access token. Reload it from the app.", the composer is blocked, the server wrote nothing; the reloaded page writes.
- No existing test or other path was changed. `cdp.py` and the GAP-E2E harness are reused as they are.

## Deviations from the specification
- The node that "turns green" is a STEP node (`st-filed`), not a function node: the real graph gives function nodes only idle/running/waiting/waiting_on_you/fault (ui.md section 6, `graph.py`), so
  `web.identity` goes `waiting_on_you` -> `running` -> `idle`; the green ones are the task's steps, and the test says so. The fake backend's "Identity filed" fixture is not what the real app sends.
- Connectors Test (stub): the stub is the offline mode, and `POST /api/connectors/stub/test` is refused with 409 "not available while the app runs offline" by design (CN-9). The walk asserts that
  sentence on the page (announced with `expect_failed`; the browser's one console line about the 409 is asserted, not ignored). The test that actually works is the added second one over the fake `claude`.
- "Stop the server process": `LiveApp.stop()` and a second `LiveApp` (thread), not a `python -m sutra_app` child. The CLI boot is GAP-E2E's `test_cli_boot.py`.
- The `browser` fixture of `tests/ui/conftest.py` is not visible from `tests/e2e/`; each file has its own copy (three lines) and puts `tests/ui` on `sys.path` for `import cdp`.

## Decisions
- The question is answered by typing into the card (`.canswerbox`, "Answer"): J2's mock question has no options. The vague example brief "A website for my cafe" makes Identity ask.
- `J2_TEMPLATE_LIBRARY=1` goes to the engine (`LiveApp(extra_env=...)`) so the team page has the Library tab; no source file changed.
- Restart on the same port: `harness.bind_socket` is wrapped by the fixture (the harness always binds port 0). A new token: `LiveApp.settings` is copied with the token before `start()`.
- The outage's refused reads are announced as `expect_failed(base_url + "/api/")` and removed after recovery (`_expect_rules.clear()`); recovery must leave zero errors. A recorder subclass of `EventSource`
  (added with `Page.addScriptToEvaluateOnNewDocument`, so no CSP is involved) counts raw `server.hello` frames.

## Known limits
- Polling and the resync both restore the graph and the chat; the test cannot separate them by timing, so the resync is proved by the second hello plus the `/api/health` re-read.
- Time: each outage waits for the browser's own three EventSource retries (about 8 s); the four tests take 31 s together.
- One Chrome, headless 1280x900; no phone width (UI-9's visual matrix owns that).

## Findings for other packages
- UI-6/UI-8: for a moment after a team's question arrives the card reads "Answered" (`answersMap`: the card is in the transcript before `/api/needs-you` lists it); the walk waits for `.c-needs:not([data-answered])`. A flash, self-healing.
- Console: the browser logs one `[network] ... 409` line for the refused Test; the page could disable Test when `health` says offline.

## Mutation check (one pass, scratch copy in /tmp; the package is tests, so the mutants break the app and UI code the walk claims to prove)
13 breakages: resync never delivered, polling threshold 300, no-token sentence reworded, token header wrong (J2 fetch wrapper), function chat writable, Library tab always hidden, Done card reworded,
server accepting any token, resync that refetches only the graph, Constraints section renamed, polling chip reworded, Engine save sending nothing, `graph.updated` ignored.
12 killed at once. 2 survived on the first pass: the Library tab (the tests only checked the pane existed; now `shown()` checks the tab and the panes are visible, killed after) and the token header of
`withToken` (J2 page fetches): the walk makes no write from the J2 page (the app's own `send()` carries the token there), so it is an unreached branch; a J2-page write (e.g. Run settings) would cover it, left to UI follow-ups.
