# Architecture: A new run in a team starts clean unless the chat agent decides it continues an earlier run
Task: sut-26-context (SUT-26)   |   Spec: `spec.md` (Refined)   |   Date: 2026-11-26

## Context
Team-chat follow-ups (`TaskService._deliver` → `_follow_up`, `orchestrator/tasks.py:915-1052`) pick the seed by recency and the framing from any orphan question, with no agent involved (spec C-2, C-4). Every engine-side carrier of earlier context keys on `task.seed_from` (C-10), so a correct `seed_from`, parent, framing and `user_text` written before `task.json` fixes the whole path without touching the engine host, `rehydrate.py`, `capabilities/*` or J2. The org-chat path already asks the chat agent for `follows` (`agent/runner.py:707-729`). The engine's `/api/say` calls `deliver_to_department` in a worker thread (`engine/api/commands.py:207-208`), and `TaskService._run_async` (`tasks.py:487-497`) already drives a coroutine from such a thread.

## Approach
1. Before the write transaction, `_deliver` checks read-only whether this line will become a follow-up (team active, no live, queued or blocked task, not an override, not `answer_only`). If so, it lists the candidates: the team's newest 5 ended tasks with a run folder after the reset marker, each with its stored brief (`user_text`) and its own newest open question. No candidates: no call, clean start.
2. It asks the chat agent once through a new narrow stage, `ChatAgent.follows`: a small template `follows.md`, the existing `_stage` loop with `attempts=1`, the existing `chat_turn`/`assignments` reply schema, and it reads `assignments[0].follows`. Any failure or exception → `None`.
3. Inside the transaction the existing branches run unchanged. In the follow-up branch, `_follow_up` re-lists the candidates and accepts the pick only if it is still one. Pick → seed = its run, parent = it, framing = its newest open question, its open questions are marked answered; when it ended stopped, crashed or cancelled, `user_text` = its brief + the owner's words. No pick → clean.
4. The owner's chat line stays the owner's words. One sentence on when to set `follows` goes into `decide.md` and `assign.md`.

## Alternatives considered
| # | Alternative | Why rejected |
|---|---|---|
| A-1 | Run the full `decide` stage for team-chat lines (Q-1 option "existing call") | It also decides intent, chart changes and teams, sees the whole chart (6,000-char digest), and can retry 3 times (`ports.py` `ATTEMPTS`, `MAX_CALLS`): a team chat must not add teams, and NFR-1 allows 1 call. The narrow stage reuses the same agent, loop, redaction and reply schema. |
| A-2 | Let J2's Identity decide in its first turn | Needs a J2 patch; rehydrate must happen before any line is posted (`rehydrate.py:385-389`), so the decision would come too late. Rejected by owner Q-5 too. |
| A-3 | A new reply family `follow_pick {follows}` | Cleaner schema, but a new registered record (`library` registry, gate, transport schema tests) for one field. The `assignments` schema already carries a validated `follows` (`replies.py:109`); the extra fields the model fills (title, brief) are ignored. |
| A-4 | Build the combined brief for every seed, including finished ones | The rehydrated run already records the seed's brief (`rehydrate.py:400`); the old brief would also land in `change_requests` and break the change-request flow tested at `tests/e2e/test_scenario_followup.py:123,162`. |
| A-5 | Read the seed's brief from its `summary.json` | A file read per candidate; absent for crashed runs; the same text as the task row for every run J2 recorded from it. FR-11 uses `tasks.user_text`. |

## Components
| File | Change | New / changed |
|---|---|---|
| `sutra_app/orchestrator/agent/templates/follows.md` | the narrow decision prompt (placeholders `dept`, `runs`, `message`, `schema`) | new |
| `sutra_app/orchestrator/agent/templates/decide.md`, `assign.md` | FR-5 sentence after "`follows` only with a task id listed for that team" | changed |
| `sutra_app/orchestrator/agent/prompts.py` | `"follows"` in `TEMPLATES` and `PLACEHOLDERS`; `run_lines(runs)` renders and clips the candidates | changed |
| `sutra_app/orchestrator/agent/agent.py` | `ChatAgent.follows(...)`; `_stage(..., context=None)` override of the call context | changed |
| `sutra_app/orchestrator/tasks.py` | `TaskService.follows_of` hook; `_open_questions`, `_candidates`, `_pick_follows`; `_deliver` calls the pick before the transaction; `_follow_up(..., pick)` rewritten; `_answer` uses `_open_questions`; `CONTINUES` text constant | changed |
| `sutra_app/orchestrator/wiring.py` | `tasks.follows_of = agent.follows` after the agent is built (`wiring.py:194`) | changed (1 line) |
| `docs/DECISIONS.md`, `docs/diagram/decisions.json` | D454 | changed |
| `docs/design/orchestrator.md` | :398 (decide text copy) and :421 (follow-up rule) follow the new behaviour | changed |

