# GAP2-welcome-settings as built: a first-run card, an owner-click update check, default-model controls, a model and effort picker, and a tab that survives a restart

Five verified gaps of the old Sutra's behaviour, built once each, at a working and tested level. No schema migration (the acknowledgement of the card is a key of the
`meta` table), no J2 file, prompt, route or golden is touched, and the J2 team page is reached only by injection from `dept_ext.js`.

## 1. A first-run welcome that reads the machine

- What the owner gets: until **Got it**, Home opens with one dialog of four readings: which of Claude and Codex can answer now (and, for one that cannot, the
  doctor's one-line fix such as `claude auth login`), where the data lives with its size, the free space and `sutra-pro backup`, what leaves the computer (prompts go only
  to the owner's own CLIs on a subscription login, an API key is refused, credential shapes are scrubbed) and what runs alone versus what is asked (the engine's budget
  and email mode). A machine with no signed-in model is told so on the card, not after the first message dies. **Got it** is stored on the server (another browser or a
  cleared cache does not bring the card back); **Not now** and Esc hide it for this load only and write nothing.
- Where: `ops/welcome.py` (`GET /api/ops/welcome` -> `{seen, facts}`, `POST /api/ops/welcome/seen`, token-gated, writes `meta.welcome_seen_at` with
  `INSERT ... ON CONFLICT DO NOTHING`, so the first time stays and a double click is harmless), `ui/static/js/welcome.js` (`Welcome`: pure `welcomeHtml`, `load`,
  `acknowledge`, `mount`, `start`). The card is mounted on `<body>`, outside `#sview`; role dialog, aria-modal, focus on Got it, Tab stays inside, Esc is Not now.
- Riders (small and local): `main.py` (`OPS_MORE`, registration of two routers in `_mount_ops_api`), `home.js` (one `Welcome.start` call in `boot()`), `home.html`
  (one script tag), `sutra-shell.css` (a block of `.sw*` rules, tokens only; the backdrop is `var(--bg)` because `test_home.py` forbids rgba), `docs/GETTING-STARTED.md` section 3.
- Facts: `models` come from the connector status and the doctor answer already cached 30 s (`ops.api.doctor_answer`); offline (or the stub connector) the one row says
  that a built-in stub answers and no real model is called. A card that is already acknowledged answers `facts: null` and runs no doctor probe. Nothing in the answer is a
  token, a key or an account name (it goes through the app's redactor; a test checks the launch token and the override key).
- Not done: the doctor's fix lines in the Connectors rows (the verifier's "cheap companion"); the old app's always-visible "sees: ..." line.

## 2. An update check by the owner's click

- What the owner gets: Settings -> **About** shows the version, the data folder and **Check for updates**. The answer is "You have 0.1.0; 0.2.0 is out." with the release page
  and the one line for this install (Mac app: download the new DMG; Windows: run the new installer; command: `uv tool install --reinstall` the new wheel; checkout:
  `git pull`), or "You have 0.1.0: up to date.", or "Could not reach GitHub..." (never an error page). `sutra-pro update-check [--json]` says the same.
  It downloads and installs nothing (D34).
- Where: `ops/update_check.py` (`check(current, fetch=None, url=RELEASE_API, how=None) -> Answer`, never raises; `install_kind`, `how_to_update`, `register(sub)` for the
  command), `ops/update_api.py` (`POST /api/ops/update-check`, token-gated, a POST on purpose so a loaded page or a link can never start it; 409 `offline` with the
  stub-mode sentence under `--offline` or the stub connector, no request made). UI: `settings_view.js` (`aboutHtml`, `checkUpdate`, `updateWords`), `home.html` (`#set-about`, a
  rail entry), `home.js` (`paintAbout`, `loadAbout`, `checkForUpdates`). `docs/OPERATIONS.md` section 4 step 0.
- The feed follows D100: the release LIST is read and filtered, never `releases/latest` (which belongs to the older product). A tag counts only if it is exactly
  `sutra-pro-vX.Y.Z` or `sutra-pro-vX.Y.Z-beta.N` (no leading zeros, no trailing newline, no `v` tag, no `-desktop` tag); drafts are dropped; a beta (or a release flagged
  pre-release) counts only when the running version is itself a beta; versions compare as tuples (0.10.0 is newer than 0.9.0; a beta is older than its stable release; PEP 440
  `0.2.0b1` reads as `0.2.0-beta.1`); a version that cannot be read never looks newer. A release link is drawn only for https on github.com.
- The one outbound request: nothing runs on import, on boot or on a timer. A test boots the app, reads every page and route, and counts zero requests, then one click is exactly
  one. The default fetcher sends a `User-Agent` and an `Accept`, nothing else (no cookie, no token), reads at most 2 MB, with an 8 s timeout. It is tested against a throw-away
  server on 127.0.0.1 (a body that stops short, a 500, a closed port, an oversized body), never the real network; everything else is an injected fetcher.
