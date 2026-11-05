# UI-1 as built: serving and boot

Owns `sutra_app/ui/{__init__,boot,routes}.py`, `tests/ui/test_serve.py`, this note. Spec: `docs/design/ui.md` 4.1, 4.2, 10, 11;
S3-web-01, -02, -09, -13; D72, D81, D82.

## What was built
- `boot.py`: `BootContext` (closed, frozen, strict; token >= 16 chars; `home` has no dept; `dept` needs the id rule and a label),
  `is_url_id`, `DeptLike`, `dept_boot`, `archived_note`, `render_page` (+ `BootMarkerError`), `inline_script_hashes`, `csp_header`.
- `routes.py`: `build_router(*, token, department, version, pages_dir)` with `/`, `/d/{dept}` (308), `/d/{dept}/`, `/favicon.ico`
  (GET and HEAD); `mount_static(app, static_dir)` at `/ui`; a page cache keyed by (mtime, size) that reads and hashes a file once.
- `__init__.py`: `mount(app, services)` (reads `settings.token`, `version`, `department` only; idempotent) and the exports.
- 180 test cases, about 2 s. 10 skip: 6 "real page" cases wait for UI-2/UI-7/UI-3 files, 4 Chrome cases need `SUTRA_BROWSER=1`.
- Checked by hand in Chrome 156 on the real J2 page (copy in /tmp, nothing committed): under this policy the DOM was byte-identical
  to a run with no policy and showed no violation; under `script-src 'self'` alone both inline scripts (lines 320, 428) were blocked.
  The page has exactly 2 attribute-less inline scripts. Mutation check: 164 breakages in a scratch copy, all caught (4 survived the
  first pass and got tests: page name not a Literal, scan resuming inside a script, cache stamp taken before the read, redirect id
  not quoted); one more breakage (no line-ending normalisation) showed the first Chrome test used a one-line script, now multi-line.

## Deviations from the specification
1. `BootContext` is also frozen, strict and hides input in errors (spec: `extra="forbid"`): no coercion of a flag, and a refused token is not echoed.
2. The id rule uses `fullmatch` (`$` accepts a trailing newline) and refuses `.` and `..` (path segments, never a team).
3. The boot block always carries all seven fields; the spec's example leaves out the defaults `archived` and `note`.
4. `inline_script_hashes` turns a lone CR into LF as well as CRLF (the HTML parser does both; Chrome confirmed it).
5. `csp_header` refuses any source that is not `'sha256-<44 chars>'` and lists a hash once; `inline_script_hashes` lists every script.
6. `mount_static` tolerates a missing folder (warning, then 404s): Starlette would raise at the first request, and the API must not die.
7. Left open by the spec: the 404 page gets the page headers and a policy without hashes, its id is cut at 80 characters and escaped;
   a page file that is missing, not UTF-8 or has no single marker answers 500 `text/plain` naming the page, never a path, and logs it.
8. HEAD is routed explicitly (FastAPI adds none); the pages are left out of the OpenAPI schema.
9. `mount` reads `PAGES_DIR` and `STATIC_DIR` from `sutra_app.ui` when it runs (tests patch them); `build_router` checks the token at build time.

## Decisions
- Handlers are plain `def`: FastAPI runs them in its thread pool, so file reads, hashing and the synchronous `department` lookup
  (one SQLite connection per thread in the orchestrator) never block the event loop.
- The boot block is JSON with every `<` as `<`; the dept in it is `row.id`, the label `row.name`. `/d/{dept}` redirects without a lookup.
- `/?dept=` is honoured only for exactly one `dept` value that passes the rule and `Services.department`; other parameters pass byte for byte.
- Tests walk routes with `fastapi.routing.iter_route_contexts`: FastAPI 0.162 keeps included routers lazily, so `app.routes` shows an
  `_IncludedRouter` and not their routes.

## Known limits
- The scanner ends a script at the first `</script`; a script holding `<!--` followed by `<script` is cut differently by browsers. None of ours does.
- A rewrite that keeps both mtime and size is not noticed by the page cache (tested as the documented rule).
- The policy and the hashes were measured in Chrome 156 only. `style-src` keeps `'unsafe-inline'` (S3-web-09). No `X-Frame-Options` (`frame-ancestors` covers it).
- Until UI-2 and UI-7 merge, `/` and `/d/{dept}/` answer 500 "cannot be served": `pages/` is empty.

## Follow-ups
- UI-2 (`j2_ui.html`): one `<!--SUTRA-BOOT-->` in `<head>`, exactly two attribute-less inline scripts, no external URL. UI-7 (`home.html`): one marker, expected one inline script.
  The "real page", style-sheet and static-file cases in `test_serve.py` switch on when the files exist (they must pass then).
- UI-0 (fake backend): `build_router(token=, department=, version=, pages_dir=)` and `mount_static(app, static_dir)` are the entry points.
- ORCH: call `sutra_app.ui.mount(app, services)` last; `Services.department` must be sync and callable from a worker thread; a route walk
  must flatten `_IncludedRouter` (see above) and skip the `/ui` `Mount`, which has no methods.
- UI-9: the smoke test is the check that no inline script of the real pages escapes the hashes (zero console errors).
