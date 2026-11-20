# Multi-agent nodes: decisions

Status: decided by Claude on its own, 2026-11-20, under the owner's rule "decide autonomously, document every decision, never leave an open question". The owner can veto any of them.
The last number in `docs/DECISIONS.md` is D252, so these continue at D253. No question is left open: where a choice was close, the decision says what was chosen and the one-line why.

How these reach the real log: package MAN-1 copies each entry into `docs/DECISIONS.md` (with sources, decided, why, rejected, diagram label), adds it to
`docs/diagram/decisions.json` and `docs/design/traceability.json` (the tests `test_diagram_decisions.py` and `test_traceability.py` fail without them). The numbers are re-taken
after a `git fetch` if others have added decisions meanwhile (`AGENTS.md`).

Format: **number, decision.** Why: one line. Package: where it is built.

## Shape

**D253. A node is an ordinary run (a `tasks` row, a run folder, a process) plus an identity row in `agent_nodes`. No new process model.**
Why: a run already has files in and out, a heartbeat, a stop ladder, recovery and cost by task, so the cheapest way to get nodes is to give that thing an identity. Package: MAN-1, MAN-5.

**D254. Everything is behind `SUTRA_NODES_V1`, default 0. With it off no new table is read, no new column is used, and `task.json` is byte-identical to today. Sub-flags `SUTRA_NODES_LANES`, `SUTRA_NODES_REVIEWER`, `SUTRA_NODES_SLOTS` also default 0 and only count when the master is on.**
Why: the owner wants today's behaviour kept and every change additive, and a flag is the way back. Package: MAN-1.

**D255. A project is a new row that groups the tasks of one request. It is made only when the flag is on and the plan has two or more steps, or when the owner starts one with `POST /api/projects`. A one-step request keeps today's path.**
Why: one budget, one stop and one teardown for the nodes of a request, without touching the simple case. Package: MAN-5.

