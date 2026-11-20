# Multi-agent nodes: build plan

Status: proposed, 2026-11-20. Design only. Each package is one branch-sized step: one coherent change, tests green, flag off by default.
Paths are under `sutra-pro/`. Read [architecture.md](architecture.md) and [guardrails-and-permissions.md](guardrails-and-permissions.md) first; decisions are in [decisions.md](decisions.md).

**Status (2026-11-20).** MAN-1 to MAN-4 are built (commits b4caeec8, 80a35494, c021b6db, 8dab4e61) and reviewed by the architect against the design. Their rulings are D297 to D305. The packages below carry what the rulings added, marked with the D number. The section "Before phase 2" lists what the developer must fix in the phase 1 code first.

## How to build it

- Follow `AGENTS.md`: branch from the newest `origin/main`, targeted tests while you work, `scripts/gate.sh` in the foreground before pushing, try the beta (`scripts/py scripts/install_app.py beta`) for any package that shows in the app, release only when the owner says so.
- Every package leaves `SUTRA_NODES_V1` at its default `0`. The "flag" column says which switch turns the new behaviour on.
- "What stays the same" is a promise and a test: the existing suite must pass with the flag off, and the vendored-file hashes must not move.
- Foundations and safety come first. The first package that can start a process under the new rules is MAN-5, and the kill switch (MAN-4) is built before it.
- Tests use `SUTRA_ENGINE=fake`, `FakeLauncher` and `ScriptedConnector`. Do not run `scripts/live_smoke.py`.

## Before phase 2 (fixes to the phase 1 code, one commit each, in this order)

These are places where the built code differs from the design in a way that matters. MAN-5 does not start until they are done and the suite is green with the flag off.

- [ ] **F1 (D302, MAN-4).** A node with no usable grant must never start. `NodeControl.gate` (or a small gate beside it) asks `node_block_of` for every queued task that has an `agent_nodes` row and returns "Held: this agent has no valid grant" when it raises `NodeBlockError`. Remove the "starts as an ordinary task" fallback in `TaskService._run_spec` (a node that still reaches it raises: the gate makes that impossible). Test: a node row with an empty, role-mismatched or too-wide grant stays `queued` with that sentence, nothing starts, the next queued task still starts.
- [ ] **F2 (D299, MAN-2).** `grants.py`: replace `commands = sandboxed_builder` with the separate field `run_tools` (`none` or `engine`; `engine` for a worker, `none` otherwise); `COMMAND_LEVELS = (none, git_reads)`; a worker gets `git_reads` when its folder is `edit`, a reviewer when it is `inspect`; the "builder tools go with folder edit" rule goes; `run_tools` is in `to_json` and `from_json` and is not capped by the owner's access or the output level. Tests: a worker with output `read` has tiers 0 and 1 and `run_tools = engine`; a worker with `edit` has 0 to 3; the audit text names `run_tools`.
- [ ] **F3 (D298, MAN-2).** `grants.py`: tier 4 no longer depends on the owner's access (`_why_not_network` keeps only "a {role} never reaches the network"); split the tool profile into `sutra` and `github` (`TOOL_PROFILES = none, sutra, github, sutra+github`; worker ceiling `sutra+github`, reviewer `sutra`); tier 1 = a folder to read or the `sutra` part (the planner always has it); tier 4 = the `github` part; a step may ask for `sutra`, `github` or both, the `sutra` part is given up to the role's ceiling without an approval, the `github` part only to a worker with one; a tier-4 approval gives `github` only. Update the `Grant` invariants and `StepRequest` to match, and keep `from_json` strict. Tests: rewrite `test_tier_4_is_only_given_to_a_worker_with_an_approval_and_an_owner_who_allowed_changes` as "...with an approval, for any folder access"; a read-only owner and a no-folder owner get tiers {0,4}; a reviewer or the planner is refused tier 4; tier 4 does not add the `sutra` part.
- [ ] **F4 (D300, MAN-1 and MAN-2).** Add `"confirm_credits": 500` to `NODE_DEFAULT_CAPS` (and its test in `test_config.py`); `Plan.confirm_credits` defaults to it; `None` means "do not ask about spend". Test: a plan estimated at 501 asks, 500 does not; `None` never asks.
- [ ] **F5 (D305, MAN-2).** `Plan.max_nodes` counts workers only. Test: 12 workers and 2 reviewers is accepted, 13 workers is not.
- [ ] **F6 (D303, MAN-4).** `NodeControl._stop_live` and kill-all run the ladders together (`asyncio.gather`, as `TaskService.shutdown` does), one failure logged and the rest going on. Test with `FakeLauncher` that takes a few seconds per stop: three nodes end in about one ladder's time.
- [ ] **F7 (D297 to D305, MAN-1).** Copy D297 to D305 into `docs/DECISIONS.md`, `docs/diagram/decisions.json` and (by `scripts/build_traceability.py`) `docs/design/traceability.json`; the amended lines of D264, D267, D269, D273, D279, D291 and D294 too. `tests/test_diagram_decisions.py` and `tests/test_traceability.py` must pass.

