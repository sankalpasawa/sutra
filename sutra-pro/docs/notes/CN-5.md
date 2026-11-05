# CN-5 as built: StubConnector and ReplyBook

## Built
- `sutra_app/connectors/stub.py`: `StubConnector(ModelConnector)`, `ReplyBook`, `StubCall` (call log for tests), constants `STUB_MODEL`, `CHUNKS`.
- The stub subclasses the CN-3 base and replaces only `_spawn` (no process): it keeps the one-shot calls, the JSON strategy and its repair
  rounds, chat sessions (work dir, `session.json`), `Hooks.before_call/after_call` around every call (a failed one included), `usage()`.
- Reply order (3.7): `scripted()`, ReplyBook `(fn, stage)`, `(fn, "*")`, `("*", "*")`, built-in (schema example as JSON, else `"[stub] "` + 60 chars).
- Numbers: provider `stub`, model `scripted`, usd 0.0, basis `none`, tokens = `len(system + prompt) // 4` in, `len(text) // 4` out (the twin
  `engine.llm.ScriptedPort` uses the same rule; one test compares them). `JsonResult.how` is always `stub`.
- `fail_next(code, times=1, message="", **kw)`, `calls`, `transcript(session_id)`, `stop(session)`, `delay` (default `STUDIO_MOCK_DELAY`).
- 56 tests in `tests/connectors/test_stub.py`, about 1 s. Mutation self-check, one pass: 20 breakages in a /tmp copy; 2 survived
  (resume id kept on an existing provider session: test added; a dead `repair` branch in the built-in `{}` rule: branch removed). No second round.

## Deviations from the specification
1. `scripted` is a keyword of `call_text` / `call_json_result` (not an `AskRequest` field): the base has no request object. CN-7 passes `req.scripted`.
2. A JSON request with no schema gets `{}` (the spec only names the text fallback; `"[stub] ..."` could never parse). The base returns that
   text unparsed when no schema is given.
3. `fail_next` refuses a code that is not a key of `ERROR_CLASSES` (ValueError) and a `times` that is not a positive int, instead of
   quietly raising a generic ProviderError: a typo in a Router test would otherwise pass for the wrong reason.
4. Tokens use floor division, not rounding: that is what `ScriptedPort` does and the twin test needs both to agree.

## Decisions
- `capabilities.native_schema` is True so the base hands the schema to the spawn; the stub also reads it from a ContextVar so a schema over
  100,000 characters, or `force_prompted` (the Router's `native_blocked`), still gets its example. ContextVars keep concurrent requests apart (tested).
- `resolve_model` always returns `scripted`: the policy's model names mean nothing to the stub and the usage row says `scripted`.
- Delay: 30 `text_delta` events (empty pieces skipped), each followed by a wait of `delay / 30`; no delay gives one `text_delta`. `text_delta`
  is always emitted, like `ScriptedPort`'s progress events (the CLIs send it only with partials). A final `text` event closes the reply.
- `stop(session)` ends a turn that is waiting out its delay (CallCancelledError, session untouched); one-shot calls have no key and cannot be stopped.
- The provider session id of a first chat turn is `uuid5(session_id)` (deterministic); an existing id is kept.
- A non-string `scripted()` result raises `TypeError("a scripted reply is text")`, as `ScriptedPort` does; the after_call record then says `cancelled`.
- Transcript holds user and assistant messages of finished turns; `start()` resets it, `forget()` drops it. A failed or stopped turn adds nothing.
- Empty replies are allowed (the stub never raises `empty_reply`; use `fail_next("empty_reply")`).

## Known limits
- `stub.py` imports nothing from the engine; the `STUDIO_MOCK_DELAY` cleaning rule is copied from `engine/llm.py` (5 lines).
- `duration_ms` is the injected clock's difference, so it is the one field that varies between two identical calls.

## Follow-ups for other packages
- CN-7: build the stub for `connector == "stub"` / `PortSpec.mock` with `StubConnector(cfg, book=..., delay=...)`; pass `scripted=req.scripted` to
  `call_text` / `call_json_result`; the stub's `after_call` record has `exit_code None`, `native_schema_sha None`, `cli_version None`.
- CN-7 / ENG: the stub-vs-`ScriptedPort` twin assertion set can use `StubConnector.calls` (rule per call) and `transcript()`.