**D256. Roles and runtimes: planner inline (today's org chat agent stage), worker on the engine runtime (an unchanged J2 run), reviewer on a new light runtime, Conductor and Gatekeeper as server code. J2's five functions are not split into nodes.**
Why: the engine is frozen and its functions share one `J2Run`, so a team run is the smallest honest worker. Package: MAN-5, MAN-11.

**D257. One scheduler. The Conductor is a task gate inside `_prepare_next` (next to `start_gate`) plus a tick, not a second queue.**
Why: FIFO, `SUTRA_MAX_RUNS`, `SUTRA_MAX_LIVE`, the spending limit and "waiting" sentences then apply to nodes for free. Package: MAN-5.

**D258. Same-team parallelism uses a `lane` column on `tasks`. The unique index becomes `(dept_id, lane)` for live statuses. Every ordinary task has lane `''`; `live_in`, `deliver_to_department` and `stop_live` see lane `''` only.**
Why: it widens the "one live task per team" rule only for nodes and leaves the rule for everything else exactly as it is. Package: MAN-1 (column), MAN-10 (use).

## Scheduling and scopes

**D259. Parallelism comes from plan edges (`depends_on`, as today) plus conflict edges the Gatekeeper derives from write scopes. A conflict edge delays a step; it never cancels it.**
Why: a step that only waited for a folder must not die because a sibling failed. Package: MAN-5, MAN-10.

**D260. Write scopes are exclusive leases on paths. The planner may only narrow a scope, never widen it. No declared scope means the whole folder, so that writer runs alone. A folder that is not a git work tree means writers run one at a time.**
Why: the safe default is serial, and the after-run check needs git. Package: MAN-10.

**D261. No git worktrees in v1. Parallel writers share the owner's folder, fenced by scope rules in the CLI, with a path-attribution check after each run. A path changed that no running node owns pauses the project and asks the owner.**
Why: worktrees need a merge step and a merge policy; scoped leases are simpler and the check catches what the fence misses. Package: MAN-10.

## State and communication

**D262. The server stays the only database writer (D16 kept). Nodes never open the database and never call the server. They write files in their own run folder.**
Why: it keeps SQLite safe and leaves nothing for a node to authenticate to or steal. Package: all.

**D263. Structured payloads (`handoff.json`, `verdict.json`, `needs.json`) are files in the node's run folder. No new run event type is added; the eight stay closed.**
Why: it extends D133 ("a published file, not a ninth run event") and keeps the engine event contract and its goldens unchanged. Package: MAN-6, MAN-11.

**D264. Messages between nodes live in `node_messages`: append-only, written only by the server, gap-free `seq` per project, `src_ref` unique per project.**
Why: the same de-duplication pattern as `chat_messages.src_ref` and `usage_ledger.call_ref`, and the same catch-up pattern as the streaming snapshot. Package: MAN-6.

**D265. Upstream data reaches a node through the existing `upstream` folder mechanism (checked paths) plus the validated hand-off, and never through `framing` or system text.**
Why: `framing` is context from the chat agent, and mixing node output into instructions is how injection works. Package: MAN-6.

**D287. Project and node changes are ordinary store events (`project.updated`, `node.updated`, `approval.opened`, `approval.decided`, `project.message`) on the existing bus. The page refetches the snapshot. Heartbeat-only batches touch the database at most once per 15 s.**
Why: it reuses the bus ring and replay and keeps write pressure down; the replay of a few heartbeat lines is harmless. Package: MAN-6, MAN-12.

**D288. SQLite, WAL and one writer stay. The change is an additive migration v6. A 12-node load test is the acceptance test. If it fails the next step is a 250 ms batch window per project, not a new database.**
Why: the numbers are guessed, not measured, so measure first and add the smallest fix. Package: MAN-1, MAN-12.

**D289. Nodes are local child processes only. Remote nodes are a non-goal; the protocol stays files, so it remains possible later.**
Why: local-first is an owner rule and a broker would be a new service and dependency. Package: none.

## Permissions

**D266. The Gatekeeper is deterministic code. A model never approves a model. Only a rule or the owner says yes.**
Why: an approval a model can give is an approval a prompt can steal. Package: MAN-2, MAN-8.

**D267. A grant is the intersection of the role table, the plan step, the department's output spec and the owner's folder access. It is frozen when the node spawns. A node cannot raise it. A node that lacks a tier ends with `needs.json`; that becomes a card and, if allowed, a new attempt.**
Why: no process waits alive for a human, and content can never change a permission. Package: MAN-2, MAN-8.

**D268. Six tiers by blast radius: 1 read, 2 write files, 3 run commands, 4 network, 5 spend, 6 external publish; tier 0 is thinking only.**
Why: the owner named these six, and each maps onto a control the connectors already have. Package: MAN-2.

**D269. Deny by default. Defaults give tiers 0 to 2 where the role, the output spec and the owner's access allow. Tier 3 is only the four git reads and J2's sandboxed builder tools. Tier 4 needs the owner. Tier 5 is a slice, never extra. Tier 6 is never granted in v1.**
Why: today's apps cannot send for real (`J2_SEND_MODE` defaults to `dry-run` and is not a task setting) and the design must not open that. Package: MAN-2.

**D270. Approvals: asked at the plan gate, after a `needs.json` end, and for budget raises. Stored as rows. "Allow for this project" only up to tier 4; tier 5 is per raise; tier 6 is not offered. They expire after 24 hours and expired means denied. With the project's Decide for me switch on, the Gatekeeper's rule table answers them instead (D294); the owner's own answer is still the only other thing that can.**
Why: three places are enough to protect the owner without wearing them out, and the answer must be the owner's own (P25 principle). Package: MAN-8.

**D274. Nodes never spawn nodes (depth 1). Only the Conductor spawns, from the accepted plan. A changed plan goes through the plan gate again.**
Why: this is the loop guard; with no code path for a node to spawn a node, no text can make one. Package: MAN-5.

**D281. Prompt-injection boundary: hand-off and read text is data in a labelled block in the user part; hand-offs are typed JSON; only enums touch control flow; no content can change a grant, an edge or a budget; paths are checked; the reviewer is read-only.**
Why: a fooled model should only be able to do what its grant allows and show words to a human. Package: MAN-6, MAN-11, and tests in MAN-2.

**D282. Egress per node: `observe` for engine nodes (J2 prompts stay byte-identical), `replace` for hand-offs, stored messages and light-node prompts. Audit rows carry node, project and role. Three secret-shaped hits by one node stop it.**
Why: it keeps D109 and D249 and adds scrub exactly where the app owns the text. Package: MAN-3, MAN-6.

**D283. Node identity is an optional `node_id` and `node_role` on `CallTag` and an optional `node` block in `task.json`, plus `SUTRA_NODE_ID` in the child environment. Empty by default; the block is left out of the dump when the flag is off.**
Why: usage, egress and allowance rows then carry the node with no new column, and `TaskSpec` already ignores unknown keys. Package: MAN-3.

## Budget and limits

**D271. Project credits: the ceiling is the sum of the node slices (so total spend equals today's separate tasks). A node's `J2_BUDGET` and `J2_BUDGET_CAP` both equal its slice, so it cannot raise itself. A spawn that does not fit the unspent slices is held.**
Why: P25 says every raise is the Requester's own, and the sum of slices makes the project ceiling true by construction. Package: MAN-9.

**D272. A `NodeMeter` in Sutra's own `engine/llm.py` shim makes the router's per-request `Allowance` cumulative per node: calls, dollars where known, and a wall-time deadline. Past a cap the host stops the run and the outcome names the limit.**
Why: the allowance exists and is enforced by the router but the engine never sent one (`allowance=None`); Codex has no dollar figure, so calls and time are its bound. Package: MAN-9.

**D273. Default caps: 3 parallel nodes per project, 12 workers, 60 calls and 30 minutes per node, 1 retry per node, 2 review loops, 2 hours per project, lease 90 s, approval expiry 24 h, spawn depth 1. All in `caps_json` and `config.py`.**
Why: they are in line with today's plan limits (12 steps, 3 runs) and are easy to raise later because they are data. Package: MAN-1, MAN-9.

**D284. Provider concurrency becomes machine-wide with file-lock slot files (`oslayer.try_lock`), one slot file per allowed process, shared by every router. Sub-flag `SUTRA_NODES_SLOTS`.**
Why: the limit is per `Router` and each engine process has its own, so N processes multiply it; a file lock also vanishes when the process dies. Package: MAN-12.

## Lifecycle and failure

**D275. A lease is `last_beat_at + 90 s`, taken inside the transaction that marks the task `starting`. Any event extends it. In project mode only, a node silent past its lease and still alive is stopped with the ladder and retried once. If the Conductor's own tick gap shows the machine slept, the lease is extended once instead.**
Why: today a hung run is never recovered while the app runs (a deliberate choice for sleeping laptops); the sleep check keeps that kindness and fixes hangs. Package: MAN-7.

**D276. Teardown after a node ends: stop the process if needed, sweep its temp files (`choices.json`, MCP config), release scope and slot, write the audit, keep the run folder. Project teardown writes `audit.jsonl` and a receipt.**
Why: nothing the owner could want is deleted, and nothing stays held. Package: MAN-5, MAN-7.

**D277. Recovery: `reconcile` runs first and unchanged; `reconcile_projects` then rebuilds leases from rows, re-adopts live nodes, and retries or fails the rest. Leases are rows, not memory.**
Why: a crash must lose nothing and double-start nothing. Package: MAN-7.

**D278. Failure policy per project, default `stop_branch` (a failed node cancels its dependants, siblings go on, as a failed task does today); `stop_all` is the other choice. A project with a failed node ends `done_with_open_items` or `stopped`, never `done`.**
Why: it is today's rule for tasks and it never claims success it did not have. Package: MAN-7.

**D285. Reviewer independence across processes: the Conductor records which provider served each worker and writes the reviewer's run pick (`choices.json`, existing agent picks) to the other provider; if the other is unavailable the review still runs and says it was not independent.**
Why: `Independence` is in one process's memory and cannot see a worker in another process. Package: MAN-11.

**D286. The reviewer is a read-only light node with a verdict enum (`approve`, `changes_requested`, `reject`) and at most 2 review loops; then the owner decides.**
Why: an independent reader that cannot write cannot be turned into a writer, and a loop cap ends ping-pong. Package: MAN-11.

**D291. The planner is the org chat agent's staged planning with a node identity and a small slice. It may add a write scope and a `needs` list per step, only narrower than the department's. The planner call gets a `CancelToken` if `call_json` has none today.**
Why: it keeps the planning flow as it is and makes it auditable and stoppable. Package: MAN-3, MAN-5.

## Safety switches and audit

**D279. Kill switch in four levels (node, project, pause all, kill all) using the one stop ladder; a file `<data>/nodes/KILL` works when the UI does not; automatic triggers on caps, scope violation, repeated egress hits, repeated lease loss and the monthly limit.**
Why: the owner must be able to stop everything by hand, and a stuck UI is exactly when that is needed. Package: MAN-4.

**D280. The audit is an append-only table `node_audit` (update and delete triggers), one row per decision or action, names and shapes and hashes only, exported to `<data>/projects/<id>/audit.jsonl` (0600) at close.**
Why: it copies `atom_ledger` and `egress.jsonl`, so the rule "never a payload" stays true. Package: MAN-2, MAN-14.

## Words, tests, release

**D290. Words: "runtime node" (a running agent) is kept apart from "graph node" (a box in the graph). The table is `agent_nodes`. The UI says "agent". The engine's `project` output type is unrelated.**
Why: the word node already means three things in this repo, and a clear name saves mistakes. Package: MAN-1.

**D292. Tests use the fake engine and the scripted connector; the gate never calls a model; `live_smoke.py` is not run. Each package is tried in the beta app. Releases, packaging and version files are not touched.**
Why: `AGENTS.md` forbids spending the owner's quota in tests and reserves the stable app and releases for the owner. Package: all.

**D293. The decisions, the design documents and the flag table are registered in `docs/DECISIONS.md`, `docs/diagram/decisions.json`, `docs/design/traceability.json`, `docs/ENVIRONMENT.md` and `sutra_app/ops/envfile.py` in MAN-1, not at the end.**
Why: the repository's own tests fail on a decision without its diagram entry, and the docs check fails on a setting nobody documented. Package: MAN-1.

**D294. Decide for me works for projects: one switch (`projects.decide_for_me`, set from the existing `J2_DECIDE_FOR_ME`) means "do not wait for me". It is passed to every worker as the existing setting, and the three node gates are answered at once by a fixed rule table in the Gatekeeper (code, never a model), each answer audited as `decided_by: rule:decide_for_me`. Tiers 0 to 3 are allowed within the role's grant; tier 4 only as read-only GitHub tools for this project; wide or missing write scopes run alone; a credit request is never raised (P25), but unspent slices may move inside the approved ceiling; a scope violation fails and quarantines the node; tier 6 is never granted and never asked. The owner's folder access, all caps, the depth rule and the kill switch stay in force. The owner reads a "Sutra decided for you" list on the project page.**
Why: the owner wants projects that run with no input; a rule table keeps "a model never approves a model", and every wall that protects spend and the outside world stays where D251, D268 and D269 put it. Rejected: letting an AI pick the answer for node gates (a model would approve a model); having Decide for me raise credits (breaks P25); answering tier 6 "yes" (the wall in D268). Package: MAN-8 (the table and the switch), MAN-13 (the "decided for you" list).

**D295. Operating-system permissions are checked per system (macOS, Windows) before a node starts. A node's reach is its grant intersected with what the computer has allowed. A new `sutra_app/syspermissions.py` beside `oslayer.py` probes the folders the plan names (a listing, and for write steps one small temporary file in the node's own scope), explains what is missing in plain steps for that system, opens the right settings page and checks again. Sutra never changes a system setting, never asks for an administrator password and never runs a node elevated. Decide for me cannot grant these. Only the steps that need a missing permission wait (state `awaiting_system`); the rest of the project runs. Skipping cancels only those steps. A late "Operation not permitted" or "Access is denied" ends a node as `needs_system_permission` with the same card. The broadest permission (macOS Full Disk Access) is a last resort and names the path. Camera, microphone, screen, accessibility and other-app control are never requested. Linux has nothing to ask.**
Why: macOS protects Desktop, Documents and similar folders per app and Windows can block writes with Controlled folder access, so a node would otherwise fail halfway with a vague error; asking up front, in system-specific words, keeps the owner in control and keeps the sentence "a model never approves" true for the machine too. (Amended by D296: the card does not outlive a closed laptop.) Rejected: asking in the middle of a run (a node would hang behind a hidden system dialog); Sutra changing the setting itself (a system setting belongs to the owner, and it would need an administrator password); one generic card for both systems (the steps are different); asking for Full Disk Access by default (far wider than needed). Package: MAN-15.

**D296. A closed laptop is a refusal. If the computer sleeps, or Sutra is closed, while any gate is open (an approval card or a system permission card), every open gate of that project counts as refused: the waiting nodes are `cancelled` with the reason "the computer went to sleep before you answered" (or "Sutra was closed before you answered"), the running nodes of the project are stopped with the existing stop ladder, the project is `stopped`, and one receipt card says why. Detected by the Conductor's tick gap (more than half a lease) and by `reconcile_projects` after a restart. A project with no open gate keeps the one-time lease extension for a sleeping laptop (N2). An open card still ends after 24 hours. This amends D270 and D295 (the system permission card no longer waits for ever).**
Why: the owner's rule: nobody is there to answer, so the work must not go on and must not wait unseen; stopping is the safe reading of silence. Rejected: waiting until the owner returns (the work and any held lease would sit unseen); stopping every project on every sleep (a project with nothing open can safely continue, as today). Package: MAN-7 (detection and recovery), MAN-8 and MAN-15 (the two cards).

## Index

| D | Topic | | D | Topic |
|---|---|---|---|---|
| D253 | node = run + identity | | D274 | depth 1 |
| D254 | flags | | D275 | lease and expiry |
| D255 | project | | D276 | teardown |
| D256 | roles and runtimes | | D277 | recovery |
| D257 | one scheduler | | D278 | failure policy |
| D258 | lanes | | D279 | kill switch |
| D259 | edges | | D280 | audit |
| D260 | write scopes | | D281 | injection boundary |
| D261 | no worktrees | | D282 | egress per node |
| D262 | single writer | | D283 | node identity |
| D263 | payloads as files | | D284 | provider slots |
| D264 | messages table | | D285 | reviewer independence |
| D265 | upstream path | | D286 | reviewer |
| D266 | Gatekeeper is code | | D287 | events |
| D267 | grants frozen | | D288 | SQLite stays |
| D268 | six tiers | | D289 | local only |
| D269 | deny by default | | D290 | words |
| D270 | approvals | | D291 | planner |
| D271 | budget slices | | D292 | tests and release |
| D272 | NodeMeter | | D293 | registration |
| D273 | default caps | | D294 | Decide for me |
| | | | D295 | system permissions |
| | | | D296 | closed laptop is a refusal |
