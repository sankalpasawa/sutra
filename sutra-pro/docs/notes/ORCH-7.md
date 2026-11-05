# ORCH-7 as built: chat agent, turn runner, prompts, agent routes

Built: `orchestrator/agent/{ports,replies,prompts,planner,agent,runner}.py` + `templates/{decide,change,assign,retry}.md`, `api/agent.py`,
`testing/scripted.py`. Tests: `test_chat_agent.py` (holds `AgentEnv` and the reply builders), `test_turn_runner.py` (`RunnerEnv`),
`test_api_agent.py`, `live/test_live_chat_agent.py` (skipped without SUTRA_LIVE): 124 tests, about 5 s.
`ChatAgent.plan/resume/choice_plan` do stages A, B, C with 3 attempts each and 6 calls per request; `TurnRunner` queues one turn at a
time (5 may wait, the next is 429) and runs T0 to T9. Every Sutra line is in `planner.LINES`; `matches_template` is what the no-prose test uses.

## Deviations from the specification
- Reply classes: `kind` is required in the transport schema (one-value enum), only `schema_version` is optional. `AssignmentPlan.to_task_workflow`
  puts dependencies BEFORE their dependants (the library workflow refuses a forward `depends_on`); the draft order is kept where allowed.
- `chat.turn` data is `{session_id, turn, message_id, phase, detail}` (`turn` = the request's message id; the UI reads `turn`, `phase`, `detail`),
  phase `error` ends a failed turn. One `planning` event per turn, not per stage.
- Extra Sutra lines the design does not list, all fixed code text: `add_only` (a team without work), `rename`, `purpose`, `declined`, `already`,
  `rejected {reason}`, `busy` (the rules' own sentence), `no_connector`, `stale`, `save_failed`, `task_failed`, `failed`, the greeting (ORCH-5's).
  A change with several ops posts ONE line of sentences joined by a space.
- `ChatStore` has no way to change a message's `state`; the runner runs `UPDATE chat_messages SET state` itself (and re-emits `chat.message`).
- The decision route `POST /api/chart/changes/{id}/decision` also exists in `api/chart.py` (ORCH-5). Mine goes through the runner (it must finish the
  request); the chart router's only decides. The agent router must be included FIRST (tested in `test_api_agent.py`).
- Usage rows: none from the runner (the router's sink writes them). `ScriptedConnector(sink=UsageStore.record)` emulates it for the ledger invariants.

## Decisions
- `change: none` with assignments is logged as a `reuse` change of their teams (and scopes): every decision is a log row. `status`, `smalltalk`, `clarify` log none.
- Stage C runs BEFORE the apply (against the dry-run chart after stage B, with the ids the store will really give); with an approval pending it
  runs after the yes (`resume`). The plan to resume is kept in `chart_changes.plan_json` `{v, message_id, text, decision, keywords}`.
- A card button is stored as the owner's line with the option's label; `src_ref` `choice:<card id>` makes a second click a 409 `already_decided`;
  a `choice` card carries `src_ref` `req:<message id>:choice`. Picking a team builds a reuse change and one assignment from the original words (no model call);
  "None of these" gets the smalltalk line. A bare yes/no answers a change only when exactly one waits; the preflight is skipped for answers and clicks.
- Candidates for a `choice` card: the named ids, then departments by word overlap. A division is reused through its department with `scope`.
- The owner's text is redacted before it is stored, shown to the model or given to a task. A `follows` that cannot be continued (no run yet) is dropped.
- `ChartStore.apply` stale or a `rules` error at apply: plan again once, then F4. `busy` is not retried. `TaskService.create` failure ends the turn
  with an error line (tasks made before it stay). A failed apply is F5. Anything unexpected is a `failed` line and the queue goes on.

## Known limits and follow-ups
- ORCH-8: import `agent.replies` before `REGISTRY.freeze()`; build `TurnRunner(publish=bus.publish_one, redact=..., connector=AsyncConnector)` into `Services.runner`;
  include `api.agent.router` before `api.chart.router`; `await runner.close()` at shutdown. ORCH-3: a `ChatStore.set_state` would replace the raw UPDATE.
- A retry of a failed card click re-runs its label as text. A turn that fails halfway through several tasks leaves the earlier ones; a retry would add them again.
- The live test shows the decision; reuse-versus-add quality is judged by reading it.

## Mutation check
24 hand-made mutants (budget bound, no-retry kinds, attempt number, keyword threshold and tie, clarify limit, cycle check, queue limit, the exactly-one-pending
rule twice, stale limit, stale/busy raising, dependency order, error kind, card ownership, stale at apply, read-only kinds, F5 branch, overhead key, node id, prompt placeholders,
approval stage C): 19 killed first; 5 survivors, 4 became tests (killed), 1 is equivalent (a function session is also `writable` false). No second round.