No schema change is needed: migration v6 is not edited by any of these (it has not been released; if a CHECK is wanted later it goes in v7).

## Order and dependencies

```mermaid
flowchart LR
  M1[MAN-1 foundations] --> M2[MAN-2 grants + audit]
  M1 --> M3[MAN-3 identity]
  M2 --> M4[MAN-4 kill switch]
  M3 --> M4
  M4 --> M5[MAN-5 projects + gate + leases]
  M5 --> M6[MAN-6 hand-off + messages]
  M5 --> M7[MAN-7 expiry + recovery]
  M6 --> M8[MAN-8 approvals]
  M5 --> M9[MAN-9 budgets]
  M6 --> M10[MAN-10 lanes + scopes]
  M8 --> M10
  M8 --> M15[MAN-15 system permissions]
  M15 --> M10
  M6 --> M11[MAN-11 reviewer]
  M8 --> M11
  M7 --> M12[MAN-12 slots + load test]
  M9 --> M12
  M6 --> M13[MAN-13 project page]
  M11 --> M14[MAN-14 tool audit]
```

## Packages

### MAN-1. Foundations (inert)

- **Goal:** the flags, the schema and the registration exist; nothing reads them.
- **Files:** `sutra_app/config.py` (`nodes_v1`, `nodes_lanes`, `nodes_reviewer`, `nodes_slots`, default caps), `sutra_app/ops/envfile.py`, `docs/ENVIRONMENT.md`,
  `sutra_app/orchestrator/schema.py` (`DDL_V6_NODES`: five tables, `tasks.lane`, index swap, appended to `MIGRATIONS`), `sutra_app/orchestrator/models.py` (`NodeBlock`, `ProjectOut`, `NodeOut`, closed models), `sutra_app/library/...` only if a family is needed,
  `docs/DECISIONS.md` (D253 to D296), `docs/diagram/decisions.json`, `docs/design/traceability.json`.
- **Tests:** `tests/orchestrator/test_schema_v6.py` (v5 file with data migrates; the new unique index forbids exactly what the old one did for lane `''`; append-only triggers raise; `src_ref` unique); `tests/orchestrator/test_config.py` (flags default 0, sub-flags ignored without the master); `tests/test_diagram_decisions.py`, `tests/test_traceability.py`, `tests/test_docs.py` (the existing ones, now covering D253+).
- **Built, plus (D297, D300, D304):** `node_messages` is keyed `(project_id, seq)`; the columns `projects.decide_for_me`, `paused`, `review_loops` and `approvals.created_at`; append-only triggers on `node_messages` too; `NODE_DEFAULT_CAPS` gets `confirm_credits` (F4).
- **Flag:** none yet (inert).
- **What stays the same:** every query and route; a v5 database migrates with its data intact; `task.json` untouched; the pre-upgrade backup still runs.

### MAN-2. Grants, tiers and the audit store (pure code)

