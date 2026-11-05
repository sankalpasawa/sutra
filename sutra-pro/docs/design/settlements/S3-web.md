# S3 · Web layer settlements (UI, orchestrator, engine)

_Batch S3-web · 2026-11-04 · decided autonomously, nothing was asked · record for `docs/DECISIONS.md` and the architecture diagram · machine twin: `S3-web.json` (exact patch text per target; this file is the short human version)._

**Sources read.** ui.md, engine.md, orchestrator.md (as they stand: engine 00:57, orchestrator 01:08, ui 00:48), library.md 8/9/13/18, connectors.md 6, sections.json, DECISIONS.md D1-D12, the J2 page and server at `ce2631f` (working tree clean for `j2_ui.html`), `j2_map.py`, and the FINAL function-node spec (`docs/design/function-nodes-spec.json`, byte-identical to `/private/tmp/claude-501/arch/spec-function-nodes.json`; it appeared during this run, so the draft was not used). Several disagreements named in the task text were already half-closed in the newer engine and orchestrator text; each block says what the files really say now.

**Measured here (Chrome 156 headless, `uv build`, J2 source; scratch files under the session scratchpad, nothing in any repo):**

| Check | Result | Used in |
|---|---|---|
| Real `j2_ui.html` under `script-src 'self'` + the 2 inline-script hashes (no `'unsafe-inline'`) | page ran: 11 rail sections drawn, 407,031 bytes of DOM, identical to the `'unsafe-inline'` run | 09 |
| Same page under `script-src 'self'` only | both inline scripts (lines 320, 428) blocked | 09 |
| Same page under `style-src 'self'` only | inline-style violations (43 `style=` attributes, one `<style>` in generated SVG at line 2426) | 09 |
| J2 page: inline event handlers / `eval` / XHR / EventSource / iframe DOM access | 0 / 0 / 0 / 0 / 0 | 09, 10 |
| Same-origin framed page, no header | read the parent's boot token | 14 |
| Same framed page with `Content-Security-Policy: sandbox allow-scripts allow-forms allow-popups; frame-ancestors 'self'` | script ran, parent access threw `SecurityError` | 14 |
| Two servers on 127.0.0.1 ports A and B, cookie `sutra_token` | B received A's cookie; after B set its own, A's next request carried B's value | 01, 03 |
| Wheel from the chassis `pyproject.toml` over a 35-file dummy tree | 32 packed; the 3 not packed: `engine/VENDORED.md` and two decoys | 08 |
| The 12 UI port anchors against `ce2631f` | all present with the stated counts | 10 |
| J2 `do_POST` | `self.path == "/api/say"` (exact, query breaks it); `do_GET` uses `urlparse(...).path` | 07 |

---

### S3-web-01 · Who serves Home and the J2 page (task 1)
- **Decision.** `sutra_app.ui` is the only server of HTML and static files: `GET /` Home, `GET /d/{dept}/` the J2 page, `GET /d/{dept}` and `GET /?dept=<id>` answer 308 (no-store; the second is a compatibility shim, nobody generates it now). The engine has no page route, no `pages.py`, no `sutra_dept` cookie, no default department (engine.md 4.9, 7.1 rows 1-2 and ENG-D4 already say so; only ui.md 0, 3.2, 13 and sections.json are stale). `paths.ui_dir()` is not created, so it returns nothing: UI tests import `sutra_app.ui.PAGES_DIR`, the engine's legacy flow tests read J2's own page through `SUTRA_J2_CHECKOUT`. The stdlib `j2_server.py` serves a page only for legacy tests and never imports the UI.
- **Why.** The UI owns the 12 edits and the token boot block; a cookie is shared by tabs and ports (measured), a path is not.
- **Rejected.** Engine page at `GET /` with a cookie and default department; engine `pages.py` calling `render_page`; `paths.ui_dir()`; a Home mode in the J2 page.
- **Changes.** ui: §0 bullet, §3.2 harness row, §4.1 `GET /` row, §13 requests 8-9, sections.json `open_risks[0]`. engine: §4.9 UI sentence, §3.1 `j2_server.py` row, §7.1 row 1. orchestrator: §6.4 mount order. diagram: Experience band note.
- **Diagram label.** pages from UI only · no cookie

