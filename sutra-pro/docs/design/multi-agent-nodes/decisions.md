# Multi-agent nodes: decisions

Status: decided by Claude on its own, 2026-11-20, under the owner's rule "decide autonomously, document every decision, never leave an open question". The owner can veto any of them.
The last number in `docs/DECISIONS.md` was D252, so these continue at D253. D297 to D305 were added by the architect after phase 1 (MAN-1 to MAN-4) was built, from the developer's notes (`dev-notes.md`, N1 to N25); D306 to D312 after phase 2 (MAN-5 to MAN-7, notes N26 to N31). They are in the sections "Phase 1 rulings" and "Phase 2 rulings" below, and where one amends an earlier decision the earlier line says so. No question is left open: where a choice was close, the decision says what was chosen and the one-line why.

How these reach the real log: package MAN-1 copies each entry into `docs/DECISIONS.md` (with sources, decided, why, rejected, diagram label), adds it to
`docs/diagram/decisions.json` and `docs/design/traceability.json` (the tests `test_diagram_decisions.py` and `test_traceability.py` fail without them). The numbers are re-taken
after a `git fetch` if others have added decisions meanwhile (`AGENTS.md`).

Format: **number, decision.** Why: one line. Package: where it is built.

## Shape

**D253. A node is an ordinary run (a `tasks` row, a run folder, a process) plus an identity row in `agent_nodes`. No new process model.**
Why: a run already has files in and out, a heartbeat, a stop ladder, recovery and cost by task, so the cheapest way to get nodes is to give that thing an identity. Package: MAN-1, MAN-5.

**D254. Everything is behind `SUTRA_NODES_V1`, default 0. With it off no new table is read, no new column is used, and `task.json` is byte-identical to today. Sub-flags `SUTRA_NODES_LANES`, `SUTRA_NODES_REVIEWER`, `SUTRA_NODES_SLOTS` also default 0 and only count when the master is on.**
Why: the owner wants today's behaviour kept and every change additive, and a flag is the way back. Package: MAN-1.

**D255. A project is a new row that groups the tasks of one request. It is made only when the flag is on and the plan has two or more steps, or when the owner starts one with `POST /api/projects` (built with the project page, MAN-13: D310). A one-step request keeps today's path.**
Why: one budget, one stop and one teardown for the nodes of a request, without touching the simple case. Package: MAN-5 (from the chat), MAN-13 (the route).

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

**D264. Messages between nodes live in `node_messages`: append-only, written only by the server, gap-free `seq` per project (how: D297), `src_ref` unique per project.**
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

**D267. A grant is the intersection of the role table, the plan step, the department's output spec and the owner's folder access (the owner's access caps the folder part of the grant only: D298). It is frozen when the node spawns. A node cannot raise it. A node that lacks a tier ends with `needs.json`; that becomes a card and, if allowed, a new attempt.**
Why: no process waits alive for a human, and content can never change a permission. Package: MAN-2, MAN-8.

**D268. Six tiers by blast radius: 1 read, 2 write files, 3 run commands, 4 network, 5 spend, 6 external publish; tier 0 is thinking only.**
Why: the owner named these six, and each maps onto a control the connectors already have. Package: MAN-2.

**D269. Deny by default. Defaults give tiers 0 to 2 where the role, the output spec and the owner's access allow. Tier 3 is only the four git reads (amended by D299: J2's builder tools are not a tier). Tier 4 needs the owner and does not depend on the folder (D298). Tier 5 is a slice, never extra. Tier 6 is never granted in v1.**
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

**D273. Default caps: 3 parallel nodes per project, 12 workers, 60 calls and 30 minutes per node, 1 retry per node, 2 review loops, 2 hours per project, lease 90 s, approval expiry 24 h, spawn depth 1, and the plan gate's confirm threshold of 500 work credits (D300). All in `caps_json` and `config.py`.**
Why: they are in line with today's plan limits (12 steps, 3 runs) and are easy to raise later because they are data. Package: MAN-1, MAN-9.

**D284. Provider concurrency becomes machine-wide with file-lock slot files (`oslayer.try_lock`), one slot file per allowed process, shared by every router. Sub-flag `SUTRA_NODES_SLOTS`.**
Why: the limit is per `Router` and each engine process has its own, so N processes multiply it; a file lock also vanishes when the process dies. Package: MAN-12.

