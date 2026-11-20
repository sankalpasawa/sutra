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

### N2. Columns the design names elsewhere but the table list did not show (additive, done)

The migration is "never edited later", so what the later packages need is in it now:

- `projects.decide_for_me` (0 or 1): D294 and guardrails 5.1 say the switch lives on the project row; the table list in architecture.md section 7 left it out.
- `projects.paused` (0 or 1): `POST /api/projects/{id}/pause` needs somewhere to keep "paused", and the status list has no `paused` value (a paused project is still `running`).
- `projects.review_loops` (count): "review loops ... counted in `projects` rows" (architecture.md 4.4).
- `approvals.created_at`: for the expiry clock and the card's age.

### N3. Append-only triggers on `node_messages` as well as `node_audit` (small addition, done)

D264 says messages are append-only; the design's data model only gave triggers to `node_audit`. A table that is only appended to by the server is cheaper to trust with the
rule written into it, as `atom_ledger` does. If MAN-6 needs to redact a stored message it must scrub before it stores (which the design already says), not edit afterwards.

### N4. `docs/design/traceability.json` was out of date before this work

The committed file said 200 decisions while the log was at D252. Registering D253 to D296 meant running `scripts/build_traceability.py`, which rewrote the file and
`docs/TRACEABILITY.md` from the current sources. A few unrelated rows (D133, D176, D179, D190) moved because the generator re-read the notes. Nothing was edited by hand.

### N5. Two existing tests pinned the schema version

`tests/orchestrator/test_live_turn.py` (migration v5) asserted `SCHEMA_VERSION == 5` and "nothing else changed"; `tests/orchestrator/test_schema.py` (v3 to v4) counted every
table of `TABLES`. Both now migrate only as far as their own version and skip the tables of later migrations. No assertion was weakened: the v5 test still checks that v5 changes
nothing but its table, and the v6 swap of the index has its own test file.

### N6. The new flags are not in `Settings.public()`

`GET /api/config` and `sutra-pro config show` list `public()`. Adding keys there would change an existing route's output while the feature is off, so the four flags are
left out for now. The kill switch command (MAN-4, `sutra-pro nodes status`) prints them.

## MAN-2. Grants, tiers and the audit store

Built as designed: `orchestrator/grants.py` (role table, tiers, `intersect`), `orchestrator/gatekeeper.py` (`evaluate(plan)`, rules only), `orchestrator/nodes_store.py` (`audit`,
approvals rows). Nothing calls them yet. The points below are places where the design said less than the code needed. Each one was decided the cautious way (deny by default) and is
open for the architect to change; every one has a test, so a change shows up as a failing test with a clear name.

### N7. A grant has a fourth folder level, `inspect` (additive)

Architecture 5.2 lists the folder as `none|read|edit`. Guardrails 4 says a reviewer's folder access is `inspect` at most (reads plus the four git reads, as `Router.folder_for`
decides). Both cannot be right, so `Grant.folder` is `none|read|inspect|edit`.

### N8. The owner's access caps tier 4 and tier 3 as well as tier 2

Guardrails 4: "if the owner chose read only, every node is at most tier 1." Built literally: with the working folder set to read only, or no folder at all, no node gets tier 2, 3 or 4.
Consequence the architect should look at: a worker that only needs the GitHub read tools (tier 4) is refused when the owner chose read only, although those tools do not touch the folder.
If that is not wanted, tier 4 should depend on the approval alone. The rule is one line in `grants.resolve` and one test (`test_tier_4_is_only_given_to_a_worker_...`).

### N9. A worker whose output only reads has tiers 0 and 1, so no "sandboxed builder tools" (T3)

Guardrails 3 says tier 3 includes "J2's sandboxed builder tools inside the run folder (D245)", and guardrails 4 and the build plan say "a worker with output `read` has tiers 0 and 1
only, whatever the plan says". A document or website run has output `read` for the owner's folder but does use J2's builder tools in its own run folder today. The grant follows the
explicit rule (tiers 0 and 1), so `commands` is `sandboxed_builder` only for a worker that may change the owner's folder. MAN-5 must decide whether the grant describes the run
folder's builder tools at all (then they need their own word, not tier 3) or whether the grant is silent about them and they stay exactly as they are today. Nothing is enforced from the
grant yet, so no behaviour changed.

### N10. Tier 1 can come from the read-only app tools instead of the folder

A worker with no working folder but with the tool profile `sutra` has tier 1 (it reads app data). Without a folder and without that profile it has tier 0 only. The profile is never on
unless the step asks for it.

### N11. "Wider than a folder" is "more than one path"; "no scope declared" is not a question

The plan gate asks when a step's write scope has more than one path (`scope_width == "wide"`). A writer with no declared scope holds the whole folder, runs alone among writers (`alone`),
and is not asked about: that is the default, serial and safe (D260), and the Decide for me table (D294) also says "run alone". If the architect wants a question for "no scope" too, it is one
more `Gate` in `evaluate`.