### S3-web-02 · Names and the one department lookup (task 2)
- **Decision.** One package `sutra_app.ui` (`mount`, `build_router`, `mount_static`, `render_page`, `inline_script_hashes`, `csp_header`); the alias `sutra_app/web.py` is not created. One boot injector `render_page`; `inject_boot` exists nowhere now. `ui.mount` reads exactly `services.settings.token`, `services.version`, `services.department`; the engine's `mount` reads `data_dir, resolve_run, deliver_to_department, stop_live, department, require_token, redact`. `lookup_dept` is removed: ONE lookup `Services.department(dept_id) -> DeptRow | None` (`id, name, archived, merged_into_name`, orchestrator 3.3); each plug-in declares a local `Protocol` `DeptLike`; both `DeptInfo` classes are deleted. `Settings.token` has at least 16 characters.
- **Why.** orchestrator 3.5 already imports `sutra_app.ui`; one lookup means one row type and no mapping layer.
- **Rejected.** The alias; `inject_boot`; `lookup_dept` beside `department`; two `DeptInfo` classes; UI importing the orchestrator's model.
- **Changes.** ui: §3.2, §4.1 code block and table, §10 `test_serve.py`, §11 UI-1, §13 request 4. orchestrator: §3.3 DeptRow row, §3.5 EngineServices and Plug-ins, §2 module map, §3.1 token validator. engine: §4.9 `EngineServices.department`. WP: **UI-1** owns without `sutra_app/web.py`.
- **Diagram label.** one dept lookup: Services.department

### S3-web-03 · The write token (task 3)
- **Decision.** Header `X-Sutra-Token` ONLY; no cookie anywhere. Every non-GET/HEAD/OPTIONS request needs it (401 `bad_token`); a present `Origin` must equal `http://<Host>` (else 403 `bad_origin`, `Origin: null` included; absent is allowed); Host allowlist on the whole app (400). ONE dependency `require_token` in `orchestrator/api/deps.py` = `Services.require_token`; the engine uses `Depends(services.require_token)`; the connectors' `write_guard` is a required keyword parameter receiving it (the name exists only there). A route-walk test fails if any non-GET route lacks it. The page gets the token from the boot JSON and sends the header on every non-GET.
- **Why.** Cookies are not port-isolated (measured: a second instance overwrote the first one's token); one path, one test matrix; the dependency form was already verified by the orchestrator.
- **Rejected.** Header-or-cookie (ORCH-D9 as written); cookie only; token in URL; a middleware as a second enforcement point.
- **Changes.** orchestrator: §6.1 Auth paragraph, §7 `test_api_security.py`, ORCH-D9, risk 10. engine: §4.9 comment. connectors: §6 router signature, CN-9 test. library: §13 first sentence. ui: §0 bullet, §13 request 9, sections.json `open_risks[2]`. diagram: key. WPs: **CN-9**, **L8**, **ORCH-1** (titles).
- **Diagram label.** write token: header only + Origin check

### S3-web-04 · The three payload additions, exact lists (task 4)
- **(a) `ChartChangeOut` — accept.** `seq, id ('chg-NNNN'), at, actor (chat_agent|user|system), decision (reuse|add|rearrange; bootstrap = add by system), status (applied|pending_approval|rejected|stale|failed), summary, reason, task_id ('req-<n>'), task_title, revision (int|null), added, moved, archived, reused (node ids)`. `chart_changes` gains `task_title` and `result_json`; `ChangeContext.request_title` = first assignment title, else the request cut to 60 characters; tasks get `change_id`; non-applied rows keep the plan and the UI draws no marks.
- **(b) `GraphView.nodes` order — accept, as depth-first pre-order:** chart children by `org_edges.position`, then the five function nodes (identity, adaptation, priority, coordination, audit), then steps by creation. The UI indexes before reading edges, so array order among siblings is what matters.
- **(c) Function-node meta — follows the final spec.** In `NodeDetail.node.meta`: `goal` (standing, FN-5), `task` (a STRING: the standing TASK line = J2's ROLE line, FN-4; the live task is `NodeDetail.task`), `context` (names of the ContextSlice = `reads`, static), `constraints` (the J2 'You may not' lines; new), `wait_on` (null|'you'|function key|builder id; from J2's map node), `hands_to` (identity [adaptation, priority, coordination, audit]; adaptation [priority, identity, audit, coordination]; priority [adaptation, identity, coordination]; coordination [priority, adaptation, identity, audit]; audit [identity]), `stats` ({calls, seconds, tokens_in, tokens_out, atoms_open, atoms_closed}; the chip counts). In `GraphView` and `graph.updated` a function node's meta is only `{stats, wait_on}`. **`last_seen` is rejected** (no such field in the spec; J2's map folds it into `detail`). The engine `node` event gains optional `wait_on` and `tokens`; the projector never writes goal/task/context from events.
- **Why.** The final spec changed three meanings (standing goal, standing task string, typed context slice); static strings on every graph node would cost about 125 KB per refetch (estimate).
- **Rejected.** A 'bootstrap' word; replaying ops at read time; static strings in the list view; library `Task`/`last_seen` as wire keys; hands_to copied from J2 ROUTES (audit would list adaptation, which code never uses, `j2.py:8969`).
- **Changes.** orchestrator §3.3 (ChartChangeOut, GraphView, GraphNodeOut, NodeDetail), §4.1 DDL, §5.2 T7/T8, §5.6 `node` row, §7 tests. engine §4.5 `node` row. library §8.1 (`FunctionNode.task` string, drop `last_seen`/`Task`), §8.2 HANDOFFS, §8.4 seed. ui §13 requests 1, 2, 3, 5, 7. WPs: **ORCH-1, ORCH-4, ORCH-5, ORCH-6, L6, E0, E3** (titles).
- **Diagram label.** wire: change lists · node order · fn meta