## Lifecycle and failure

**D275. A lease is `last_beat_at + 90 s`, taken inside the transaction that marks the task `starting`. Any event extends it. In project mode only, a node silent past its lease and still alive is stopped with the ladder and retried once. If the Conductor's own tick gap shows the machine slept, the lease is extended once instead. The gap is measured on the wall clock, from the end of one tick to the start of the next (D311).**
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

**D291. The planner is the org chat agent's staged planning with a node identity and a small slice. It may add a write scope and a `needs` list per step, only narrower than the department's, through a separate second call, the node plan (D306), never through the planner's existing schema. The planner call gets a `CancelToken` if `call_json` has none today (it had none; how it must stop a running call: D301).**
Why: it keeps the planning flow as it is and makes it auditable and stoppable. Package: MAN-3, MAN-5.

## Safety switches and audit

**D279. Kill switch in four levels (node, project, pause all, kill all) using the one stop ladder; a file `<data>/nodes/KILL` works when the UI does not; automatic triggers on caps, scope violation, repeated egress hits, repeated lease loss and the monthly limit.**
Why: the owner must be able to stop everything by hand, and a stuck UI is exactly when that is needed. Package: MAN-4 for the four levels and the file; the automatic triggers are built with their causes (D303).

**D280. The audit is an append-only table `node_audit` (update and delete triggers), one row per decision or action, names and shapes and hashes only, exported to `<data>/projects/<id>/audit.jsonl` (0600) at close.**
Why: it copies `atom_ledger` and `egress.jsonl`, so the rule "never a payload" stays true. Package: MAN-2, MAN-14.

## Words, tests, release

**D290. Words: "runtime node" (a running agent) is kept apart from "graph node" (a box in the graph). The table is `agent_nodes`. The UI says "agent". The engine's `project` output type is unrelated.**
Why: the word node already means three things in this repo, and a clear name saves mistakes. Package: MAN-1.

**D292. Tests use the fake engine and the scripted connector; the gate never calls a model; `live_smoke.py` is not run. Each package is tried in the beta app. Releases, packaging and version files are not touched.**
Why: `AGENTS.md` forbids spending the owner's quota in tests and reserves the stable app and releases for the owner. Package: all.

**D293. The decisions, the design documents and the flag table are registered in `docs/DECISIONS.md`, `docs/diagram/decisions.json`, `docs/design/traceability.json`, `docs/ENVIRONMENT.md` and `sutra_app/ops/envfile.py` in MAN-1, not at the end.**
Why: the repository's own tests fail on a decision without its diagram entry, and the docs check fails on a setting nobody documented. Package: MAN-1.

**D294. Decide for me works for projects: one switch (`projects.decide_for_me`, set from the existing `J2_DECIDE_FOR_ME`) means "do not wait for me". It is passed to every worker as the existing setting, and the three node gates are answered at once by a fixed rule table in the Gatekeeper (code, never a model), each answer audited as `decided_by: rule:decide_for_me`. Tiers 0 to 3 are allowed within the role's grant; tier 4 only as read-only GitHub tools for this project; wide or missing write scopes run alone; a credit request is never raised (P25), but unspent slices may move inside the approved ceiling; a scope violation fails and quarantines the node; tier 6 is never granted and never asked. The owner's folder access (it caps the folder part of every grant, D298), all caps, the depth rule and the kill switch stay in force. The owner reads a "Sutra decided for you" list on the project page.**
Why: the owner wants projects that run with no input; a rule table keeps "a model never approves a model", and every wall that protects spend and the outside world stays where D251, D268 and D269 put it. Rejected: letting an AI pick the answer for node gates (a model would approve a model); having Decide for me raise credits (breaks P25); answering tier 6 "yes" (the wall in D268). Package: MAN-8 (the table and the switch), MAN-13 (the "decided for you" list).

