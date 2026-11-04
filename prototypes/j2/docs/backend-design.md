# Backend builder: design (Phase 0, nothing built yet)

Branch `backend-builder` (from `template-library-fixes`). Flag `J2_BACKEND=1`. With the flag unset nothing below
runs: no new LLD section, no backend workflow, no new check, no new file in the run, no new prompt text.

This document was written from the code as it is on 4 Nov 2026 (`j2.py`, `j2_artifact_models.py`, `j2_rules.py`,
`j2_template_lib.py`, `j2_check.py`, `j2_server.py`, `j2_ui.html`, `j2_flow_test.py`, the generic templates, the
conditions files) and from two recorded runs (`runs/j2-20261103-162711`, `runs/j2-20261103-184249`). Every
statement about the current flow names the function it comes from. Estimates are marked as estimates.

## How the website output works today (what the design builds on)

1. **Stages.** `_plan_stages` reads the brief: documents named in it become stages (`prd`, `hld`, `lld`), then
   `website` when the brief names a site. `_begin_stage` starts each one; the LLD's `agent_output` (`parse_lld`)
   becomes `self.blueprint` for the website stage. A send deed (`_deed_stage`) is the one stage with no agents:
   code registers one workflow, one atom, one check.
2. **Documents.** `OUTPUTS[kind]["sections"]` lists a document's sections; Adaptation plans one workflow per
   section (`LLD_PLAN`), the builder writes it. With `J2_ARTIFACT_SCHEMA=1` the builder answers with data
   (`reply_schema` of the section's Pydantic model in `j2_artifact_models.SECTION_MODELS`), code validates it
   (`_read_artifact`), runs the section's rules (`j2_rules.RULES`, `_artifact_receipts`: receipts
   `artifact-schema`, `artifact-rules`, `artifact-render`) and renders the markdown (`render_section`). The
   markdown is what `parse_lld` and the L-conditions (`conditions/lld.json`, `lld_condition`) read.
3. **Template library.** With `J2_TEMPLATE_LIBRARY=1` (implies the schema flag) `_route_template` builds a need
   (`_template_need`: the done-when items the workflow covers, the charter facts behind them, and for a page
   section the LLD slice's selectors and field names as extra enum fields), `j2_template_lib.route` picks reuse /
   extend / create / generic (rules a to e), `save_into_run` copies the template's four files under
   `runs/<id>/templates/`, and the builder's `--json-schema` carries the template's `schema.json`
   (`_with_section`). Every receipt of that workflow carries `template_route` and `template_version`.
4. **Page builders.** `_turn_workflow_agent`: each website workflow owns one section of `site/index.html`
   (`assemble`); the builder sees its LLD slice (`_page_context`: "YOUR SPEC"), the style guide, and the HLD
   summary. Code runs the atom's checks (`run_check`: `file-exists`, `grep-count`, `element-count`,
   `named-test`, `facts-present`, `tap-targets`, `lld-slice`, `behavior-steps`) up to `MAX_CHECK_ATTEMPTS` (3)
   times; a failed check goes back to the builder with its evidence. `site/vN.html` is kept per build.
5. **Audit.** `_audit_site`: `j2_check.check` renders the page in headless Chrome at 360 and 1280 px, fills and
   submits each form with navigation blocked, measures design; `_conditions` checks N1 to N8
   (`conditions/website.json`), where N7 wants every form to have an `action` or a `mailto:`.
6. **Records.** `calls.jsonl` (tokens, seconds, model per call), `template_calls.jsonl`, `receipts.jsonl`,
   `templates.json`, `summary.json` (`_write_summary`), `artifacts.json` (`artifacts/types.json`),
   `report.md`. The UI reads them through `j2_server.py` (`/api/state`, `/api/docs`, `/api/run-templates`,
   `/api/library/...`, `/api/artifacts/tree`, `/api/code`).
7. **Tests.** `j2_flow_test.py` is one file of plain functions called from `__main__`; `--fast` stubs the
   browser, `--fast --browser` drives Chrome. `run_checks.sh` runs both in mirrored copies.

---

## A. Backend

### 1. Stack

**One file, `server.py`, standard library only** (`http.server`, `socketserver`, `sqlite3`, `json`,
`urllib.parse`, `argparse`, `os`, `sys`, `datetime`). It serves `index.html` from its own folder at `/`, the JSON
API under `/api/`, and keeps one SQLite file.

Where things live in the run:

| file | written by | what |
|---|---|---|
| `runs/<id>/site/server.py` | the backend builder (an AI call), through code | the server |
| `runs/<id>/site/index.html` | the page builders, as today | the page the server serves |
| `runs/<id>/site/bookings.sqlite` | `server.py` at first start | the data, when a person runs it |
| `runs/<id>/backend/check-<attempt>.sqlite` | `server.py`, started by the checks | the checks' own data, never mixed with the person's |
| `runs/<id>/backend/start-<attempt>.log` | code | the server's stdout and stderr during the checks |
| `runs/<id>/backend.json` | code | the backend record: endpoints, tables, template, check results, how to run it |