### S3-web-05 · The function drawer follows the final spec (UI side of task 4)
- **Decision.** Details tab order: head (persona, status, `node.detail`, usage, `meta.stats` counts), Goal, Task (+ 'Working for' from `NodeDetail.task`, wait_on), Context ('What this function is given'), Work atoms in **J2's atom-card labels** (Goal, Constraints, Context, How, Expected output, Verification, Result) with the status line OPEN/CLOSED/VERIFY FAILED/ABANDONED (the plugin word 'Limits' is not used), Constraints, Hands to. Department page adds 'Go to the <function> tab' (J2 `FN_TAB`) and J2's Summary/Conversations/Thinking. The **Identity chip opens the department's writable session**; the other four open their own read-only sessions (FN-7). `FnodeView.normalize` reads exactly the S3-web-04 keys.
- **Why / rejected.** The UI text predates the spec; plugin labels clash with J2's 'limits' (Priority's envelope). Rejected: plugin labels, a live Task object, opening the read-only Identity log, atom dots (dropped by the spec).
- **Changes.** ui §6.4, §6.5, §7, §10, sections.json `open_risks[4]`. WP: **UI-6** (title).
- **Diagram label.** drawer: spec labels · Identity = dept chat

### S3-web-06 · SSE (task 5)
- **Decision.** The 11 names and payloads already match. Added: `connector.health|switch|mode` (published by the connector router through the bus; UI TYPES = 14; Settings refetches `/api/health`). `server.hello`/`server.resync` carry no `id:`. `Last-Event-ID` above the head -> `resync {restart}`, older than the ring -> `resync {gap}`, else replay. Client rule: within one `connect()` handle the first hello is ignored, every later hello is handled as resync (covers auto-reconnect, manual re-create and id collisions across launches). Polling fallback every 2 s: graph, chart, chart changes, needs-you, departments, open sessions with `after=`, open node. The ping is an invisible comment, so no watchdog.
- **Why.** Names and payloads already match; what was open is the restart case (ids restart at 1 each launch), the connector events that the connector section publishes, and an incomplete polling list (the Home rail and the change log would freeze). Refetch-on-hello is a client rule and needs no protocol change.
- **Rejected.** Epoch in the id; persisted seq; a JS watchdog; WebSocket.
- **Changes.** orchestrator §6.3, §7 `test_events_sse.py`. connectors §6 Events. ui §7 SutraEvents, §9 row X4, §6.6 Settings, §10 `events.test.js`. diagram: 'live' arrow. WPs: **ORCH-2**, **UI-3**.
- **Diagram label.** SSE: refetch on reconnect · connector events

