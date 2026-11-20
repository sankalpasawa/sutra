# Multi-agent nodes: developer notes

Status: written while building phase 1 (MAN-1 to MAN-4), 2026-11-20. These notes are for the architect: where the design met the real code and what was changed or left
open. Each item says what the design said, what the code showed, what was done, and what the architect should decide. Paths are under `sutra-pro/`.

## MAN-1. Foundations

### N1. `node_messages.seq` cannot be gap-free per project if it is the table's AUTOINCREMENT (small change, done)

- Design: architecture.md section 4.1 and 7 say `seq` is "gap-free per project, from the table's autoincrement"; D264 says "gap-free `seq` per project".
- Code: an `INTEGER PRIMARY KEY AUTOINCREMENT` counts for the whole table. With two projects posting, project A would see seq 1, 3, 4 and project B 2, 5. A page that detects a gap
  (the `after=` catch-up of the streaming contract) would think messages were lost.
- Done: migration v6 makes the key `(project_id, seq)`. The writer (MAN-6, `NodeStore.post`) takes `MAX(seq) + 1` for the project inside its one write transaction. The server is
  the only writer and a write transaction is exclusive (`BEGIN IMMEDIATE`), so two posts cannot take the same number. `UNIQUE (project_id, src_ref)` is as designed.
- Architect: nothing to decide unless you want a global sequence for the page. If so, the page must stop treating a gap as loss.
- Architect ruling: approved, D297. The key `(project_id, seq)` with `MAX(seq)+1` in the writer's one transaction stays. The guarantee: for one project the stored `seq` values are exactly 1 to n at every committed state (primary key, one writer under `BEGIN IMMEDIATE`, number taken and used in the same transaction, a repeated `src_ref` takes no number, no update or delete, `project.message` after COMMIT). A page that gets anything but k+1 after `?after=k` has lost a message and refetches. No global sequence. MAN-6 writes the writer and its four tests.

### N2. Columns the design names elsewhere but the table list did not show (additive, done)

The migration is "never edited later", so what the later packages need is in it now:

- `projects.decide_for_me` (0 or 1): D294 and guardrails 5.1 say the switch lives on the project row; the table list in architecture.md section 7 left it out.
- `projects.paused` (0 or 1): `POST /api/projects/{id}/pause` needs somewhere to keep "paused", and the status list has no `paused` value (a paused project is still `running`).
- `projects.review_loops` (count): "review loops ... counted in `projects` rows" (architecture.md 4.4).
- `approvals.created_at`: for the expiry clock and the card's age.
- Architect ruling: approved, D304. Design text corrected (architecture section 7). No change to the code.

### N3. Append-only triggers on `node_messages` as well as `node_audit` (small addition, done)

D264 says messages are append-only; the design's data model only gave triggers to `node_audit`. A table that is only appended to by the server is cheaper to trust with the
rule written into it, as `atom_ledger` does. If MAN-6 needs to redact a stored message it must scrub before it stores (which the design already says), not edit afterwards.
- Architect ruling: approved, D304. Messages are append-only; a stored message is never edited; a project is never deleted in v1 (D305), so the foreign key never blocks anything.

### N4. `docs/design/traceability.json` was out of date before this work

The committed file said 200 decisions while the log was at D252. Registering D253 to D296 meant running `scripts/build_traceability.py`, which rewrote the file and
`docs/TRACEABILITY.md` from the current sources. A few unrelated rows (D133, D176, D179, D190) moved because the generator re-read the notes. Nothing was edited by hand.
- Architect ruling: nothing to decide. Registering decisions goes through `scripts/build_traceability.py` only, never by hand. D297 to D305 are to be registered the same way (F7 in the build plan).

### N5. Two existing tests pinned the schema version

`tests/orchestrator/test_live_turn.py` (migration v5) asserted `SCHEMA_VERSION == 5` and "nothing else changed"; `tests/orchestrator/test_schema.py` (v3 to v4) counted every
table of `TABLES`. Both now migrate only as far as their own version and skip the tables of later migrations. No assertion was weakened: the v5 test still checks that v5 changes
nothing but its table, and the v6 swap of the index has its own test file.
- Architect ruling: approved, D304 (no code change). The tests that pin a version migrate only as far as their own version.

