# CN-3 as built: ModelConnector base and ClaudeConnector

## Built
- `sutra_app/connectors/base.py`: `ModelConnector` ABC (one-shot `call_text`/`call_json`/`call_json_result`, chat `start/send/stream/stop/resume/forget`,
  `auth_status` 30 s cache, `flags`, `usage`), plus the internals the design names: `TurnPlan`, `LineParser`, `Hooks`, `CallInfo`, `CallRecord`.
- `sutra_app/connectors/claude.py`: `ClaudeConnector`, `ClaudeParser`, `CLAUDE_ERROR_MAP` (rows C1-C25 as data, `C25` maps to `"ok"`).
- Tests: `test_claude_parse.py` (parser on the fixtures), `test_claude_connector.py` (argv goldens, sessions, JSON strategy, hooks, health),
  `test_claude_errors.py` (one case per row, meta-test against the fake's rows and the design table). About 135 tests, 15 s.
- Mutation self-check, one pass: 16 breakages in a /tmp copy (delta rule, backwards counter, file threshold, persistence flag, effort check, quota text,
  error class swap, native size gate, repair count, file mode, resume flag, workdir check, num_turns rule, auth-cache drop, turn count, turn_done leak).
  2 survived (size gate, `send` leaking `turn_done`); one test added for each; both now killed. No second round.

## Deviations from the specification
1. The design names `TurnPlan`, `LineParser`, `Hooks`, `CallRecord` without fields; they are defined in base.py (see the module docs). `Hooks` has `before_call`,
   `after_call` and `on_quota`. `CallRecord` also carries `native_schema_sha`: the Router records a schema whose native call ended in `structured` in `native_blocked`.
2. Hooks can be set per call (`hooks=` on `call_*`, `send`, `stream`; the Router needs per-request allowances) or on `connector.hooks`.
3. `models()` is a plain method (default `[]`), not abstract; `call_json_result` is added next to the specified `call_json` and takes `force_prompted`
   (the Router's `native_blocked`), `repair_rounds`, `images`, `on_event`. `call_json` forwards them.
4. Backwards counter: 3.4 says `max(0, total - cum)`, 3.8 says a counter that goes backwards is "taken whole". 3.8 is implemented (usd = total).
5. `turn_done` carries `data["result"]` = the TurnResult as JSON; `send()` returns the object itself and does not pass `turn_done` to `on_event`.

## Decisions
- `resolve_model`: `SUTRA_CLAUDE_MODEL`, then `CLAUDE_CLI_MODEL`, override the request/policy model, then `sonnet`. Names are checked against a pattern (argv safety).
- The chat system text is stored in `<workdir>/system.txt` (0600; `SessionState` has no field for it) and sent on every turn. `start()` replaces an existing `session.json`.
- `resume()`: `session.json` is authoritative; missing file or lost work dir gives `provider_session_id=None`; a malformed id is dropped; a stored `workdir` that is not
  `<work_root>/<session_id>` is refused. `send()` does the same checks. A failed turn changes nothing in the state (also not `cum_usd`).
- One turn per session at a time (`InvalidRequestError`, "already running a turn"); `stop()` only reaches session turns (one-shots end with `Router.close()` -> `runner.stop_all`).
- Claude `reasoning_tokens` = `output_tokens_details.thinking_tokens` clipped to output (not in the spec). Usd is rounded to 10 places (removes float noise: 0.0097459, 0.0092889).
- C3b: the base asks `recover(plan, error)` once; Claude retries with the system text inline. Files (system prompt, MCP config) live in a private `_files` dir under the work
  root, mode 0600, removed with the call; one-shot cwd is a fresh dir under `_oneshot`.
- `--max-budget-usd` = `Allowance.max_usd` minus what earlier spawns of the same request spent; none left raises `EnvelopeExceededError` before a spawn.
- Images: PNG or JPEG by magic bytes (the design says PNG); anything else is `invalid_request`. `MAX_PROMPT_CHARS` = 4,000,000.
- `probe_auth` returns `installed=False` for a missing CLI; `probe_flags` raises `CliMissingError`. `--system-prompt-file` is not probed (it is absent from `--help`).
- Hooks for CN-4 (Codex): `transport_schema(schema)` (strict schema) and `clean_native(value, schema)` (prune_nulls) are no-ops in the base.

## Known limits
- UNVERIFIED live: an empty `--system-prompt ""` (always passed, as J2 does); MCP tool calls by the model; `--max-budget-usd` behaviour.
- The MCP entry is a minimal adapter (`ClaudeConnector.mcp_servers`): server `sutra`, `SUTRA_DB_RO` = `<data_dir>/sutra.db` is an ASSUMED name; CN-8 overrides the method.
- Cost of a failed call is not folded into `cum_usd`. Idle deadline applies only to streams with partials. POSIX only.

## Follow-ups for other packages
- CN-7 Router: implement `Hooks` (allowance gate in `before_call`, usage row from `CallRecord`, `HealthBook` from `on_quota`/`code`); on `SessionLostError` or a
  switch set `provider_session_id=None` and reset counters itself; key `native_blocked` on `record.native_schema_sha` when `record.code == "structured"`.
- CN-4: subclass the base, override the four hooks plus `transport_schema`, `clean_native`, `models`, `recover`; reuse `_run_probe`, `_private_dir`.
- CN-8: replace `ClaudeConnector.mcp_servers` with `tools/profiles.py` output. Design owner: 3.4 C-row "usd = max(0, ...)" should say "taken whole when it goes backwards".
