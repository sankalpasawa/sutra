# J2 sync 4, lane C as built: the ask port (a function's answer is a turn of its own agent session)

Built (design 3.4 and 3.5; D147 to D149; owner rule R2). Source: `connectors/models.py` (`RouteContext.pick`), `connectors/router.py` (`PICK_PURPOSES` gains `agent_chat`, `_pick_for`,
`_plan`), `orchestrator/agent_ask.py` (new: `AgentAsk`, `AskTurn`), `orchestrator/chats.py` and `models.py` (`ChatMessageOut.ask`, `_ask_of`, `ASK_REF`),
`orchestrator/wiring.py` (`AppServices.agent_chat`, filled in `build_services` only). Tests: `tests/connectors/test_router_pick.py` (49, 18 new rows), `tests/orchestrator/test_agent_ask.py`
(40, new), `tests/orchestrator/test_chats.py` (28, new), `tests/integration/test_agent_ask_e2e.py` (11, new, after lane B). Commits: C1 `fdb462de`, C3 `ac0265ca`, C2 `cd92bc4c`, C4 `2824d5ac`
(with a WIP commit and the merges of lanes A and B between them).

How a question runs: `turn(dept, run, agent)` is None unless the agent is one of the five functions and has a session stamped with that run (an archived one counts); `begin` stores the owner's
line (scrubbed, `ask:<id>`) and takes the session's one-question mark; `ask` is J2's callable as ONE `Router.ask` of that session: the pick of its own cascade in `RouteContext.pick`
(own, run, team; `default` passes none), the user text through the egress in replace mode and the app's secrets, 2 calls, $0.25, 120 s, purpose `agent_chat`, the run's overhead atom;
`end` stores the agent's line (`ask:<id>:records` or `:model`) once and always releases the mark. `can_ask` is False, with the sentence the owner reads, offline (including `SUTRA_CONNECTOR=stub`),
with no router or chat port, and under the owner's limit (the gate's own words); `ask` then refuses without a call. Every failure of the model side is an `AskFailed`, and only that.

## Measured
- Lane suites, run once, serially, on the merged tree (A2, B1 to B4 part 1 and this lane): `tests/connectors` green (2 min 8 s), `tests/orchestrator` green (1 min 5 s), `tests/integration` green (19 s).
- The end-to-end file (a real mock team run, the real router over the fake `claude` and `codex`, 11 tests): about 7 s. What the real call carried: `--model sonnet --effort low --max-budget-usd 0.25`
  for a function with no pick; `--model haiku --effort low` for Audit after its pill was set; J2's own system prompt and records (`YOUR RECORDS ... QUESTION`) on stdin; one ledger row each with the session,
  node, function, purpose `agent_chat`, task, team and the run's overhead atom (0.01 usd, 120 in, 30 out under the fake); a failed question books `ok = 0` with both attempts (claude quota, then codex quota).
- A pasted credential and an app secret never reach the model: checked on the stub's prompt and system text, and on the stdin and argv of the real connector over the fake CLI; the egress audit row of the
  question is in replace mode and names shapes and counts only.
- Known reds on this tree that are not lane C's: `tests/test_traceability.py` (37 handlers against its 30: lane G3 regenerates) and two tests of `tests/contracts/test_contract_route_table.py` (the page's J2 path
  list in `sutra_ctx.js`: lanes B4 and E).

## Deviations from the design, and why
- `AgentAsk.__init__` has one more optional keyword, `clock` (the services clock, which the owner's limit is read against); the wiring passes it. Without it the system clock is used.
- The design says the text goes through `scrubbed(text, redact)` with "audit row in replace mode"; `scrubbed` writes no audit row (only `Egress.check` does). The user text (the records and the question)
  therefore goes through the router's egress in replace mode first (the audit row, which also replaces the app's secret values), then through `scrubbed`, so a router with no egress is no gap. The system text
  (J2's fixed words) goes through `scrubbed` only. The stored question and answer lines are scrubbed too.
- `ASK_REF` is defined in `chats.py` beside `STEER_REF` (the store needs it for `_ask_of`) and re-exported by `agent_ask.py`; the other way round would be an import cycle.
- `AskFailed` is imported where it is raised (`_failed`), not at the top: `engine/api/__init__` imports J2, and the orchestrator must not load it at import time of `wiring`.
- `turn(dept, None, agent)` is None (a run that names nothing is not a run of the team); it does not fall back to the live run: `DeptCommands.ask` resolves the run itself.
- A model that answers with no text is an `AskFailed("the model returned no text")`: otherwise J2's `answer` would return its records text labelled `model`.
- `connector.choice_unavailable` for a pick that cannot run now carries the call's session id (it was always `None`: only the engine's calls reached that branch and they have no session); engine calls still send `None`.
- `begin` refuses an empty question with a `validation` error (the route never sends one) and `end` stores nothing for an empty answer; `AgentAsk.asking(session_id)` is a small public read of the busy mark, used by the tests.
- The question token is random (12 hex digits) unless `ids` is given, then it is the hex part of `ids.session_id()` (deterministic under `FakeIds`); the wiring does not pass `ids`.
- The end-to-end file lives where the design puts it (`tests/integration`) and imports the harness of `tests/e2e` by path; it is skipped on Windows like that suite (a real engine process and the fake CLIs are POSIX, D104).

## Left, for others
- Lane G: `docs/design/orchestrator.md` (agent_ask), `connectors.md` (`RouteContext.pick`, `agent_chat` in `PICK_PURPOSES`, the session id in the pick-miss event), the D147 to D149 texts and pills, `traceability`.
- Lane E: `ChatMessageOut.ask` is on the wire (`q`, `records`, `model`) and in the `chat.message` event payload; the node panel's Ask mode and J2's `function_chat.js` read it.
- `scripts/live_smoke.py --scenario ask` (design 6.3 names it) has no owner in 5.2 or 5.3 (lane D4 lists `late-judge` only).
- Not done, by the design (7.4): asking a workflow builder or the validator (the same port serves a builder's step session once J2's `answer` covers builders), live typing of an answer, server-side repair of an
  interrupted question (the question line stays without an answer line; J2's panel says "No answer was stored.").