### N6. The new flags are not in `Settings.public()`

`GET /api/config` and `sutra-pro config show` list `public()`. Adding keys there would change an existing route's output while the feature is off, so the four flags are
left out for now. The kill switch command (MAN-4, `sutra-pro nodes status`) prints them.
- Architect ruling: approved, D305(f). The flags stay out of `Settings.public()` and `GET /api/config`. The page learns the flag from `GET /api/nodes/status` (404 means off).

## MAN-2. Grants, tiers and the audit store

Built as designed: `orchestrator/grants.py` (role table, tiers, `intersect`), `orchestrator/gatekeeper.py` (`evaluate(plan)`, rules only), `orchestrator/nodes_store.py` (`audit`,
approvals rows). Nothing calls them yet. The points below are places where the design said less than the code needed. Each one was decided the cautious way (deny by default) and is
open for the architect to change; every one has a test, so a change shows up as a failing test with a clear name.

### N7. A grant has a fourth folder level, `inspect` (additive)

Architecture 5.2 lists the folder as `none|read|edit`. Guardrails 4 says a reviewer's folder access is `inspect` at most (reads plus the four git reads, as `Router.folder_for`
decides). Both cannot be right, so `Grant.folder` is `none|read|inspect|edit`.
- Architect ruling: approved, D304. Folder levels are `none`, `read`, `inspect`, `edit`; architecture 5.2 corrected.

### N8. The owner's access caps tier 4 and tier 3 as well as tier 2

Guardrails 4: "if the owner chose read only, every node is at most tier 1." Built literally: with the working folder set to read only, or no folder at all, no node gets tier 2, 3 or 4.
Consequence the architect should look at: a worker that only needs the GitHub read tools (tier 4) is refused when the owner chose read only, although those tools do not touch the folder.
If that is not wanted, tier 4 should depend on the approval alone. The rule is one line in `grants.resolve` and one test (`test_tier_4_is_only_given_to_a_worker_...`).
- Architect ruling: changed, D298. Tier 4 does not depend on the owner's folder access: it follows the role (worker only) and an approval. The folder access caps tiers 2 and 3 and nothing else. The tool profile is split into `sutra` and `github` so a tier-4 grant does not carry the app-database read. Code fix F3. Also found: the engine path has no way to carry a tool profile yet, so MAN-8 adds it (`tool_profile` in the node block, optional `PortSpec.tools`).

### N9. A worker whose output only reads has tiers 0 and 1, so no "sandboxed builder tools" (T3)

