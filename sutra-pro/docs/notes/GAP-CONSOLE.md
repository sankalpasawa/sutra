# GAP-CONSOLE as built: owner console (usage and cost, Atom log, health, diagnostics) and HTML error pages

Built: `sutra_app/ops/api.py` (router `/api/ops/{info,doctor,usage,diagnostics}`), `ui/pages/console.html`, `ui/static/js/console_view.js`, `ui/static/css/sutra-console.css`;
in `ui/boot.py` page `console` (no team), in `ui/routes.py` `GET /console` (same boot, CSP hash and headers) and the HTML 404/500 page; a rail link in `home.html`.
Tests: `tests/ops/test_api_ops.py` 33, `tests/ui/test_console.py` 16 (+1 browser, SUTRA_BROWSER=1), `tests/ui/js/console_view.test.js` 44 (run by `test_node_suite`).

## What it does
- `/console`: Usage and cost (period today/7d/30d/all in UTC dates, stub toggle, tiles calls / Claude usd / Codex tokens, a bar per day, team and function table, ten dearest atoms with
  `/d/{dept}/?tab=<fn tab>` and `/?pane=graph&node=<id>` links, connectors with quota and the next reset), Atom log (paged 25, newest first), Health (facts, doctor checks, Check again, Download diagnostics).
- Live: `usage.recorded` coalesced 1 s, `atom.updated`, `connector.*`, `task.updated`; the 2 s polling fallback (the doctor only every 30 s).
- Diagnostics zip (GET with `X-Sutra-Token`): info, doctor, last 2 000 log lines, public settings, schema versions, department folder sizes, README. Redactor first, then patterns
  (`sk-` keys, bearer, `key=value`). No chat, prompt, site file, `.env`, or engine.json value.
- Error pages: `Accept` starting with `text/html` and a 404 or 500 (also an AppError 404) gives app name, request id, Home link, log path; JSON clients keep the envelope.

## Deviations from the specification
- New route `GET /api/ops/usage?period=&include_stub=`: `/api/usage/summary` has no time window, so the period picker could not work from it. One call returns totals, providers, days, teams, functions, top atoms.
- The HTML error pages are installed from `ui.routes.mount_static` (wraps every exception handler; the handler still runs first, so logging and redaction are unchanged). `main.py` and `ui/__init__.py`
  are not mine, and `mount_static` is the one call of the UI that receives the app. Only 404 and 500 change; 401, 405 and 422 stay JSON even for a browser.
- `home.js` is unchanged: a plain `<a href="/console">` needs nothing there. The link sits in a new rail section "Owner" (class `railteam`).
- Atom log: node filter goes to the server (`node_id`, from seq 0, cap 5 000 rows); state, check, UTC date filters run on the loaded rows. The log route pages forward only, so the console starts at
  `last_seq - 1000` (`atom_log.last_seq` of `/api/ops/info`) and has "Load 1000 older rows".
- The "node drawer" link is `/?pane=graph&node=<id>` (Home selects the node in the graph); the drawer itself is not opened by a link in Home today.

## Decisions
- "notional, subscription" is shown when the provider's rows say `billing: subscription` (Claude's `usd_basis` is `reported` either way); otherwise the basis word (rate card, no price).
- Doctor runs with `offline=settings.offline`; its `port` check is replaced by "this server listens on host:port" (it would otherwise warn about the port it holds). `?refresh=1` skips the 30 s cache.
- Uptime is from the lock file's `started` when it names this process, else the import time of `ops.api`.
- A card is `GET /api/atoms/{id}` drawn by `FnodeView.atomHtml`; when the atom is gone, the card the ledger row can give.

## Existing tests changed (intended behaviour change, nothing weakened)
`tests/ui/test_serve.py` (route set and 405 list gain `/console`), `tests/contracts/test_contract_route_table.py` (pages set), `tests/contracts/test_contract_world.py` (the world mounts the ops router so
the view-script route check sees `/api/ops/*`), `tests/ops/test_logsetup.py` (the ops module now exists: asserts True, and False only with the module hidden).

## Known limits
- Rows in the browser test have no atom behind them, so its card fetch 404s on purpose. Quota times show in the browser's zone; "today" is the UTC date.
- First doctor call online runs the CLI status probes (seconds, no model call); `fake_backend` serves neither `/console` nor `/api/ops`.

## Follow-ups
- GAP-DOCS: document `/console`, `/api/ops/*`, the diagnostics zip. Later: move `install_error_pages` into `ui.mount` when `ui/__init__.py` is free. Chassis: nothing needed.

## Mutation check (one pass, copy in /tmp)
20 breakages (period start, inclusive boundary, stub filter, cache ttl, token guard, tail length, key pattern, top order, notional flag, port override, doctor offline, 500 page, accept rule, escaping,
boot rule, from-date, sort order, safePath, window, notional label): all killed at once; no survivor.