**D295. Operating-system permissions are checked per system (macOS, Windows) before a node starts. A node's reach is its grant intersected with what the computer has allowed. A new `sutra_app/syspermissions.py` beside `oslayer.py` probes the folders the plan names (a listing, and for write steps one small temporary file in the node's own scope), explains what is missing in plain steps for that system, opens the right settings page and checks again. Sutra never changes a system setting, never asks for an administrator password and never runs a node elevated. Decide for me cannot grant these. Only the steps that need a missing permission wait (state `awaiting_system`); the rest of the project runs. Skipping cancels only those steps. A late "Operation not permitted" or "Access is denied" ends a node as `needs_system_permission` with the same card. The broadest permission (macOS Full Disk Access) is a last resort and names the path. Camera, microphone, screen, accessibility and other-app control are never requested. Linux has nothing to ask.**
Why: macOS protects Desktop, Documents and similar folders per app and Windows can block writes with Controlled folder access, so a node would otherwise fail halfway with a vague error; asking up front, in system-specific words, keeps the owner in control and keeps the sentence "a model never approves" true for the machine too. (Amended by D296: the card does not outlive a closed laptop.) Rejected: asking in the middle of a run (a node would hang behind a hidden system dialog); Sutra changing the setting itself (a system setting belongs to the owner, and it would need an administrator password); one generic card for both systems (the steps are different); asking for Full Disk Access by default (far wider than needed). Package: MAN-15.

**D296. A closed laptop is a refusal. If the computer sleeps, or Sutra is closed, while any gate is open (an approval card or a system permission card), every open gate of that project counts as refused: the waiting nodes are `cancelled` with the reason "the computer went to sleep before you answered" (or "Sutra was closed before you answered"), the running nodes of the project are stopped with the existing stop ladder, the project is `stopped`, and one receipt says why (a note in the org chat, not a card: D311). Detected by the Conductor's tick gap (more than half a lease) and by `reconcile_projects` after a restart. A project with no open gate keeps the one-time lease extension for a sleeping laptop (N2). An open card still ends after 24 hours. This amends D270 and D295 (the system permission card no longer waits for ever).**
Why: the owner's rule: nobody is there to answer, so the work must not go on and must not wait unseen; stopping is the safe reading of silence. Rejected: waiting until the owner returns (the work and any held lease would sit unseen); stopping every project on every sleep (a project with nothing open can safely continue, as today). Package: MAN-7 (detection and recovery), MAN-8 and MAN-15 (the two cards).

## Phase 1 rulings (architect, after MAN-1 to MAN-4 were built)

Decided on 2026-11-20 from the developer's notes N1 to N25 and a reading of the code (`git diff origin/main..HEAD`). Where the code differs from the design the ruling says which one changes.

**D297. `node_messages` is keyed `(project_id, seq)` and `seq` is 1, 2, 3 ... per project with no gap and no repeat. The writer (`NodeStore.post`, MAN-6) works in ONE write transaction: it looks for `(project_id, src_ref)` first and, if the message is there, returns that row and takes no number; otherwise it takes `MAX(seq) + 1` for the project and inserts. A table-wide AUTOINCREMENT is not used. There is no global sequence for the page.**
Guarantee the resume contract needs: at every committed state of the database the `seq` values of one project are exactly 1 to n. It holds because (1) the primary key forbids a repeat; (2) the server is the only writer and a write is `BEGIN IMMEDIATE`, so two posts cannot read the same maximum; (3) the number is taken and used in the same transaction, so a rollback gives it back; (4) a repeated `src_ref` takes no number; (5) the triggers forbid UPDATE and DELETE, and a project is never deleted in v1 (D305); (6) `project.message` is published after COMMIT, and a reader sees one committed snapshot, so it sees a prefix 1 to k, never a hole. So `GET /api/projects/{id}/messages?after=k` returns k+1, k+2, ... in order; a page that gets anything but k+1 first has lost a message and refetches from its last contiguous number; the snapshot carries `last_message_seq`. Why: the page's catch-up is the streaming contract's (D201 to D238), which only works when a gap means loss. Rejected: a table-wide AUTOINCREMENT (project A would see 1, 3, 4: a false loss); a global sequence for the page (the page would have to stop treating a gap as loss, and the bus already has its own `seq`). Package: MAN-1 (key, done), MAN-6 (writer and its tests: two projects interleaved, a repeated `src_ref`, a rollback, and 50 posts that read back as 1 to 50).

