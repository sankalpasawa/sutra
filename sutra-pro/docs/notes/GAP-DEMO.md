# GAP-DEMO: as-built notes (offline demo, D97)

## What was built
- `sutra_app/orchestrator/agent/demo.py` (about 140 lines): `demo_book()`, a `DemoBook` with one entry per chat-agent stage, keyed
  `("chat_agent", "decide" | "change" | "assign")`. Replies are built with the closed library models (`ChatDecision`,
  `ChartChangeRequest` + `AddOp` + `NewNode`, `AssignmentPlan` + `AssignmentDraft`) and dumped to JSON; nothing is invented.
- decide: the department of the digest sharing most words with the message (name or goal) is reused (ties: the exact topic name,
  then the newest), else `add`. change: one `AddOp` under the root named from the first 2 to 4 meaningful words (one word gets
  "Team", none gives "General Team"), goal = the message cut to 120 characters (what the digest shows). assign: one assignment,
  title and brief from the message, target = the best department of "CHART AFTER THE CHANGE", i.e. the one just added.
- retry needs no entry: the agent asks the same stage again with the retry text appended, so the same prompt parts give the same reply.
- `factory.build_router(..., replybook=None)` hands the book to the stub of a stub-only router; `wiring.build_services` passes
  `demo_book()` only when `settings.offline` is true. `SUTRA_CONNECTOR=stub` alone, injected connectors and all older tests keep the plain stub.
- The engine's own calls are untouched (engine mock mode, `ScriptedPort`).

## Deviations and decisions
- A `ReplyBook` reply takes no arguments, so it cannot see the prompt. `DemoStub(StubConnector)` overrides the private hook
  `_resolve` only to put `plan.prompt` in a ContextVar; the book names it as `connector_class` and the factory builds
  `getattr(replybook, "connector_class", StubConnector)(cfg, book=replybook)`. `stub.py` is not touched (not owned).
- The prompt is read with three regexes (`OWNER REQUEST:`, `CHART ...:` and `Root id:`). A prompt without `OWNER REQUEST:` raises ValueError.
- Word matching uses `STOP_WORDS` of `textutil`; "team" and "general" (words this module adds) never count as a keyword.
- Riders: no existing test of `factory.py` or `wiring.py` had to change; none was weakened. New factory/wiring tests are in `test_agent_demo.py`.
- Tests: 24 unit tests, 3 integration tests (FakeLauncher x2, and one with the REAL engine process, about 2 s, which is cheap enough).

## What offline can and cannot do
- Can: create and reuse teams from the message, run J2's mock scenario in the real engine (Identity asks its questions in the team's
  chat; one answer lets the run end Done), show graph, five function nodes, atoms and a finished run. All usage rows are `stub`, `scripted`, usd 0.
- Cannot: no Claude, no Codex; real reasoning, rearranging (move, merge, split, rename) and status or small talk are not understood:
  every message is a new task for one team. The Test, sign-in and "check connectors" buttons answer 409 `offline` ("not available while the
  app runs offline"). Team names are the message's first words, not a thoughtful label.

## Known limits and follow-ups
- Two messages that share one common word (for example "website") land in the same team, as specified.
- The names `Track Sales Leads Quotes`-style are literal; a nicer topic extractor would need a model.
- Follow-up for the scheduler: the install smoke test (D88) can now post a message with `--offline` and wait for `waiting_user`.
- Mutation self-check: 14 mutants of demo.py, factory.py and wiring.py; 2 survived the first run (goal cut, topic-name tie-break), tests added, all 14 killed.
