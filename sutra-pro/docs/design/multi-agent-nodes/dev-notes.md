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
- Architect ruling: right to stop, decided, D306. The fields do NOT go into `AssignmentDraft` (that moves the `chat_turn` schema, the decide and assign prompts and the flag-off goldens) and there is no flag-aware schema generator. They come from a separate small stage D, the "node plan", a second planner call that exists only with the flag on and only for a request with two or more steps. The org chat agent gets `node_plan(request, drafts)`; the runner calls it in `_hand_off` after the assignments are final (stage C, or the approved resume) and before `_reserve_project`. Its reply is a new closed family `node_plan` in `agent/replies.py` (registered like `chat_turn`): `steps: [{ref, scope: [<=5 relative paths], needs: [sutra|github, <=2]}]`; its prompt is a fifth template `nodeplan.md` added to `prompts.TEMPLATES` and `PLACEHOLDERS` (the pinned list is extended on purpose, as N19; the four existing templates and `chat_turn.v1.json` stay byte-identical, and `docs/schemas/` only GAINS `node_plan.v1.json` and one line in `index.json`: a test checks that no existing schema file changed). The call carries the planner's identity and stop token (D301) and has its own cap of 2 attempts. The code only reads it as a request: `scope` goes through `normalize_scope` into `StepRequest.scope` and `needs` into `StepRequest.tool_profile` (`github` also `wants={4}`); the Gatekeeper and the owner decide, a planner can never add a tier. A reply that does not validate is asked again with the reasons; a stage that fails gives the defaults (no scope, no needs) and an audit row `plan.defaults`; the project never fails because of it. Built in MAN-8 (it is the input of the plan gate's tier-4 and wide-scope questions and needs the tier-4 delivery), `scope` is carried and shown in MAN-8 and enforced in MAN-10. What the plan gate can and cannot ask before then: it can ask the estimate question only (and refuse a plan over 12 workers); it cannot ask tier 4 or a wide scope, because no step carries them; a writer holds the whole folder and (from MAN-10, with lanes) runs alone. Rejected: derivation by the Gatekeeper from the output specs alone (they say `read` or `edit`, not which paths or tools: there is nothing to derive), and a model-free owner-typed scope (the project page may add it later, MAN-13).

### N27. A request's output spec is the team's `output` setting; `auto` counts as `read` (MAN-5)

`ProjectService` needs each team's output spec BEFORE a run, but `J2_OUTPUT=auto` (the default) is decided by the engine per run. `projects.default_output_of` reads the team's and the global
`engine.json` `output`; a named type gives its `workspace`, `auto` and anything unreadable give `read`. The grant is a description (D299) and nothing enforces it yet, so this is the
cautious reading; MAN-10 (scopes, lanes) is where it must be exact.
- Architect ruling: approved for MAN-5 to MAN-9, decided, D307. Reading `auto` as `read` is right ONLY while the grant is a description: it is not "cautious" for scheduling, because an `auto` team may pick a type that changes the owner's folder. Rules: (1) the `grant.issued` row says "output auto (decided in the run)" so the record never claims more than is known (code fix G10); (2) MAN-10, with lanes on, treats a worker whose output is `auto` as a POSSIBLE writer: with no declared scope it holds the whole folder and runs alone (D260), and the conflict edges are derived on that reading; with lanes off, parallelism of different teams is exactly today's; (3) the page draws a conflict edge only when lanes are on (the edges are stored from MAN-5 and enforced from MAN-10). Also found while checking this (no N item): the org chat agent's calls are tagged `workspace="edit"` (D127), so the planner can today READ and, with "read and change", EDIT the owner's folder; the design said the planner touches no folder. Decided, D307: the planner has no stored grant; with the flag on its calls are tagged `workspace="read"` (code fix G6), flag off is as today.

### N28. A project's plan that needs the owner waits until MAN-8 (MAN-5)

