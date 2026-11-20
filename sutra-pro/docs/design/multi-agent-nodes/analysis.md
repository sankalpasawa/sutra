# Multi-agent nodes: why it does not work today

Status: analysis, 2026-11-20. Design only. Paths are relative to `sutra-pro/`.
"Fact" means it was read in the code on `main`. "H" means it was reasoned from the code and not run.
In these documents "node" alone means a runtime node (a running agent). A "graph node" is a box in the app's graph, which already exists.

**Short answer.** Sutra Pro already runs things in parallel, but only one team run per process. A team run is one `tasks` row, one folder `runs/<run_id>`, and one `python -m sutra_app.engine` process. Every agent the owner names lives inside that process, or inside the server, as a function name in a tag. Five things are missing:
1. A node identity.
2. A second worker in one team.
3. A project around the nodes.
4. Limits that span processes.
5. A permission layer between roles.

## Findings

- **F1. One live task per team (blocker).**
  - Fact: `sutra_app/orchestrator/schema.py:70` has `UNIQUE INDEX tasks_one_live_per_dept ON tasks(dept_id) WHERE status IN ('starting','running','waiting_user')`.
  - Fact: `tasks.py` `_prepare_next` (line 622) and `waiting.py` `why_waiting` (line 41) answer "team busy".
  - Fact: `live_in`, `deliver_to_department` and `stop_live` assume the same one-live-task rule.
- **F2. Inside a run, the agents are one thread (blocker).**
  - Fact: `sutra_app/engine/j2.py:4825` `_run_safe` holds `with self.lock` for the whole run, and builders run one after another.
  - Fact: line 4690 `user_says` (patch P4) returns False while a run is in flight.
  - Fact: there is no thread pool in `j2.py`. J2's own `depends_on` is for prompts and display, not scheduling.
  - Fact: the engine is vendored and frozen (D13, D249).
- **F3. No node identity (blocker).**
  - Fact: `engine/port.py` `CallTag` (line 23) has `run_id`, `dept_id`, `task_id`, `function` and others, but no node or project id.
  - Fact: permission comes from a table keyed on the function name string, in `engine/capabilities/workspace.py` `workspace_for`.
  - Fact: the egress audit row has no node field.
  - Cost by task works today, but cost by project does not exist.
- **F4. No project (blocker).**
  - Fact: a request's tasks share only `request_id` and `depends_on`.
  - Fact: the budget is per run (`J2_BUDGET`, D251, D252). The monthly dollar limit only gates the start of a queued task (`limits.py` docstring).
  - Fact: the router's `Allowance` exists, but `engine/llm.py:324` passes `allowance=None`, and it is per request, not a running total.
  - Fact: stop is per task or per team. `orchestrator.md` 5.6 says "no idle reaper in v1".
- **F5. Limits are per process (blocker at scale).**
  - Fact: `policy.default.json` sets Claude 4 and Codex 2. `router.py:340` and `:411-416` keep these in semaphores inside one `Router` object.
  - Fact: each engine process builds its own router (`engine/host/loop.py:378` `_connector_port`). With three runs that is up to 12 Claude CLIs.
  - Fact: `Independence` and the health book are in-memory per process, so a reviewer in another process cannot see who built the work.
  - `quota.json` is shared across processes already.
- **F6. One working folder, no write fence (blocker for parallel writers).**
  - Fact: `workdir.py` allows ONE folder, with `read` or `edit` for all of it.
  - Fact: `folder_watch.py` diffs the whole folder per run, so two parallel runs would see each other's changes. It says nothing when the folder is not a git work tree.
- **F7. The only human gate is J2's question.**
  - Fact: nothing asks "worker 3 wants to run commands: allow?".
  - Fact: external send is off and cannot be turned on through the app. `J2_SEND_MODE` defaults to `dry-run` (`engine/j2_send.py:76`) and is not one of the ten `TaskSettings` keys. A design must keep this.
- **F8. A stuck node cannot be recovered.**
  - Fact: a silent but alive process is never killed while the app runs (`orchestrator.md` 5.6, `SILENT_AFTER_S` in `runs.py`). `reconcile` only handles a missing pid, or a silent one at app start.