`server.py` takes `--port` (required, no default, so two runs never collide) and `--db` (default
`bookings.sqlite` beside the script). It binds `127.0.0.1` only. Everything the user types is the one line
`python runs/<id>/site/server.py --port 8790`.

**Reasons to choose otherwise, and why not:** Flask or FastAPI would make the generated code shorter, but the run
folder would then need a virtualenv and a pinned install, the safety scan would have to trust a third-party
import tree, and "the code proves the backend runs" would depend on the machine's packages. `http.server` is
single-threaded by default; `ThreadingHTTPServer` is in the standard library since 3.7 and costs one word. SQLite
through `sqlite3` is also standard library, file-based, and the check can read the file directly. No reason to
choose otherwise for a booking list.

### 2. The two new LLD sections

With `J2_BACKEND=1`, `OUTPUTS["lld"]["sections"]` becomes the five of today plus **"API endpoints"** and **"Data
model"**, in that order, after "Form fields" and before "File structure" (the file structure then names
`server.py`). `LLD_SECTIONS`, `LLD_PLAN`, `OUTPUTS["lld"]["mock_atom"]`, `artifacts/types.json`'s `lld.workflow.
sections` and `conditions/lld.json` L1 ("All five sections") are built or read at import time today; they become
functions of the flag (`lld_sections()`), read at each reset like `load_rates` already is. L1's text becomes
"All sections are present" with the count from the list.

**Id prefixes.** The request says endpoints are "E1..". `E` is already the prefix of Interactive elements
(`Element.id`, `LLD_RUBRIC` D-2, `lld-ids-unique` which requires every id of sections, elements and fields to be
unique in one document). So the design uses **`A1, A2, ...` for API endpoints and `T1, T2, ...` for tables**.
If you want `E` for endpoints anyway, the elements would have to be renamed, which changes every LLD prompt and
parser; say so and I will list that cost.

**Pydantic models** (`j2_artifact_models.py`, same style as `Element` and `FormField`; every constraint stays a rule):

```python
class EndpointField(Artifact):
    name: str            # "name", "email", "class", "preferred_date"
    type: str            # "string" | "integer" | "boolean" | "date" | "email"
    required: bool
    from_field: str = "" # the LLD form field id this request field carries, e.g. "F3"; "" for a response field

class EndpointError(Artifact):
    status: int          # 400, 404, 405
    when: str            # "a required field is missing"

class Endpoint(Artifact):
    id: str                                  # A1, A2, ... in order
    method: Literal["GET", "POST", "PUT", "DELETE"]
    path: str                                # "/api/bookings"
    purpose: str
    called_by: List[str] = []                # LLD element or form selectors that call it: ["#booking"]
    request_fields: List[EndpointField] = []
    response_fields: List[EndpointField] = []
    errors: List[EndpointError] = []
    example_request: str = ""                # one JSON object as text, from the charter's facts only
    expected_status: int                     # 201 for the example, 200 for a list
    expected_fields: List[str] = []          # response field names the example reply must carry

class Column(Artifact):
    name: str
    type: Literal["INTEGER", "TEXT", "REAL", "BLOB"]
    nullable: bool = False
    primary_key: bool = False
    maps_to: str = ""                        # the endpoint request field it stores, e.g. "A1.email"

class Table(Artifact):
    id: str                                  # T1, T2, ... in order
    name: str                                # "bookings"
    columns: List[Column]

class LLDEndpoints(Artifact):   TEMPLATE "LLD/1", SECTION "API endpoints";  endpoints: List[Endpoint]; assumptions
class LLDDataModel(Artifact):   TEMPLATE "LLD/1", SECTION "Data model";     tables: List[Table]; assumptions
```

`LLD` (the whole-document model) gains `endpoints` and `tables`; `OPTIONAL_FIELDS` gains `called_by`,
`request_fields`, `response_fields`, `errors`, `example_request`, `expected_fields`, `maps_to`, `from_field`,
`nullable`, `primary_key`. `render_section` renders the two sections as lines the readers can parse:

```
- **A1** POST `/api/bookings`: create a booking. Called by `#booking`. Request: name (string, required, F1), ...
  Response: id (integer), ... Errors: 400 when a required field is missing. Example: {"name": "..."} -> 201 with id, name