### S3-web-07 · J2's stdlib server and POST paths (task 6)
- **Decision.** Confirmed: `do_POST` compares `self.path` exactly (`j2_server.py:250-263`), `do_GET` parses the path. It only matters if the ported page (which adds `?dept=`) is served by a stdlib server; the app never does that (uvicorn + FastAPI + UI router), and J2's unported page has `dept` empty so the wrapper adds nothing. The vendored adapter routes POST by `urlparse(self.path).path`; a test pins it; J2 itself is untouched.
- **Why.** Two ways the stdlib server could meet the ported page (a developer starts it by hand; a legacy test points the ported page at it); one line removes the trap and J2's file stays untouched.
- **Rejected.** Patching J2's `j2_server.py`; serving the ported page from the stdlib adapter; stripping the query in the browser (breaks the FastAPI scope rule).
- **Changes.** engine §3.1, §9 `test_engine_views.py`, E2 title. ui R13, §4.2. WP: **E2**.
- **Diagram label.** J2 stdlib server: tests only

### S3-web-08 · Packaging (task 7)
- **Decision.** The nine globs in `pyproject.toml` are sufficient; **no glob is missing** (wheel experiment above). `engine/VENDORED.md` is intentionally not data. New `tests/test_packaging.py` (owner ORCH-8): `tomllib` + `glob(recursive=True)` fails on any unmatched non-Python file under `sutra_app/`, a must-have list, a slow wheel build, and a check that no module reads `docs/schemas` at runtime. The library's `docs/schemas/templates/` is generated documentation, the runtime copy is `engine/templates/**`.
- **Why.** UI request 6, ORCH risk 10 and UI R8 all ask for package-data; the chassis already has it, the only open question was a missing glob, and the experiment says none is missing. The test keeps it true as files are added.
- **Rejected.** A MANIFEST-only approach (sdist only); one glob per file; shipping `docs/schemas`.
- **Changes.** repo: new test, no pyproject change. orchestrator §8 ORCH-8, risk 10. ui request 6, R8, `open_risks[10]`. library §9.2. WP: **ORCH-8** (owns + acceptance).
- **Diagram label.** wheel carries every data file (tested)

### S3-web-09 · CSP and fonts (task 7)
- **Decision.** **Change** scripts, **accept** styles: `script-src 'self' 'sha256-…'` for each attribute-less inline script (computed by `inline_script_hashes(html)` from the final HTML, cached per page file), `style-src 'self' 'unsafe-inline'` (43 inline `style=` attributes), rest as ui 4.1. **Fonts: accept not vendored** (no grounded source; stacks fall back; owner-supplied files would go to `ui/static/fonts/` with `@font-face` in `sutra-shell.css`, no code change).
- **Why.** Model text is untrusted and the app can run model CLIs; the hash policy was measured to work and costs about 20 lines.
- **Rejected.** `'unsafe-inline'` for scripts; nonces; splitting the J2 script; fetching fonts from outside the grounded set.
- **Changes.** ui §4.1 (headers paragraph, code block), §10 `test_serve.py`, R5/R10/R12, `open_risks[7]`. diagram key. WP: **UI-1** (title).
- **Diagram label.** CSP: script hashes · no CDN · no fonts

### S3-web-10 · What the J2 UI has that the 12 edits miss (task 8)
- **Decision.** Nothing in the 12 edits breaks (anchors re-verified). Four things are left out and added: (1) the **`?tab=` deep-link race** (J2 calls `showTab` at parse time, before the E12 scripts; fix `SutraCtx.currentTab` + `dept_ext.js init()`); (2) **E13**, the wording edit the final spec demands (FN-28): `ranked` -> `priced`, `no ranking records` -> `no pricing records` (2), `No ranking records in this run` -> `No pricing records in this run`, `Funded, in the order it ranked them` -> `Funded, in registration order; Coordination sets the run order`; parity goldens get the same pairs; (3) `sandbox` attribute on both preview iframes (E2); (4) **archived department**: J2's fetches ignore non-2xx, so `dept_ext.js` hides the composers (`body.archived`) and the server refuses writes with 403. Deep links to Workflows/Artifacts, sky backgrounds, the edge router, pins with Reset layout and the parallel runner live inside the copied script or the engine gate and are untouched; the seven `localStorage` keys are enumerated (only `j2pos` is per run, E10 scopes it).
- **Why.** Found by reading the J2 page and the final spec against the port plan: (1) is a real load-order race, (2) is a requirement of the approved spec that the byte-parity rule would otherwise reject, (3) and (4) follow from decisions 12 and 14.
- **Rejected.** Hand-editing the copied page outside `port_j2_ui.py`; keeping J2's 'ranked' wording (it contradicts owner rule 4, 'Priority prices, never orders'); re-dispatching `sutra:tab` from a timer; relying on an error banner for the archived page (J2's code never reads the status).
- **Changes.** ui §5 (E2, E6, new E13), §6.7, §7, §10, R3. engine §7.2 archived rule. WPs: **UI-2, UI-3, UI-8**.
- **Diagram label.** ?tab= deep link mounts new views