**D298. Tier 4 (the GitHub read tools, through the owner's own `gh`) does not depend on the owner's folder access. It depends on the role (a worker only) and on an approval (the owner's, or the Decide for me rule table's). The owner's folder access caps the FOLDER part of a grant (tiers 2 and 3, and what the folder lets a node read) and nothing else. The tool profile is split into its two parts: `sutra` (read-only app data, tier 1) and `github` (tier 4). A grant's `tool_profile` is `none`, `sutra`, `github` or `sutra+github`; a tier-4 grant holds `github` only, and holds `sutra` only if the step asked for it separately. Tiers are not a ladder: a grant lists each tier it holds.**
Why: the GitHub tools touch no file in the folder, so "read only" says nothing about them; the approval is the owner's real control over the network. The `sutra` part opens the whole app database read-only (known limit), so a tier-4 request must not carry it along. Delivery (a gap the code showed): today the engine path has no way to give a call a tool profile (the policy says `none`; `CallTag` and `CompletionRequest` carry no tools), so MAN-8 adds a `tool_profile` to the `node` block and an optional `PortSpec.tools` (empty by default) that `RouterPort` puts on a node's agent-turn calls only (never on a builder-tools call, which has its own grant); the plan gate does not ask the tier-4 question before this works (same package). A reviewer gets the `sutra` part at most; the planner none. Rejected: tying tier 4 to folder `edit` (it refuses a read-only owner a read-only tool and mixes two controls); keeping the bundle `sutra+github` for tier 4 (it hands out the app database read with it). Package: MAN-2 (grant rules, a fix), MAN-8 (delivery and the question).

**D299. J2's builder tools are not a tier and not part of the owner's-folder reach. A grant describes them in one separate field, `run_tools`: `engine` for a worker (the engine's own rule, unchanged, in the run folder) and `none` for the planner and the reviewer. The field is a description, written in the `grant.issued` audit row so the record is true; the grant does not enforce it, because the engine decides. Tier 3 becomes only the four git reads on the owner's folder: `commands` is `none` or `git_reads`. A worker gets `git_reads` when its folder level is `edit` (its Audit agent runs `inspect`, as `workspace_for` decides); a reviewer when its level is `inspect`. "A worker whose output only reads has tiers 0 and 1" stays, and means: nothing in the owner's folder beyond reading. Its builder tools in its own run folder are as they are today.**
What the code showed: a builder-tools call (`CompletionRequest.run_tools`, a `ToolGrant`) runs in a folder strictly inside the run folder; the router gives it no owner's folder and no MCP profile; the engine switches it on (`llm.tools_on`: live with the Claude CLI unless `J2_AGENT_TOOLS=0`) for the folder-type outputs of `types.json`; the department output spec's `workspace` (`read` or `edit`) says only what builders may do in the OWNER's folder. So the two reaches are independent, and calling the builder tools "tier 3" made a document or website run (`read`) look as if it had no tools when it has them today. Known limit, written on purpose: `types.json` gives those builders Read, Write, Edit, Glob, Grep, Bash, WebSearch and WebFetch; they are fenced by the CLI sandbox when `srt` is found (macOS, Linux) and by J2's check that a file outside the folder fails the workflow. A node's grant does not narrow them in v1 (`agent_tools` is a locked engine setting, not a task key; a per-task key is a J2 sync); the owner can still turn them off for all runs in the engine settings. So tier 4's words "no other network tool" mean Sutra's own tools. Rejected: leaving the grant silent (the audit would not say what a worker can do); a tier 3 that depends on the output level (it would remove today's tools from document runs, which is a replacement); narrowing the tools per node now (frozen engine). Package: MAN-2 (grant fields, a fix), MAN-5 (the `grant.issued` row says `run_tools`).

**D300. The plan gate's confirm threshold is 500 work credits. It is `NODE_DEFAULT_CAPS["confirm_credits"]` in `config.py`, copied into `projects.caps_json["confirm_credits"]` at plan time like the other caps. The plan's estimate is the sum of its steps' `estimate_credits`; a step with no estimate from the planner counts as its slice (the team's `J2_BUDGET`, default 100). `Plan.confirm_credits` defaults to the configured number, and `None` (never ask about spend) only when the owner started the project with their own `budget`: that number is the owner's answer already. Decide for me answers this gate "allow up to the ceiling" as before (D294).**
Why: a full documents-plus-website run needs 500 or more (`docs/ENVIRONMENT.md`), so one ordinary run never trips it, but five default runs or two heavy ones do, which is more than the owner would start by hand in one go. Rejected: no number (a project could cost any amount with no question); asking on every plan (wears the owner out). Package: MAN-1 (the key, a fix), MAN-5 (estimate and ceiling), MAN-8 (the gate).