A plan over the confirm threshold (more than five default-sized steps) makes the project `awaiting_approval`, its questions are stored as `approvals` rows with an audit row `gate.asked`,
and the task gate holds every node ("Waiting for your answer before this project starts"). There is no card and no route to answer yet (MAN-8), so such a project runs nothing until MAN-7's
expiry (24 h) or a restart refuses the gate (D296). Flag-on only.
- Architect ruling: holding is the right default, decided, D308, with one fix. Refusing or skipping would either throw away the owner's plan (the rows are exactly what MAN-8 reads, so holding loses nothing) or start spending nobody approved (the opposite of D300). What was wrong is "silent": a plan of six ordinary steps (6 x 100 > 500) is a normal request and it would just sit. Code fix G7: the request's reply says it in plain words ("I set up the project <title>. It is estimated at about N credits, which is over 500, so it waits for your OK. Nothing has started. If nobody answers it is cancelled after 24 hours.") as a new Sutra line `project_waits`, and the 24 h end or a restart already leaves the D296 note. MAN-8 is the first package of phase 3 and replaces the line by the card; the flag stays off in every beta the owner is given until MAN-8 is in. MAN-8 also owns what the code does not do yet: the answer path (re-run `evaluate` with `approved`, rewrite `grants_json` of nodes that have not spawned, move `awaiting_approval` nodes to `planned` or `queued` by their task, project to `running`), Decide for me (the runner passes `decide_for_me` to `reserve` from the request's `J2_DECIDE_FOR_ME`; today it is always 0), and the rule that the estimate question is stored as kind `plan_estimate`, tier 5, with the answers allow once or deny only (D270: tier 5 is never "for the project").

### N29. Smaller points of MAN-5

- A plan the Gatekeeper refuses makes a `failed` project with no node; the runner then tells the owner "I could not start that work: <why>" and makes no task.
- The planner's node row is made at adoption (`role planner`, `runtime inline`, `state done`); a request that ends with no project leaves only the id in the usage and egress rows.
- A cancelled planner call ends the turn with the existing "Something went wrong on my side" line: a new template line would change the pinned `LINES` set.
- Resuming a request after an approval of a chart change plans through `agent.resume`, which has no identity or token yet (not wired).
- `TaskService._launch` no longer calls `_stop` from inside the start loop: `_stop` drains through the watcher, whose `after_drain` is `start_ready`, and the start loop holds that lock (the first
  version of M1 deadlocked on it). `_stop_from_launch` does the same steps without it.
- The node's state is the projector's from MAN-5: `sync_task` maps the task's status to the node's, so a node is `cancelled` only when its task ended stopped or was cancelled (D303).
- `test_projects_parallel` of the plan is covered by `test_conductor_gate.py` (three at a time, FIFO, a dependant waits, `max_runs` bounds everything), which runs the real scheduler.
- Architect ruling: approved, with three changes. (a) A refused plan is a `failed` project with no node and the owner is told why: approved (it is the deny-by-default answer; the line is the existing `task_failed`). (b) A cancelled planner call must not end with "Something went wrong on my side": the owner pressed Stop. Code fix G7 adds the Sutra line `stopped` ("Stopped. I did not start anything."); the pinned `LINES` set is extended on purpose (N19). D301 said "ends the request as stopped". (c) The resumed request must carry the planner's identity and stop token like a fresh one, otherwise a kill cannot stop its call and its planner node is never made: code fix G5 (`_as_planner` also in `_decide_flow` before `agent.resume`). Approved as built: the planner node row at adoption; the `_launch` rewrite (`_stop_from_launch`, the two looks before and after the start): it also changes flag-off behaviour in one way (a task that ended while its process was starting no longer leaves that process running), which is a fix for every task, so the design now says "the same behaviour" for the flag-off scheduler instead of "byte for byte" (architecture 9); the node follows its task through `sync_task` (D303 d: `cancelled` only when the task ended stopped or cancelled); `test_projects_parallel` is covered by `test_conductor_gate.py` because it runs the real scheduler (the build plan's file name is corrected).

### Notes on the review items

- m10 (for MAN-7): `reconcile_projects` must settle `agent_nodes` whose task `reconcile` ended while the app was down, including a node the launch guard abandoned (`mark_ended` stopped) and
  one left `leased` with no pid; it runs after `reconcile` and never starts a task.
- Architect ruling: m10 is met by `reconcile_projects` as built (a node follows its task through `sync_task`, a reserved node with no task is cancelled, an open gate is refused, leases restart from now, nothing is started). Approved.
- F3 vs the build plan's wording: with a read-only owner a worker has a folder to read, so its tier-4 grant is `{0, 1, 4}`; `{0, 4}` is the no-folder owner. The test says so.
- Architect ruling: the developer is right and the build plan was wrong. A read-only owner with a folder gives folder `read`, so tier 1, so `{0, 1, 4}`; only the no-folder owner gets `{0, 4}`. The F3 line in the build plan is corrected; no code change (D298 is unchanged).
- m1: a database `INSERT OR REPLACE` on `node_messages` really does remove the old row without firing the append-only trigger (SQLite fires delete triggers on REPLACE only with
  `recursive_triggers` on). The code never writes that spelling and a test fails the day it does; turning the pragma on for the whole app was not done (it would change every other trigger).
