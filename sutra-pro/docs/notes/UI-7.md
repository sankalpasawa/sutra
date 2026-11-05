# UI-7 as built: Home page and Settings

Owns `pages/home.html`, `static/js/{home,settings_view}.js`, `static/css/sutra-shell.css`, `tests/ui/test_home.py`,
`tests/ui/js/{settings_engine,settings_connectors}.test.js`, this note. Spec: `docs/design/ui.md` 3.3, 6.6, 6.7, 7, 8, 9, 10; S1-contracts-03/-08, S3-web-06/-13, S4-fnodes-12; D18.

## What was built
- `settings_view.js` (`SettingsView`, no DOM, no timer of its own): `engineHtml`, `engineBody` ({set, unset}), `engineErrors`, `formProblems`, `connectorsHtml`, `signInState`,
  `appearanceHtml`, and the flows that take an `api`: `testConnector`, `signIn` ({done, cancel}), `watchHealth`, `loadEngine`, `saveEngine`. `dept` is put in the query by hand.
- `home.html`: J2's Simple skeleton (`#sview`, rail in `#dview`, `#nodepanel`), one inline script (first-paint theme, hashed by the CSP), no handler attributes.
- `home.js` (`HomePage`, with `state()`): `boot loadAll renderChat send answerNeeds selectPane renderRail renderNeeds onEvent themeApply barSet renderSettings saveEngine
  testConnector signIn` plus `cancelSignIn errorWords poll`. Org chat `cs_org` through `ChatView`; graph and chart through `GraphView`/`OrgChartView` (created when their pane
  first shows); node clicks open `NodePanel`; one `SutraEvents` stream with `pollFn`; deep links `?pane=graph|chart&node=&change=`.
- `sutra-shell.css`: right column, start page, banner, rail Teams and Settings, the Settings groups; tokens only (a test fails on a hex colour or a url).
- Tests: 71 node tests (0.3 s); `test_home.py` 6 static tests (in the gate) and 39 browser tests (`SUTRA_BROWSER=1`, about 50 s, one Chrome each).

## Deviations from the specification
1. `settings_view.js` is not purely functions of strings: it also holds the small server flows (Test, Sign in, health watch, load and save), each given an `api`, so the node tests
   can prove "Test posts ...", "polls until ...", "Cancel sends DELETE" without a browser. It still touches no DOM and no global.
2. "A field returned to its default goes to `unset`": for one team the layer below is the defaults AND the all-teams file; a value equal to it is unset only when the team's layer holds
   the field, otherwise it is set (the environment can make `effective` differ from every layer).
3. `signIn` also stops by itself once `expires_in` + 30 s have passed without an answer (shows "expired"); `signInState` has steps idle, pending, signed_in, failed, expired, cancelled, error.
4. An answered `needs_you` card reads just "Answered" (ChatView's card has no place for the text); the owner's own click is remembered only to open/close the card.
5. The chat's `choice.option` is the option's `id` (label when it has none); `text` is the label.

## Decisions
- Right pane default is the Workflow graph; Chat (`#gochat`) is always current in the rail, the right pane's item has `aria-current="true"`. Settings in the rail are three buttons that open the pane at that group.
- `has-site` is set when the graph has more than the root, or a pane other than the graph was picked; a rail click on a phone also shows the right column (`sp-preview`), an automatic first-graph switch does not.
- The progress bar appears with the first `chat.turn` of cs_org and stays; `error` hides it; a finished turn re-reads the whole org chat (a message can turn into `state: error` after it was read).
- Engine edits are never repainted over by events (only by save, scope change, or a change of the team list); a refused save keeps what was typed and names the field.
- On a phone (<= 600 px) the menu button is moved before the header (J2's own page leaves it below the screen).
- `connector.*` events refetch `/api/health` once each; Sign in polls every 2 s (a test shortens it by wrapping `SettingsView.signIn`).

## Known limits
- Labels and hints of the 30 engine fields are this package's wording (`FIELD_TEXT`); the engine section gives none. Unknown fields show their own name.
- The polling fallback (X4) is wired (`pollFn` = `HomePage.poll`) and tested by calling it; the real drop-and-reconnect walk is UI-9's smoke. Chrome 156 only.
- A needs-you answer to a team whose session is not in `/api/departments` asks `/api/departments/{id}` first; no test drives that path.
- Mutation pass (scratch copy in /tmp, 18 single-site breakages in `settings_view.js` and `home.js`): 17 died at once; the survivor (a team base that ignores the all-teams file) got a test and
  died. The pass also showed that a flow which never stops hangs the node run with an instant fake wait: the fake wait now yields to the event loop and the fake api fails after 300 calls.

## Follow-ups
- UI-9: the smoke can use `HomePage.state()`; the visual matrix needs `home-start`, `home-graph`, `home-chart` (pane buttons `#rail [data-pane]`) and a Settings shot per group.
- ORCH/engine: `GET /api/engine/settings` must answer `department` only with `?dept=`; the page decides "this team" from that key.