**D301. A planner Stop must stop the running call, not wait for it. MAN-5 adds an optional `cancel` to `call_json_result` and the one-shot plan of the base connector, the Claude and Codex connectors and the stub, so the token is bound to the spawned process exactly as a chat turn's is (D215) and the cancel ladder ends it in at most 12 s. A small registry of the in-flight planner tokens (in `ProjectService`, built in MAN-5) is what node stop, project stop and kill-all ask to stop. Pause-all does not (what runs finishes). A cancelled planner call ends the request as stopped; no plan is adopted.**
Why: the planner's call is a CLI child inside the server that the stop ladder never sees; the cooperative token of MAN-3 (checked before each attempt) lets it run up to the call's timeout (120 s) and spend quota after a kill, which breaks "kill all stops everything" (D279). The mechanism exists; the cost is four signatures and one argument. D296 is not involved: the planner has no open gate, because the plan gate comes after planning. Rejected: accepting the wait; cancelling the asyncio task only (it would orphan the child). Package: MAN-5 (connector change, registry, planner wiring), MAN-4's `NodeControl` gets the registry then.

**D302. A node whose grant is missing, unreadable or wider than the role table never starts, not even as an ordinary task. The task gate holds it with a sentence ("Held: this agent has no valid grant") and `_run_spec` has no fallback. MAN-5's Conductor then fails the node with a `grant.denied` audit row.**
Why: an ordinary task has the reach of a team run, which is wider than a reviewer's; "deny by default" must hold for the broken case too. Holding one task does not stop the queue: the start loop moves on to the next (`continue`). Package: MAN-4 (fix: the gate checks `node_block_of`), MAN-5 (the fail).