- Architect ruling: approved as it is, D312. The guard is the test (a scan of the code for `OR REPLACE` on the two append-only tables, plus a behaviour test); the app's pragma stays off. It is written in architecture section 7 as a known limit: the triggers stop UPDATE and DELETE, not a REPLACE, and the owner editing the database by hand is outside the threat model. If the schema is touched again anyway, v7 adds a `BEFORE INSERT` trigger that raises when the same key exists; a migration is not worth it for this alone.

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
- Architect ruling: the FILE approach is approved (design text corrected: dependants are given `handoff.accepted.json` through the existing `upstream` listing, `RunSpec.upstream` gets no new field; D265 holds). The intake inside the projector's transaction is approved (state, message and dependants must change together), with a limit, decided, D309: the file hashes of one hand-off share a budget of 64 MB in all (not 64 MB each: 200 files could hold the writer for minutes); past the budget a file is checked by size only and counted as `unchecked` (code fix G9; MAN-12's load test measures it). Two things the notes did not say, found in the code: (1) `finish.run_steps` skips every later step when one step takes more than 10 s, and the `handoff` step comes LAST, so a slow `agent_views` or `catalog` would leave a node with no hand-off, fail it and re-run the whole team. Code fix G1: for a node the `handoff` step runs first (a non-node run keeps its order). (2) The host lists only the top-level files of the run folder; what a worker changed in the owner's folder is not in the hand-off. That is MAN-10's job (D309): `handoff/1` gets an optional `changes` list of paths and the intake's closed key set grows with it (host and server ship together). A body over 16 KB is stored as `{file, sha256, bytes}` where the sha is of the message text, not of the file; MAN-11 (the reader of that reference) makes the two agree (hash the file bytes). A hand-off whose `status` is `blocked` is not a success: from MAN-11 (the first writer of it) the node ends `failed`, never retried.

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
- Architect ruling: what is built is approved against the design (leases from the task's last event, one retry as a new attempt with `agent_nodes.task_id` re-pointed, `stop_branch` and `stop_all`, D296 by tick gap, 24 h and restart, `reconcile_projects`, the lease-twice trigger). The open points:
  - **Receipt of D296:** decided, D311. A plain note in the org chat IS the receipt, not a stopgap: a receipt tells, it asks nothing, and `needs_you` is for questions. No receipt card kind is built in MAN-8 or MAN-15; the project page (MAN-13) shows `stop_reason` and the audit rows. D296's words "one receipt card" are amended.
  - **Nothing can open a gate yet:** approved; MAN-8 (plan, grant, estimate) and MAN-15 (system) open them as `approvals` rows, so `refuse_open_gates` already covers both (the system gate is stored with tier 1 or 2, since `open_approval` takes tiers 1 to 5).
  - **`failure_policy` is unreachable:** decided, D310. The planner never sets it (a model does not choose how a project fails). The owner sets it: an optional `failure_policy` in `POST /api/projects` (D255's route, which no package built: it is now in MAN-13 with the page), default `stop_branch`; a request made in the chat is always `stop_branch`. The code and its tests stay.
  - **Lease clock = the task's `last_event_at`:** approved. `last_beat_at` is a copy for the page.
  - **A retry may start at once:** approved.
  - **Wall clock for the sleep check:** decided, D311. The design said "monotonic gap"; a monotonic clock does not run while the computer sleeps on macOS and Linux, so it would never see a sleep. The tick uses the injected wall clock (`Clock`). A clock jump forward gives a false "slept", which is the safe side (a gate is refused, a lease is extended once). Code fix G2: `_last_tick` is set when a tick ENDS, not when it starts: today the tick's own ladders (up to 12 s each, one `refuse_open_gates` after another) count as sleep and can refuse an open gate falsely.
  - Found in the review, not in the notes (code fixes G3, G4, G8): a node held by the gate for "no valid grant" is never failed (D302 said the Conductor fails it with `grant.denied`; today the project sits for ever); `TaskService.retry_in` makes the new attempt with no `depends_on`, so a retried dependant loses the upstream hand-off of the steps it waited for; `reserve` for a request that already has a failed or stopped project returns "ok" with no nodes, and `link_task` ignores a step with no node, so those tasks would run as ordinary tasks past the gate.

### Architect rulings found in the review of phase 2 (no N item)

- Architect ruling: the fixes before phase 3 are G1 to G10 and the move-only split C0, listed in `build-plan.md` ("Before phase 3"). In short: G1 the `handoff` step runs first for a node; G2 the tick measures its gap from the end of the last tick; G3 a node held for "no valid grant" is failed with `grant.denied`; G4 a node's retry keeps its dependencies (upstream); G5 the resumed request carries the planner's identity and token; G6 flag-on planner calls are `workspace=read`; G7 the lines `stopped` and `project_waits`; G8 `reserve` and `link_task` fail closed; G9 the 64 MB hash budget; G10 `grant.issued` says "output auto"; G11 register D306 to D312; C0 split `projects.py` into `projects.py` and `conductor.py`. Everything else in the code agrees with the design (lifecycle, lease, one scheduler and gate composition, `node_messages` and D297, hand-off flow, failure rows N1 to N12 and N14, D296, D301 to D303).
- Architect ruling: the Conductor lives in `projects.py` (`gate`, `sync_task`, `tick`, `refuse_open_gates`, `stop`), not in `conductor.py` as the component table said. Decided, D312: the design now says so, and the split into `conductor.py` is done first in phase 3 (C0, a move with no change of behaviour) because MAN-8 to MAN-11 add to the gate and the tick. The node states `ready` and `torn_down` of the first state diagram are not stored states (`queued` is "ready" and `torn_down_at` is a column); `handing_off` exists only inside one transaction and no reader sees it. Architecture 3.3 is corrected. The project is made by `reserve` (before the tasks) and each task is linked by `link_task` in the transaction that makes it, not by one `adopt` in one transaction: approved, because the tasks are made by the chat agent's unchanged runner one transaction each; a crash between them is settled by `reconcile_projects`.

## Phase 2 review round (the fixes before phase 3, then MAN-8, MAN-9 and MAN-15)

### N32. The planner's Stop never reached the runner (G5, G7)
The D301 handling in the runner (`except CallCancelledError`) was dead code: the agent's `_stage` turned every connector error, the owner's Stop included, into a `ConnectorFailure`, so a stop ended as "I can't reach Claude (the turn was stopped)". Fixed in the agent: `ports.was_stopped(exc)` (code `cancelled`, not retryable) lets it go up as it is, so the runner ends the turn with the new line `stopped`. Tests: `test_resumed_planner.py` (fresh and resumed request).
- Architect ruling: accepted. It is the fix D301 and G5/G7 asked for (a stop must reach the runner and end as `stopped`). No change.

### N33. `project_waits` cannot be reached at the default threshold yet (G7)
The chat agent plans at most 5 steps (`MAX_ASSIGNMENTS`), and 5 x the slice of 100 is 500, which is not over the confirm threshold of 500. So the architect's test "a six-step plan's reply says it waits" cannot be made through the chat; the test lowers the threshold. The line is reachable at the default only once a step has its own estimate (the node plan stage, MAN-8) or a larger slice (MAN-9). The two lines are in a separate table, `planner.NODE_LINES`, not in `LINES`: the coordinator's rule was that the flag-off set stays as it was; `line()` and `matches_template` read both. `Reservation` gained `title` and `waits`; the estimate question stores `credits` and `limit` in its request so a request that is planned again finds the numbers.
- Architect ruling: accepted, and the cause is fixed in D318: the threshold was unreachable (5 default steps are 500, not over 500). Default becomes 400 (G18); the test then needs no lowered threshold. The `NODE_LINES` table is accepted (the flag-off set stays as it was).

### N34. How the tick gap is measured with a given `now` (G2)
`tick(now=...)` sets the next gap from `now` plus what the tick took on the clock, so a test that passes `now` and a real run give the same reading. The tick's own work is never a sleep.
- Architect ruling: accepted. No change.

### N35. G3 and G8 details
G3 also fails nodes that wait in `awaiting_approval` or `awaiting_system` with a broken grant (a grant is rewritten only by the answer path of MAN-8), never retries (`_fail(retry=False)`), and writes `grant.denied` with fixed words. G8 and B2 are one change: `reserve` returns a not-ok reservation for any project that has ended (failed, stopped, done) and `link_task` raises (`AppError busy`) for a step with no node and for a node that has its task already.
- Architect ruling: accepted. G3 and G8 as built match D310.

### N36. B1: what "contained" means
`Tx.savepoint()` (new, in `db.py`) undoes the writes and the events of a part that failed. `sync_task` runs `_sync_task` in one; on an exception the node is ended `failed` with the audit row `node.error` (fixed words, nothing from the node), never retried, its dependants are cancelled and the project is settled, each in its own savepoint; the task's own change is not lost. A hand-off that is refused (`handoff.refused`) still follows the normal rule, one retry. `read_handoff` is total: deep nesting, bytes that are not Unicode, a lone surrogate, a path that cannot be compared are `HandoffRefused`. A retry for an archived team (`AppError` from `retry_in`) ends the node `failed` with "(it could not be tried again)".
- Architect ruling: accepted. A node ends `failed` with fixed words and nothing from the node; the savepoint is the right tool.

### N37. MJ5: the hand-off is read before the transaction (a new hook in the projector)
`Projector.before_drain` (set by the wiring only while the flag is on) calls `ProjectService.prepare_handoff(task_id)` before `drain` opens its transaction: when the task is the run of a worker node and `handoff.json` is there, the file is read, checked and hashed and `handoff.accepted.json` is written outside any transaction; the result waits in a small dict, keyed by the file's stamp, until `_hand_off` uses it. A file that changed meanwhile, or a task that ended another way, is read again inside as before. The accepted file may exist for a node that is then refused for another reason; nothing gives it on.
- Architect ruling: accepted (MJ5). Note for MAN-12: the waiting dict is keyed by the file's stamp, so a changed file is read again inside; keep that test.

### N38. MJ7 and the audit names
A stop by the owner denies the open questions with the audit row `approval.denied` (actor owner); a stop by the system uses `gate.refused`. `_refuse_in` is the whole database part of the D296 refusal inside one transaction; the tick uses it, so the decision and the stop commit together. A project that is `awaiting_approval` with no open question is ended by the tick ("not approved: no question was left to answer"); the answer path of MAN-8 moves a project on in the transaction of the answer, so this never meets a project in the middle of an answer.
- Architect ruling: accepted. The audit names (`approval.denied` by the owner, `gate.refused` by the system) match guardrails 8.

### N39. Minor 2: a new value of `_stopped_by`
`TaskService.stop_node(..., by=)` records `system` for a lease that ran out, a kill and a stop the app decided. It is not `app`: the Heads up wording for `app` says "when the app closed". A `system` stop is listed as "stopped before it finished"; the owner's own stop is still never listed.
- Architect ruling: accepted. `system` is the right value for a stop the app decided.

### N40. Existing tests that changed on purpose
`test_a_nodes_folder_that_is_a_file_fails_closed` (Minor 3: it said `none`); `test_kill_all_says_when_the_file_could_not_be_written...` now expects the switch to read `kill` from memory; the two kill-switch tests that replaced `stop_node` pass the new `by` keyword on. Nothing was deleted or weakened: each now asserts the safer rule.
- Architect ruling: accepted. Each changed test now asserts the safer rule.

### N41. Minor 7, D313: where the hold is installed
With the flag off the wiring builds nothing. `start_services` looks at the database after the migration and installs `nodes_store.held_while_off` as the task gate only when some step of a project has not started (blocked or queued). An app that never made a project has `task_gate = None` exactly as before.
- Architect ruling: accepted, D313 (the owner's). The one read of `agent_nodes` at start with the flag off is what D313 allows; it amends D254.

### N42. D314: restart attempts are counted from the audit trail
No column was added: `node.restarted` rows are counted (`MAX_RESTARTS = 2`). `attempt - restarts <= retries` keeps the single real retry. A node whose task `reconcile` ended as stopped with "the app was closed" or crashed with "the app was closed while it ran" is a restart; a stop by the owner is not.
- Architect ruling: accepted, D314 (the owner's).

### N43. Known v1 limits recorded (m9)
`node_audit` and `node_messages` have no retention in v1 (they are append-only and a project is never deleted, D305); the size is small (words and numbers only) and a retention rule needs a decision about the append-only triggers, so it waits for a later version.
- Architect ruling: accepted. No retention in v1; revisit when the append-only triggers are touched (v7).

### N44. MAN-8: the node plan has no schema file in `docs/schemas`
The architect expected `node_plan.v1.json` there. The exporter only writes the families the library registers; `chat_turn` (registered by `agent/replies.py` too) has no file either, so the new family follows it and `docs/schemas/` is unchanged. A flag-on request with two or more steps makes ONE more model call (the node plan), so every existing flag-on test that scripts the planner now scripts that reply too (`NO_REQUESTS` in `test_projects_adopt.py`).
- Architect ruling: accepted, D316 (b). No `node_plan.v1.json`; D306's last sentence is amended. The extra model call for every flag-on request of two or more steps is the design's own (D306).

### N45. MAN-8: where the plan is kept
The answer path must evaluate the plan again, so the step requests are kept in `projects.caps_json["plan"]` (ref, team, scope, needs, estimate, depends_on). It is an internal key, left out of `ProjectOut.caps`. No migration: the other choice was a v7 column for a table that has not been released.
- Architect ruling: accepted, D316 (a). `caps_json["plan"]` is an internal input of the answer path, never shown, never edited after the project is made (D274). A v7 column is allowed if a later package needs more.

### N46. MAN-8: the Decide for me table
`gatekeeper.RULE_TABLE` is data (nine rows, a test walks it) and `decide_for_me_answer` is the function the reserve uses: tiers 0 to 3 and tier 4 are allowed for the project, a wide or missing scope is allowed once (the words say only "allowed" until MAN-10 can keep writers apart, D323), the plan estimate is allowed once up to the cap `project_credits` and never beyond, a permission of the computer and tier 6 are never answered, credits are never raised. The row `scope_violation` (`on_scope_violation()`, "quarantine") is the runtime rule of MAN-10 and is only data and a pure function until then; the row `slice_move` and `move_unspent` were removed (D324). The row `sutra_tools` is new (D325).
- Architect ruling: accepted, D319. The table matches D294 (cannot raise credits, cannot grant a permission of the computer, audited as `rule:decide_for_me`). Two additions: the estimate over `project_credits` stays open for the owner (D318, D319 b), and the switch must also read the owner's own setting (G13). The `scope_wide_or_missing` words must not say "runs alone" yet (G19, D323).

### N47. MAN-8: the card (built in the phase 3 follow-up, G12)
First built as a model only; NOT posted as a message of the org chat, the `needs_you` list does not count it, and the page does not draw it, so there is no UI test. The reason: the `ChatCard` union is part of recorded API shapes, and adding a kind there moves goldens for the flag-off app; it needs its own change with the page (MAN-13). A no to any question of the plan stops the project ("not approved: you said no"), also the tier-4 question of one step: the design said "a deny or expiry cancels the nodes"; cancelling only the one step was not asked for.
- Architect ruling: (1) NOT acceptable as the end of MAN-8: the card in the chat, `needs_you` and the page's rendering are built before phase 4 (D317, G12); the reason given (a new `ChatCard` kind moves flag-off shapes) does not hold, since an earlier kind was added the same way and a response with no such row keeps its bytes. Until then a flag-on beta goes to nobody who cannot call the API. (2) A no to any question stops the whole project: accepted for now because it fails to the safe side, but the design wants a per-step cancel for a question about one step (D315 b, P1, as D295's skip), and the card must say what a no does (G21).

### N48. MAN-8: the request carries `decide_for_me`
`ChatPost` has a new optional field `decide_for_me` (stored in the line's `meta` like `budget`). It is read only with the flag on; with it off the field is accepted and ignored. A hand-off, a plan step or a message of a node has no way to set it.
- Architect ruling: accepted, D316 (c), with G13: do not store the field when the flag is off, and read the owner's own Decide for me setting as well, because no screen sends this field.

### N49. Existing tests extended on purpose in this round
`test_engine_port_contract.py` (`PortSpec.tools`), the node block goldens (`tool_profile`), `test_config.py` (`project_credits`), the two budget assertions (`budget_credits` is now the sum of the slices). Nothing was removed or weakened.
- Architect ruling: accepted. Pinned lists were meant to be extended (N19). `test_config.py` also changes for G18.

### N50. MAN-9: what changed in meaning, and what is thin
`projects.budget_credits` is now the ceiling, the sum of the slices; the owner's own number (each run's `J2_BUDGET`, D252) is each slice and is kept as `caps.owner_budget`. The slice reaches the run as `J2_BUDGET` and `J2_BUDGET_CAP` at `_run_spec`, so a run cannot raise itself (P25); the only test of "no raise without the Requester" is that these two settings are written and the task's own settings are not rewritten: the engine's cap behaviour is the existing D251 one and was not re-tested. The triggers say their words in a plain note (D311), not a card. `make_slices` and `move_unspent` are pure and tested; nothing calls `move_unspent` yet (the move is a rule for a later package that spends). Project dollars are read from `usage_ledger` through the nodes' tasks; with no `budget_usd` they are not limited.
- Architect ruling: accepted with limits, D320. A slice is final (no raise card: the budget gate moves to Non-goals for v1); the ceiling is per attempt; the "fit" check is a guard. The missing engine re-test of "no raise" is accepted: J2's own Decide for me waits for the Requester on a raise (P25) and `J2_BUDGET_CAP` equals the slice, so the Sutra-side test (both settings reach `task.json`) is the right proof. Two real gaps found: a node that hit its cap can still end `done` (G14, D321 a) and the project wall time counts from creation (G15, D321 b).

### N51. MAN-15: what is not verified
Everything uses fake adapters and a patched platform. NOT verified: a real macOS Files & Folders dialog, a real Controlled folder access block, a real elevated process, the settings pages the adapters open (`x-apple.systempreferences:` and `windowsdefender://`), and the page. The late-refusal check (`is_permission_failure`) reads the words of an outcome (EPERM, WinError 5, "Operation not permitted", "Access is denied", "Permission denied"), so an unrelated crash that quotes one of them is also read as a permission need. `oslayer` has no "app location" helper yet: nothing asks for it.
- Architect ruling: accepted with changes, D322. Fix before phase 4: G16 (probe time limit, no task for an ended project), G17 (late card "Check again" must not clear while the folder refuses). Before publish: P3, P5 (the manual check). `is_permission_failure` reading words is accepted: a false positive makes a node wait for a card, which the owner can skip; the words list stays short.

## Phase 3 follow-up (G12 to G22, P1 to P3, M1 to M5, D324, D325)

### N52. G12: the card is a chat message
One `node_approval` card for each open question, written by `ProjectService.sync_cards` in the transaction that opens the question and marked answered (it points at itself, as a card decided without a line does) when the question is answered or ends. `needs_you` and its count include it (no new field: the item carries `message_id`); `NodeApprovalCard` joined `ChatCard` and `NeedsYouOut.kind` gained `node_approval`. The page draws buttons that post to the answer route, or to the check and skip routes for a permission. A flag-off app has no such row, so no response changes. The reply line says every kind of question (`project_waits`, `project_asks`, `project_system`).

### N53. P1, M1: a no is as wide as the question
A no to a question about one step (tier 4, wide scope, the app's own data, a permission) cancels that step and the steps that wait for it; a no to the estimate, an expiry, a stop and a closed laptop stop the project. A late permission question that runs out, or meets a sleep, only ends: healthy steps keep their work, and only the failed step's dependants are cancelled (as with any failure). A skipped permission cancels every step it names; an answer never releases a step that an open permission question still names.

### N54. D324 as built
`budgets.chain_spend` counts a node's model calls and dollars over its task chain; `slice_left` is the slice minus those calls. `_run_spec` gives a retry `J2_BUDGET = J2_BUDGET_CAP = slice_left` (at least 1); `_retry` refuses a node with nothing left, with the words "That step used up all its credits". The credit counted for a call is a stand-in until the host can report J2's own credits. `snapshot().spend` and the dollar limit use `project_spend`.

### N55. G14, G15: caps
A run whose meter fired ends `crashed` (outcome in plain words: "stopped: this step used up its model calls / used up its dollars / ran out of time"), so it hands nothing on. `NodeMeter.begin` checks and counts a call under one lock; the planned "count spawns, not asks" was not built. The project wall time counts from the first node start and leaves out paused time (from the audit rows `project.paused` and `project.resumed`).

### N56. D325 and the network
`sutra` is only a question (`sutra_tools`). Not changed: J2's builder tools (`WebFetch`, `WebSearch`, `Bash`) reach the network from inside the CLI (D299); the egress scrub covers the prompt text only, so what such a tool fetches or sends is not scrubbed. The engine's `calls.jsonl` keeps the tool names and inputs; MAN-14 turns them into audit rows.

### N57. Minors: what was done and what was not
Done: m1 (a late answer is audited as a refusal), m2 (a permission question has its own two routes; the generic route is 422), m3 (see N53), m4 (the steps say Sutra Pro and name `claude` and `codex`; the card promises no button), m5 (only the outcome prefix the host writes, "Your computer did not allow it", counts as a permission need), m7, m8, m9 (atomic meter), m10, m11 (`nodes resume` leaves `nodes.resume` next to the folder so a running app drops a switch it holds in memory; a nodes path that is a file gives a plain error), m12, m13. NOT done on purpose: m6 (iCloud Drive and `/Volumes` are not probed and the write probe is in the folder root: D322 a and b say so), the Windows probe still tests Sutra's own process, not the `claude` and `codex` programs that write (the manual check P5 must say whether Controlled folder access blocks them), `HandoffRefused` reasons still say "hand-off" in a few places. Known limit: a J2 run that crashes from an OS refusal is marked only when J2's error text starts like a Python OSError (`[Errno 1]`, `[Errno 13]`, `[WinError 5]`, `PermissionError`); a tool refused inside the CLI is not seen.

### N58. Live checklist addition (m15)
Before MAN-15 is called verified on a real computer: (a) the Claude and Codex command-line programs accept tools together with a JSON-schema call (the engine port puts the app tools on agent turns that may carry a schema); (b) the macOS Files & Folders dialog appears for the program that writes, not only for Sutra Pro; (c) Windows Controlled folder access with `claude` and `codex`.


## Phase 4 (MAN-10 to MAN-14; D326 to D331)

### N59. MAN-10: leases, lanes and scope enforcement
Leases are rows (D328): a node's `writes_json` and state; an `expired` node holds its lease until it is torn down. Overlap is compared without case and with `/` for `\`, so Windows spellings (`Site\Index.html`, `site/index.html`) are one place. Lanes (`SUTRA_NODES_LANES`) only let two steps of one team run together; the unique index `(dept_id, lane)` did not move. The "runs alone" words are true now and are used.
Violation attribution is a deviation from the design's per-node idea (D329): the host's folder watch cannot say which of two parallel writers wrote a path, so a path is a violation only when NO writer of the project owns it (the union of the writers' scopes). A node that writes inside another writer's scope is therefore not caught by this check; the leases already keep overlapping writers apart, and the narrowed edit tools of Claude (the Codex connector has no such narrowing) are the second wall. The probe file `.sutra-probe-*` is never a change. NOT verified: a real folder watch on a real project; a real Claude or Codex program writing outside its scope; Windows long paths and short (8.3) names in the comparison (only the spellings above are tested).

### N60. MAN-11: the reviewer
A light host (`python -m sutra_app.nodes`): same files and events as an engine run, one model call, a stop line or `KILL` ends it, it writes only its own files. The verdict is a closed typed object read at the end (at most 8 KB); only the enum and the step names matter. Independence is picked from the usage ledger by provider; with one provider only, the review says "not independent". `changes` and `reject` open one question (kind `review`) that Decide for me never answers; a yes sends the named steps back (two loops), a no ends the project as it is. NOT verified: a real reviewer model, a real second provider, the verdict words on the page with real text.

### N61. MAN-12: slots, coalescing and the load numbers
Numbers (fakes, one machine, `tests/orchestrator/test_nodes_load.py`, 24 stand-in nodes, 40 rounds, 8 threads): writes to `tasks` 960 without coalescing and 72 with it; `StoreBusy` 0; no gap in the event bus for a page that replays after every round; a hand-off taken in at most 0.046 s. The server router gets its slot pool in the wiring because the connector factory is pinned not to read extra settings (D331). NOT verified: two real Sutra processes sharing real Claude programs, Windows `msvcrt.locking` slots, and anything with real model latency: these numbers prove the database and the bus, not the providers.

### N62. MAN-13: the page and the route
Decided in D326. Two deviations from the architecture table: `POST /api/projects` answers `202 {message_id, turn}` (a project cannot exist before its plan), and the page is mounted by its own function (`ui.mount_project_page`) so the pinned mount test and every flag-off page stay as they were. `request_id` is not a field. The page has three layers (store, view, client) with node tests (`project_store.test.js`, `project_view.test.js`, `project_page.test.js`) and a route test; the words avoid "node", "lease", "tier", "grant" and "gate" (tested). NOT verified: the page in a real browser (no browser smoke was run: the beta, by hand), the layout at phone width, dark and light themes, a long project with many steps.

### N63. MAN-14: the tool-call audit
Decided in D327. What it covers: the name, kind and a file's base name of each tool call of a node, as audit rows at the node's end (and at a retry). What it does not cover (the owner's question about D325): J2's own builder tools (`WebFetch`, `WebSearch`, `Bash`) still reach the network from inside the CLI; Sutra's egress scrub covers the prompt text it sends, not what a tool fetches or sends, and `calls.jsonl` still holds tool inputs unscrubbed. The audit shows THAT a tool was used. Codex reports the kind of tool only, so its rows have no tool name beyond the kind. NOT verified: a real Claude or Codex run writing `tools.jsonl` (the router hook is tested with the connector's own event shape, not a live program).

### N64. Not done in phase 4
m6 of the phase 3 review (a conscious skip, recorded earlier); a page that lists projects; browser smoke; P4 (real call counts and minutes), P5 (the manual check on a real Mac and Windows) and the live checklist of N58 are still open and belong to the beta.


## Architect's review of phase 4 (D332 to D341)

### N65. Found in the review, not in the developer's notes
The grant gate after a `needs.json` (D270, D315 d) was not built and was not listed: no node can ask for more in v1, so it moves to Non-goals (D335). The hand-off `files` list included `tools.jsonl` (G23, D339). The host's "Your computer did not allow it" prefix applies to ordinary runs too (G24, D340). The reviewer's independence label came from the host's guess and not from the Conductor (G25, D338). A node whose folder cannot be read by git, or whose changes are many, is not checked for scope and says nothing (G26, D336). Leases hold among the steps of projects and not against ordinary tasks of other teams (D337). N56 and N63 say the scrub "covers the prompt text": for an engine step's own prompts it only observes (byte-identical, an audit row counts shapes), so the true sentence is in D339.

### N66. Beta conditions and what is not verified
Conditions are in D341 and in the OPERATIONS note. Not verified, and so not to be called working: a real folder watch on a real project, Claude's `Edit(path/**)` rules with a real program, a real Codex step outside its scope, a real reviewer on two providers, the page in a real browser (phone width, dark and light), Windows `msvcrt` slots, Windows long and short names in the scope comparison, real model latency under the load test, the real first-start dialogs on a Mac and Windows (P5), real call counts and minutes (P4).
