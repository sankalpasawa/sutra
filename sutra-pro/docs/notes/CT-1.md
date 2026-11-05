# CT-1 as built: cross-section contract tests

## What was built
`tests/contracts/` (a package), 11 files, 134 tests plus 1 xfail, about 6 s. Every module imports the sections it compares at the top (no
"if it imports"). `test_contract_world.py` holds the shared fixture `world`: the real orchestrator (database, chart, `TEnv` of ORCH-6, task service,
projector, usage store) in one `Services`, the engine's routes mounted on it with `mount`, and one router per section (engine, 8 orchestrator
routers, connectors with the real guard, UI). The other modules import `world` and the fixtures it needs by name from it.
- `route_table`: engine = the 23 exact + 4 templated J2 paths of the UI's own list (`J2_EXACT`/`J2_PREFIXES` in `sutra_ctx.js`) + GET/PUT settings;
  no `/d/{dept}` copy, no header/cookie team; `dept` mandatory (400/404); the department rule text; no two routers share a method and path; one
  write guard on every non-GET route of every router; token before team; `Services` against `EngineServices` (parameter lists); say/reset through the
  real task service; every path a page script calls is served, every engine route is called by a page.
- `settings`: the 7 task keys on both sides (values and bounds), locked switches refused (422), Settings routes against `EngineSettings.layered`
  (the layers stack, 0600 files, next run only), `ENGINE_OWNED` names the engine's files. `env_and_spec`: one allowlist for launcher and CLI children,
  `RunSpec`/`TaskSpec` field parity and round trip, the task.json and folder modes the service really writes, inbox lines read by the engine's tailer.
- `usage`: `llm.ask` -> stub router -> `EventUsageSink` -> `events.jsonl` -> Projector -> ledger -> API (turn atom, builder `<run>:W-n.aK`, overhead key,
  failed call, replay idempotent, per-atom sums = total, stub left out of totals). `make_port`: signature, single definition, no `RunSpec` in connectors,
  `ScriptedPort` = stub-only router (result and row), chat agent path through `AsyncConnector`. `run_events`: Appendix A as data against engine
  and orchestrator, builders strict, golden file, unknown field/type, end statuses. `fnodes`: atom ids vs `atom_sid`, no NULL atom id anywhere after a
  golden replay, chip and drawer `meta` keys, atom usage excludes stub rows. `json_extract_parity`: one object, no second `def`. `diagram_strings`: `gen.py` read as text.

## Deviations and decisions
- The diagram-strings case runs (does not skip): `gen.py` already carries the strings of S4-fnodes 12 and S1-17. It is never executed (it writes a file).
- `test_the_layer_factory_accepts_every_argument_the_host_passes` is `xfail(strict=False)`: real E3/E6 defect (host passes `spec=`, `layer.factory` names it
  `task`), same as E7 finding 1. Strict would break the gate for whoever fixes it. Remove the marker with the fix.
- No `conftest.py` (not owned): fixtures live in `test_contract_world.py` and are imported by name; imports of `orchestrator.*` come after it because
  `orchestrator/conftest.py` puts `tests/library` on `sys.path`. The golden file of E7 is the engine side of the function-node replay (no live run, 6 s).
- `/api/health` is called by a page script and served by no router yet (ORCH-8): listed in `NOT_MOUNTED_YET` in the route-table module; remove it then.
- The engine's `dept` is read from the request, not declared as an OpenAPI parameter, so "takes dept" is tested by behaviour (400 `dept_required`).

## Known limits
- No real engine process is spawned and no CLI is called; the real host runs only in E7's tests. A `settings.json` written by the host is not read here.
- The UI side is the router and the JS list; no browser. Scans of page scripts are regex over string literals and miss URLs built from variables.

## Needs / follow-ups
- E3 or E6: fix the `spec`/`task` keyword (see xfail). ORCH-8: `/api/health`, and wire `Services` as the world does (`department = DepartmentStore.row`, ...).

## Mutation check (one pass, copy in /tmp)
18 breakages (route dropped, dept rule, budget bound, allowlist name, `J2_*` passed on, default atom, builder atom form, router atom, stub rows in
atom sums, second extractor, diagram string, usage `atom` field, `make_port` signature, unguarded PUT, unchecked task settings, route under `/d`, unlocked
field, end status). 16 killed at once; the dept rule (the tests compared it with itself) got a literal-text test; unchecked task settings is equivalent
(the Checked work task refuses them on insert as well).
