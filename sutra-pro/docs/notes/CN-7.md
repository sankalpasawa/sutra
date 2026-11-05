# CN-7 as built: Router, transcript carry-over, engine and orchestrator ports

## Built (`sutra_app/connectors/`, tests in `tests/connectors/`, connectors.md 3.6, 3.8, 3.10, S1-contracts-02/05/06/07/08, S4-fnodes-07)
- `transcript.py`: `render_carry_over(messages, from_provider=, to_provider=)`: whole up to 60,000 characters, else last 40 whole + one 120-character line per older message (8,000 cap).
- `router.py`: `Router` (`plan`, `ask`, `call_json`, `complete`, `chat_start/send/stream/stop/pin`, `status`, `provider_summary`, `drain`, `close`), `Plan`, `RouterStatus`, `mode_from_env`.
- `engine_port.py`: `make_port(spec, *, usage_sink=None)` (the only one), `port_from_config` (same with a given `ConnectorConfig`; tests point it at the fakes), `build_connectors`, `RouterPort` (describe, preflight, complete, close).
- `orchestrator_port.py`: `AsyncConnector` (`call_json`, `status`, `records_usage`) and `build_tag`.
- 209 tests in the eight owned files, about 13 s. Mutation self-check, one pass: 18 breakages in a /tmp copy (retry count, delay index, fallback rule, max_calls and ceiling off by one, native blocklist, avoid/pin order,
  digest width, atom_id mapping, stub text strip, switch detection, busy check, duplicate last message, stub connector name, gate in before_call, session hook, health events, ...). 1 survived (the
  gate in `before_call` was reached by `_drive` and the post-wait check anyway): a test now proves a refused spawn never queues for a slot. No second round.

## Deviations from the specification
1. `Router(...)` also takes `connector` (auto|claude|codex|stub), `offline`, `policy_source`, `policy_error`; the router reads NO environment. `mode_from_env()` turns SUTRA_CONNECTOR/SUTRA_OFFLINE into those two values for the factory (CN-9).
   A restriction is the single provider, even if a rule's order omitted it. `plan(req, *, pinned=None)` has the extra keyword.
2. `max_attempts` is the number of TRIES per provider (J2 `range(2)`, and 3.10 "retries once"): the default is one retry after 2 s. 5.4's "2 s, then 5 s" needs `max_attempts` 3.
3. `complete()` with a `json_schema` and `ask()` with a schema call the base's `_oneshot_plan`/`_execute` (and the stub's `_request`): the base has no public call that returns the reply text of a schema request
   without parsing it, and `complete()` must not repair. Native, then ONE prompted retry on a `structured` error; Codex nulls are pruned from the text.
4. `native_blocked` is a set of `(provider, sha of the transport schema)`, not bare shas: a Codex rejection must not block Claude.
5. A call without schema in `call_json` is asked for `{"type":"object"}` on the prompted path (the base returns raw text for no schema). A reply that is not an object is `InvalidJsonError` in `AsyncConnector`.
6. `AsyncConnector.status()` leaves out `account` (PII); a missing `purpose` stays CallTag's default `agent_turn`; only the five documented context keys are read.

## Decisions
- One `UsageIn` per request in a `finally`; a sink that raises is logged and swallowed (a lost row must not fail a model answer). A request that fails at plan time (NoProviderError, missing image, closed router) also records a row (ok false, provider = first of the rule's order, no attempts).
  `JsonResult.usd`/`calls_made`/`usd_spent` and `CompletionResult.usd` are request totals; tokens, model, session id are the answering turn's. `detail` of a failed request's error gets the row's keys.
- Gate order: gate, concurrency slot, gate again (the deadline may pass while queued); a retry checks the gate BEFORE it sleeps. `max_usd` handed to a connector is reduced by what earlier spawns of the request spent; the call timeout is cut to the time left to the deadline (min 1 s).
- Skip reasons are actionable and name no provider twice ("Claude: CLI not found on PATH (install it and run `claude` once)"). Health events (`connector.health`) fire when `HealthBook.state` changes after a spawn.
- Chat: every turn follows the policy order (pinned first), so a session returns to Claude after a quota switch once Claude is healthy (one carry-over); the system text (`system.txt`) is re-sent on a switch. `connector.switch` and the session hook run after the turn succeeds;
  the old provider's session is forgotten in a daemon thread (`drain()` waits). The carry-over is followed by `New message:`; the owner's message, if already stored last, is dropped from the history.
- Progress: `{"chars","text"}` cumulative (no repeat when the closing `text` equals the deltas), `{"note": ...}` once when a fallback answered. `partials` only when a progress callback is given and no schema.
- Concurrency: one semaphore per provider from the policy (the stub 64). Today's counters in `status()` live in memory (the ledger is the truth).

## Known limits
- `close()` cannot interrupt an injected `sleep` or a wait for a concurrency slot; a one-shot stub reply with `STUDIO_MOCK_DELAY` cannot be stopped (ScriptedPort's can).
- A chat turn that fails after `start()` replaced `session.json` (a switch) leaves the file on the new provider with no provider session id; the next turn simply starts a session with the carry-over.
- `preflight`/`describe` may run a status command when its 30 s cache is stale; they never call a model. The `Named` stub double in the tests answers `turn.provider == "stub"` whatever its name.

## Follow-ups
- CN-9: `build_router` can reuse `build_connectors` and `mode_from_env`, pass `PolicyLoad.source/error`, publish `connector.mode`; `/api/connectors/status` = `Router.status()` plus tools and mediated; Codex sign-in calls live on the connector.
- CN-3 (base): a public "schema text without parsing" call would replace the private use in 3. ORCH-3: `UsageStore.record` de-duplicates on `(task_id, call_ref)`; `MemoryUsageSink` does not.