Untouched: `engine/host/loop.py`, `engine/rehydrate.py`, `capabilities/*`, `engine/j2.py`, `scripts/vendor_j2.py`, `scripts/port_j2_ui.py`, `run_inputs.py`, `chart_rules.py`, page files. No P47, no E33.

## Data model
No schema change, no migration. Rows written as before; values change:

| Field | Before | After |
|---|---|---|
| `tasks.settings_json._seed_from` / `task.json.seed_from` | newest run with a folder | the picked candidate's run, else empty |
| `tasks.parent_task_id` / `task.json.parent_run_id` | team's latest task | the picked candidate, else empty |
| `tasks.framing` | newest orphan question of any ended task | the picked task's newest open question, else empty |
| `tasks.user_text` | owner's words | owner's words; for a stopped, crashed or cancelled pick: `CONTINUES.format(brief=clip(seed.user_text, 20_000), words=owner's words)` |
| `chat_messages.answered_by` | the one orphan question | every open question of the picked task; none on a clean start |

`CONTINUES = "{brief}\n\nThe owner now writes: {words}"` (tasks.py constant). Task title stays `one_line_title(user_text)` (`_insert`), so a combined task is titled by the earlier brief's first line.

## Interfaces
```python
# sutra_app/orchestrator/agent/agent.py
class ChatAgent:
    async def follows(self, dept_id: str, text: str, runs: Sequence[tuple[str, str, str, str, str]]) -> str | None:
        """runs: (task_id, title, status, brief, open question or "") newest first. One call (attempts=1), step "follows",
        schema REGISTRY.transport_schema("chat_turn", kind="assignments"). Returns assignments[0].follows (unchecked: the
        caller re-validates), None on StageFailed. Other exceptions propagate."""

    async def _stage(self, stage, family, kind, prompt, schema, request, budget, build, attempts=None,
                     context: Mapping[str, str] | None = None) -> Any:   # context None -> call_context(request...) as today

# follows: request = PlanRequest(text=text, message_id=0) (only used for cancel=None); context =
#   {"purpose": "chat_plan", "session_id": ORG_SESSION_ID, "node_id": ROOT_NODE_ID, "atom_id": overhead_atom_id(f"follows-{dept_id}")}

# sutra_app/orchestrator/agent/prompts.py
def run_lines(runs: Sequence[tuple[str, str, str, str, str]], *, width: int = 1000) -> str:
    """'- <id> | <title> | <status>\n  brief: <clipped>\n  open question: <clipped or ->' per run; '(none)' when empty."""

# sutra_app/orchestrator/tasks.py  (TaskService)
follows_of: Callable[[str, str, Sequence[tuple[str, str, str, str, str]]], Awaitable[str | None]] | None = None
    # set by wiring; None (tests that do not set it) => every follow-up starts clean
def _open_questions(self, conn, sid: str, task_id: str) -> list[sqlite3.Row]       # id, text; unanswered, oldest first
def _candidates(self, conn, dept_id: str, sid: str) -> list[tuple[TaskRow, str]]    # newest 5 ended, folder, after marker; (row, newest open question text or "")
def _pick_follows(self, dept_id: str, said: str) -> str | None                      # outside any transaction; never raises for model trouble
def _follow_up(self, tx, dept_id, sid, body, scope_id, settings, input_files=(), pick: str | None = None) -> Delivery
```
`_pick_follows` returns None without a call when: `follows_of` is None, the team is missing or hidden, a live task exists, a queued or blocked task exists, or `_candidates` is empty. It wraps the call in `try/except Exception` (log at info, return None) and runs it with `self._run_async(lambda: self.follows_of(dept_id, said, runs))`.

`follows.md` text (developer may adjust wording, not meaning):
```
You are the chat agent of one organisation. The owner wrote in the chat of the team {dept}. RUNS lists that team's earlier runs, newest first, each with the brief it worked on and the question it left open. Decide whether the owner's words continue ONE of those runs or answer its open question. Set `follows` to that run's task id only when they do; when you are not sure, or the words are a new request, leave `follows` empty: the team then starts a new run. Write exactly one assignment with ref a1 and dept {dept}; its title and brief are not shown to anyone.
RUNS:
{runs}
OWNER WORDS:
{message}
SCHEMA:
{schema}
Answer with ONE JSON object that matches SCHEMA.
```
FR-5 sentence for `decide.md` and `assign.md`: "`follows` only with a task id listed for that team, and only when the owner's words continue that task's run or answer its question; when not sure, leave it empty".