- **T1** `bookings`: id INTEGER primary key, name TEXT, email TEXT, class TEXT, preferred_date TEXT, created_at TEXT
```

`parse_lld` gains `endpoints` and `tables` (None-safe like the others), so `doc_agent_output("lld")`, the chain,
`self.blueprint` and `lld_slice` carry them. `lld_slice` adds to a page workflow's slice the endpoints whose
`called_by` names one of its sections' selectors or forms.

**Rules** (`j2_rules.RULES`, data only; every one is a rule type that exists today except the two marked new):

| section | rule | from |
|---|---|---|
| API endpoints | `ids_sequential` path `endpoints` prefix `A` | L2 |
| | `enum` path `endpoints[].method` values GET, POST, PUT, DELETE | L7 (new condition, below) |
| | `prefix` (new rule type, 8 lines: every value at the path starts with the prefix) path `endpoints[].path` prefix `/api/` | L7 |
| | `not_empty` paths `endpoints[].purpose`, `endpoints[].example_request`, `endpoints[].expected_status` | L7 |
| | `ref_exists` path `endpoints[].request_fields[].from_field` target `this.form_fields[].id`, `fail_text` "{id} carries {bad}, which is not a form field of this document" | L7 |
| | `covers_all` (new rule type, ~15 lines: every id in the target list appears at least once at the path) path `endpoints[].request_fields[].from_field` target `this.form_fields[].id`, name "every form field maps to a request field" | L7 |
| | `ref_exists` path `endpoints[].called_by` target `this.elements[].selector` + `this.form_fields[].form` (ref_exists takes one target today; it gets a list of targets, 3 lines) | L7 |
| Data model | `ids_sequential` path `tables` prefix `T` | L2 |
| | `not_empty` paths `tables[].name`, `tables[].columns[].name` | L8 |
| | `enum` path `tables[].columns[].type` values INTEGER, TEXT, REAL, BLOB | L8 |
| | `ref_exists` path `tables[].columns[].maps_to` target `this.endpoints[].request_fields[].qualified` (code adds `qualified` = "A1.email" when it records the section, so the path resolves) | L8 |

"Every endpoint the page calls exists" is checked where the page exists, not in the LLD: it is the `backend-endpoint`
check's companion `page-calls-known-endpoints` (section 4), which reads the built page's `fetch("/api/...")` and
`action="/api/..."` targets and requires each to be an LLD endpoint path.

Two new LLD conditions in `conditions/lld.json`, only present when the flag is on (`load_conditions` filters by a
`flag` key): **L7** "Every API endpoint has a method, an /api/ path, an example request and an expected status, and
every form field maps to a request field" (check `lld-endpoints`, code in `lld_condition`), **L8** "Every table has
columns with types" (check `lld-tables`). `LLD_RUBRIC` is unchanged (Audit's judgement; the new items are code
checks).

**Prompts.** No change to `LLD_BUILDER` or any `agents/*.md`. `J2_BACKEND=1` sets `J2_ARTIFACT_SCHEMA=1` (as the
library flag does today, `artifact_schema_on`), so the two sections are always written as data: the builder gets
the section's schema and `_artifact_task`'s existing sentence ("Send the data for API endpoints only, in the
fields of the schema"), and code renders the markdown. The plain-markdown path for these two sections does not
exist, and the design does not add line grammar to the prompt for it.

### 3. The backend builder

**Which workflow.** A code-registered workflow, like `_deed_stage` registers a send: after the last website
workflow of the stage is done and before Audit, `_backend_stage` registers `W-n Backend` with one atom
(`how.kind "AI"`, `how.agent "W-n Builder"`), `outputs ["site/server.py"]`, `section None`, `lld_sections` = the
ids of every LLD endpoint and table (so `_lld_gaps` stays satisfied and the Map shows what it implements). It is
priced from the rate card key `backend` (proposed 15, the same as `form`; `rates.json` sits in `agents/j2/`, so
that one-line addition waits for your OK; until then the code default is 15 and the receipt says so). Adaptation
does not plan it and Priority does not price it, exactly as a send deed; the stage gate (`_stage_cost`) counts it
when the flag is on. If the credits left cannot cover it the usual decision question is asked (`_stage_gate`),
with "the backend" as the item.

Why code-registered and not planned: Adaptation's planning prompt is in `agents/j2/adaptation.md`, which stays as
it is; a planned backend workflow would need new words there ("plan a backend workflow with these checks").

**Its turn** is `_run_backend(w)`, a sibling of `_run_artifact` (which already writes one file from a builder's
reply): up to `MAX_CHECK_ATTEMPTS` attempts, one AI call each, every attempt runs all five checks of section 4,
a failed check goes back as "ATTEMPT n OF 3. THESE CHECKS FAILED ON YOUR LAST ATTEMPT: ..." with the exact
evidence, then the normal hand-off to Coordination, or to Adaptation with the receipts after the last failed
attempt (`atom_failed`, as today).

**Reply schema** (`J2_ARTIFACT_SCHEMA=1`, so `--json-schema`): `reply_schema(BackendServer, {})` where

```python
class BackendServer(Artifact):
    TEMPLATE "Backend/1", SECTION "server.py"
    code: str                    # the whole server.py
    port_arg: str = "--port"     # the flag that sets the port
    db_arg: str = "--db"         # the flag that sets the SQLite path
    endpoints_implemented: List[str]   # LLD endpoint ids, e.g. ["A1", "A2"]
    tables_created: List[str]          # LLD table ids
    notes: str = ""
```

Rules (`("backend", "server.py")`): `not_empty code`; `ref_exists endpoints_implemented -> lld.endpoints[].id`
with `required_target`; `covers_all` the other way (every LLD endpoint id is implemented); the same two for
tables. The Python file is one JSON string field; `_run_artifact`'s `<<<FILE` markers are the fallback when the
schema flag is off, but with `J2_BACKEND=1` the schema flag is on, so the string field is the path. A 150-line
server is about 6 KB, well inside `max_tokens=16000`.

**Prompt.** `system_prompt(fn, reply_format, builder=...)` already takes the builder file name, so the backend
builder uses **a new file `agents/j2/backend.md`** (no existing file changes). Proposed full text, to be written
only after your OK:

```markdown
<!-- PLACEHOLDER: written for this prototype, not an official J2 file. -->
# Backend agent (one per registered backend workflow, e.g. "W-9 Builder")

## What you do
- You exist for one registered workflow: the backend of the site. You write one file, server.py, and
  nothing else. Code saves it, starts it and runs the checks; you never run anything.
- Standard library only: http.server, socketserver, sqlite3, json, urllib.parse, argparse, os, sys,
  datetime. No other import. No subprocess, os.system, eval, exec, sockets, urllib.request or
  http.client. Write no file except the SQLite database at the --db path.
- The server takes --port (required) and --db (default: bookings.sqlite beside the script). It binds
  127.0.0.1 only. GET / serves index.html from the script's own folder; every other path is the API.
- Implement exactly the LLD's API endpoints: method, path, request fields, response fields, error cases
  and statuses as written. Reply JSON with Content-Type application/json. A missing required field is
  the error the LLD names (400 unless it says otherwise). Unknown paths are 404, wrong methods 405.
- Create the LLD's tables at start if they don't exist (CREATE TABLE IF NOT EXISTS). Store what the
  request fields carry, nothing else. Use parameters in every SQL statement, never string formatting.
- Use only facts from the charter and the LLD: no invented classes, prices, addresses or names.
- If a check fails, code tells you the exact error and you retry, within your envelope. Then report to
  @Coordination what you changed; code runs the checks, so don't claim they pass.
```

**The page's form: mailto to fetch().** Three things, all behind the flag, none in `agents/*.md`:

- The form's section builder sees the endpoints its form calls in its LLD slice ("YOUR SPEC" now carries
  `endpoints: [{"id": "A1", "method": "POST", "path": "/api/bookings", "request_fields": [...]}]`), and a
  code-built sentence after it: "BACKEND: the form posts to the API. Give the form `action="/api/bookings"
  method="post"` and on submit prevent the default, send the fields as JSON with fetch() to that path, then show
  the reply's confirmation (or its error) in an element inside your section; no mailto."
- N7 (`_forms_have_destination`) already accepts `action="/api/bookings"`: it only rejects empty, `#` and
  `javascript:` actions. The mailto destination from the brief ("sends the booking to
  bookings@stillpoint.example") is shown as text on the page in the test brief (section 10 rewrites that line),
  not used as the form's action.
- `j2_check`'s form test (fills sample values, `requestSubmit`, blocks navigation) still passes: the submit event
  fires, the fetch fails quietly under `file://` and its rejection is caught by the page's handler (the builder is
  told to catch it). N2 "no JS errors" is unaffected because a caught fetch rejection is not an error event.

With `J2_BACKEND` unset: no endpoints in the slice, no BACKEND sentence, the form keeps mailto, as today.

### 4. The checks (code only, each a receipt)

All five are `run_check` types (`backend-compile`, `backend-safety`, `backend-start`, `backend-endpoint`,
`backend-e2e`), listed in the backend atom's `verification` by code, run by `_run_checks` so every result is a
receipt line (`_receipt`: atom, check, type, target, expect, actual, pass, evidence, attempt, by code) and the
atom's status follows the existing rule (failed / could not run / passed). They live in a new module
`j2_backend.py` (`~250 lines`), called from `run_check` the way `j2_send.check` is.

| check | what it does | passes when | fails with |
|---|---|---|---|
| `backend-compile` | `py_compile.compile(path, doraise=True)` in a subprocess with `python -I` | no exception | `SyntaxError: <file>:<line>: <msg>` verbatim |
| `backend-safety` | `ast.parse` then one walk: imports, attribute calls, names, string literals | nothing on the block list, every import in the allowlist | one line per hit: `line 42: import subprocess is not allowed`; `line 88: open(..., "w") writes a file; only the sqlite database may be written` |
| `backend-start` | `subprocess.Popen([sys.executable, "-I", "server.py", "--port", P, "--db", "backend/check-<n>.sqlite"], cwd=run folder, env={"PATH": minimal, "PYTHONIOENCODING": "utf-8", "LANG": "C.UTF-8"}, stdout+stderr to `backend/start-<n>.log`, new process group)`; P from `socket.bind(("127.0.0.1", 0))` and released; polls `GET /` for up to 10 s | HTTP 200 on `/` with `index.html`'s bytes, process alive | `the server did not answer on 127.0.0.1:P within 10 s; last lines of its log: ...` or `exited with code N before answering` |
| `backend-endpoint` (one per LLD endpoint, target `A1`) | sends `example_request` with `method` to `path` with `urllib.request` (code's own, not the server's) with a 5 s timeout | status == `expected_status` and every `expected_fields` name is a key of the JSON reply (for a list reply, of its first item) | `A1 POST /api/bookings: expected 201, got 500; body: ...` or `reply lacks fields: id` |
| `page-calls-known-endpoints` (one, target `index.html`) | reads `action="/api/..."` and `fetch("/api/...")` targets in the built page | every one is an LLD endpoint path with the matching method | `the page calls /api/book, which no LLD endpoint has` |
| `backend-e2e` (browser; `--fast` = could not run, never a failure) | a code-owned helper `http.server` on a second free port serves `wrap.html` and `site.html` from a temp folder and proxies `/api/*` to the backend with `urllib.request`, so the behaviour wrapper (`j2_check.behavior`, given a base URL instead of `file://`) is same-origin with the page; the steps are built from the LLD: `set <form> input[name=F.name] <value>` for each form field (values from the charter facts: the first class name, the brief's fake email; a date field gets today), `click <form> [type=submit]`, `wait 800`, `expect-visible <the confirmation element>`; then code `GET`s the list endpoint through the proxy and looks for the values it typed | the steps pass and the list reply holds one row whose fields equal the typed values | the step that failed with `judge_steps`'s own evidence, or `GET /api/bookings returned 2 rows, none with email test@stillpoint.example` |

Block list for `backend-safety`: imports outside `{http, http.server, socketserver, sqlite3, json, urllib.parse,
argparse, os, os.path, sys, datetime, time, re, html, pathlib, logging, typing, functools, collections, uuid,
threading}`; the names `subprocess`, `socket` (as a module), `urllib.request`, `http.client`, `ctypes`, `importlib`,
`shutil`, `eval`, `exec`, `compile`, `__import__`; the attributes `os.system`, `os.popen`, `os.exec*`, `os.spawn*`,
`os.remove`, `os.unlink`, `os.rename`, `os.rmdir`, `shutil.*`; `open()` with a mode containing `w`, `a`, `x` or `+`
(the server has no reason to write a file; the database goes through `sqlite3.connect`); `sqlite3.connect` with a
literal path that is absolute or contains `..`. Runtime companion in `backend-start`: a listing of the run folder
before and after the checks; any new file other than `backend/check-<n>.sqlite` (and its `-journal`/`-wal`) fails
`backend-start` with the file's name. `python -I` keeps the script folder off `sys.path` and ignores `PYTHON*`
variables, so a planted module beside `server.py` is not imported and no secret from the environment reaches the
process (the env is built from scratch, never copied from `os.environ`, so `.env` values never pass).

After the checks: `terminate()` the process group, `kill()` after 3 s, as `run_chrome` does. The checks never run
two servers at once: `backend-start` keeps the process for `backend-endpoint` and `backend-e2e`, then stops it;
the receipts record the port, the pid, the log path and the seconds.

Retry wiring: `_run_backend`'s loop is `_run_artifact`'s loop; the evidence block it sends back is the same
`- <check> (<type> <target>, expect <expect>): <evidence>` lines. The early-stop rule of the page builders ("the
same check failed with the same evidence twice") applies.

---

## B. Template library for the backend

### 5. Generic templates

`j2_template_lib.ARTIFACTS` gains `"backend"`; `SECTION_MODELS` gains `"backend": {"server.py": BackendServer}` and
the two LLD entries. `python3 j2_template_lib.py` then regenerates `templates/lld/generic.json` (now seven
entries) and writes `templates/backend/generic.json` (one entry, "Backend/1 · server.py"). `generic_drift`
keeps the files honest, as today. With the flag unset the two extra LLD models are not in `SECTION_MODELS`, so
`generic.json` for the LLD must still match: the file is generated with the flag on, and `generic_drift` and
`generic()` read the flag-off list filtered from it (the test in section 8 checks both states).

Routing is unchanged: `_route_template(w, "lld", "API endpoints")`, `(w, "lld", "Data model")` and
`(w, "backend", "server.py")` go through `route` with the same need (`_template_need`): the workflow's done-when
items, the charter facts behind them, and for the backend the LLD's endpoint paths and table names as extra enum
fields (`endpoints_implemented` enum = the A ids, `tables_created` enum = the T ids), the way page sections get
`elements` and `form_fields` today. `fact_fields` adds `("lld", "API endpoints")` and `("backend", "server.py")`
to `FACT_FIELD_SECTIONS` so a fact like "the fields name, email, class and preferred date" becomes a field list
the generator can turn into enums. `save_into_run` copies each chosen version under
`runs/<id>/templates/lld/api-endpoints/...`, `.../lld/data-model/...`, `.../backend/server-py/...`, by the same
code path (`run_tpl_rel` is section-slug based already).

### 6. What a specialised backend template adds

For Still Point Yoga the generator would be expected to write (from the need's facts only; the mock generator
`specialise` does exactly this):

- LLD "API endpoints": `endpoints[].path` enum `["/api/bookings"]`, `request_fields[].name` enum
  `["name", "email", "class", "preferred_date"]`, `facts_used` enum = the charter facts; one own rule
  `enum request_fields[].name` from "facts".
- LLD "Data model": `tables[].name` enum `["bookings"]`, `columns[].name` enum = the request fields plus `id`,
  `created_at`; the `class` column's description names the five classes.
- Backend "server.py": `endpoints_implemented` enum `["A1", "A2"]`, `tables_created` enum `["T1"]`, and the
  descriptions in the studio's words ("the bookings of Still Point Yoga: name, email, class, preferred date").

It inherits every generic rule (`keeps_problems` refuses a specialised template that drops a required generic
field or a generic rule), so ids in order, `/api/` prefix, method enum, the form-field mapping, and the
endpoint/table references stay enforced; it adds only enum narrowings and `facts_used`. A Thread & Loom backend
(orders, not bookings) shares no fact with it, so coverage is 0 and the router creates its own; the only
sharing is the generic layer.

### 7. Recording the template in the checks

Every backend receipt already gets `template_route` and `template_version` through `_receipt(..., **extra)`
(`_artifact_receipts` passes them for the three artifact layers; `_run_checks` is given the same `extra` for the
five backend checks, so every line of `receipts.jsonl` for the backend atom carries
`{"template_route": {"template", "version", "kind", "action"}, "template_version": N}`). `backend.json` repeats
them once at the top with the sha of the `schema.json` actually sent (`art_schema.library.sent_section_sha`, as
`calls.jsonl` records it today). The Library tab's decision rows (`/api/run-templates`) therefore show the backend
workflow like any other, and the receipt list on the atom card names the template.

---

## C. Test plan (written now, run after "go")

### 8. Mock tests (no AI, `j2_flow_test.py`, `--fast`)

| test | what it asserts |
|---|---|
| `backend_off` | with the flag unset, a `lib_run(YOGA_BRIEF)` writes no `backend/`, `backend.json` or `server.py`, the LLD has five sections, no receipt has a `backend-*` type, `templates/backend` does not exist, and `plain_unchanged` (prompt for prompt against the checkpoint) still passes |
| `backend_compile_check` | a good `server.py` (a fixture written by the test from the mock reply) passes; `def x(:` fails with the `SyntaxError` line in the evidence |
| `backend_safety_check` | the good file passes; one case each: `import subprocess`, `os.system("ls")`, `eval(x)`, `import socket`, `urllib.request.urlopen`, `open("x", "w")`, `sqlite3.connect("/tmp/x.db")`, `import requests`; each fails naming its line and the reason; a file that writes `../x.txt` at start fails `backend-start` with the file name |
| `backend_start_check` | the good file answers `GET /` with `index.html`; a file that exits at once fails with its exit code and log tail; a file that binds `0.0.0.0` fails ("must bind 127.0.0.1"); a file that sleeps 20 s fails with the timeout; the process is gone after the check (no pid left) |
| `backend_endpoint_check` | against the good file: `A1 POST` 201 with `id`, `A2 GET` 200 with a list; a wrong status (returns 200 for the POST) fails with "expected 201, got 200"; a missing endpoint (no `/api/bookings` GET) fails with 404 in the evidence; a reply without `id` fails naming the field |
| `backend_e2e_check` | `--fast`: the check reports could not run and the atom is "could not run", never failed; `--browser`: the form in the mock page posts through the proxy and the booking comes back from `GET /api/bookings` with the typed values |
| `backend_in_run` | a `lib_run(YOGA_BACKEND_BRIEF)` with `J2_BACKEND=1`: the LLD has seven sections with A1, A2, T1; the backend workflow is registered after the last page workflow, priced 15, its five check kinds are in `receipts.jsonl` with `template_route`; `site/server.py` exists; `backend.json` names the template and version; the run ends Done |
| `backend_templates` | run 1 into an empty temp library creates "Still Point Yoga API endpoints", "... Data model", "... server.py" (v1 each, `extends` the generic refs); run 2 with the same brief reuses all three (rule a, no new version, `used_by` lists both runs); each run has its copies under `runs/<id>/templates/lld/api-endpoints`, `.../lld/data-model`, `.../backend/server-py`; `generic_drift() == []` with the flag on and off |
| `backend_retry` | a planted first reply with `import subprocess` is refused by `backend-safety`, the second attempt's prompt carries that exact line, the second reply passes, the atom's receipts show attempt 1 failed and attempt 2 passed |
| `backend_schema` | `reply_schema(BackendServer, {})` and the two LLD section schemas pass `inline_definitions`'s invariants (no nested definitions, every `$ref` resolvable) and are accepted by one live `claude -p --json-schema` dry call in the live-build script (not in the suite) |

### 9. Live runs (after "go", `STUDIO_PROVIDER=claude-cli`, under `caffeinate`, server on 8773)

| run | setting | estimate |
|---|---|---|
| Run 1 | the test brief (section 10), `J2_BACKEND=1`, `J2_TEMPLATE_LIBRARY=1`, `J2_ARTIFACT_SCHEMA=1`, `J2_LIBRARY_DIR=/tmp/j2-backend-lib` (new, empty) | 170 to 200 AI calls, 55 to 70 minutes, 20 to 24 generator calls |
| Run 2 | the same brief, the library from Run 1 | 150 to 180 AI calls, 45 to 60 minutes, 0 to 4 generator calls |

How the estimates were made: run `j2-20261103-184249` (same brief, documents plus a failed website stage) recorded
147 AI calls and 40.9 minutes with 18 generator calls; run `162711` recorded 44 calls and 10.9 minutes for the
PRD alone. Two more LLD workflows add about 6 calls and 3 minutes; the backend adds 1 to 3 builder calls plus the
checks (about 20 s each attempt); the website stage that never finished in 184249 adds its 7 builders and one or
two audit rounds. Run 2's generator calls drop because an identical need reuses by fingerprint (rule a) without a
generator call.

Answers during the runs: a budget or decision question gets "1" after checking that option 1 is add-and-keep-going
(otherwise stop and report); every other question is answered from the brief only, with option numbers.

**Comparison table** (one row per run, from recorded data only, "not recorded" where missing):

run id | stages made | done-when met | AI calls | input/output tokens | minutes | generator calls and seconds | created / extended / reused / generic | first-try schema pass % | retries | backend checks passed per kind (compile, safety, start, endpoint n of m, e2e) | e2e pass

Sources: `summary.json` (stages, done-when, ai_calls, workflow_agents.retries), `calls.jsonl` (tokens, seconds),
`template_calls.jsonl` (generator), `templates.json` (actions), `receipts.jsonl` (`artifact-schema` attempt 1 pass
rate, `backend-*` per kind), `backend.json` (e2e).

**Success** = `server.py` starts, every endpoint check passes, the e2e round trip passes, Run 2 makes fewer
generator calls than Run 1, no decision in either run is an extend below 0.5 (the router now overrules those to
create, so this shows as zero `overruled` records).

### 10. The test brief (to be saved as `scenarios/still-point-yoga-backend.md` in Phase 1)

> Create the design documents (PRD, HLD and LLD) and then build the website with a small backend for Still Point
> Yoga, a small yoga studio at 4th Floor, 22 Church Street, Bengaluru 560001.
>
> The page shows the name Still Point Yoga and the address as text, with no embedded map.
>
> The weekly class list has five classes, each with day, time and price in rupees:
> Monday 7:00 am Gentle Flow 500
> Tuesday 6:30 pm Strength Yoga 600
> Thursday 7:00 am Breath and Stretch 450
> Saturday 9:00 am Beginners Basics 400
> Sunday 8:00 am Slow Sunday 500
>
> The page has a class booking form with the fields name, email, class and preferred date. The form sends the
> booking to the site's own API: POST /api/bookings stores it, and GET /api/bookings lists the stored bookings.
> The page shows the stored bookings under the form after a booking is made. The studio's contact email,
> shown as text, is bookings@stillpoint.example. Payment is made at the studio. No online payment is taken.
>
> The teachers' names are not decided yet, and the studio has no phone number. Do not show teacher names or a
> phone number, and do not make any other detail up. Use only fake data in examples: the example booking is
> Test Person, test@stillpoint.example, Gentle Flow, next Monday.
>
> The page must work on phones. The documents, the website and the backend must agree with each other.

Changes from the recorded brief: "with a small backend", the API sentence in place of "sends the booking to
bookings@stillpoint.example", the stored-bookings line, the contact email kept as text, and the fake example
booking (a fake name and address; no phone number at all, so none to fake).

---

## D. Delivery

### 11. Phases, each gated by tests

| phase | what | estimate | gate |
|---|---|---|---|
| 1 | `j2_backend.py` checks (compile, safety, start, endpoint, page-calls, e2e helper proxy) and `run_check` wiring; fixtures | 1 day | `backend_compile_check`, `backend_safety_check`, `backend_start_check`, `backend_endpoint_check`, `backend_e2e_check` (--browser); `--fast` suite still 108 ok |
| 2 | LLD sections: models, rules (`prefix`, `covers_all`, multi-target `ref_exists`), `render_section`, `parse_lld`, `lld_slice`, conditions L7/L8, `lld_sections()` and the import-time lists made per-run; `artifacts/types.json` sections | 1 day | `backend_off`, `plain_unchanged`, `rules_split`, `artifact_schemas` extended with the two sections, `docs_chain` |
| 3 | the backend workflow: `_backend_stage`, `_run_backend`, `BackendServer` model and rules, the slice's endpoints and the BACKEND sentence for the form builder, `backend.json`, summary and report lines, `agents/j2/backend.md` (after your OK), rate key | 1.5 days | `backend_in_run`, `backend_retry`, `backend_schema`; a live single-call build of `server.py` with the fixed schema (scratchpad script, like `live_build.py`) |
| 4 | template library: `ARTIFACTS`, `SECTION_MODELS`, generic files, `FACT_FIELD_SECTIONS`, `save_into_run` paths, receipts' `template_route` | 0.5 day | `backend_templates`, `template_library` (unchanged assertions), library sha check (26 versions unchanged) |
| 5 | UI (section 12) and `j2_server.py` endpoints | 0.5 day | `artifacts_tab`, `artifacts_tree`, `template_library` browser part, a new `backend_tab` test (--browser) |
| 6 | live runs 1 and 2, the report `runs/backend-test-report.md`, PR | 2.5 hours of runs plus the write-up | the success line of section 9 |

Each phase: a checkpoint commit, the change, a commit, `./run_checks.sh` (with `left_bar`, `left_bar_toggle`,
`graph_map`, `map_motion` skipped as before, since the first two are known and the last two need a run that is not
on this machine), push.

### 12. UI

- **Documents tab**: the two LLD sections render as they come out of `lld.md` (`docBody` is heading-driven; no
  change). `ITEM_AT` gains `A` and `T` so atom cards can link to "A1".
- **Artifacts tab and tree**: `artifacts/types.json` gets a `backend` type (`kind type`, `form code`,
  `file site/server.py`, `deliverable true`, `depends_on ["lld", "website"]`) and a `backend-record` record
  (`backend.json`, `backend/*.log`), so `server.py` opens in the code view like `index.html` does and the logs
  are listed as evidence.
- **Atom card of the backend workflow**: the five receipts, as any atom's; the e2e line names the row that came
  back; the `template_route` chip the page already draws for library runs.
- **Library tab**: three more decision rows (two LLD, one backend) and the `backend` artifact group, from the same
  `/api/run-templates` and `/api/library` data; no new rendering.
- **"How to run it" line**: on the run's ready strip (`view=simple`, the "ready" state) and at the top of the
  Artifacts tab when `backend.json` exists: `python runs/<id>/site/server.py --port 8790`, then
  `http://127.0.0.1:8790/`. Read from `backend.json`'s `how_to_run` so the UI never composes a path.
- **Report** (`report.md`): one "Backend" paragraph: endpoints, tables, checks passed per kind, the template and
  version, the run line.

### 13. Risks and out of scope

Risks:
- **The e2e check needs Chrome and a same-origin page.** The helper proxy answers that; if Chrome is missing the
  check is "could not run", never a failure, and the run still ends (the same rule as `tap-targets`).
- **A builder reply that is valid JSON but not valid Python** fails `backend-compile` and costs an attempt; three
  such attempts hand the receipts to Adaptation, as today. The live single-call build in Phase 3 measures how
  often that happens before the live runs.
- **The safety scan is static.** It blocks the names it knows and `python -I` with an empty env limits what a
  missed one can reach, but it is not a sandbox. The server is started on `127.0.0.1`, with a fresh env, in the
  run folder, for the length of the checks only; the design says so in `backend.json` and the report.
- **The form test under `file://`** sends the fetch to nowhere; the builder is told to catch it. If a live builder
  does not, N2 fails with the uncaught rejection and the retry carries it.
- **Port collisions** with 8773 or another run: the checks take a free port from the OS each attempt; the person's
  own `--port` is their choice.
- **Two more LLD workflows** cost two more sections at the document rate and the stage gate may ask for credits
  earlier (the recorded run already raised twice).

Out of scope: authentication, sessions, payments, email sending from the server, deployment (no Docker, no
systemd, no host), HTTPS, rate limiting, migrations beyond `CREATE TABLE IF NOT EXISTS`, more than one page, and
any backend for a documents-only run.