- **Goal:** the permission model as functions and a table, with no wiring.
- **Files:** `sutra_app/orchestrator/grants.py` (role table, tiers, `intersect(role, step, output_spec, owner_access) -> Grant`), `sutra_app/orchestrator/gatekeeper.py` (rules only: `evaluate(plan)`), `sutra_app/orchestrator/nodes_store.py` (`audit()`, `approvals` rows), `tests/orchestrator/test_nodes_injection.py` (fixtures only at this stage).
- **Tests:** `test_grants.py` (a grant is never wider than the owner's access; worker with output `read` has tiers 0 and 1; reviewer never tier 2; tier 6 never; planner cannot add a tier); `test_nodes_audit.py` (append only; no payload fields; reasons clipped and redacted); property test: intersection is monotone (more restrictions never add a tier).
- **Built, plus (D298, D299, D304, D305):** folder level `inspect`; fixes F2, F3, F4, F5 above. The grant's fields are `{tiers, folder, scope, tool_profile, commands, run_tools, caps}` (architecture 5.2).
- **Flag:** `SUTRA_NODES_V1` (nothing calls it yet).
- **What stays the same:** the connectors, `workspace_for`, `Router.folder_for` (read only by `grants.py`).

### MAN-3. Identity plumbing

- **Goal:** every call, usage row, egress row and run file can say which node it belongs to.
- **Files:** `sutra_app/engine/port.py` (`CallTag.node_id`, `node_role`, optional, default empty), `sutra_app/engine/spec.py` (`TaskSpec.node`), `sutra_app/orchestrator/models.py` (`RunSpec.node`, left out of the dump when `None`), `sutra_app/engine/host/loop.py` (base tag from `task.node`), `sutra_app/orchestrator/runs.py` (`SUTRA_NODE_ID` in `child_environment`), `sutra_app/connectors/egress.py` (two optional audit fields), `sutra_app/connectors/usage.py` (node id into `detail`), `sutra_app/orchestrator/agent/runner.py` (planner identity on its calls, and a `CancelToken` if `call_json` has none: check first).
- **Tests:** `tests/orchestrator/test_run_spec_golden.py` (`task.json` byte-identical with the flag off); `tests/engine/test_engine_spec.py` (a spec with a node block validates, an older reader ignores it); `tests/connectors/test_egress.py` (the row has node fields only when the tag has them); `tests/engine/test_engine_port_contract.py` (the contract unchanged).
- **Built, plus (D301, D304):** the planner's `cancel` reaches the router (checked before each attempt). It does not yet stop a running call: MAN-5 finishes that (D301). The usage row carries `detail.agent_node`; the egress row `node` and `role`.
- **Flag:** `SUTRA_NODES_V1` for writing the block; reading is always allowed.
- **What stays the same:** J2 prompts and goldens, `test_engine_vendor.py` hashes, the usage row shape for tasks without a node, the router's behaviour.

### MAN-4. Kill switch and pause

- **Goal:** the owner can stop and pause before anything can spawn. Built first on purpose.
- **Files:** `sutra_app/orchestrator/killswitch.py` (reads `<data>/nodes/KILL` and `PAUSE`, level logic), `sutra_app/orchestrator/api/projects.py` (`/api/nodes/pause-all`, `/kill-all`, `/api/nodes/{id}/stop`), `sutra_app/ops/cli.py` (a command `nodes kill|pause|resume|status`), `sutra_app/orchestrator/tasks.py` (a stop-by-node helper that calls the existing ladder).
- **Tests:** `test_killswitch.py` (file present means no spawn; removing it resumes; the ladder is the one in `ProcessLauncher.stop` via `FakeLauncher`); `test_api_nodes_security.py` (token required; 404 with the flag off); CLI test.
- **Built, plus (D302, D303, D304):** `GET /api/nodes/status`, `POST /api/nodes/resume`, the 2-second `NodeControl` watcher, and `TaskService.task_gate` (pulled forward from MAN-5). Fixes F1 and F6 above. The automatic triggers of D279 are **not** in this package (D303): they come with their causes (MAN-7, MAN-9, MAN-10).
- **Flag:** `SUTRA_NODES_V1`.
- **What stays the same:** `TaskService.stop`, `stop_live`, the stop ladder and its timings; every existing route.

### MAN-5. Projects, the task gate and leases (cross-team parallelism)

- **Goal:** a request with 2 or more steps becomes a project; its nodes are tasks started through the existing scheduler under the Conductor's gate; basic teardown.
- **Files:** `sutra_app/orchestrator/projects.py` (`ProjectService.adopt`), `sutra_app/orchestrator/conductor.py` (`task_gate`, `tick`, basic teardown), `sutra_app/orchestrator/tasks.py` (`task_gate` argument, called in `_prepare_next` after `start_gate`; lease taken in the same transaction), `sutra_app/orchestrator/agent/runner.py` (one hook after tasks are created), `sutra_app/orchestrator/wiring.py` (build the services), `sutra_app/orchestrator/api/projects.py` (read routes), `sutra_app/orchestrator/projector.py` (node state from run events, `project.updated`).
- **Tests:** `test_projects_adopt.py` (a 4-step plan makes 1 project, 4 nodes, 4 tasks with the plan's `depends_on`); `test_conductor_gate.py` (parallel cap, kill switch, held task shows a waiting sentence, starts by itself when released); `test_projects_parallel.py` with `FakeLauncher` (independent steps start together, a dependent waits, FIFO kept, `max_runs` and `max_live` still bound everything); `test_projects_off.py` (flag off: the same plan makes plain tasks exactly as before).
- **Also (D298 to D305):**
  - The Conductor's `task_gate` asks `NodeControl.gate` first and adds its own checks (D303); a node with no valid grant is held and then failed with a `grant.denied` row (D302).
  - The plan becomes a `gatekeeper.Plan`: `TaskWorkflow` steps plus each team's output spec become `PlanStep`s; the planner's schema gets the optional `scope` and `needs` per step only while the flag is on (the planner's prompt and schema are unchanged with it off). A step with no estimate counts as its slice (D300).
  - `grant.issued` rows state `run_tools` (D299). `agent_nodes.task_id` follows the current attempt (D305).
  - The planner's stop (D301): `cancel` through `call_json_result` and the one-shot plan of the base connector, Claude, Codex and the stub (tests: a running planner call is ended by Stop within the cancel ladder; the stub shows the token reaches it); a registry of in-flight planner tokens in `ProjectService`; node stop, project stop and kill-all ask it. Tests in `tests/connectors/` and `test_projects_adopt.py`.
  - Kill ends the project (D303 d): a kill sets every project with a live node to `stopped`, cancels its queued and blocked nodes, and nothing restarts by itself after resume; a node stopped by the owner or the switch is never retried. The projector owns node state from here (the `mark_ended` of MAN-4 becomes its rule: a node is `cancelled` only if its task ended stopped).
- **Flag:** `SUTRA_NODES_V1`.
- **What stays the same:** FIFO, the caps, `why_waiting` text for ordinary tasks, `settle_blocked`, one live task per team (lane `''`), the chat agent's plan and cards.

### MAN-6. Hand-off and messages

- **Goal:** a finished node hands its work to dependants through a validated, scrubbed, stored message.
- **Files:** `sutra_app/engine/host/handoff.py` and `sutra_app/engine/host/finish.py` (a `handoff` step: write `handoff.json` when the task is a node; never fails the run), `sutra_app/orchestrator/conductor.py` (intake: validate, scrub, store, release), `sutra_app/orchestrator/nodes_store.py` (`post`, `messages(after)`), `sutra_app/orchestrator/tasks.py` (`_run_spec` adds the hand-off to `upstream`), `sutra_app/orchestrator/api/projects.py` (`/messages`), `sutra_app/orchestrator/events.py` (topics).
- **Tests:** `test_handoff_schema.py` (size caps; paths relative, no `..`, no link, checksum matches); `test_handoff_injection.py` (a planted instruction changes no grant or edge and sits only in a data block; a planted secret is redacted); `test_node_messages.py` (D297: seq is 1 to n per project with two projects interleaved, with a repeated `src_ref` that takes no number, after a rolled-back post, and for 50 posts read back as 1 to 50; `after=` catch-up returns k+1 first); `tests/engine/test_engine_finish.py` (the existing finish steps unchanged; the new step skipped for a non-node run); `test_engine_events_contract.py` (still the closed eight).
- **Flag:** `SUTRA_NODES_V1`.
- **What stays the same:** the eight run events, `upstream` copying and its checks, `finish.run_steps` order and guards, J2 files.

### MAN-7. Lease expiry, retries, recovery and failure policy

- **Goal:** a hung or crashed node is recovered; a crash or restart loses nothing. Also the automatic trigger "a node loses its lease twice" (D303), and a node stopped by the owner or the kill switch is never retried.
- **Files:** `sutra_app/orchestrator/conductor.py` (expiry, sleep check, retry through `attempts.py`, failure policy), `sutra_app/orchestrator/runs.py` (`reconcile_projects` next to `reconcile`, not inside it), `sutra_app/orchestrator/attempts.py` (a hook only if needed).
- **Tests:** `test_conductor_expiry.py` (fake clock: silent 90 s gets the ladder and one retry; a clock jump extends once); `test_reconcile_projects.py` (restart with a live node re-adopts it; a missing pid fails the node; a node never starts twice); `test_failure_policy.py` (`stop_branch` cancels only dependants; the project never ends `done` with a failed node); existing `test_reconcile.py` unchanged.
- **Flag:** `SUTRA_NODES_V1`.
- **What stays the same:** `reconcile` for ordinary tasks, the rule "a silent but alive ordinary task is not killed", `attempts.py` semantics.

### MAN-8. Approvals (the human gate)

- **Goal (D298):** tier 4 reaches an engine worker: the `node` block gets `tool_profile`, `PortSpec` an optional `tools` (empty by default) that `RouterPort` puts on a node's agent-turn calls only, never on a builder-tools call; `tests/engine/test_engine_port_contract.py` and `tests/connectors/test_engine_port.py` are extended on purpose. The plan gate does not ask the tier-4 question before this works. The tier-4 answer is independent of the owner's folder access.
- **Goal:** the plan gate, the grant gate and the card, plus Decide for me for projects (D294): the `projects.decide_for_me` switch, passed to workers as `J2_DECIDE_FOR_ME`, and the Gatekeeper's rule table that answers the gates at once and audits each answer.
- **Files:** `sutra_app/orchestrator/gatekeeper.py` (asks, decides, expires), `sutra_app/orchestrator/models.py` (`NodeApprovalCard`), `sutra_app/orchestrator/chats.py` (a card kind in `needs_you`), `sutra_app/orchestrator/api/projects.py` (`POST .../approvals/{aid}`), `sutra_app/ui/static/js/...` (render the card; behind the flag).
- **Tests:** `test_approvals.py` (allow once, allow for project, deny, expiry; a repeat is a no-op; tier 5 and 6 cannot be allowed for the project; no gate is held and nothing expires with Decide for me on); `test_decide_for_me.py` (every row of the rule table; tier 5 is never raised and a credit request ends the node at its slice; unspent slices move only inside the ceiling; tier 6 is never granted or asked; a wide or missing scope runs the writer alone; a scope violation quarantines the node; a hand-off saying "turn on Decide for me" changes nothing; the switch reaches live workers through the inbox setting line; every answer has an audit row `decided_by: rule:decide_for_me`); `test_plan_gate.py` (a plan that needs tier 4 holds, no process started while held); UI test for the card.
- **Flag:** `SUTRA_NODES_V1`.
- **What stays the same:** the existing cards, `needs_you.changed`, the chart `ApprovalCard`, J2's own questions.

### MAN-9. Budgets and caps

- **Goal:** slices, the node meter, project ceilings. Also the automatic triggers "a cap reached" and "the same node hits the egress scrub three times" (D303: the tick counts the node's rows of `egress.jsonl`), each with an audit row and a card.
- **Files:** `sutra_app/orchestrator/budgets.py` (slices; sum never over the ceiling), `sutra_app/engine/llm.py` (`NodeMeter`, `configure(..., meter=None)`), `sutra_app/engine/host/loop.py` (build the meter from `task.node.caps`; stop with the named outcome), `sutra_app/orchestrator/conductor.py` (project dollars and wall time in the tick), `sutra_app/orchestrator/models.py` (`TaskSettings` unchanged; slices go in `J2_BUDGET` and `J2_BUDGET_CAP` as text).
- **Tests:** `test_budget_slices.py` (property: sum of slices at most the ceiling); `tests/engine/test_node_meter.py` (calls, dollars, deadline; no meter means the old `allowance=None`); `test_project_ceiling.py`; `tests/engine/test_engine_llm_shim.py` unchanged for runs without a node; P25 test: no raise without the Requester.
- **Flag:** `SUTRA_NODES_V1`.
- **What stays the same:** `J2_BUDGET` meaning, D251 and D252, `Limits`, the router's own gate and `max_calls_per_request`.

### MAN-10. Same-team lanes, write scopes and conflict edges

- **Goal:** two workers of one team run together when their scopes do not overlap; the owner's folder is safe. Also the automatic trigger "a scope violation" (D303).
- **Files:** `sutra_app/orchestrator/tasks.py` and `waiting.py` (busy key `(dept, lane)`; `live_in`, `deliver_to_department`, `stop_live` look at lane `''`), `sutra_app/orchestrator/conductor.py` (scope lease check), `sutra_app/orchestrator/grants.py` (scope narrowing rule), `sutra_app/connectors/workdir.py`, `claude.py`, `codex.py` (`Folder.scope`), `sutra_app/engine/host/folder_watch.py` (a path list for attribution; used only by nodes), `sutra_app/orchestrator/gatekeeper.py` (`scope.violation`).
- **Tests:** `test_lanes.py` (two nodes of one team start together with the sub-flag, not without; an ordinary task still queues behind a live ordinary task); `test_scope_leases.py` (overlap delays, disjoint runs together, no scope runs alone, no git means serial); `test_scope_violation.py` (a path nobody owns pauses the project and raises a card); `tests/connectors/test_claude_scope.py` (argv has the scoped allow rules and `.git` denied); existing workdir tests unchanged.
- **Flag:** `SUTRA_NODES_LANES` (with the master).
- **What stays the same:** the unique-index rule for lane `''`, `deliver_to_department`, the owner's access cap, the folder text the CLIs get when no scope is set.

### MAN-11. Reviewer (light runtime)

- **Goal:** a read-only reviewer node that returns a verdict, independent of the maker when possible. The reviewer's grant takes its output level from the strongest step it reviews (D305).
- **Files:** `sutra_app/nodes/__main__.py`, `host.py`, `reviewer.py`, `templates/reviewer.md`; reuses `engine/events.py` `EventWriter`, `engine/host/heartbeat.py`, `engine/host/inbox.py`, `connectors/engine_port.make_port`; `sutra_app/orchestrator/runs.py` (`ProcessLauncher` picks the module by `task.node.runtime`), `sutra_app/orchestrator/conductor.py` (spawn after workers, verdict intake, loop cap, independence pick via `agent_picks`), `sutra_app/orchestrator/gatekeeper.py` (verdict rules).
- **Tests:** `test_light_host.py` (same files and events; heartbeat; stop line ends it; `KILL` ends it); `test_reviewer_verdict.py` (enum only affects flow; text shown as plain text); `test_review_loops.py` (2 loops then a card); `test_reviewer_independence.py` (picks the other provider; says "not independent" when it cannot); `test_reviewer_readonly.py` (grant has no tier 2; argv has no edit tools); injection fixtures from MAN-2 run against it.
- **Flag:** `SUTRA_NODES_REVIEWER` (with the master).
- **What stays the same:** the engine process and J2's own Audit function inside a team run; the `Independence` object; the event set.

### MAN-12. Provider slots, heartbeat coalescing and the load test

- **Goal:** machine-wide provider limits; write pressure measured and held down.
- **Files:** `sutra_app/connectors/slots.py` (`flock` slot files via `oslayer.try_lock`), `sutra_app/connectors/router.py` (one acquire and release hook around the existing semaphore), `sutra_app/orchestrator/projector.py` (skip the `touch` of a heartbeat-only batch within 15 s), `tests/orchestrator/test_nodes_load.py`.
- **Tests:** `test_slots.py` (two routers in two processes never exceed the policy; a dead process frees its slot); `test_heartbeat_coalescing.py` (offset replay is harmless); `test_nodes_load.py` (12 fake nodes for 5 minutes, `StoreBusy` count 0, event ring not starving the page; marked slow, run in the gate). If it fails: the 250 ms batch window per project, as a follow-up inside this package.
- **Flag:** `SUTRA_NODES_SLOTS` (with the master) for slots; coalescing only for node tasks.
- **What stays the same:** `max_concurrency` per router when the sub-flag is off, the touch behaviour for ordinary tasks, `quota.json`.

### MAN-13. The project page

- **Goal:** the owner sees a project: the graph of nodes, state, spend, approvals, audit, and can stop it. The page learns whether the feature is on from `GET /api/nodes/status` (404 means off); the flags stay out of `Settings.public()` (D305).
- **Files:** `sutra_app/ui/static/js/project_*.js`, the page template and route (`/p/<id>`), a link from the chat's request card; reuses the graph drawing and the `SutraEvents` intake; follows the streaming client layers (intake, store, client, view).
- **Tests:** `tests/ui/` node tests for the store and view (pure state machine, snapshot plus `after=` catch-up, reconnect); a browser smoke in the beta (by hand); the existing UI suites unchanged.
- **Flag:** `SUTRA_NODES_V1`.
- **What stays the same:** every existing page, the live chat, the graph page.

### MAN-14. Tool-call audit

- **Goal:** the audit lists tool names and kinds for each node, with no inputs.
- **Files:** `sutra_app/connectors/router.py` (an optional `on_tool(tag, name, kind, target_basename)` hook from events the connectors already parse), `sutra_app/engine/host/loop.py` (write `tools.jsonl` in the run folder), `sutra_app/orchestrator/conductor.py` (import at teardown into `node_audit`).
- **Tests:** `test_tool_audit.py` (names and kinds only; a path is a basename; nothing when the tag has no node); connectors tests unchanged.
- **Flag:** `SUTRA_NODES_V1`.
- **What stays the same:** `tool_kinds.py`, the chat's tool lines, the connector event stream.

### MAN-15. System permissions on Mac and Windows

- **Goal:** (closed laptop is a refusal, D296: an open card does not survive a sleep or a restart; tested in `test_gate_sleep_refusal.py`, built in MAN-7 and wired in MAN-8 and here) before a node starts, check what the computer has allowed (macOS Files & Folders and Full Disk Access; Windows Controlled folder access, elevation, long paths), explain it in plain steps for that system, open the right settings page and check again (D295). Built after MAN-8 (it reuses the card) and **before** MAN-10 (the first package that lets parallel writers run).
- **Files:** `sutra_app/syspermissions.py` (`probe`, `explain`, `open_settings`, one adapter each for macOS, Windows and "nothing to ask"), `sutra_app/oslayer.py` (small helpers: is the process elevated, long paths on or off, app location), `sutra_app/orchestrator/gatekeeper.py` (call the probe after the grants are computed; the node state `awaiting_system`), `sutra_app/orchestrator/conductor.py` (the task gate holds an `awaiting_system` node; reason `needs_system_permission` for a late failure), `sutra_app/orchestrator/models.py` (`SystemPermissionCard`), `sutra_app/orchestrator/api/projects.py` (`POST .../system/{item}/check` and `/skip`), the card in the UI (behind the flag), migration v6 (state value).
- **Tests:** `test_syspermissions.py` with a fake adapter per system (a permission error from a listing gives `needs_permission`; a write probe leaves no file behind and never touches `.git`; a plan that never names a protected folder shows no card); `test_system_card.py` (only affected nodes wait, others run; skip cancels only those; "Check again" moves them to `ready`; Decide for me does not answer it; the card has the Mac steps on macOS and the Windows steps on Windows); `test_late_permission_error.py` (an `EPERM` or `WinError 5` from a node ends it as `needs_system_permission` and raises the card once); `test_elevated_refused.py` (a Windows elevated process refuses new nodes); audit rows `system.*` present. Tests use `SUTRA_ENGINE=fake` and monkeypatched platform: no real system dialog in the gate.
- **Manual check (both systems, in the beta app, owner's go-ahead):** on a Mac, a project in `~/Desktop` with Files & Folders off shows the system dialog from the probe and then runs; refusing it shows the card; turning it on and "Check again" works. On Windows, Controlled folder access on blocks a write and shows the card; allowing the programs fixes it. Record the exact card words that were needed. The Windows result is the first real Windows measurement for this feature and must be written down either way.
- **Flag:** `SUTRA_NODES_V1`.
- **What stays the same:** how ordinary tasks and chats open folders, `workdir.py` and its folder access setting, `oslayer.py`'s stop and process behaviour, the Windows installer and the Mac DMG, and every system setting on the owner's computer (Sutra changes none of them).

## Cross-checks before the first release of any package

1. `scripts/gate.sh` green with the flag off, and with `SUTRA_NODES_V1=1` on the new tests.
2. `tests/engine/test_engine_vendor.py` unchanged: no `j2*.py` moved.
3. The golden `task.json` and the prompt goldens unchanged with the flag off.
4. A restart in the beta app while a project runs: the project resumes or fails per node, nothing starts twice.
5. The kill file stops everything within the ladder's time.
6. `scripts/ownership-audit.sh`: no owner name, no login, no absolute home path in any file.

## Not in this plan (and why)

- Parallel builders **inside** one team's J2 run: needs a J2 sync and is outside "enhance, do not replace".
- Remote nodes or a broker: local-first (D289).
- External publish by a node: a wall in v1 (D269).
- Git worktrees per node: scoped leases first (D261).
- Critical-path scheduling: FIFO is enough for plans of at most 12 steps.
