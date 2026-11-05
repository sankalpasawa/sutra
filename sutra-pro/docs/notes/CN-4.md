# CN-4 as built: CodexConnector

## Built
- `sutra_app/connectors/codex.py`: `CodexConnector` (subclass of the CN-3 base), `CodexParser`, `CODEX_ERROR_MAP` (rows X1-X18 as data, `X18` maps to `"ok"`),
  `CodexSignIn` (the device-flow handle), `parse_device_auth`, `parse_reset_time`, `quota_from_rate_limits`, `API_KEY_REFUSED`.
- Tests: `test_codex_parse.py` (parser on the fixtures, delta usage 12,174 / 10,368 cached / 5, helpers), `test_codex_connector.py` (argv goldens for exec, resume,
  tools, schema, images; login pre-check; catalog; effort clamp; rollout quota; sign-in; stop; flags), `test_codex_errors.py` (one case per row, meta-test against the design
  table and the fake's rows, parser-level message cases). About 125 tests, under 25 s.
- Mutation self-check, one pass: 19 breakages in a /tmp copy (401 streak size and reset, delta rule, `--ephemeral`, system-text-once, rollout reset fallback, poll throttle,
  effort clamp, API-key refusal, signed-out check, warning threshold, replacement model, last-rollout-line, parser stop, partials, auth-cache drop, thread-lost rule, resume sandbox flag).
  1 survived (the rollout reader took the first `token_count` line, not the last); a test was added and now kills it. No second round.

## Deviations from the specification
1. Images: one `-i <png>` per file, placed BEFORE `-m` (the spec puts them last). `exec --help` shows `-i <FILE>...` as variadic, so a following `-` could be read as an image.
2. The reply is the last NON-BLANK `agent_message` (spec: the last one); a turn that completed counts even when the exit code is bad.
3. `begin_sign_in()` returns a `CodexSignIn` (`.as_dict()` is `{id, url, code, expires_in}`); polling is `sign_in_poll(id)` and `cancel_sign_in(id)` on the connector (5.6 only fixed the routes).
   A cancelled sign-in reports `failed` with reason `cancelled`.
4. `CodexConnector(..., rates=, sandbox=)`: `rates` is the policy's `rates["codex"]` (slug -> `Rate`), `sandbox` is `read-only` or `workspace-write` (anything else is refused).
5. `_precheck` (login status, cached 30 s) also refuses `billing api_key` with the D7 text as `not_signed_in`: a second line of defence behind the Router's plan-time drop.

## Decisions
- `partials` is always off (capability `partials=False`; `call_text` and `stream` ignore the flag): Codex prints no deltas, so an idle deadline would kill a long silent generation.
- The system text goes in the prompt (`<system>...</system>`) on the first turn of a thread only; the thread keeps it. One-shot calls always carry it.
- Unknown slug: replaced by the first `visibility list` model, a `notice` event comes before the first stream event. A catalog that cannot be read leaves the slug alone (the spawn then fails normally);
  a failed read is retried after 60 s, a good one after 1 h. Effort is clamped to the highest supported level not above it, else the lowest; also a `notice`.
- X5: the parser stops the process itself (`proc.cancel()`, handed over by `_track`) after two 401 `error` events in a row; `_has_code` matches `401` only as a word of its own (request ids).
- X6 reset time: "try again at <date time>" (local time), else the rollout's `resets_at` when its window is exhausted, else None (HealthBook then cools down 30 min).
- Quota from the rollout: `used` is a fraction, `warning` from 80 %, `exhausted` at 100 % or when `rate_limit_reached_type` is set; the fuller of primary and secondary is shown.
  It is also forwarded to `hooks.on_quota` and as a `quota` event after the last stream event. `AuthStatus.plan` is the last plan the rollout named.
- A second `begin_sign_in` cancels a pending one. `begin_sign_in` waits at most 20 s for link and code. A poll that finds `login status` signed in ends the child.
- `forget_command` is `codex delete <thread>` (only for a valid thread id).

## Known limits
- `--ephemeral` one-shot calls leave no rollout, so only chat turns carry a `Quota`.
- A sign-in poll reports success when `login status` is signed in, also if the owner was already signed in before the flow began.
- UNVERIFIED live: native schema against the real API, `-i` images, MCP tool calls, the API-key status wording, `codex delete` without a prompt, reset-time wording other than the dated form.
- `CallInfo.effort` shows the requested effort, not the clamped one. POSIX only.

## Follow-ups for other packages
- CN-7 Router: set `connector.rates` from the policy; call `begin_sign_in`/`sign_in_poll`/`cancel_sign_in` from CN-9's routes; drop a provider whose `AuthStatus.billing == "api_key"` at plan time.
- CN-8: override `CodexConnector.mcp_servers(tools)` (a minimal adapter now; the `SUTRA_DB_RO` path `<data_dir>/sutra.db` is ASSUMED, as in CN-3).