- **F9. Hand-off is file names only.**
  - Fact: `tasks.py:701` `_files_of` lists up to 200 file names, and `RunSpec.upstream` allows at most 10 upstream runs. There is no summary, no checksum and no "this is data".
- **F10. Pressure at scale (not a blocker today).**
  - Fact: the server is the only database writer (`db.py`, D16). WAL, `busy_timeout` 5 s, `BEGIN IMMEDIATE` for every write.
  - Fact: `RunWatcher` runs one task per live run, polling every 400 ms (`runs.py:432`). Each heartbeat batch moves `tasks.last_event_at` (`projector.py:138-170`). The bus ring is 1000 events (`events.py`).
  - H: at 12 to 30 nodes this means more write transactions and a faster-wrapping ring. Not measured.

## Checked and not the cause

- **SQLite today.** Engine processes never open the database. It is a later pressure point (F10).
- **One running direct chat.** `direct_running.py` is per chat session and per process, so it is a trap if someone models nodes as direct-chat turns, not a cause for engine runs.
- **Single-process orchestrator.** Partly: runs are already child processes.
- **Global start lock.** `TaskService._gate` is one asyncio lock held while a process starts, so starts are serial, but each is short. Spawn cost is H.
- **Connectors.** They are stateless per call apart from the semaphores (F5).
- **Streaming work.** It is an asset, not a cause. `LiveTurn` gives numbered, replayable events that a node view can reuse (D222).

## Preservation contract

The existing behaviours that must stay are listed in `architecture.md` section 9. In short:

- P1 checkpoints
- P2 resume
- P3 stop and `CancelToken`
- P4 idempotent send
- P5 egress scrub (both modes stay)
- P6 budgets (P25, `Limits`)
- P7 J2 provider seam
- P8 local data
- P9 releases untouched
- P10 vendored engine and goldens
- P11 one live task per team for ordinary tasks
- P12 single database writer
- P13 `SUTRA_MAX_RUNS` and `SUTRA_MAX_LIVE`
- P14 owner access caps every grant
- P15 external send stays off

Each is kept by the mechanism in `architecture.md` section 9 and by the "what stays the same" column of the matching MAN package.

## Addendum: facts found while building phase 1 (2026-11-20)

Read in the code by the architect after MAN-1 to MAN-4; they changed the design through D297 to D305.

- **F11. The engine path cannot carry a tool profile.** Fact: `policy.default.json` has `tool_profile: none` for every call; `CallTag` and `CompletionRequest` have no tools field; only chat and the orchestrator ask for `sutra` or `github` (through `AskRequest.tools`). So tier 4 (and tier 1 through the `sutra` tools) had no way to reach an engine worker. Answered by D298 (MAN-8).
- **F12. J2's builder tools are a separate reach.** Fact: a builder-tools call is a `ToolGrant` (`CompletionRequest.run_tools`) that runs in a folder strictly inside the run folder; the router gives it no owner's folder (`folder_for` is skipped) and no MCP profile; the engine switches it on (`llm.tools_on`) and `types.json` lists its tools (Read, Write, Edit, Glob, Grep, Bash, WebSearch, WebFetch); `agent_tools` is a locked engine setting, not a task key. The department output spec's `workspace` only says what builders do in the OWNER's folder. Answered by D299.
- **F13. The profile `sutra+github` is a bundle.** Fact: the MCP server and `tool_names_of` already accept the parts separately (`github` alone works); the policy type and the first design named only the bundle, which hands the whole app database read with the GitHub tools. Answered by D298.
- **F14. A one-shot JSON call has no process-level stop.** Fact: `call_json_result` takes no `cancel`; a chat turn's token reaches the spawned process through `TurnPlan.cancel` (D215). Answered by D301.
- **F15. `agent_nodes.task_id UNIQUE` and retries.** Fact: a retry is a new `tasks` row (`TaskService.retry`, `parent_task_id`). The node row therefore follows the current attempt (D305).
- **F16. Stop restarts the queue.** Fact: `TaskService._stop` ends with `start_ready()`, so the kill file must already be on disk when the ladders run (it is: `kill_all` writes it first), and a stopped node must never be picked up again by a retry rule (D303).
