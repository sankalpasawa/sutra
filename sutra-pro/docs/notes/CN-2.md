# CN-2 as built: fake CLIs, test harness and fixtures

## Built
- `tests/fakes/{claude,codex,gh}`: two-line sh wrappers for `tests/fakes/fake_cli.py` (stdlib, Python 3.9+, also runnable in-process: `fake_cli.Run`). Its docstring lists every `FAKE_*` variable, the scenario syntax and the call-log fields.
- Scenarios (`fake_cli.scenario_names(cli)`, `fake_cli.py --scenarios claude`): every stream in the manifest by short name or file stem; `ok` (ok_structured when a schema was sent, else ok_plain); `hang`, `hang_silent`, `slow`, `slow401`
  (codex), `noise`, `crash`, `truncated_exit0`, `bad_flag`, `session_lost`, `empty_reply`; one preset per row of connectors.md 3.4/3.5 (`C2`..`C25`, `X2`..`X18`, with C3a/b, C6a-c, C19a-e, X3a-c, X5b/c; C1, X1, X4 need none);
  `file:<absolute path>` replays any JSONL file; `FAKE_PATCH` edits any line. A scenario that is wrong for a CLI is an error naming all known ones. Shared sequences work for both CLIs (`quota` and `overloaded` exist for each).
- Session ids are rewritten; counters are cumulative per session in `sessions.json`, so the captured two-call sessions come out exactly (Claude 0.0097459 then 0.0190348, Codex 12168 then 24342); `FAKE_COST_USD`/`FAKE_USAGE` set one call's own amounts.
- Call log: `calls.jsonl` (written at the start, one record per invocation) and `exits.jsonl` (exit, signal, end time). Files given to `--output-schema`, `--system-prompt-file`, `--mcp-config` are read while the call runs (the connector deletes them).
- `tests/connectors/conftest.py` (stdlib only): fixtures `fake` (a `FakeCli`: `sequence`, `auth`, `reply`, `cost`, `usage`, `set`, `env`, `process_env`, `config_kwargs`, `bin_dir`, `run`, `popen`, `feed`, `finish`, `calls`, `model_calls`,
  `last_call`, `sessions`, `wait_for`, `visible_env_keys`, `approve_device_auth`), `make_fake` (module scope), `fixtures` (read access), `fakes_dir`.
- Fixtures: new `handwritten/` (versions, top-level codex help, three `claude mcp list` samples, the gh data); MANIFEST gains `origin: handwritten` and `recorded_after`; README rewritten.
- `scripts/capture_connector_fixtures.py`: the refresh tool (`SUTRA_LIVE=1`, `--plan`, `--only`, `--skip`, `--out`, `--claude`, `--codex`, `--pass-env`): at most two model calls per CLI, scrubbed and trimmed output, merged into `cli_errors.json`.
- `tests/connectors/test_fakes.py`: 227 tests, about 15 s. Mutation self-check: about 110 breakages of the fake, the harness and the script, applied to a copy in /tmp; every one fails a test (survivors got a test or were equivalent).

## Deviations from the specification
1. `FAKE_CLI_SEQUENCE` is consumed by model calls only (claude -p, codex exec, exec resume), not by every invocation: status, help and version commands would otherwise shift every test. `FAKE_CLAUDE_SEQUENCE`/`FAKE_CODEX_SEQUENCE` add a per-CLI counter.
2. The wrappers read `SUTRA_FAKE_PYTHON`, then `FAKE_PYTHON`, then `python3`, and run `python -E -S`. A connector drops `SUTRA_*` from the child environment, so `FAKE_PYTHON` is what travels through `extra_env`; `-S` saves 10 ms a call.
3. `kind` in the call log (call, probe) and `op` were added to the specified `{cli, argv, cwd, stdin, env_keys}`; so were n, scenario, session_id, pid, t_start, files, cwd_entries, env_values (`FAKE_LOG_ENV`), stdin_complete.
4. Every probe command (including `gh api`) has kind `probe`; only `claude -p`, `codex exec` and `codex exec resume` are `call`.

## Decisions
- The fake enforces only what a capture shows or the design states: bad `--json-schema`, missing `--system-prompt-file`, bad or missing `--output-schema`, missing `-C` dir, no `-s`/`-C` on `exec resume`, `--verbose` with stream-json (wording UNVERIFIED). Unknown flags are NOT rejected (`--system-prompt-file` is accepted but absent from `--help`): use `bad_flag`.
- An unknown session id is accepted as a new session; `session_lost` is explicit. A signed-out CLI turns the default `ok` into its not-signed-in stream; an explicit scenario always wins.
- `env_keys` leaves out what sh, macOS or Python add by themselves (PWD, OLDPWD, SHLVL, _, __CF_USER_TEXT_ENCODING, Xcode shim names, LC_CTYPE when neither LANG nor LC_ALL is set). `fake.visible_env_keys(call)` also drops the `FAKE_*` names.
- Codex rollout files go to `$CODEX_HOME` or `<state>/codex_home`, never into the real `~/.codex`, and not for `--ephemeral` calls; they hold session_meta and event_msg lines too, so a reader must pick the token_count lines out.
- gh: only `GET` is served; `--jq`, `--template`, `--input` exit 2; `gh auth token` prints a recognisable fake token so a test can assert it never leaks; repos exist only if named in `FAKE_GH_REPOS` (default octo-org/hello-world).
- Invented wording, marked in the code: the edited texts of C6, C14, C19, X11, `usage_limit_try_again`; Codex api_key status text; `claude mcp list` rows after ADR-035; gh texts. Never read these as evidence of what the real CLIs print.
- The capture script keeps its scratch directory only after a failure, never touches the repo unless `--out` is the default, and is tested only against the fakes (no real CLI was run).

## Known limits
- The fake does not start MCP servers named in `--mcp-config` or `-c mcp_servers.*`; CN-8 replays `mcp/*.jsonl` as client scripts. The capture script's MCP and interrupt steps are therefore only tested up to the fakes' answers (it warns when a CLI never contacts the probe server).
- POSIX only (`fcntl`). Timing tests allow for a loaded machine; the harness caps every fake at `FAKE_MAX_SECONDS=20`.
- `claude --version`/`codex --version` formats, `claude mcp list` rows and the Codex api_key status are handwritten (see MANIFEST wording_source).

## Follow-ups for other packages
- CN-3/CN-4: put `FAKE_PYTHON` in `extra_env` (`fake.config_kwargs()` does); `extra_env` must accept `FAKE_*` names (none contains KEY, TOKEN, SECRET or PASSWORD); use the row ids (`fake.sequence("C7")`) and `fake.model_calls()[i]["files"]`.
- CN-8: the 20 KB truncation case is `contents/big.txt` (60,000 bytes, `FAKE_GH_BIG_BYTES`); issue 3 carries an injection sentence for the untrusted wrapper.
- CN-9: `FAKE_HELP_MISSING=--json-schema` makes a provider `degraded`; `fake.approve_device_auth()` finishes a sign-in; `FAKE_CLAUDE_VERSION`/`FAKE_CODEX_VERSION` trigger the version warning.
- Design owner: connectors.md section 7 should say `SUTRA_FAKE_PYTHON` or `FAKE_PYTHON`, and "one per model call". No file outside CN-2 had to change.