### N12. There is no number for "the confirm threshold"

Guardrails 5 says the plan gate asks when "the estimate is over the project's confirm threshold" and gives no default. `Plan.confirm_credits` is None (never asks about the estimate) until
MAN-5 or MAN-8 gets a number from the architect. D273's default caps do not contain one either.

### N13. The plan has no tier, scope or `needs` field yet

`TaskWorkflow` steps are `AssignmentStep`s: a team, a brief, `depends_on`. D291 says the planner may add a write scope and a `needs` list per step. `evaluate` works on a plan that has been
put into plain values (`gatekeeper.Plan`, `PlanStep`); turning a `TaskWorkflow` plus the departments' output specs into one, and the planner's new fields, belong to MAN-5. `grants.py` takes the
output spec as a word (`read`/`edit`) or any object with a `workspace` attribute, so it imports nothing from the engine and the real `OutputSpec` fits without a copy.

### N14. Small additions

- `IdFactory` (and so `FakeIds`) gained `project_id`, `node_id`, `grant_id`, `approval_id` (`prj_`, `nd_`, `gr_`, `ap_` and 12 hex).
- `NodeStore` has only what MAN-2 needs (audit, approvals). `put_node`, `lease`, `release` and `post` of the architecture's component table arrive with the packages that use them.
- `approvals.decided_by` is `owner`, `system` or `rule:<name>` (the Decide for me rule table, D294). An answer that arrives after `expires_at` is stored as `expired` (denied).

## MAN-3. Identity plumbing

Built as designed: `CallTag.node_id` and `node_role`, `TaskSpec.node` (read) and `RunSpec.node` (written, left out of the file when it is None), the host's base tag, `SUTRA_NODE_ID`, the
two optional egress fields, the node id in the usage row's `detail`, and the planner's identity. The golden files in `tests/fixtures/run_spec/` were written by the code of `origin/main` before
this package, so "byte-identical" is checked against the old code's own output.

### N15. `tasks.py` is touched in MAN-3 (the writer of the block)

The build plan's file list for MAN-3 has no `tasks.py`, but "the block is written only with SUTRA_NODES_V1" has to live somewhere, and `_run_spec` is the only place that builds a `RunSpec`.
It now asks `nodes_store.node_block_of(conn, task_id)` for the block, only when `settings.nodes_v1` is on (with it off the table is not read: a test fails if it is). MAN-5 adds the rows.
A node that has no usable grant starts as an ordinary task and the log says so with ids only. The alternative, refusing to start it, would let one bad row stop the FIFO queue (the start
loop raises). Decision for the architect in MAN-5: the task gate must refuse to start a node whose grant is missing, so this fallback is never reached.

### N16. The egress row gets `node` and `role`, not `project_id`

Architecture section 5 says the egress row records `node_id` and `project_id`; the build plan and D283 say two fields from the tag, and the tag has `node_id` and `node_role` only. The row has
`node` and `role`. The project is one join away (`agent_nodes.project_id`). Adding `project_id` to the tag would change the tag contract again for little.

### N17. `usage_ledger.node_id` is the graph node, so the agent node goes in `detail`

`UsageIn.node_id` and `RouteContext.node_id` already mean the graph node (a function, a step, the root). The runtime node's id is therefore written as `detail.agent_node` and
`detail.agent_role`, only for a node's calls (the build plan says "node id into `detail`"). The orchestrator context key for the planner is `agent_node_id` / `agent_role` for the same reason.

### N18. The planner's stop token is cooperative

`call_json` had no `CancelToken`. One is now an optional argument all the way to the router (`JsonRequest.cancel`), honoured before every attempt, fallback and back-off, like a chat
turn's. It does not kill a connector's running process: for a chat the token is also bound to the spawned process, and doing that for a one-shot JSON call means a `cancel` argument through
`call_json_result` of the base connector, Claude, Codex and the stub. Nothing uses the token yet (the planner gets an identity and a token in MAN-5), so this was not widened. Open for the
architect: is a planner Stop that waits for the current call (at most the call's timeout, 120 s) acceptable, or should MAN-5 pay for the connector change?

### N19. Pinned tests that changed

`test_engine_port_contract.py` (the exact field list of `CallTag`), `test_engine_spec.py` (the run-spec field list now has `node`) and `test_orchestrator_port.py` (the signature of
`AsyncConnector.call_json` now ends in `cancel`). Each is a list of names the package was meant to extend.

### N20. `SUTRA_NODE_ID` is documented in ENVIRONMENT.md

`scripts/check_docs.py` fails on a `SUTRA_*` name in the source with no row. It is a name Sutra sets for a node's run; the server's own value of it is never passed on.