- Not done / decided: no `SUTRA_RELEASE_API` environment override (the fetcher is injected instead, so a variable cannot redirect the app's one outbound request); the repository
  slug (`sankalpasawa/sutra`) is a constant, as in the release docs. No staging, delta download, swap or countdown (old app: mandatory updates), no background poller.

## 3. Default-model controls in Settings -> Connectors

- What the owner gets: a **Default model** group under Connectors, per provider: **Make first**, **On/Off** and the model, from the models the provider lists (the "More models"
  fold). One sentence says what it changes and what it does not: a chat pinned with its pill keeps its pill, and the image checks of Audit keep their own order. When the
  saved first choice cannot run (not signed in, out of quota), its row says "Your saved choice could not be used; Codex is answering." instead of falling back silently.
- Where: `settings_view.js` (`policyHtml`, `policyBody`, `policyProblem`, `policyErrors`, `loadPolicy`, `savePolicy`, `answering`), `home.html` (`#set-models`), `home.js`
  (`paintModels`, `loadPolicyState`, `changePolicy`, one change handler, `make-first` in the click handler; the group repaints on `connector.health`).
- A change is a read-modify-write: `GET /api/connectors/policy`, then `PUT` of the WHOLE policy with only `defaults.order`, `providers.<p>.enabled` and `providers.<p>.model`
  changed (rules, rates, timeouts, sandbox, concurrency and every other key are copied; a test compares them to the file the app ships). The server adopts it live.
- The page refuses, without a request, to turn off the last provider that is on, to make an Off provider first and to save an empty model; a 422 `policy_invalid` is mapped to the
  provider its line names.
- Decided: the server's `parse_policy` does NOT require `defaults.order` to list only enabled providers (the verifier's note assumed it), so "at least one model stays on" is
  enforced by the page (the server still checks the shape). A server-side rule would be a change to the connectors layer and was left out. The `SUTRA_CLAUDE_MODEL` and
  `CLAUDE_CLI_MODEL` environment variables still override the policy's Claude model at the connector; the page does not show them.

## 4. A model and effort picker in the chat pill

- What the owner gets: under the provider buttons of a chat pinned to a provider, a model list (Best available, Opus, Sonnet, Haiku with a short note each; a "More models" group
  with the pinned snapshots, Fable and the 1M-context spellings; for Codex the models Codex itself lists) and an effort select that lists only what the model accepts. Both are
  per chat and stored with the chat's session. A model the provider does not offer is refused at the click with the valid ones named, not saved and failed at the next turn.
- Where: `connectors/model_catalog.py` (`ModelOption`, `claude_options`, `options_for`, `efforts_of`, `names_of`); `ModelInfo` gained `note` and `group` (additive, defaults);
  `ClaudeConnector.models()` now returns the catalog (`best, opus, sonnet, haiku` then the More rows); `ProviderPill` gained `model_options`, `chat_model`, `chat_effort` and
  `can_pick`; `Choice` gained `effort`; `RouterChatPort.choose(session_id, provider, model, effort)` checks the model against `options_for` and the effort against the model,
  and writes both to the stored `SessionState` (a chat that has no session yet starts one with them; a chat whose session runs on the other provider refuses until the provider is
  chosen, as before); `chat_v2.ChoiceIn.effort` (optional) and the route answer `{session_id, provider, model, effort}`; the 422 carries the port's sentence.
  UI: `model_pick.js` (`ModelPick`: `pickHtml`, `choiceRequest`, `selectRequest`), `chat_pill.js` (one lookup that appends the picker), change handlers in `home.js` and
  `node_panel.js`, `dept_ext.js` (`pickers()`: loads the script on a team page), `sutra-panel.css`.
- The ids were probed on the tested CLI. `printf '' | claude --model <id> -p --output-format text` on Claude Code 2.1.308 (no model turn is spent: the run dies on the missing
  prompt after the model name is resolved) accepted `best, opus, sonnet, haiku, fable, claude-opus-4-8, claude-opus-4-7, claude-opus-4-6, claude-sonnet-4-6, opus[1m], sonnet[1m]`
  and refused the control `totally-bogus-model` ("doesn't recognize the model"). `tests/connectors/test_model_catalog.py` pins the catalog to that record.
- The fable/best decision: `best` (the alias for the newest model the account can run) is in the main rows, `fable` (the same model by its own name) sits under More models, so the
  first rows are aliases that cannot go stale and the old three (`sonnet`, `opus`, `fable`) are all still offered. The four pinned snapshots had no window in `budget.WINDOWS`: they
  were added at 1M, "declared, not measured" exactly as the old app did, so every offered Claude model has a known window.
- Changed on purpose: `tests/connectors/test_claude_connector.py::test_models_version_and_capabilities` pinned `["sonnet", "opus", "fable"]` and now pins the catalog's first four
  and that the three are still present.
