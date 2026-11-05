# CN-6 as built: routing policy, health book, usage

## Built (`sutra_app/connectors/`, tests in `tests/connectors/`, connectors.md 3.6, 3.8, S1-contracts-05/17, S4-fnodes-07)
- `policy.default.json` + `policy.py`: closed models (`RoutingPolicy`, `ProviderPolicy`, `Defaults`, `Match`, `Rule`, `Rate`), `Resolved`,
  `parse_policy` / `load_default_policy` / `load_policy(data_dir)` -> `PolicyLoad(policy, source, error, errors)` / `write_policy` (atomic, 0600),
  `RoutingPolicy.resolve(req)` and `resolve_fields(...)`. `allow_api_key_billing` is gone: a file holding the key at any depth fails with its own message.
- `health.py`: `HealthBook(clock=)`: `installed(p, probe)` 60 s, `auth(p, probe, refresh=)` 30 s, `failed(p, err)`, `ok(p)`, `set_quota`, `update(p, error=, quota=)`,
  `cooldown`, `state` (-> `HealthState` for `/api/connectors/status`), `skip_reason(p, installed_probe=, auth_probe=)` (one call for the plan's drops), `snapshot`.
- `usage.py`: `usage_from_claude/codex`, `cumulative_delta`, `cost_delta`, `rate_card_usd`, `Attempt`, `UsageIn` (fields of connectors 3.8, with `step`, `atom_id`),
  `build_usage_row`, `step_label`, `call_ref`, `new_request_id`, `UsageSink` (runtime Protocol), `MemoryUsageSink`, `save/load_session_state`.
- 107 tests, about 1 s. Mutation self-check: 22 breakages in a copy under /tmp, one survived (rule-level duplicate `order`), test added, none left.

## Deviations from the specification
1. `UsageIn.how` allows `text` besides native|prompted|repaired|stub|chat: a plain text ask has no JSON strategy, and the engine's `usage_event` refuses an empty `how`.
2. `Rate` has a fourth optional price, `cache_write_per_mtok` (null = priced like fresh input); the shipped default still lists the three keys of the design.
3. Claude's `usd = max(0, total - cum)` is refined to "a total below the previous one is taken whole" (the CD5 rule for counters that go backwards).
4. `call_ref` falls back to `r:<request_id>` also when `call_no > 0` but `run_id` is empty (a bare number would collide across runs).

## Decisions
- Precedence for effort and timeout: matching rule > request > defaults (the engine sends an effort on every call, so with the request first the `summary` rule could never apply).
- A counter "went backwards" when ANY part of `Usage` is smaller than before; then the new counter is the call's usage, whole.
- `Match.tools` compares as a set of names; fnmatch is case-sensitive; an empty `match` is a catch-all; a missing stage/role is matched as "".
- Cooldowns: only quota, rate_limited, overloaded, flag errors and the crash breaker block; `not_signed_in` drops the auth cache, `cli_missing` marks not installed.
  Same-kind blocks keep the later end. `ok()` lifts every block and an exhausted snapshot. Exhausted quota with no reset time blocks 15 min (Claude) / 30 min (Codex) from when seen.
- `skip_reason` order: not installed, signed out (`signed_in is False` only), API-key billing (`billing == "api_key"`, no override), then blocks.
- Row sums: `usd` adds the attempts that know theirs (None when none does); tokens are None when no attempt reported a count; usd rounded to 9 places.
- `step` = builder id when `tag.function` is `W-<n>`, else `J2.<a-h>` from `tag.step` 1..8, else None. `fn`, `dept_id` are None when empty.
- A request that failed before any spawn takes `provider=` from the caller (the planned one) and has zero attempts.
- `load_session_state` returns None for a missing or corrupt file (the caller starts a new provider session).

## Known limits
- Health states `missing` and `signed_out` come from fresh caches only; `state()` never probes. Time-based expiry raises no event: the router compares states itself.
- `MemoryUsageSink` does not de-duplicate on `(task_id, call_ref)`; only the server's `UsageStore` does.

## Follow-ups for other packages
- CN-3/CN-4: use `usage_from_*`, `cumulative_delta`, `cost_delta`, `save_session_state`; `CLAUDE_CLI_MODEL` / `SUTRA_CLAUDE_MODEL` overrides of the model are NOT applied in `policy.py`.
- CN-7: build rows only with `build_usage_row`, publish `connector.health` from `HealthBook.state` changes, use `policy.resolve(req)` and `Resolved.retry_delay`.
- ORCH-3: `UsageStore` implements `UsageSink.record(row: UsageIn) -> int`; `UsageIn` has no `at` (that is `UsageOut`).
