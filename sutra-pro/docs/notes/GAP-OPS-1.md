# GAP-OPS-1 as built: operator CLI, instance lock, logging, browser choice, scripts

Built: `sutra_app/ops/{__init__,lock,doctor,logsetup,cli,envfile,browser}.py`, `scripts/run.sh`, `scripts/stop.sh`; `__main__.py` (thin dispatcher) and `main.py` (lock,
logging, browser, request id, ops-router mount). Tests: `tests/ops/` 114 tests in about 13 s (doctor 26, cli+start-up 41, lock 16, logsetup 12, browser 15, envfile 6).

## What it does
- `sutra-pro [serve] [flags]` unchanged; new `--browser auto|chrome|default` and `--verbose`. Words `doctor status stop config open` go to `ops.cli`; `serve` is optional.
- Lock: `app.lock` (flock) + `app.pid` (`"<pid> <port>"` line, then JSON). `run` locks before anything else; a held lock prints "already running on ... (pid N)", opens
  the browser unless `--no-browser`, exit 0. `stop` = SIGTERM, wait 20 s (`--wait`), never SIGKILL. Exit codes 0/1/2; `status` of a stopped app is 1.
- Doctor: 14 checks (python, data_dir, disk, database, env_file, claude, codex, gh, chrome, port, instance, library, browser, settings), statuses ok/warn/fail/skip.
- Logging: rotating `server.log` 5 MB x 5 (all files 0600), `RedactingFilter` (message, args, traceback), `X-Request-Id` (12 hex) on every response incl. 400 and 500.

## Deviations from the specification
- Lock and logging are taken in `run` (the server process), not in `create_app`: `create_app` is called many times per test process and by the E2E harness, and ORCH-8 decided a
  library call must not change logging. `create_app` gains only the request-id wrapper (outermost, via `build_middleware_stack`) and the `ops.api` router mount.
- The lock is taken BEFORE the socket is bound (so `--port 8780` against a running instance gives "already running", not "port taken"); the port is added to `app.pid` after binding.
- uvicorn re-raises SIGTERM when it is done, so `run` does not return after a stop: the lock is released from `AppServer.shutdown` (attribute `after_shutdown`) as well.
- `config init` writes the EFFECTIVE env file (`Settings.env_file`: `<project>/.env` in a checkout, `<data>/.env` installed, `SUTRA_ENV_FILE`), not always `<data>/.env`, so what it writes is what the app reads (D95).
- ORCH-8's `wiring.configure_logging` (plain FileHandler) is no longer called; it stays in `wiring.py` (its test still uses it). The console handler shows WARNING and up (DEBUG with `--verbose`).
- `doctor`: a CLI that is broken is a warning while the other CLI works, a failure when neither does. A CLI version other than the tested one is a warning. gh missing is `skip`.
- `AppServer.opener` defaults to `browser.open_url` (was `webbrowser.open`); `run` sets it after construction so the ORCH-8 test double needs no new argument. No existing test was changed.

## Decisions
- `SUTRA_BROWSER_APP` beats `auto`/`chrome`, not `--browser default`. App names go to `open -a` on macOS and are run as an executable elsewhere.
- `sutra-pro stop` with nothing running exits 0 (the goal is met). It refuses to signal when the pid is gone but the lock is held, or when the pid file is unreadable.
- Extension contract for GAP-DATA: modules `ops.backup`, `ops.retention`, `ops.exporter` may define `register(sub)` (add parsers with `parents=[cli.common_parser()]`, `set_defaults(func=f)`, `f(args)->int`);
  `ops.backup.before_upgrade(settings)` runs before the server is built and a failure stops the start (exit 1). `cli.COMMANDS` maps name to `f`.
- The first-run doctor (empty data folder = no `db.sqlite3`) prints only failures; it never stops the start.
- `config set` writes the parsed typed value (`budget` 55, `rates` false) under the field name; empty clears to the default. Locked fields are allowed here only.

## Known limits
- The doctor's `database` check opens the file read-only; a database in the middle of a migration by a running server may answer "locked" (reported as fail).
- Access-log lines carry no request id (uvicorn logs them outside the request's context).
- `scripts/run.sh` was run only with `--help` (it would otherwise start a server); the venv-creation branch (`uv venv`) is not exercised by a test.
- Default browser detection reads the LaunchServices plist on macOS only.

## Follow-ups for other packages
- GAP-CONSOLE: use `ops.doctor.run(settings, offline=True).to_dict()` and `logsetup.request_id_var` / `scope["state"]["request_id"]`; export `router` from `sutra_app.ops.api`.
- GAP-DOCS: document `--browser`, `--verbose`, `SUTRA_BROWSER_APP`, the commands and their exit codes. Chassis: README/ENVIRONMENT should list `SUTRA_BROWSER_APP`.
- GAP-E2E: `create_app` takes no lock; start the process (`python -m sutra_app`) to test the lock.

## Mutation check (one pass, copy in /tmp)
17 breakages (lock result, foreign pid file, port bounds, traceback redaction, query string, request id length, rotation count, disk comparison, API-key login, usable-CLI rule,
stop signal, set validation, env file mode, default-browser preference, lock release after shutdown, twin with --no-browser, library sync overwrite): 16 killed at once; the
port-bounds one survived (only 70000 was tested) and got a test for 0, 65535 and 65536. All 17 killed. A stray test (uvicorn.Config with its default log_config) polluted the access
logger for later tests; fixed with log_config=None.
