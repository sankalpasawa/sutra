# CN-9 as built: factory, HTTP API and live tests

## Built (`sutra_app/connectors/{factory,api}.py`; tests in `tests/connectors/{test_factory,test_api,test_live}.py`; connectors.md 5.5, 5.6, 6, S1-contracts-08, S3-web-03, S3-web-15)
- `factory.build_router(settings, *, usage_sink, events, transcripts, session_hook)`: reads only `data_dir`, `connector`, `offline` (a test proves it); no environment. Loads the policy (a bad user file is
  kept out and its reason rides in `status().policy.error`), builds the connectors with `build_connectors`, probes `--help` once per CLI, logs a version other than 2.1.308 / 0.146.0, publishes `connector.mode`.
- `api.build_api_router(*, router, write_guard)`: `/api/connectors` prefix; `write_guard` is a required keyword (missing = `TypeError`); the six PUT/POST/DELETE routes depend on it, the six reads do not.
  Routes: status, models, policy (GET/PUT), `{provider}/test`, `codex/sign-in` (POST, GET `{id}`, DELETE `{id}`), `sessions/{id}/provider` (PUT), tools, mediated (GET, POST refresh).
- 49 tests in the two files (about 25 s together, fakes only). Live: 4 tests, run once by hand here (about 55 s): all passed on the owner's logins.
- Mutation self-check, one pass: 18 breakages in a /tmp copy (stub-only rule, required flags dropped, version compare, mode event, `only=`, flag list, forget_auth, status order, policy adoption, size cap,
  missing guard on the pin route, Retry-After, offline refusal on test, offline tools, token count, 404 mapping, Codex sandbox adoption, restricted test router). 3 survived; 2 got a test (size cap message, `tokens_in`
  = `input_total`); 1 is equivalent (the test router already holds only one connector, so its `connector=` argument cannot change a result).

## Deviations from the specification
1. `build_router` also takes `config` (a `ConnectorConfig`, so tests aim the executables at the fakes) and `**router_kw` (clock, sleep, health) beyond the specified signature.
2. "Degraded": `HealthBook` has no such state and CN-6 is merged. A missing REQUIRED flag (`factory.REQUIRED_FLAGS`: the ones every call puts on the command line) is recorded as the existing `flag`
   cooldown: health state `cooldown`, reason "the CLI does not accept a needed flag", 10 minutes, a `connector.health` event, the plan skips it and falls back. Optional flags (schema, images, tools, resume) do not degrade.
3. Stub and offline build a stub-only router and never probe a CLI (`status` then lists only `stub`).
4. Error codes: ORCH's `STATUS_BY_CODE` is closed and not mine to edit, so this module answers its own codes in the same envelope: `policy_invalid` 422, `offline` 409, `refresh_too_soon` 429 (with `Retry-After`),
   and a `ConnectorError` keeps its own code (`quota` 429, `timeout` 504, `invalid_request` 422, `cli_missing` 503, others by kind: unavailable/auth 503, bad_output 502). `not_found`, `provider_unavailable`, `validation`, `bad_token` are ORCH's.
5. Poll body is `{"state","reason"}` (the spec shows only `state`); test body adds `provider`, `model`, `tokens_out`, `reply`; models without `provider=` lists all with a `provider` key.
6. `test_live.py` makes THREE calls per CLI, not two (schema; chat turn with a tool; resume turn): the listed checks cannot share fewer.

## Decisions
- A stored policy is also adopted by the running router (routing rules, Codex sandbox and rate card), so status and file never disagree; concurrency caps and the set of connectors keep their start-up values until restart.
- The Test button runs through a second `Router` over ONE connector that shares the policy, health book, usage sink and events (a fallback answering would mislead); its usage row has purpose `connector_test`. It reads
  `router._sleep/_clock/_rng/_events` (same package) so injected clocks carry over.
- A finished Codex sign-in drops the cached auth and publishes `connector.health` (the page sees `signed_out` clear at once).
- Offline refuses test, sign-in and a mediated refresh (409 `offline`) and reports `tools.github` false without running `gh`.
- `gh auth status` for `tools.github` runs with the connectors' `extra_env`, on every status call (not cached).

## Known limits
- `PUT /policy` cannot add a provider whose connector was not built at start-up (it is reported "not configured").
- The Codex `tool_call` event carries no tool name (observed live: `{"type": "mcp_tool_call", "id"}`), so the live test only requires that a call happened for Codex and checks the name for Claude.
- Sign-in start blocks up to 20 s in a thread-pool worker (the connector waits for the link and code).

## Follow-ups for other packages
- ORCH-8: `app.include_router(build_api_router(router=router, write_guard=services.require_token))`, `build_router(settings, usage_sink=..., events=bus.publish_one, transcripts=ChatTranscripts(chats), session_hook=chats.set_provider)`.
- ORCH: add `policy_invalid`, `offline`, `refresh_too_soon` to `STATUS_BY_CODE` if the page should treat them uniformly. UI-7: use `user_message()` from `error.message`.
- CN-3/CN-4 owners: expose `version()` on the base class (the factory uses `getattr`).