### S3-web-11 · Drag-to-pin in the new views; `?embed=1` (task 8)
- **Decision.** Pins stay in J2's own Map views (J2 code; E10). **Out of v1 for the new graph and org chart views** (deterministic layout recomputed on every update, read-only chart, no spring engine, not in the owner's seven steps); later key `sutra:pins:<graph|chart>:<dept|all>`. **`?embed=1` out of v1**: not a J2 parameter (J2 reads run, view, tab, mapview), hand-over is a link (owner step 7), an embedded page would double the 700 ms poll and SSE; `frame-ancestors 'self'` keeps the door open.
- **Why.** Fewest moving parts and no change to J2 behaviour; the UI section had put both out of scope (section 1, R12) without a decision record.
- **Rejected.** Pins in the new views in v1; a force or spring layout for them; `?embed=1` now; an iframe of the Simple view inside Home (UI-D6 already rejected it).
- **Changes.** ui §1 out-of-scope list, R12, `open_risks[11]`, §3.2 storage note. diagram note.
- **Diagram label.** no drag-to-pin / ?embed in new views (v1)

### S3-web-12 · Where the J2 routes live (found by comparing routes; closes ORCH E-1 and ENG-D4)
- **Decision.** Root paths with `?dept=` only; the `/d/{dept}/` prefix mount, the `X-Sutra-Dept` header and any cookie are deleted. Missing dept 400 `dept_required`, unknown 404 `not_found`, archived department: reads 200, writes 403 `read_only` (orchestrator envelope).
- **Why.** The wrapper plus one `runQ` edit already give `?dept=`; a prefix needs 43 URL edits; one mount halves the engine's test matrix; ORCH-D7 already says `?dept=`.
- **Rejected.** A path prefix `/d/{dept}/api/...` (43 URL edits or a `<base href>`); both mounts (double tests, two URL spaces); an `X-Sutra-Dept` header or a cookie (shared across tabs; the UI never sends them).
- **Changes.** engine §1 ENG-06, §4.9, §6 F1/F2/F3/F9, §7.1 heading, §7.2, §9, §10 E4, ENG-D4, §12 risk row, sections.json. orchestrator §1.3 E-1, §5.6, §6.2. WP: **E4**.
- **Diagram label.** J2 routes at root · department in ?dept=

