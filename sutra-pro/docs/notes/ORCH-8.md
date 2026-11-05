# ORCH-8 as built: app shell, wiring, CLI, health, scenario and packaging tests

Built: `sutra_app/main.py` (`create_app`, lifespan, `LoopbackHostMiddleware`, CLI `run`, `bind_socket`, `AppServer`), `__main__.py` (`main`),
`orchestrator/wiring.py` (`build_services`, `start_services`, `stop_services`, `refresh_function_nodes`, logging), `orchestrator/api/system.py`
(`/api/health`, `/api/config`). Tests: `test_scripted_conversation.py` (16, steps 1 to 8 over HTTP, failures, a restart mid-run), `test_startup.py` (32, incl. a real child
process stopped by SIGTERM with a stream open), `test_api_security.py` (28), `tests/test_packaging.py` (9 + 1 slow wheel build, run once: green). About 14 s.

## Deviations from the specification
- The Host guard is our own ASGI middleware, not Starlette's `TrustedHostMiddleware`: that one answers plain text, the design wants the envelope `bad_host`.
- Logging: a redacting FORMATTER (so tracebacks are cleaned too), installed by the CLI (`configure_logging`), not by `create_app` (a library call must not
  change a process's logging). Lines go to `<data>/logs/server.log` (0600) and stderr.
- `create_app` builds the services (dirs 0700, database object, connector router) but opens no connection and starts nothing; the lifespan migrates, bootstraps,
  sweeps, refreshes function nodes, reconciles and starts work. With an injected `connector` the `/api/connectors` routes sit on a stub-only router.
- The library's `/api/schemas` router is mounted (guard = `require_token`) between the connector routes and the UI; 6.4 does not list it, S3-web-15 names it.
- `REGISTRY.verify_refs()` and `freeze()` run in the CLI only. Freezing in `create_app` would freeze the test process's global registry.
- `/api/health`: `schema` = `PRAGMA user_version`; a connector status slower than 1.5 s gives `connectors: {}` (the launcher polls with a 2 s limit); a database
  that cannot answer gives 503 `ok: false`.
- `Services` is subclassed as `AppServices` (adds `connector_router` and the startup report fields).

## Decisions
- Port: `--port N` or `SUTRA_PORT` means exactly that port (exit 2 if taken); otherwise 8780 then the next free up to 8799. The socket is bound first and handed
  to uvicorn, so `/api/config` shows the real port (`--port 0` works). Browser opens after startup unless `--no-browser`; `--offline` = stub + engine mock.
- Shutdown order: turn runner, event bus, connector children, WATCHERS, stop ladders, WAL checkpoint, database. `AppServer.shutdown` closes the bus before
  uvicorn waits for connections (an open SSE stream would otherwise hold the stop for the 5 s graceful timeout; measured: 0 s with it).
- FOUND BY THE TESTS: `RunWatcher` could see a process the ladder had just killed, find no `run.ended` and mark the task `crashed` before `TaskService.shutdown`
  settled it as `stopped` ("the app was closed"): 4 failures in 12 runs. Closing the watchers first removes the race (`test_the_watchers_end_before_the_stop_ladders`).
- Scripted scenario: the fake engine plays run.started, waits for the answer, closes the atom, reports a call, ends; the test writes the question, Identity
  waiting and the opened atom into `events.jsonl` itself (deterministic). Event order is read from `/api/events?once=1`.
- The route walk reads FastAPI 0.162's lazy `_IncludedRouter` (private); the test asserts it sees 30+ reads and 20+ writes, so a FastAPI change fails loudly.
- `test_a_running_app_opens_nothing_under_docs` records every `open()` while the app runs (only two library generators name `docs/schemas`).
## Known limits
- No real engine process is started (fake launcher); the CLI test runs `--offline` on the stub connector.
- After SIGTERM uvicorn re-raises the signal when done (exit status 143, graceful stop first).
- `VENDORED.md` is in the wheel (MANIFEST.in + `include-package-data`); harmless.
## Follow-ups for other packages
- ORCH-5 / ORCH-7: both define `POST /api/chart/changes/{id}/decision`; the agent's wins (included first, tested). FastAPI warns "Duplicate Operation ID" when
  `/openapi.json` is built. Drop one, or give one an `operation_id`.
- ORCH-6: `RunWatcher.tick` and `TaskService.shutdown` should not race (see above); a shutdown flag on the watcher would make the wiring order unnecessary.
- CT-1: `/api/health` is served now; remove it from `NOT_MOUNTED_YET` and mount `api.system.build_router()` in its world.
- REL-2: the launcher logs to `logs/app.log`, the server to `logs/server.log`.

## Mutation check (one pass, copy in /tmp)
17 breakages (host check, port syntax, router order, error handlers, queued-start hook, reconcile, bus close, function-node refresh, health on db failure,
health wait, log redaction, server bus close, explicit port, task shutdown, injected-connector router, token in config, watchers first): all 17 killed (4 needed
a re-run: the scratch copy lacked git). The run produced the watcher race above and tests for queued start, router order, the port rule and the SIGTERM time.
