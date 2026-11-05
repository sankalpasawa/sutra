# GAP-W1 as built: integration defect fixes (G01, G02 test, G03 rule, G04)
## Built
- G01a `engine/fnodes/layer.py`: `factory(..., task=None, *, spec=None, ...)`; `spec` is the host's name for the `TaskSpec`, `task` stays
  as its alias, both together are a `TypeError`. A default run (no `SUTRA_HOOKS`) now gets `FunctionNodeHooks`.
- G01a `engine/host/loop.py`: a hook layer that cannot be built still falls back to `EventHooks` with the `publish.error` trace line
  and now also posts the `system` line "function nodes are off: <reason>" (after `run.started`, first of the host's system lines).
  `SUTRA_NODES=off` posts nothing. A factory `ValueError` is still "could not start".
- G01b `loop.py`: `_stop_run` (stop line and SIGTERM) calls `hooks.abandon_open("stopped")` after the run thread is waited for and
  before the summary, the final publish and `run.ended`. `HostHooks.__getattr__` forwards it; plain `EventHooks` has none (skipped,
  not an error). Both E7 `xfail` marks are gone; the two tests pass.
- G03 `config.default_env_file` and `engine.paths.default_env_file`: `SUTRA_ENV_FILE`, else `<project>/.env` when
  `project_root()/pyproject.toml` exists, else `default_data_dir()/.env`. `engine/paths.py` gets its own `default_data_dir` (same rule as
  config's, using its own `project_root`) so the engine does not import `config`.
- G04 `config.DB_FILENAME = "db.sqlite3"`; `Settings.db_path`, `ClaudeConnector.mcp_servers`, `CodexConnector.mcp_servers` and
  `profiles.mcp_servers` use it (they import it from `sutra_app.config`).
- G02: the `library/specs/*.json` glob was already in `pyproject.toml`; this package only adds the wheel test.
- `tests/integration/test_wiring_defects.py` (20 tests, about 7 s): factory name and alias, `Host._make_hooks` without override,
  the failure reason and the chat line, stop and SIGTERM abandon, both env-file functions, the constant, a real MCP subprocess per
  entry builder over a `Database.migrate()` + `ChartStore.bootstrap()` database, the wheel member.
## Existing tests changed
- `tests/engine/test_engine_fn_golden.py`: the two `xfail` marks removed (as specified).
- `tests/contracts/test_contract_fnodes.py`: the non-strict `xfail` on `test_the_layer_factory_accepts_every_argument_the_host_passes` removed (it XPASSed: same G01 defect).
- `tests/connectors/test_tools_mcp.py` (golden MCP entry, line 458) and `tests/connectors/test_codex_connector.py` (`-c` flags, line 182):
  the expected `SUTRA_DB_RO` is `<data>/db.sqlite3` instead of `sutra.db` (the intended behaviour change, not a weaker assertion).
## Decisions and deviations
1. The "function nodes are off" line is written by `_serve` with the other system lines, not by `_make_hooks` (the chat file and `J2Run`
   do not exist yet when the hooks are built). `Host._function_nodes_off` holds the reason until then.
2. The SIGTERM test drives the real host in-process through the E7 recorder (`rec._answer` replaced by a function that calls
   `Host.request_termination`), not by a real signal: the signal handler only calls that method (E3).
3. The wheel test builds from a copy of `pyproject.toml`, `README.md` and `sutra_app/` under `tmp_path` (the checkout is not touched);
   it skips with a printed reason when uv is missing or cannot build offline (takes about 1.3 s here).
4. The 0600 mode check and the `.env` template named in G03 belong to GAP-OPS-1 (`config init`, doctor), not here.
## Known limits
- Mock-mode scenario only; a real-model run with the layer on is GAP-E2E/GAP-LIVE. The launcher still sets no `SUTRA_ENV_FILE` (by spec).
## Follow-ups
- GAP-OPS-1: `sutra-pro config init` should write `default_env_file()`; `doctor` should report which file that is.
## Mutation check
One pass, 15 breakages (spec ignored, both allowed, abandon call dropped, wrong reason, chat line dropped, reason not kept, two env
inversions, env file variable ignored, constant renamed, three connector names reverted, spec glob dropped, layer abandon emptied): 15 died.
