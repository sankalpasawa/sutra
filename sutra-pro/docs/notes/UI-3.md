# UI-3 as built: client core

Owns `sutra_app/ui/static/js/{sutra_ctx,sutra_events}.js`, `tests/ui/js/{ctx,events}.test.js`, `tests/ui/test_node_suite.py`, this note.
Spec: `docs/design/ui.md` 4.2, 5 (E2, E6), 7, 8, 9 X4, 10; S1-contracts-03, S3-web-03, -06, -10, -15; D80, D81.

## What was built
- `sutra_ctx.js`, one global `SutraCtx` (the file is one function, so J2's top-level names cannot clash; also `module.exports`):
  `boot`, `dept`, `currentTab`, `run()`, `esc`, `paint`, `tab`, `withDept`, `installFetch`, `J2_PATHS`, `ApiError`, `api.get|post|put|del`.
  It also does E2's job: the two preview iframes' `data-src` becomes `src` (plus `dept`) at DOMContentLoaded unless J2 set a `src` first.
- `sutra_events.js`, one global `SutraEvents`, no dependency: `TYPES` (14 names), `connect`, `coalesce`.
- Tests: `ctx.test.js` 75 cases, `events.test.js` 62, `test_node_suite.py` 9. The scripts run in vm contexts as a browser loads them (fake
  document, fetch, clock, EventSource); node time 0.4 s, pytest 1.5 s. The wrapper test proves a failing file fails the run.
- By hand in Chrome 156 (stand-in server in /tmp, nothing committed): boot block with `<`, wrapper (`dept` once, token on POST/PUT/DELETE
  only), frames, `sutra:tab` on document and window, a drop-and-reconnect server (the browser itself sent `Last-Event-ID: 5`, no new
  EventSource made, every later hello became `server.resync`), three HTTP 500 answers (readyState CLOSED; streams re-created at 1.0, 3.1, 7.1 s;
  `polling` at 3.1 s, `live` at 7.1 s, polling stopped, first event `server.resync`).
- Mutation check in a scratch copy: 288 single-site breakages, all caught. Earlier passes left 10 gaps that got tests (encoded query keys, a
  foreign window's fetch, paint order, a missing console, a throwing close(), a stream forgotten after a failed re-create, no onState, the
  TypeError text, a pollFn error text, close() inside a callback) and one real bug found while reading them: a close() inside `onState("polling")`
  left the polling timer running (the timer is now made before the callback). About 20 guards that a surrounding try/catch made redundant
  were removed: a mutant there is equivalent, so it could only ever be dead code.

## Deviations from the specification
1. The first `server.hello` of a handle is ignored only when no error came before it; after an error it acts as `server.resync`. A page opened
   while the server restarts would otherwise never refetch what its first calls missed.
2. A later hello reaches `onEvent` as `"server.resync"` with the hello's own body; a real resync is forwarded unchanged (two after a restart: coalesce).
3. `J2_PATHS` is a frozen object `{exact (23), prefixes (4), matches(pathname)}` (a list of names in the design); the 23 and 4 equal j2_server.py
   (`SUTRA_J2_CHECKOUT=<J2> node --test tests/ui/js/ctx.test.js` re-checks it; run once here).
4. The token goes only to root-relative URLs (wrapper and `api`); an absolute, `//host` or `/\host` URL never gets it, and `api` rejects such a
   path with `bad_path` before any request. The design says "every non-GET"; D81's point is that the token stays on this origin.
5. `api` calls use `window.fetch` as it was before `installFetch(window)`, so they never get `dept`, even for a path J2 also has.

## Decisions
- `ApiError({status, code, message, details})` or `ApiError("code")`. The client makes `network` (status 0), `bad_payload`, `bad_path`; an error
  body that is not the envelope gives `http_<status>` (J2's `{error:"text"}` and FastAPI's `{detail:"text"}` supply the message).
- The wrapper is installed at load only for `page:"dept"` (the design's words); a department from the path alone feeds `withDept` and `runQ`.
  `dept`: Home gives `""`; else the block's `dept` if it passes the id rule (never `.` or `..`); else `/d/<id>` of the path, up to a `/` or the end.
- `sutra:tab` has `detail {name}` and bubbles; `tab()` returns whether it dispatched; `paint()` whether it touched the DOM.
- `connect`: state starts `offline` (no callback); `open` counts as live like a hello; errors are consecutive and cleared by either; the first poll
  comes after one `pollMs`; one `pollFn` at a time; a stream the browser closed for good is re-created after 1, 2, 4, 8, 15, 15 s with no `after`;
  a constructor that throws is an error; no EventSource means polling at once (`offline` with no `pollFn`); a body that is not JSON arrives as `{}`;
  a callback that throws is logged with `console.error` and the stream goes on; after `close()` nothing is called, even from inside a callback.
- `coalesce(fn, ms)`: the window starts at the first call, the run gets the last call's `this` and arguments, `cancel()` for a view's `destroy()`.
- `api`: `cache: "no-store"`, no token on GET, a body only when given, an empty 2xx answer is `null`, a non-JSON 2xx is `bad_payload`.
- "On Home one `connector.*` event triggers one `/api/health` refetch" is tested as the wiring (`connect` + `coalesce`); the refetch is UI-7's.

## Known limits
- No timeout or abort on `api` calls; a `pollFn` that never settles stops polling until the browser ends its request.
- `coalesce` merges by time and keeps only the last arguments; a page that needs one refetch per key keeps one coalesced function per key.
- Verified in Chrome 156 only. A `Request` object passed to `fetch` is not touched (J2 passes strings).

## Follow-ups
- UI-2: load `sutra_ctx.js` after the boot block and before J2's script; E4 `runQ`, E5 `boot.dept_label`, E6 `tab`, E10 `dept` work as written (tested with the
  stub of `j2_ui_render.js`); the ported iframes must keep `data-src`. UI-0's fake backend: `server.hello` first, without `id:`.
- UI-4 to UI-8: give `connect` a `pollFn` (the X4 list), coalesce refetches (about 150 ms), treat `server.resync` as "refetch everything shown",
  and call `close()` / `cancel()` in `destroy()`. UI-7's Settings passes `dept` itself: `api.get("/api/engine/settings", {dept})`.
- UI-9: the smoke test is the first run of the hello-resync rule against the real server.
