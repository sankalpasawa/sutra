# UI-0 as built: test tooling

Owns `tests/ui/{conftest,cdp,fake_backend,test_fake_backend}.py`, `tests/ui/fixtures/**`, `tests/ui/screens/.gitignore`,
`scripts/capture_j2_fixtures.py`, this note. Spec: `docs/design/ui.md` 10 (Tooling), 11; S1-contracts-03/-08, S3-web-06/-13, S4-fnodes-08; D85.
An interrupted first attempt left the code and fixtures uncommitted and five areas without tests; this run reviewed all of it, wrote
those tests (J2 routes, UI mount, the owner's lines, cdp.py, conftest, capture script), fixed what they found, and committed.

## What was built
- `cdp.py`: headless Chrome over CDP (`websockets` sync client, reader thread). `find_chrome` (SUTRA_CHROME, macOS app, PATH, Playwright cache),
  `ChromeProcess` (own profile and session, SIGTERM then SIGKILL), `Browser` (goto, reload, js, wait_for, exists/count/text, click, hover, type,
  press, shot, set_theme, set_size, console_errors, failed_requests, expect_failed, clear_diagnostics, dialogs), `--self-test`, `--where`.
- `conftest.py`: the `browser` marker and fixtures `fixtures_dir screens_dir make_fake_server fake_server fake browser`. `browser` skips without Chrome
  and fails a test that ends with a failed request it did not announce.
- `fake_backend.py`: `make_app(fixtures_dir, pages_dir, static_dir, token, version)` mounts the real `sutra_app.ui` and serves ORCH 6 from the
  fixtures (library ids, J2's nine status words, seven edge kinds, five atom words), J2's 28 routes at the root (`?dept=`, `?run=` per team, captured
  bytes), `/api/engine/settings`, connector Test and Sign in, `/api/atoms/log`, SSE (hello without id, ring of 1000, resync, topics, `once`) and the
  write guard (token, Origin, Host). Four stages (`1` new app, `2` Web asks about the menu, `3` answered, `full` two teams, divisions, a pending merge,
  every status word); the first brief and an answer play scripted flows of events. Controls: `/__fake/emit|fixture|fail|log|state|reset|page|mount`.
- `fixtures/`: the 22 items of the design plus `chart.v3`, `changes.v3`, `functions.json` (goal, task, context, constraints, check texts per function),
  `atom-log.json`, `chat-others.json`, `j2/` (34 files, 1.05 MB, from a J2 mock run at ce2631f, state 118 KB) and `tools/` (stand-in DevTools, Chrome, J2).
- `capture_j2_fixtures.py --j2 <checkout> --j2-python <python> [--check]`: runs J2's server under a frozen clock in a scrubbed environment, saves routes
  byte for byte, the harness inputs and goldens, `MANIFEST.json`; proves J2 untouched (git status before and after). About 2 s; `--check` is byte-exact.
- `test_fake_backend.py`: 311 test functions, 7 groups (see its docstring); no Chrome, J2 or model needed. Opt-in: `SUTRA_BROWSER=1` (7 Chrome tests),
  `SUTRA_J2_CHECKOUT=<J2>` (+ `SUTRA_J2_PYTHON`) for the drift check against the real J2.

## Deviations from the specification
1. graph.v3 has Identity `idle`, not `filed`: a function node uses the first five status words only (S2-models-03).
2. More fixtures than listed, and the stage model; `?run=` is accepted only for the team's own runs (D73), which the table does not say.
3. A line the owner writes outside a scripted story gets an id after the whole fixture of that chat (ids ascend, gaps are normal).
4. Extras in `Browser` (`hover`, `startup_timeout`, `expect_failed`, `clear_diagnostics`, `dialogs`) and timeouts as names (`cdp.STOP_GRACE_S`, `STARTUP_S`).
5. Real-page tests (`/` and `/d/web/` on `pages/home.html`, `pages/j2_ui.html`) skip until UI-7 and UI-2 merge; the same checks run on stand-in pages now.
6. `--check` calls a J2 that moved to a new commit but gives the same bytes "ok" (it did: J2 is at 33aeeda, template provenance in the Library tab).

## Decisions
- J2 reads are served from captured bytes (no re-serialising), so UI-2's parity and UI-8 see what J2 sends.
- SSE is hand-framed `StreamingResponse` (event, id, data), not `EventSourceResponse`: exact control of ids, replay and drops.
- Chrome tests cover what only Chrome shows: the driver, CSP violations as console errors, the mount pages with the real `sutra_ctx.js` and `sutra_events.js`.
- Time limits in tests are generous upper bounds; states and lower bounds are what is asserted (the machine can be loaded).

## Found while testing
- `run_team` died with a raw URLError when J2 exited mid-run; `/api/say` answered 500 for `{"text": 5}`; the drift check failed when only J2's commit moved.
- Mutation check (scratch copies under /tmp, single-site breakages, MUTATION_RESULT)

## Known limits
- Fixtures are checked against the design, not against library models (`Atom`, `LedgerRow` are not merged): add a validation test when they are.
- A line posted to a division goes to the department chat only; the division transcript is a fixed fixture. Page-size defaults (50, 200) are not observable with the small fixtures.
- Chrome 156 is the only browser tried. Priority, Coordination and Audit atoms are generated from `functions.json` and the node's counts.

## Follow-ups for other packages
- UI-2: goldens are `j2/golden-{simple,sprog,workflows,rail,needs,map,agent,layout}.json`; harness inputs `state.json`, `previews.json`, `render-docs.json`, `maps.json`. J2 has moved (see 6): re-check the anchors.
- UI-5/UI-6: `/__fake/mount/graph.html` and `panel.html` expose `window.view|panel|mounted|events|liveState|mountErrors|opened|navigated` (comments in the files).
- UI-9: the smoke walk can post the first brief and read the story; for a visual matrix build one `cdp.Browser` per module (the `browser` fixture is per test).
