# CN-1 as built: connector foundations

## Built (`sutra_app/connectors/`, tests in `tests/connectors/`, connectors.md 2, 3.1, 3.2, 4)
- `errors.py`: `ConnectorError(ModelError)` and the 23 classes of the 3.2 table (`code`, `kind`, `retryable`, `fallback_ok`, `provider`, `detail`, `resets_at`,
  `user_message(tz=)`, `as_dict()`); the six engine-named codes also subclass the engine's class. `ERROR_CLASSES`, `error_for_code`, `KINDS`.
- `models.py`: the 3.1 models, all `extra="forbid"`; `Allowance`/`CallTag` are the engine's class objects; `ConnectorConfig.resolved_work_root()`.
- `env.py`: `PASS_NAMES` (tuple; imports nothing from the app), `child_env(provider, extra, environ=)`, `is_secret_name`.
- `process.py`: `Command`, `ExitInfo`, `ProcessRunner` (`start`, `run`, `live`, `stop_all`), `RunningProcess` (`lines`, `wait`, `cancel`, context manager).
  Own process group; stdin, stderr and stdout each have a thread; a watchdog thread enforces the total and idle deadlines; ladder SIGINT 5 s, SIGTERM 5 s, SIGKILL 2 s.
- `jsonio.py`: `extract_json`/`close_json` are the library's objects; `parse_reply`, `validate_reply`, `parse_and_validate`, `format_errors`, `repair_prompt`, `prune_nulls`.
- `schema.py`: `to_json_schema`, `strict_schema`, `minimal_validate`, `example_from_schema`, plus `schema_text`, `schema_sha`, `fits_native`, `resolve_ref`.
- `__init__.py`: the error classes; `Router`, `build_router`, `make_port` resolve lazily from `router`/`factory`/`engine_port` once those modules exist.
- 5 test files, 180 tests, about 12 s (the process tests wait for real signals). Mutation self-check: 20 breakages of the package in a copy under /tmp (flags, secret-name guard, ladder, idle clock, process group, stderr cap, orphan kill, repair caps, prune, strict, bool-as-number, clamp, id pattern, cleanup, extra=forbid, 100,000 gate, first-reason-wins), every one failed a test (one by hanging the suite); no survivors.

## Deviations from the specification
1. `__init__` cannot export `Router`, `build_router`, `make_port` yet (CN-7, CN-9). A module `__getattr__` loads them on first use and `__all__` lists them only when their module exists; no change is needed here later.
2. The spec leaves unsaid where deadlines live and how a run ends. `ProcessRunner.start(cmd, timeout_s=, idle_timeout_s=)` takes them; the runner never raises for a bad exit, `ExitInfo.reason` (`exit|total_timeout|idle_timeout|cancelled`) tells the parser what to raise.
3. `minimal_validate` returns a list of error lines (empty = valid) rather than raising; `jsonio.validate_reply` raises `InvalidJsonError` from it.
4. `to_json_schema(class)` is the library's `transport_schema` (a `RegistryError` becomes `InvalidRequestError`); a dict is checked for JSON and an object root.
5. `child_env` gives both CLIs the same base. `provider` only names the child in an error. It also drops `SUTRA_*` names from `extra`, and a secret-looking name in `extra` raises `ValueError`.

## Decisions
- `invalid_json` has `fallback_ok=False`: the table says "by policy", and the router reads `policy.fallback_on_invalid_json` (default false) itself. `session_lost` and `no_model` ("n/a") are also False.
- Two table cells with two values map as listed: `crashed` retryable, `protocol_error` not; `provider_error` retryable, `model_not_found` not.
- `as_dict()` is the wire/log form: it drops `detail` keys named prompt, system, user, stdin, env, messages or containing KEY/TOKEN/SECRET/PASSWORD, cuts strings at 2,000 characters and lists at 50. The error object keeps its full `detail`.
- Quota text uses local time by default: `user_message(tz=...)` exists so tests (and the UI) can pin a zone.
- After a child has ended, the rest of its group gets SIGKILL (no orphans; an MCP child cannot hold stdout open). A grandchild outside the group is given 2 s, then the stream ends without it.
- `TurnResult` fields the design lists without a default are required (`model`, `provider_session_id`, `usd`, `usd_basis`, `duration_ms`).
- `AskRequest.schema` shadows pydantic's deprecated `schema()`; the one warning is silenced while the class is built.
- `prune_nulls(value, schema)` needs the ORIGINAL schema (class or dict before `strict_schema`): only a null at a not-required property goes. Without a schema every null dict value goes.

## Known limits
- `strict_schema` leaves a map with free keys (`additionalProperties` as a schema) as it is, and drops no format/length keywords; it stays UNVERIFIED against the real Codex API (connectors.md 10).
- `minimal_validate` checks type, required, enum, const, anyOf/oneOf, allOf, properties, items and local `$ref`; formats, patterns and lengths are not checked.
- POSIX only (`killpg`, `start_new_session`). A stdout line over 8 MiB is cut (its rest is dropped). Timing tests use 0.6 s ladder rungs.

## Follow-ups for other packages
- CN-3/CN-4: build `Command(argv, cwd, env=child_env(provider, cfg.extra_env), stdin_text, cleanup=[...])`, call `runner.start(cmd, timeout_s=, idle_timeout_s=)`, feed `lines()` to the parser, then map `ExitInfo.reason` to `CallTimeoutError`/`CallCancelledError` and `stderr_tail` to the error table.
- CN-7: use `schema_sha` for `native_blocked` and `fits_native` for the 100,000-character gate; `Router.close()` calls `ProcessRunner.stop_all()`.
- ORCH-6: import `PASS_NAMES` from `sutra_app.connectors.env`; it is a tuple of names, with the four lower-case proxy twins.