## Sequence diagrams
```mermaid
sequenceDiagram
    participant O as Owner (team chat)
    participant E as engine /api/say (worker thread)
    participant T as TaskService
    participant A as ChatAgent.follows
    participant M as model (connector)
    participant DB as database
    O->>E: words
    E->>T: deliver_to_department(dept, words)
    T->>DB: read: team, live, queued/blocked, candidates (no tx)
    alt follow-up and >=1 candidate
        T->>A: _run_async(follows(dept, words, runs))
        A->>M: one call, step "follows"
        M-->>A: {assignments:[{follows: id|null}]}
        A-->>T: id | None (any error -> None)
    end
    T->>DB: write tx: re-check branches (answer / Busy / follow-up)
    alt follow-up
        T->>DB: re-list candidates; pick valid? seed+parent+framing(+combined user_text) : clean
        T->>DB: insert task, post owner's words, mark the seed's questions answered
    end
    T-->>E: Delivery(follow_up)
    T->>T: kick() -> _begin writes task.json (seed_from, framing, user_text)
```

## Cross-cutting
| Concern | Design |
|---|---|
| Errors | Every model trouble (connector failure, timeout, bad output, a test double's own exception) → clean start (FR-3). Re-validation in the transaction makes a stale or foreign id harmless. |
| Concurrency | The call is outside the transaction (NFR-8). A second line during the call: the first creates a queued task, the second's transaction sees it → Busy (`tasks.py:951-952`). A team that became live during the call: the existing answer/Busy branches win; the pick is dropped. |
| Logging | `log.info` when the pick call fails, with the exception class only (no owner words). |
| Security / privacy | The prompt goes through `ChatAgent._redact` (`agent.py` `_stage`); owner words are already `clean`ed (`tasks.py` `_deliver`). Only titles, statuses, briefs and question texts go in; no files. |
| Performance | One call per team-chat follow-up with an earlier run; owner's line is stored after it (R-3). Candidate listing is one indexed query plus at most 5 question lookups and folder checks. |
| Config | None new. Timeout = `settings.chat_timeout` via the agent. |
| Backward compatibility | Old rows and folders unchanged; `task.json` layout unchanged (NFR-7). Old open questions stay open and become framing only if their run is picked. |

## Rollout and rollback
Ships with the next beta/release; no flag (the owner asked for the behaviour). Rollback = revert the commits; no data to migrate either way (tasks made under the new rule are ordinary rows).

## Test strategy
| Level | File | Covers |
|---|---|---|
| unit (prompts, agent) | `tests/orchestrator/test_chat_agent.py` | template placeholders (existing test picks up `follows`), FR-5 text in three templates (AC-7), `run_lines` clipping and the 5 cap (AC-6 rendering), `ChatAgent.follows` with `ScriptedConnector`: returns the id, returns None for no follows and for bad output, makes exactly 1 call, step `follows` |
| unit (service) | `tests/orchestrator/test_tasks.py` with a fake `follows_of` | AC-1 to AC-6, AC-10 to AC-14; updated :387, :403, :444, :478, :485, :519 |
| integration (wired app, real engine in mock mode) | `tests/e2e/test_scenario_followup.py`, `tests/e2e/test_scenario_restart_stop.py` | AC-8 (Stop and app close: `user_text`, `summary.json` brief, chat line, byte-identical old folder), AC-9 (rehydrated brief equals the seed's, words in `change_requests`, old folder byte-identical), wiring of `follows_of` |
| records | `tests/test_diagram_decisions.py`, `tests/test_ownership.py` | AC-15, NFR-6 |
| goldens | `tests/orchestrator/test_run_spec_golden.py`, `test_project_context_golden.py` | NFR-7 (must pass unchanged) |

## Traceability
| Requirement | Component | Test |
|---|---|---|
| FR-1 | `_pick_follows`, `ChatAgent.follows` | test_tasks AC-1, AC-3 |
| FR-2 | `_follow_up` re-validation | test_tasks AC-3, AC-2 (foreign id) |
| FR-3 | `_pick_follows` try/except, `_follow_up` clean branch | test_tasks AC-1, AC-2 |
| FR-4 | `_candidates`, `prompts.run_lines`, `follows.md` | test_tasks AC-6; test_chat_agent run_lines |
| FR-5 | `follows.md`, `decide.md`, `assign.md` | test_chat_agent AC-7 |
| FR-6 | `_follow_up` framing | test_tasks AC-4, AC-5 |
| FR-7 | `_follow_up` marking via `_open_questions` | test_tasks AC-4, AC-5, :485 |
| FR-8 | `_candidates` (ended statuses) | test_tasks AC-4, :519 |
| FR-9 | `CONTINUES` in `_follow_up` | test_tasks :519, AC-3; e2e AC-8 |
| FR-10 | rehydrate unchanged + FR-9 | e2e AC-8, AC-9 |
| FR-11 | `_candidates` brief = `user_text` | test_tasks AC-10 |
| FR-12 | no engine change | e2e AC-8, AC-9 (`tree_sha`) |
| FR-13 | `_candidates` marker filter | test_tasks AC-11, :431, :444, :478 |
| FR-14 | `_pick_follows` early return | test_tasks AC-11, AC-12 |
| FR-15 | `_follow_up` posts `body` | test_tasks :519; e2e AC-8 |
| FR-16 | DECISIONS.md, decisions.json | test_diagram_decisions (AC-15) |
| NFR-1 | `attempts=1`; early returns | test_tasks AC-2, AC-12, AC-13; test_chat_agent one call |
| NFR-2 | try/except, agent timeout | test_tasks AC-2 |
| NFR-3 | no rule code | review; T7 grep |
| NFR-4 | orchestrator-only change | T7 diff stat report |
| NFR-5 | `run_lines` width, 5 cap | test_chat_agent; test_tasks AC-6 |
| NFR-6 | synthetic fixtures | test_ownership |
| NFR-7 | no `RunSpec` change | run-spec goldens |
| NFR-8 | call before `db.tx()` | test_tasks AC-14 |

## Decisions
**D-1 Narrow chat-agent stage for team-chat follow-ups.** Context: owner decision 1 (the chat agent decides), NFR-1 (1 call), a team chat must not change the chart. Decision: `ChatAgent.follows`, own template, existing `_stage`, `attempts=1`, existing `chat_turn`/`assignments` schema. Consequences: no new reply family; the model writes a throwaway title and brief (a few dozen tokens); usage is booked under the chat agent with key `follows-<dept>`.

**D-2 Decide outside the transaction, validate inside.** Context: owner Q-2; SQLite write transactions must stay short. Decision: `_pick_follows` before `db.tx()`, candidates re-listed in `_follow_up`. Consequences: a race costs at most one wasted call; the result is always a candidate at write time.

**D-3 Combined brief only for a stopped, crashed or cancelled seed.** Context: FR-9, FR-10, owner Q-5; J2 records its first owner line as the brief when it starts fresh, and keeps the seed's brief when it rehydrates. Decision: `user_text = CONTINUES(...)` for `BAD_END` seeds, owner's words otherwise. Consequences: no J2 patch; change requests stay clean; R-6 (a done seed that rehydrate refuses) keeps today's loss, with the brief in `upstream/`.

**D-4 Seed brief from `tasks.user_text`.** Context: FR-11. Decision: no `summary.json` read. Consequences: chains keep the first brief (it is inside each combined `user_text`); clip at 20,000 bounds growth.

**D-5 Clean start closes no question.** Context: owner decision 2, FR-7. Consequences: Needs-you keeps old questions (Q-10, R-8), today's reset-path closing (`tasks.py:1050-1051` via `test_tasks.py:485`) goes away.

Recorded for the repo as D454 (amends D21).

## Risks
| # | Risk | Mitigation |
|---|---|---|
| R-1 | D451 memory still carries unrelated earlier requests | Owner decision; unchanged. |
| R-2 | Kaivan's `_seed_output`/`followup` ticket touches the same seeded path | Different files (`loop.py`, `select.py`); merge order to agree; this change only makes `seed_from` empty more often. |
| R-3 | Latency before the owner's line shows | Beta check (T8); the timeout bounds it. |
| R-4 | Wrong continue / missed continue | Prompt carries each run's own question; clean is the default. |
| R-5 | `remove-real-run-gates` / `live-view` land first and move code | Plan T0 rebases and re-checks names, not line numbers; none of the touched files is in J2. |
| R-6 | Refused done seed loses the brief | Rare; brief in `upstream/<id>/summary.json`. |
| R-7 | Tests and the offline demo with no scripted reply start follow-ups clean | Plan T4, T5 push replies where a test means a continuation. |
| R-8 | Old questions linger in Needs-you | Q-10 to the owner. |