Guardrails 3 says tier 3 includes "J2's sandboxed builder tools inside the run folder (D245)", and guardrails 4 and the build plan say "a worker with output `read` has tiers 0 and 1
only, whatever the plan says". A document or website run has output `read` for the owner's folder but does use J2's builder tools in its own run folder today. The grant follows the
explicit rule (tiers 0 and 1), so `commands` is `sandboxed_builder` only for a worker that may change the owner's folder. MAN-5 must decide whether the grant describes the run
folder's builder tools at all (then they need their own word, not tier 3) or whether the grant is silent about them and they stay exactly as they are today. Nothing is enforced from the
grant yet, so no behaviour changed.
- Architect ruling: decided, D299. J2's builder tools are not a tier and not owner's-folder reach (a `ToolGrant` call runs in the run folder, with no owner's folder). The grant gets a separate field `run_tools` (`engine` for a worker, `none` otherwise), written in the `grant.issued` row and not enforced by the grant. Tier 3 is only the four git reads (`commands` is `none` or `git_reads`); a worker has them when its folder level is `edit`. Code fix F2. Known limit, now written in guardrails section 3: the builder tools include Bash, WebSearch and WebFetch and the grant does not narrow them in v1.

### N10. Tier 1 can come from the read-only app tools instead of the folder

A worker with no working folder but with the tool profile `sutra` has tier 1 (it reads app data). Without a folder and without that profile it has tier 0 only. The profile is never on
unless the step asks for it.
- Architect ruling: approved, D298 and D304. Tier 1 comes from a folder to read or from the `sutra` part of the profile; it reaches an engine worker through the same MAN-8 delivery as tier 4.

### N11. "Wider than a folder" is "more than one path"; "no scope declared" is not a question

The plan gate asks when a step's write scope has more than one path (`scope_width == "wide"`). A writer with no declared scope holds the whole folder, runs alone among writers (`alone`),
and is not asked about: that is the default, serial and safe (D260), and the Decide for me table (D294) also says "run alone". If the architect wants a question for "no scope" too, it is one
more `Gate` in `evaluate`.
- Architect ruling: approved, D304. The plan gate asks about more than one path; a writer with no declared scope is not asked about and runs alone. Guardrails 5 corrected.

### N12. There is no number for "the confirm threshold"

Guardrails 5 says the plan gate asks when "the estimate is over the project's confirm threshold" and gives no default. `Plan.confirm_credits` is None (never asks about the estimate) until
MAN-5 or MAN-8 gets a number from the architect. D273's default caps do not contain one either.
- Architect ruling: decided, D300. The default is 500 work credits (`NODE_DEFAULT_CAPS["confirm_credits"]`, copied into `projects.caps_json`). A step with no estimate counts as its slice. `None` only when the owner gave their own `budget`. `Plan.confirm_credits` defaults to the configured number. Code fix F4.

### N13. The plan has no tier, scope or `needs` field yet

`TaskWorkflow` steps are `AssignmentStep`s: a team, a brief, `depends_on`. D291 says the planner may add a write scope and a `needs` list per step. `evaluate` works on a plan that has been
put into plain values (`gatekeeper.Plan`, `PlanStep`); turning a `TaskWorkflow` plus the departments' output specs into one, and the planner's new fields, belong to MAN-5. `grants.py` takes the
output spec as a word (`read`/`edit`) or any object with a `workspace` attribute, so it imports nothing from the engine and the real `OutputSpec` fits without a copy.
- Architect ruling: approved, D304 and the MAN-5 list. MAN-5 turns the `TaskWorkflow` and the output specs into a `gatekeeper.Plan`, and the planner's schema gets the optional `scope` and `needs` only while the flag is on. `grants.py` keeps taking the spec as a word or any object with a `workspace` attribute.

### N14. Small additions

- `IdFactory` (and so `FakeIds`) gained `project_id`, `node_id`, `grant_id`, `approval_id` (`prj_`, `nd_`, `gr_`, `ap_` and 12 hex).
- `NodeStore` has only what MAN-2 needs (audit, approvals). `put_node`, `lease`, `release` and `post` of the architecture's component table arrive with the packages that use them.
- `approvals.decided_by` is `owner`, `system` or `rule:<name>` (the Decide for me rule table, D294). An answer that arrives after `expires_at` is stored as `expired` (denied).
- Architect ruling: approved, D304. `NodeStore` grows with the packages that use it. One addition for MAN-6: `post` follows D297.

## MAN-3. Identity plumbing

Built as designed: `CallTag.node_id` and `node_role`, `TaskSpec.node` (read) and `RunSpec.node` (written, left out of the file when it is None), the host's base tag, `SUTRA_NODE_ID`, the
two optional egress fields, the node id in the usage row's `detail`, and the planner's identity. The golden files in `tests/fixtures/run_spec/` were written by the code of `origin/main` before
this package, so "byte-identical" is checked against the old code's own output.

### N15. `tasks.py` is touched in MAN-3 (the writer of the block)

The build plan's file list for MAN-3 has no `tasks.py`, but "the block is written only with SUTRA_NODES_V1" has to live somewhere, and `_run_spec` is the only place that builds a `RunSpec`.
It now asks `nodes_store.node_block_of(conn, task_id)` for the block, only when `settings.nodes_v1` is on (with it off the table is not read: a test fails if it is). MAN-5 adds the rows.
A node that has no usable grant starts as an ordinary task and the log says so with ids only. The alternative, refusing to start it, would let one bad row stop the FIFO queue (the start
loop raises). Decision for the architect in MAN-5: the task gate must refuse to start a node whose grant is missing, so this fallback is never reached.
- Architect ruling: changed, D302. The fallback "start as an ordinary task" is removed: an ordinary task has the reach of a team run, wider than a reviewer's, so a broken grant must fail closed. The task gate holds a node with no usable grant (sentence "Held: this agent has no valid grant"); the queue goes on because the loop `continue`s. MAN-5's Conductor fails the node with `grant.denied`. Code fix F1. Touching `tasks.py` in MAN-3 is approved.

### N16. The egress row gets `node` and `role`, not `project_id`

Architecture section 5 says the egress row records `node_id` and `project_id`; the build plan and D283 say two fields from the tag, and the tag has `node_id` and `node_role` only. The row has
`node` and `role`. The project is one join away (`agent_nodes.project_id`). Adding `project_id` to the tag would change the tag contract again for little.
- Architect ruling: approved, D304. The egress row has `node` and `role`; the project is one join away. Architecture 5 corrected.

### N17. `usage_ledger.node_id` is the graph node, so the agent node goes in `detail`

`UsageIn.node_id` and `RouteContext.node_id` already mean the graph node (a function, a step, the root). The runtime node's id is therefore written as `detail.agent_node` and
`detail.agent_role`, only for a node's calls (the build plan says "node id into `detail`"). The orchestrator context key for the planner is `agent_node_id` / `agent_role` for the same reason.
- Architect ruling: approved, D304. The runtime node is `detail.agent_node` and `detail.agent_role`; `usage_ledger.node_id` stays the graph node.

### N18. The planner's stop token is cooperative

`call_json` had no `CancelToken`. One is now an optional argument all the way to the router (`JsonRequest.cancel`), honoured before every attempt, fallback and back-off, like a chat
turn's. It does not kill a connector's running process: for a chat the token is also bound to the spawned process, and doing that for a one-shot JSON call means a `cancel` argument through
`call_json_result` of the base connector, Claude, Codex and the stub. Nothing uses the token yet (the planner gets an identity and a token in MAN-5), so this was not widened. Open for the
architect: is a planner Stop that waits for the current call (at most the call's timeout, 120 s) acceptable, or should MAN-5 pay for the connector change?
- Architect ruling: not enough, D301. The cooperative token lets a running planner call go on for up to its timeout (120 s) and spend quota after a kill. MAN-5 adds `cancel` to `call_json_result` and the one-shot plan of the base connector, Claude, Codex and the stub so the token is bound to the process as a chat turn's is (D215), plus a registry of in-flight planner tokens that node stop, project stop and kill-all ask. Pause does not. D296 is not involved (the planner has no gate). MAN-3's part stays as built.

### N19. Pinned tests that changed

`test_engine_port_contract.py` (the exact field list of `CallTag`), `test_engine_spec.py` (the run-spec field list now has `node`) and `test_orchestrator_port.py` (the signature of
`AsyncConnector.call_json` now ends in `cancel`). Each is a list of names the package was meant to extend.
- Architect ruling: approved. Pinned lists were meant to be extended; each change was on purpose. MAN-8 will extend the `CallTag`/`PortSpec` pins again for D298.

### N20. `SUTRA_NODE_ID` is documented in ENVIRONMENT.md

`scripts/check_docs.py` fails on a `SUTRA_*` name in the source with no row. It is a name Sutra sets for a node's run; the server's own value of it is never passed on.
- Architect ruling: approved. The server's own `SUTRA_NODE_ID` is never passed on (`ProcessLauncher.environment` pops it): checked in the code.

## MAN-4. Kill switch and pause

Built: `orchestrator/killswitch.py` (`KillSwitch`: the two files; `NodeControl`: stop a node, pause, kill, resume, and the watcher), `orchestrator/api/projects.py` (the node routes),
`ops/nodes.py` (`sutra-pro nodes status|pause|kill|resume`), `TaskService.stop_node`, and the wiring (built only while `SUTRA_NODES_V1=1`). The ladder is the existing one: `stop_node` calls
`_stop`, which calls `launcher.stop`; nothing else signals a process. The tests drive it with `FakeLauncher` and the real `TaskService`.

### N21. The `task_gate` hook is pulled forward from MAN-5

"File present means no spawn" has to be true in MAN-4, and the only place a node's task is started is `TaskService._prepare_next`. So it has the optional `task_gate(conn, now, row)` that the
build plan puts in MAN-5, asked after `start_gate` in the same transaction. MAN-4 installs `NodeControl.gate` there (the files first, the table only when a file holds something back; an
ordinary task is never held). MAN-5's Conductor gate replaces the callable and must keep the rule. Flag off: the hook is None and the scheduler is byte for byte as it was.
- Architect ruling: approved, D303. MAN-5's Conductor gate asks `NodeControl.gate` first and adds its own checks: composed, never replaced. With a missing grant the gate also holds the node (D302, F1).

### N22. Routes and commands beyond the design's list

The design lists `pause-all`, `kill-all` and `nodes/{id}/stop`. Added: `GET /api/nodes/status` (the page needs to show the switch) and `POST /api/nodes/resume` (the design says "until the file is
removed" but gives the owner no button for it). `affected` means "nodes that now wait to start" for pause-all and "nodes stopped" for kill-all. Node stop answers `{stopped: false}` for a node whose
task is over and 404 only for an id that does not exist. All of them answer 404 `not_found` while the flag is off, before the token is looked at.
- Architect ruling: approved, D304. `GET /api/nodes/status` and `POST /api/nodes/resume` are in the design now (architecture 6); `affected` means what the note says. Reads need no token, as every read of the app (D305e).

### N23. Who acts on a KILL file made by hand

The Conductor's tick does not exist yet (MAN-5, MAN-7), so `NodeControl` has a small watcher of its own (one `lstat` every 2 s, started with the app, only with the flag on) and acts once at
start for a file that was left there. It deals with each file once (by its size and time stamp). When the Conductor arrives its tick should call `enforce()` and this loop can go. The command
line only writes and removes the files: a launch token is never on disk, so it cannot call the server, and the file is the one thing the server watches anyway. With the flag off nothing
looks at the files and the command says so.
- Architect ruling: decided, D303. The 2-second `NodeControl` watcher stays for good: the Conductor's tick may also call `enforce()`, but a stuck tick must not be able to hold back a kill. The command line only writes and removes the files. Also: the kill ladders must run together (F6): the code runs them one after the other, which makes a kill of 12 nodes take up to 144 s instead of about 12 s.

### N24. A stopped node's state is `cancelled`, the project is not touched

`NodeStore.mark_ended` moves a node to `cancelled` with the reason ("stopped by you", "stopped by the kill switch"). The projector's real state machine and the project state
(`stopped`) are MAN-5. Dependants of a stopped task are cancelled by the existing `settle_blocked` rule, as for any task that ended badly. A kill leaves queued nodes queued (they wait with the
sentence "Stopped: the kill switch is on ...") and they start by themselves after `resume`.
- Architect ruling: approved for MAN-4, with one change for MAN-5 (D303 d): a kill ends the project. Every project with a live node becomes `stopped`, its queued and blocked nodes are `cancelled`, and nothing starts by itself after resume; pause only holds. A node the owner or the kill switch stopped is never retried. The projector owns node state from MAN-5: a node is `cancelled` only when its task ended stopped (today `mark_ended` runs after `stop_node` even if the run had just ended well).

### N25. D296 names, fixed now

Nothing is detected yet (MAN-7). The words and audit names are constants in `nodes_store.py` so MAN-7, MAN-8 and MAN-15 share them: node `cancelled` with the reason "the computer went to sleep
before you answered" or "Sutra was closed before you answered"; one audit row `gate.refused` per open gate (actor `system`, decision `deny`), and `project.stopped` when the project stops because of it.
Both fit the existing audit table and its 200 character limit.

- Architect ruling: approved, D304. The constants stay in `nodes_store.py`; guardrails 8 lists the two audit actions.
- Architect ruling (found in review, no N item): code fix F5 (D305b), `gatekeeper.Plan.max_nodes` counts workers only (the design says 12 workers and reviewers on top), and F7, the new decisions D297 to D305 are registered in `docs/DECISIONS.md`, `docs/diagram/decisions.json` and `docs/design/traceability.json`. The full list of fixes before phase 2 is F1 to F7 in `build-plan.md`.

## Phase 2 (MAN-5 to MAN-7), built after the architect's rulings

### N26. The planner's `scope` and `needs` fields are NOT added (MAN-5, stopped on purpose)

build-plan MAN-5 says the planner's schema gets an optional `scope` and `needs` per step only while the flag is on. The step model is the library's `AssignmentStep` / the chat agent's
`AssignmentDraft`, whose JSON schema is derived from the model and pinned by the schema goldens and the transport-schema registry. Giving the flag-on planner a different schema means a
second model family (or a flag-aware schema generator) in `library/` and `agent/replies.py`, and the byte-identical promise for the flag-off prompt would then rest on a registry switch. That
is a design change, not a fix, so it is left out: the plan the Gatekeeper evaluates has no tiers, scope or needs (`ProjectStep` has none), grants are the role-table defaults, and a writer holds
"the whole folder" (it runs alone). Architect: decide whether the fields go into the library (and which goldens move), or whether the planner proposes scopes in a separate second call.

### N27. A request's output spec is the team's `output` setting; `auto` counts as `read` (MAN-5)

`ProjectService` needs each team's output spec BEFORE a run, but `J2_OUTPUT=auto` (the default) is decided by the engine per run. `projects.default_output_of` reads the team's and the global
`engine.json` `output`; a named type gives its `workspace`, `auto` and anything unreadable give `read`. The grant is a description (D299) and nothing enforces it yet, so this is the
cautious reading; MAN-10 (scopes, lanes) is where it must be exact.

### N28. A project's plan that needs the owner waits until MAN-8 (MAN-5)

A plan over the confirm threshold (more than five default-sized steps) makes the project `awaiting_approval`, its questions are stored as `approvals` rows with an audit row `gate.asked`,
and the task gate holds every node ("Waiting for your answer before this project starts"). There is no card and no route to answer yet (MAN-8), so such a project runs nothing until MAN-7's
expiry (24 h) or a restart refuses the gate (D296). Flag-on only.

### N29. Smaller points of MAN-5

- A plan the Gatekeeper refuses makes a `failed` project with no node; the runner then tells the owner "I could not start that work: <why>" and makes no task.
- The planner's node row is made at adoption (`role planner`, `runtime inline`, `state done`); a request that ends with no project leaves only the id in the usage and egress rows.
- A cancelled planner call ends the turn with the existing "Something went wrong on my side" line: a new template line would change the pinned `LINES` set.
- Resuming a request after an approval of a chart change plans through `agent.resume`, which has no identity or token yet (not wired).
- `TaskService._launch` no longer calls `_stop` from inside the start loop: `_stop` drains through the watcher, whose `after_drain` is `start_ready`, and the start loop holds that lock (the first
  version of M1 deadlocked on it). `_stop_from_launch` does the same steps without it.
- The node's state is the projector's from MAN-5: `sync_task` maps the task's status to the node's, so a node is `cancelled` only when its task ended stopped or was cancelled (D303).
- `test_projects_parallel` of the plan is covered by `test_conductor_gate.py` (three at a time, FIFO, a dependant waits, `max_runs` bounds everything), which runs the real scheduler.

### Notes on the review items

- m10 (for MAN-7): `reconcile_projects` must settle `agent_nodes` whose task `reconcile` ended while the app was down, including a node the launch guard abandoned (`mark_ended` stopped) and
  one left `leased` with no pid; it runs after `reconcile` and never starts a task.
- F3 vs the build plan's wording: with a read-only owner a worker has a folder to read, so its tier-4 grant is `{0, 1, 4}`; `{0, 4}` is the no-folder owner. The test says so.
- m1: a database `INSERT OR REPLACE` on `node_messages` really does remove the old row without firing the append-only trigger (SQLite fires delete triggers on REPLACE only with
  `recursive_triggers` on). The code never writes that spelling and a test fails the day it does; turning the pragma on for the whole app was not done (it would change every other trigger).

### N30. MAN-6: what a dependant is given, and where the intake runs

- The hand-off reaches a dependant as a FILE: after the intake accepts `handoff.json`, the server writes `handoff.accepted.json` (validated, scrubbed, with a plain note that it is data) into the
  node's run folder, and the existing `upstream` listing offers it (`_files_of` lists every top-level file that is not run plumbing; `handoff.json` was added to `RUN_FOLDER_INTERNALS`, so
  the node's own raw file is never offered). The host copies it under `upstream/<run id>/` and its one-line upstream message names it. Nothing goes into `framing` (D265). The design's
  `RunSpec.upstream` "adds the hand-off" is therefore the file name in `files`, not a new field.
- The intake runs INSIDE the projector's transaction (`ProjectService._hand_off` from `sync_task`), because the node's state, the message and the dependants must change together. The checksum of
  every listed file is recomputed there (files over 64 MB are checked for size only, and counted as `unchecked`); a very large hand-off therefore holds the writer for the time it takes to read
  those files. MAN-12's load test should look at it.
- A node whose run ended well and whose hand-off is missing or refused is `failed` (audit `handoff.refused`), is retried once (MAN-7) and its dependants are cancelled only when the retry is used up.
- `finish.NODE_STEPS` (not `STEPS`) holds the `handoff` step: a run that is not a node gets no new trace line.

### N31. MAN-7: what is built and what is not

Built: leases checked by `ProjectService.tick` against the task's last event (any event, heartbeat included, extends it); a node silent for 90 s goes `expired`, its process through the stop ladder, and
is retried once as a new attempt of the same node (`TaskService.retry_in`, `agent_nodes.task_id` re-pointed in the same transaction, dependants' `depends_on` re-pointed so they wait for the new
attempt); a tick that comes more than half a lease late is a sleeping computer (leases extended once per node); a node that loses its lease twice stops the project (audit `trigger.lease_lost`, D303 e);
a crash, a refused hand-off and "the app was closed" are retried once, the owner's stop and the kill switch never; `stop_branch` (default) and `stop_all`; D296 (`refuse_open_gates`: tick gap, 24 h expiry,
restart); `reconcile_projects` after `reconcile` (nodes follow their tasks, leases restart from now, a reserved node with no task is cancelled, an open gate is refused with "Sutra was closed before
you answered"). Wired in `start_services` / `stop_services`.

Open points for the architect:
- **The receipt of D296 is a plain note** in the org chat (`I stopped the project "<title>": <reason>. Start it again when you are back.`), once per project. A card kind for it belongs with
  `NodeApprovalCard` in MAN-8.
- **Nothing can open a gate yet** except the plan gate's estimate question (stored by MAN-5): D296 is tested against approval rows made in the tests. The "system permission" gate is MAN-15.
- **`failure_policy` has no way to be set to `stop_all` yet** (the planner has no such field, N26); the code and its tests exist.
- **The lease clock** is the task's `last_event_at` (the projector sets it per batch), not a column the engine writes: `agent_nodes.last_beat_at` is a copy for the page, refreshed by the tick.
- **A retry may start at once**: `stop_node` ends with `start_ready`, so the new attempt can already be `leased` when `tick` returns. The tests say so.
- The `retries` cap is read from the project's `caps_json` (default 1, D273); there is no `max_nodes` bound on retries beyond it.
