# ORCH-1 as built: foundation (settings, database, schema, records, wire models, require_token)

Built: `config.py` (Settings, `.env` reader, layout helpers); `orchestrator/{errors,ids,redact,textutil,db,schema,records,models,services}.py`,
`api/deps.py` (`require_token`, error envelope, redacting response), `testing/__init__.py` (FakeClock, FakeIds, EventCollector).
4 test files + conftest, 195 tests, under 2 s. `plain_check` does not exist; `chart_changes` has `task_title`/`result_json`; `atoms.display`,
`atom_ledger` (append-only triggers) and `usage_ledger.step/atom_id/detail_json` are in DDL v1. `RunEvent` is a closed union of the engine's 8 events
(every `engine.events` builder output parses strictly in a test); `node` takes `wait_on` and `tokens` and has no `goal`.

## Deviations from the specification
- `records.py` holds the four stored records only (chat_session, chat_message, usage_record, work_task). `ChatDecision`, `AssignmentPlan`,
  `AssignmentDraft` stay with ORCH-7 (`agent/replies.py` is its file); their validator and transport-safety tests belong there.
- `chat_session.kind` and `chat_message.kind` ARE the record discriminator (one class, five kinds each). `chat_message` has no `id` (the store
  assigns it after the gate) and `card`/`usage_record.detail` are free JSON, so the registry refuses their transport schema (`transport_dict`);
  they are never sent to a model. `chat_session` and `work_task` are transport safe (tested).
- GateError on API input is always 422 `validation` (the library design would map `size` to 413; no such code exists in 6.1).
- Data dir fallback is `~/.sutra-pro` (D88), not the section's `~/.sutra-app`; `<project>/data` is used only beside a `pyproject.toml`.

## Decisions
- Settings is frozen; `token` and `override_key` are `exclude=True, repr=False` (in no dump, repr or `public()`); host only `127.0.0.1` or `localhost`;
  `max_live >= max_runs`; port 0 allowed; `J2_OVERRIDE_KEY` from the environment first, then `SUTRA_ENV_FILE`; a blank key means no key.
- `require_token` checks the token first (401), then Origin (403). It reads `request.app.state.services.settings.token`, so one function serves every
  router; with no services it fails closed (500). Safe methods pass untouched. More than one token or Origin header is refused.
- `Redactor.scrub` cleans the data before JSON is written (a secret with a quote or accent would be escaped and missed in the text); explicit extras
  (token, override key) are redacted at any length, env and `.env` values need 8 characters.
- `Database` publishes each commit's events as one list with `seq` 0 (the bus assigns it) and `at` from the clock; a failing subscriber is logged, never
  undoes the commit. `StoreContext.get` knows node, atom (`work-atom/0.3` rows only), org_chart (`chart`, `head` or a revision number), department.
- DDL is a tuple of single statements so a migration and its `user_version` bump are one transaction (tested to roll back).
- `parse_event(line, strict=False, *, dropped=None)` returns the variant or raises `EventParseError` (codes not_json, not_object, unknown_type, invalid);
  non-strict drops undeclared keys at the top and one level into nested closed objects and appends them to `dropped`.
- `TaskSettings` (7 keys, unset left out of the dump) is checked at import against the engine's `TASK_SETTING_KEYS`; `schema` fields are `schema_` with
  the alias `schema` (`RunSpec`, `RunStarted`, `AtomOut`, run-event atom).
- Extras in `textutil`: `stem`, `name_key` (for ORCH-5's name-equality rule) and `one_line_title` (the 60-character request title, T7).
- `NodeInit` (3.3 names it without fields) is `{node: Node payload dict, session_title, writable, session_id}`; ORCH-5 may reshape it.
- Importing `records.py` registers four families in the global REGISTRY: L8/ORCH-8 must import it before `REGISTRY.freeze()`.

## Known limits and follow-ups
- ORCH-2: the bus must give `Event(seq=0)` a real seq. ORCH-8: call `install_error_handlers(app, redacted_response_class(Redactor(env_file,
  extra=[token, key])))`, set `app.state.services`, pass `require_token` as the connectors' `write_guard`. The catch-all handler re-raises under TestClient.
- tests/orchestrator/conftest.py appends `tests/library` to sys.path to reuse `factories_atom` (that folder has no `__init__.py`).

## Mutation check
21 hand-made mutants (token length, loopback check, max_live bound, secret minimum and order, header count, empty Origin, BEGIN IMMEDIATE, publish
before COMMIT, a trigger, the live-task index, non-strict pruning, run.ended code, task end rule, yes/no punctuation, empty jaccard, change id width,
status table, StoreContext schema filter, function status, session time order). 18 killed first; 3 survivors (max_live equal to max_runs, an atom/1
row seen through `get('atom')`, session time boundary) became tests and are killed. No second round.