- Limits: no picker while nothing is pinned (a model needs its provider; the pill says the app chooses); a chat that still runs on the other provider shows a note that the model
  can be chosen after its next message (a provider switch starts a fresh session on the policy's model, so a model for the new provider cannot be stored earlier); a Codex that cannot
  list its models offers no picker and the server checks only the shape of a name, as before. The effort select shows "Default" until the chat has an effort.
  Not taken (as the verifier listed): the fast/service-tier switch, per-provider switches, DeepSeek.

## 5. A page that outlives a restart

- What the owner gets: quit and reopen the app (or `sutra-pro stop` and start it), and the tab that was open keeps working: the next Send or Answer goes through. Before, every
  write was refused with "This page was opened without its access token. Reload it from the app." and the owner had to notice, reload and retype.
- Where: `ui/static/js/tab_heal.js` (`TabHeal`: `parseBoot(html, {page, dept})`, `heal(ctx, fetchFn)`, `isDead`). Rider in `sutra_ctx.js` (`healer`, `healToken`, a `repeated`
  parameter on `send`, a `.then` in the `installFetch` wrapper): a write refused with `401 bad_token` reads the page's own path and query again (`cache: no-store`, through the page's
  ORIGINAL fetch, so no token is sent), takes the token from the boot block, and repeats the write ONCE. It works for the app's own calls and for J2's wrapped fetch on a team page (a
  string body or none; a body that cannot be sent twice is not repeated, and the caller still gets its own 401). `home.html` loads the script after `sutra_ctx.js`; a team page gets it
  from `dept_ext.js` `pickers()`.
- No new route (D81): the token still reaches a page only through its boot block. `parseBoot` accepts only a block of the same page kind and the same team, a token of at least 16
  characters, and a text of at most 2 MB; a path that could leave the origin (`//host`) is never fetched. One heal runs at a time (callers that arrive during it share it) and at most
  one a minute, so a server that keeps refusing cannot make a loop; when the heal fails the existing "opened without its access token" banner shows as before. A read never heals (it
  carries no token). Without `tab_heal.js` the page behaves exactly as before.
- Proof: `tests/ui/js/tab_heal.test.js` (18, real `sutra_ctx.js` in a vm), `tests/ui/test_tab_heal_contract.py` (two real `create_app` instances with different tokens over one
  data folder: the old token is a 401 `bad_token`, the page's own path carries the new one in the parseable block, the write then passes; no route hands out the token), and an
  end-to-end browser test with the real scripts (`/__fake/restart` changes the token under an open page).
- Not done: the optional snack area (a bottom-right notice for "Sutra stopped, reconnecting" and uncaught errors); failures stay inline banners. `console_view.js` reads the token once
  at mount for the diagnostics download, so a console tab opened before a restart still needs a reload for that one button.

## Tests
- Python: `tests/ops/test_welcome.py` (7), `tests/ops/test_update_check.py` (34), `tests/connectors/test_model_catalog.py` (9), six cases added to
  `tests/connectors/test_chat_port.py` and one to `tests/orchestrator/test_api_chat_v2.py`, `tests/ui/test_tab_heal_contract.py` (2).
- JS: `welcome.test.js` (19), `settings_policy.test.js` (20), `settings_about.test.js` (10), `model_pick.test.js` (12), `tab_heal.test.js` (18).
- Browser (opt-in, `SUTRA_BROWSER=1`, headless Chrome): `tests/ui/test_home_welcome_settings.py` (8: the card, Not now, Esc, Got it with a reload, Make first with the whole policy,
  a model change and the last-provider refusal, About, the picker, the heal end to end). The fake backend serves the welcome card (seen by default), the policy and models routes, the
  update check and, only when a test asks, a chat pill; its guarded-writes list names the three new writes and the choice route.
- Found on the way, not touched: `/api/chats/cs_org/providers` is not served by the fake backend, so every Home browser test that does not announce it errors at teardown with that
  404 (the test files say so in comments); it was so before this package (`home.js` asks for it at load). The new tests turn the fake's pill route on instead.

## Shared files edited, kept small (for the merge)
`main.py` (one constant, three lines in `_mount_ops_api`), `ops/cli.py` (one name in `OPTIONAL_MODULES`), `home.js` (state, paint and change handlers, one `Welcome.start` line, one
`onPillChange`), `home.html` (three divs, one rail button, three script tags), `settings_view.js` (two groups added before the flows section), `sutra_ctx.js`, `chat_pill.js`,
`node_panel.js` (one handler), `dept_ext.js` (its own `pickers()`; the long list line is untouched), `api/chat_v2.py` (`ChoiceIn.effort` and the route call), `sutra-shell.css` and
`sutra-panel.css` (blocks), `tests/ui/fake_backend.py` (one function and one call), `tests/ui/test_fake_backend.py`, `tests/ui/test_home.py` and `tests/contracts/test_contract_world.py` (the pinned lists: the guarded writes, the rail buttons, the routers of the contract world).