### S3-web-13 · Wire words the UI adopts (found by comparing payloads)
- **Decision.** (a) ids are LIB/ORCH ids (`root`, `web`, `web.identity`, `s-…`, `cs_org`, …; function-node id keeps the dot because it is a URL segment, not the spec's slash); `/d/{dept}/` is validated with the generic URL-id rule then `Services.department`; the strict department rule stays in the orchestrator (U-1 closed). (b) node status = J2 map words + `archived`; the UI's old words are deleted. (c) edge kinds `contains/has_function/has_step` (tree) and `handoff/depends_on/speaks_to/step` (cross links); loops only for same-kind twins; a step relation is stored once as `depends_on` (the engine's `handoff[]` is its inverse and is not stored). (d) atom lifecycle field is `state`. (e) chat POST: 503 before storing on `cs_org` only; department/division/J2 `say` never 503. (f) bootstrap row is actor `system`.
- **Why.** orchestrator 1.3 (U-1) and library 18.2 already chose the ids and status words and ui.md 0 says 'the UI conforms'; the UI examples were written against an earlier orchestrator draft. The false-loop problem is real because the engine publishes both directions of each dependency. The UI's X1 assumed 202 always, but orchestrator T0 answers 503 before storing, and J2's page ignores non-2xx answers of `/api/say`.
- **Rejected.** Server-side `n:`/`f:`/`s:` prefixes; translating at the API edge; keeping two status vocabularies; storing both `handoff` and `depends_on` for one relation; a slash in function-node ids; a 503 on department posts.
- **Changes.** ui §0, §4.1/4.2 id rule, §6.1, §8 examples, §9 X1, §10/UI-0. orchestrator §1.3 U-1, §6.2 POST row, §5.6 `step` row, §3.3 AtomOut. engine §7.1 row 26. WPs: **UI-0, UI-4**.
- **Diagram label.** wire words: J2 map statuses, LIB ids

### S3-web-14 · Generated content is sandboxed (found while checking the token)
- **Decision.** Every engine `text/html` response carries `Content-Security-Policy: sandbox allow-scripts allow-forms allow-popups; frame-ancestors 'self'`; every engine response `nosniff` and `no-referrer` (once, in `api/reply.py`); the two preview iframes also get `sandbox` in markup; `create_app` turns off `/docs` and `/redoc` (CDN, offline). Accepted cost: generated sites that use storage, cookies or the app's API fail inside the preview.
- **Why.** The boot block makes the token readable by any same-origin script; measured: an unsandboxed framed page read it, a sandboxed one could not. ui R10 left the headers to 'the server section' and none defined them.
- **Rejected.** A second port or origin for generated content; `allow-same-origin` (defeats the sandbox); an iframe attribute alone (a new-tab open would be unprotected); stripping scripts from generated sites.
- **Changes.** engine §7.2 headers paragraph, new `tests/engine/test_engine_api_headers.py`, E4. ui E2, R10. orchestrator §6.4. diagram: 'department views' arrow. WP: **E4** (owns + acceptance).
- **Diagram label.** generated sites sandboxed

### S3-web-15 · Error envelope, library route names, J2 path list (found while comparing routes)
- **Decision.** (1) New routes (orchestrator, library, connectors) use `{error:{code,message,details}}`; the connectors' flat shape moves `kind` into `details`; the J2-compatible engine routes keep J2's bodies. (2) The library router moves to `/api/schemas`, `/api/schemas/{family}/{version}`, `POST /api/schemas/validate` (`/api/library` means J2's template library). (3) `J2_PATHS` matches whole pathnames exactly (23 paths) except the prefixes `/api/library/`, `/site/`, `/file/`, `/shot/`, so `/api/runs/{run_id}` never gets `dept`.
- **Why.** The UI's `ApiError` reads one envelope; a prefix match on `/api/runs` would add `dept` to `/api/runs/{run_id}`; `/api/library/schemas` would be handled as J2's template library. All three are cheap now and expensive once code exists.
- **Rejected.** One envelope for the J2 routes too (breaks the unchanged J2 page); keeping `/api/library/schemas`; prefix matching for every J2 path.
- **Changes.** connectors §6 Errors; library §13; ui §4.2/§7/§10 `ctx.test.js`; orchestrator §6.1. WPs: **L8, CN-9, UI-3**.
- **Diagram label.** errors: {error:{code,message,details}}

---

## Unresolved (with the fallback in force)

| Topic | Why not settled | Fallback |
|---|---|---|
| Who speaks to the owner: spec FN-8 ('the Chat agent never writes to you') against ORCH-D1 (org chat voice 'Sutra') | chat-agent design, not web layer; a recorded default in the spec | ORCH-D1 stays; the UI labels whatever `who` arrives |
| Division chats: ORCH-D1 filtered-view session per division against spec FN-6 / risk 13 ('a division adds no session') | orchestrator data model | UI opens `node.chat_session_id`, works either way |
| Source of `departments.goal` (was fed from the node event's step label) | no event carries the charter | stays empty in v1; fill from `goal.json` at `run.ended`; test forbids a step label there |
| Library `FunctionNode` shape against the final spec | function-node batch may differ | wire keys built from `FunctionSpecs`, `HANDOFFS`, atoms table, so they do not depend on it |
| Hash CSP, sandbox and `EventSource` reconnect measured in Chrome 156 only | no other browser here | `csp_header()` is one function; hello-triggered refetch and the 2 s poll cover reconnect |
| Wheel check on a machine without uv or cached setuptools | verified offline here only | the glob case always runs; the wheel case is slow-marked and skips with a reason |