**D303. The kill switch has one owner and four rules. (a) A KILL file made by hand is enforced by `NodeControl`'s watcher (one `lstat` every 2 s, plus once at start); it stays when the Conductor arrives, so a stuck tick cannot hold back a kill; the tick may call `enforce()` too (it deals with each file once). (b) The Conductor's task gate (MAN-5) asks `NodeControl.gate` first and adds its own checks: composed, never replaced. (c) Kill-all and node stop run the stop ladders together (as app shutdown does), so the whole kill takes about 12 s, not 12 s per node. (d) A kill ends the project: with MAN-5, every project with a live node becomes `stopped` ("stopped by the kill switch"), its queued and blocked nodes are `cancelled`, and nothing starts by itself after resume; the owner starts again. Pause only holds: nothing is cancelled and what waited starts at resume. A node that the owner or the kill switch stopped is never retried or restarted by the Conductor. (e) The automatic triggers of D279 are built with their causes, not in MAN-4: caps and three egress hits in MAN-9, a node that loses its lease twice in MAN-7, a scope violation in MAN-10; the monthly limit is the existing `Limits` hold.**
Why: the owner must be able to stop everything even when the page or the tick is stuck, and a stop that restarts work by itself after resume is a surprise (the closed-laptop rule, D296, reads silence as stop in the same way). Rejected: letting the tick be the only watcher; queued nodes starting again by themselves after a kill (the dev's N24 reading, right for MAN-4 alone, where there are no projects yet). Package: MAN-4 (fix c), MAN-5 (b, d), MAN-7, MAN-9, MAN-10 (e).

**D304. Developer findings adopted as design (N2, N3, N7, N11, N14, N16, N17, N21, N22, N23, N24, N25): `projects.decide_for_me`, `projects.paused`, `projects.review_loops` and `approvals.created_at` are columns of migration v6; `node_messages` has the append-only triggers; a grant's folder level is `none`, `read`, `inspect` or `edit` (`inspect` = read plus the four git reads, as `Router.folder_for` decides); the plan gate asks about a write scope of MORE THAN ONE PATH, and a writer with no declared scope is never asked about but runs alone (D260, D294); `IdFactory` makes `prj_`, `nd_`, `gr_` and `ap_` ids; the egress row carries `node` and `role` (the project is one join away); the usage row carries the runtime node as `detail.agent_node` and `detail.agent_role` (`usage_ledger.node_id` stays the graph node); the `task_gate` hook is in MAN-4 (pulled forward); the routes `GET /api/nodes/status` and `POST /api/nodes/resume` exist beside the designed ones; a stopped node is `cancelled` and the projector owns node state from MAN-5; the D296 words and audit names (`gate.refused`, `project.stopped`) are constants in `nodes_store.py`.**
Why: each is additive, safe and was needed by the code; none replaces anything. Package: MAN-1 to MAN-4 (done), documented in architecture and guardrails.

**D305. Small rules found while building phase 1. (a) A reviewer's output level is the strongest level among the steps it reviews (`edit` if it reviews a writer), so it gets the git reads exactly when the work it checks changed files. (b) `max_nodes` (12) counts workers; reviewers come on top (as D273 says). (c) `agent_nodes.task_id` points at the node's CURRENT attempt; an earlier attempt stays in `tasks` through `parent_task_id`, and a retry re-points the row in the same transaction that makes the new task. (d) Projects are never deleted in v1 (the append-only tables hold them); archiving is a later decision. (e) Reads of the new routes need no token, as every read of the app; every write needs it. (f) The new flags stay out of `Settings.public()` and `GET /api/config`; the page learns the flag from `GET /api/nodes/status` (404 means off).**
Why: each closes a gap the code showed and none changes a rule the owner set. Package: MAN-2 (b, fix), MAN-5 (c), MAN-11 (a), MAN-13 (f).

## Phase 2 rulings (architect, after MAN-5 to MAN-7 were built)

Decided on 2026-11-20 from the developer's notes N26 to N31 and a reading of `git diff 8dab4e61..72a31f0f`. The code agrees with the design except where a ruling says otherwise; each ruling says which one changes. The fixes are G1 to G10 and C0 in `build-plan.md` ("Before phase 3").

**D306. The plan carries a step's write scope and its `needs` through a separate small planner call, the "node plan" (stage D), not through the planner's existing schema. It runs only with `SUTRA_NODES_V1` on and only for a request with two or more steps, after the assignments are final and before `ProjectService.reserve`. Reply: a new closed family `node_plan` (`steps: [{ref, scope: [<= 5 relative paths], needs: [sutra | github]}]`), registered in `agent/replies.py` like `chat_turn`; prompt: a fifth template `nodeplan.md`. The call carries the planner's identity and stop token (D301), has its own cap of 2 attempts, and is only a request: `scope` goes through `normalize_scope` into the step's request, `needs` becomes its tool profile (`github` also asks tier 4); the Gatekeeper and the owner decide; a planner can never add a tier. If the stage fails the defaults apply (no scope, no needs) and an audit row `plan.defaults` says so; the project never fails because of it. `AssignmentDraft`, the `chat_turn` schema, the decide and assign prompts and every flag-off golden stay byte-identical; `docs/schemas/` only gains `node_plan.v1.json` and one line in `index.json`.**
Why: the planner's step model is derived into the pinned `chat_turn` schema and prompts, so adding fields there moves flag-off goldens, and a flag-aware schema would make flag-off bytes depend on a runtime switch; the output specs say only `read` or `edit`, so nothing can be derived from them. Before it exists the plan gate can ask the estimate question only; it cannot ask tier 4 or a wide scope because no step carries them, and a writer holds the whole folder. Rejected: fields in `AssignmentDraft`; a flag-aware schema generator; the Gatekeeper deriving scope from the output specs (nothing to derive); asking the owner to type scopes (MAN-13 may add that later). Package: MAN-8 (stage, tier-4 and wide-scope questions, `scope` carried and shown), MAN-10 (`scope` enforced).

**D307. What a grant says about an output nobody knows yet, and what the planner may touch. (a) A team whose output is `auto` is read as `read` for the grant while the grant is a description (MAN-5 to MAN-9), and the `grant.issued` row says "output auto (decided in the run)". (b) From MAN-10, with lanes on, a worker whose output is `auto` is treated as a possible writer: no declared scope means the whole folder and it runs alone (D260). With lanes off, different teams run in parallel exactly as today. The page draws a conflict edge only when lanes are on. (c) The planner has no stored grant. With the flag on its calls are tagged `workspace="read"`: it may read the owner's folder as the org chat agent does today and can never edit it. With the flag off it stays as today (`edit`, D127, capped by the owner).**
Why: nothing enforces the grant's folder yet, so `read` is only a record, but a record must not claim more than is known; for scheduling the safe reading is "may write". The planner's calls were tagged `edit` (D127), which the design had not noticed: a folder file with an injected instruction could have made the planner write. Rejected: `auto` as `edit` everywhere now (it would serialise every default team before anything uses it); a planner with no folder at all (it would change how it plans). Package: MAN-5 (record, G10; planner tag, G6), MAN-10 (possible writer, conflict edges).

**D308. A gate that nothing can answer yet is held and said out loud, never skipped and never silent. Until MAN-8 a plan over the confirm threshold makes the project `awaiting_approval`, the questions are stored, every node waits, and the reply to the owner says so in plain words (the Sutra line `project_waits`); the 24 h end or a restart ends it with the D296 note. The flag stays off in every beta the owner is given until MAN-8 is in. MAN-8 owns the rest: the answer path (re-evaluate the plan with what was approved, rewrite the grants of nodes that have not spawned, move the nodes on), Decide for me (`reserve` gets `decide_for_me` from the request's `J2_DECIDE_FOR_ME`; the rule table answers in the same transaction, no hold), and the estimate question stored as kind `plan_estimate`, tier 5, answered allow once or deny only (D270).**
Why: the stored rows are exactly what MAN-8 reads, so holding loses nothing; refusing would throw the plan away and skipping would start spending nobody approved (D300). Rejected: refuse at planning; treat "no answer path" as yes. Package: MAN-5 (the line, G7), MAN-8.

**D309. Hand-off intake rules. (a) Dependants are given `handoff.accepted.json` (written by the server after the check) through the existing `upstream` listing; `RunSpec.upstream` has no new field (D265). (b) The checksums of one hand-off share a budget of 64 MB in all; past it a file is checked by size only and counted as `unchecked` (the intake runs inside the projector's transaction, so it must be short). (c) For a node the host's `handoff` step runs first among the finish steps: a slow `agent_views` or `catalog` must never leave a node with no hand-off. (d) The host lists the run folder's top-level files; MAN-10 adds an optional `changes` list (paths a worker changed in the owner's folder) to `handoff/1` and the intake's key set grows with it. (e) A body over 16 KB is stored as `{file, sha256, bytes}` with the sha of the FILE; a hand-off with status `blocked` ends the node `failed`, never retried (MAN-11, the first writer of it).**
Why: each closes a gap the code showed in the first hand-off flow; none changes a rule of D263 to D265, D281. Rejected: hashing outside the transaction (the node's state, the message and its dependants must change together); keeping the step last. Package: MAN-6 (b, c as fixes G9, G1), MAN-10 (d), MAN-11 (e).

**D310. Retry and failure rules completed. (a) A node's retry keeps the dependencies of the attempt it replaces (they are done), so the new attempt is given the same upstream; only the owner's own retry of an ordinary task is as it was. (b) A node the task gate holds for "no valid grant" is failed by the tick: its task is cancelled, the node is `failed` with an audit row `grant.denied` (actor conductor), and the failure policy applies (D302 completed). (c) `failure_policy` is set by the owner only: an optional field of `POST /api/projects` (built with the page, MAN-13), default `stop_branch`; the planner never sets it and a request made in the chat is always `stop_branch`. (d) `reserve` is fail-closed: a request that already has a failed or stopped project is not "ok", and a task whose step has no node is an error, never an ordinary task past the gate.**
Why: (a) a retried dependant would otherwise run blind; (b) today such a project sits for ever; (c) a model should not choose how a project fails and the code had no way to set it; (d) deny by default. Package: MAN-7 (a, b fixes G4, G3), MAN-5 (d, G8), MAN-13 (c).

**D311. The closed-laptop check and its receipt. (a) The tick gap is measured on the wall clock (`Clock`), from the END of one tick to the START of the next, so the tick's own stop ladders are not read as a sleep; a monotonic clock stops during sleep on macOS and Linux and could never see one. A clock jump forward reads as a sleep, which is the safe side. (b) The receipt of D296 is a plain note in the org chat (once per project, by its `src_ref`), plus `projects.stop_reason` and the audit rows `gate.refused` and `project.stopped`. No receipt card kind is built in MAN-8 or MAN-15. This amends D275 and D296.**
Why: (a) the first version counted its own work as sleep and could refuse an open gate falsely; (b) a receipt tells and asks nothing, and `needs_you` is for questions. Rejected: a monotonic gap; a card that needs dismissing. Package: MAN-7 (G2), MAN-13 (the page shows the reason).

**D312. The design as built, written down. (a) The Conductor (the task gate, the node state machine, teardown, the tick, retry, the D296 refusal, stop) lives in `projects.py` beside `ProjectService`; C0, a move with no change of behaviour, splits it into `conductor.py` before MAN-8 so later packages land where the design says. (b) The stored node states are `planned`, `awaiting_approval`, `awaiting_system`, `queued`, `leased`, `running`, `expired`, `done`, `failed`, `cancelled`; `ready` is the moment an answer arrives (the node goes to `planned` or `queued` by its task) and `torn_down` is the column `torn_down_at`; `handing_off` is only a step inside one transaction. (c) A project is made by `reserve` before its tasks and each task is linked by `link_task` in the transaction that makes it (the chat agent's runner makes tasks one transaction each); `reconcile_projects` cancels a node whose task was never made. (d) The flag-off scheduler has the same behaviour as before, with one fix for every task: a process that began for a task that ended meanwhile is stopped. (e) Known limit: the append-only triggers stop UPDATE and DELETE, not `INSERT OR REPLACE` (SQLite fires delete triggers on a replace only with `recursive_triggers`); the guard is a test that scans for the spelling, and a `BEFORE INSERT` trigger goes into v7 if the schema is touched again.**
Why: the design and the code should say the same thing, and each point was a place where building showed a simpler or truer shape. Package: MAN-5 to MAN-7 (done), C0 before MAN-8.

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
| D297 | message `seq` per project | | D302 | no grant, no start |
| D298 | tier 4 and the folder | | D303 | kill switch ownership |
| D299 | builder tools are not a tier | | D304 | phase 1 findings adopted |
| D300 | confirm threshold 500 | | D305 | small rules |
| D301 | planner stop | | D306 | node plan stage |
| | | | D307 | auto output, planner reach |
| | | | D308 | a gate nothing answers yet |
| | | | D309 | hand-off intake rules |
| | | | D310 | retry and failure rules |
| | | | D311 | sleep check and receipt |
| | | | D312 | the design as built |

## Phase 2 rulings, second part (owner, after the phase 2 review)

**D313. Turning the flag off never lets a project's steps run as ordinary tasks. When the app starts with `SUTRA_NODES_V1` off and the database holds a step of a project that has not started (blocked or queued), that step stays on hold with a plain note ("On hold: this step is part of a project, and projects are switched off. Switch them on again, or stop this step") and the owner can stop it like any task. The hold is installed only when such a step exists, so an app that never used projects is exactly as before. A step that already runs is not touched. This amends D254 (what "off" means for a step that waits) and D302.**
Why: an ordinary task has the reach of a whole team run, wider than a node's grant, so letting a waiting step start that way after the flag goes off would give it more than anyone granted; the owner turning the switch off means "stop", not "run it the old way". Rejected: starting them as ordinary tasks (the old text of ENVIRONMENT.md); cancelling them at start (the owner may switch the flag on again and want them). Package: MAN-5 (built as a fix in the phase 2 round).

**D314. An app that was closed is not a node that failed. `reconcile_projects` re-adopts a node whose process still lives (its lease starts again from now). A node found dead because the app was closed (its task ended with "the app was closed") gets a fresh attempt as a new task of the same node, audit `node.restarted`, that does NOT spend its one retry; at most 2 such restart attempts per node (counted from the audit rows), after that the closing counts like any failure. A real failure still has its single retry (`attempt - restarts <= retries`). This amends D277 and D305 (c).**
Why: closing the laptop or the app is the owner's own act, and a project that fails because they went to lunch would be a poor product; the cap stops a node that crashes the app from being started for ever. Rejected: counting the closing as the one retry (the owner's habit would use it up); no cap. Package: MAN-7 (built as a fix in the phase 2 round).

