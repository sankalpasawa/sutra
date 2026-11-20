# Multi-agent nodes: architecture

Status: proposed, 2026-11-20. Design only. Findings: [analysis.md](analysis.md). Permissions and safety: [guardrails-and-permissions.md](guardrails-and-permissions.md).
Decisions D253 on: [decisions.md](decisions.md). Work packages MAN-1 on: [build-plan.md](build-plan.md).
Phase 1 (MAN-1 to MAN-4) is built; this document was corrected after it from the developer's notes ([dev-notes.md](dev-notes.md)) by the architect rulings D297 to D305. Corrections are marked with their D number.

## 1. The idea in one page

A team run in Sutra Pro is already a small, well-behaved worker: its own process, its own folder, files in and files out, a heartbeat, a stop ladder, crash
recovery. The only things it lacks are an **identity**, a **permission set**, a **budget slice** and a **project around it**.

So the design does not add a new kind of process. It does this:

1. A **node** is a normal run (a `tasks` row, a run folder, a process) that also has a row in a new table `agent_nodes`: who it is, what it may do, how much it may spend.
2. A **project** is a new row that groups the nodes made for one request, with one budget, one stop and one teardown.
3. Two server-side helpers run the project. Both are plain code, not models:
   - the **Conductor** decides when a node may start and watches it;
   - the **Gatekeeper** decides what a node may do and asks the human when a rule says so.
4. Nodes start through the **same** scheduler as every task (`start_ready`), so FIFO, `SUTRA_MAX_RUNS`, `SUTRA_MAX_LIVE`, the spending limit and the stop ladder all apply for free.
5. Everything is off until `SUTRA_NODES_V1=1`. With the flag off, no table is read, no new column is used, and `task.json` is byte-identical to today.

## 2. Context

```mermaid
flowchart TB
  Owner([Owner in the UI])
  subgraph server["Sutra server (one process, the only database writer)"]
    Chat["Org chat agent<br/>(planner identity)"]
    Proj["ProjectService<br/>projects, agent_nodes"]
    Cond["Conductor<br/>(task gate + tick)"]
    Gate["Gatekeeper<br/>(rules, approvals, audit)"]
    Sched["TaskService.start_ready<br/>(unchanged FIFO + caps)"]
    Watch["RunWatcher + Projector<br/>(drain events, project rows)"]
    DB[("SQLite WAL<br/>~/.sutra-pro")]
    Bus["Event bus + SSE"]
  end
  subgraph nodes["Child processes, one per model-using node"]
    W1["Worker node<br/>engine runtime (J2 run)"]
    W2["Worker node<br/>engine runtime"]
    R1["Reviewer node<br/>light runtime"]
  end
  Files[("Run folders<br/>task.json, inbox.jsonl,<br/>events.jsonl, handoff.json")]
  WF[("Owner's working folder<br/>scoped write leases")]
  Prov["Router -> claude / codex CLIs"]
  Owner -->|request, approvals, stop| server
  Chat -->|TaskWorkflow| Proj
  Proj --> Gate
  Gate -->|approval card| Owner
  Proj --> Cond
  Cond -->|task gate| Sched
  Sched -->|spawn| nodes
  nodes <-->|files only| Files
  Files --> Watch
  Watch --> DB
  Proj --> DB
  Gate --> DB
  DB --> Bus --> Owner
  W1 --> WF
  W2 --> WF
  nodes --> Prov
```

Where this sits in the existing system: the new boxes are `ProjectService`, `Conductor`, `Gatekeeper` and the light node host. Everything else on the picture
already exists (`TaskService`, `RunWatcher`, `Projector`, the bus, the run-folder protocol, the router).

## 3. Approach

### 3.1 Node types and roles

| Role | Runtime | Uses a model? | Process? | Job | Starts from |
|---|---|---|---|---|---|
| **Conductor** | server code | no | no (a gate and a tick in the server) | Decides when a node may start, watches leases, tears down, recovers. | project created |
| **Gatekeeper** | server code | no | no | Issues grants, applies rules, asks the human, records the audit. Never a model: a model never approves a model. | project created |
| **Planner** | inline (today's org chat agent stage) | yes, one short call | no (runs in the server as now) | Picks teams and the step graph. Gets an identity and a small budget slice. May add a write scope per step but only narrower than the department's, never wider. | owner request |
| **Worker** | engine runtime (an ordinary J2 run) | yes | yes | Does one plan step as a normal team run. Unchanged inside. | a ready plan step |
| **Reviewer** | light runtime (new small host) | yes | yes | Reads what workers handed off and the folder, read-only, and returns a verdict. | workers done (sub-flag) |

Why only these:

- The engine is frozen, and its five functions share one `J2Run` object. They are **not** split into nodes (see decision D256 and alternative B below).
  A worker node is a whole team run, and the team still has its Identity, Adaptation, Priority, Coordination and Audit inside, exactly as today.
- The planner already exists as the org chat agent's staged calls. It is not a process and does not become one. It gets an identity so it is audited and budgeted like the others.
- The reviewer is a new, small kind of run because the owner asked for an independent reader that is separate from the makers. It does not load J2.

Three runtimes, one protocol:

| Runtime | What runs | Speaks |
|---|---|---|
| `engine` | `python -m sutra_app.engine` (unchanged) | `task.json` in, `events.jsonl` out, `inbox.jsonl`, `heartbeat`, `run.ended` |
| `light` | `python -m sutra_app.nodes` (new, no J2) | the **same** files and the same eight events, so `RunWatcher`, `Projector`, `reconcile` and the stop ladder work on it untouched |
| `inline` | server code | rows and audit only |

### 3.2 What a node is, concretely

A node is two rows and a folder.

```
tasks         (existing)  the run: status, run_id, pid, settings, last_event_at   + new column lane
agent_nodes   (new)       the identity: node_id, project_id, role, runtime, plan_ref, grants, budget slice, write scope, lease
runs/<run_id> (existing)  the folder: task.json now carries an optional "node" block (ignored by older readers)
```

Identity travels in four places so it cannot get lost:

1. `task.json` gets an optional `node` block: `{id, project_id, role, runtime, attempt, grants_id}` (see section 5).
2. `CallTag` gets two optional fields, `node_id` and `node_role` (empty by default), so every model call, usage row and egress row carries them. (The usage row's own `node_id` column is the GRAPH node, so the runtime node goes in its `detail` as `agent_node` and `agent_role`; the egress row has `node` and `role`; the project is one join away: D304.)
3. The child environment gets `SUTRA_NODE_ID` (a plain id, not a secret). The server's own value of it is never passed on: a run is a node only when its `task.json` says so.
4. Every audit row names the node.

### 3.3 Lifecycle

```mermaid
stateDiagram-v2
  [*] --> planned: plan accepted
  planned --> awaiting_approval: needs a grant the rules do not give by default
  awaiting_approval --> ready: owner approves, or the Decide for me rule table answers at once
  awaiting_approval --> cancelled: owner denies or approval expires
  planned --> awaiting_system: the computer has not allowed a folder yet (Mac or Windows permission)
  awaiting_system --> ready: owner allowed it, checked again
  awaiting_system --> cancelled: owner skips these steps
  planned --> ready: dependencies done, no approval needed
  ready --> queued: task row queued (task gate open)
  queued --> leased: slot, write lease, budget slice granted
  leased --> running: run.started seen
  running --> handing_off: run.ended seen
  running --> expired: lease lost (no event for lease_s)
  running --> failed: run.ended crashed or budget stop
  expired --> queued: retry once (attempt + 1)
  expired --> failed: retry used up
  failed --> queued: retry once (attempt + 1)
  handing_off --> done: handoff.json valid, scope check passed
  handing_off --> failed: handoff invalid or scope violation
  done --> torn_down: lease released, temp files swept
  failed --> torn_down
  cancelled --> torn_down
  torn_down --> [*]
```

What each step means in plain words:

| Step | What happens | Who does it |
|---|---|---|
| **spawn** | The Conductor's task gate lets the queued task through (it asks the kill switch first and holds a node with no valid grant: D302, D303). `_prepare_next` makes the run folder and `task.json` (with the `node` block) and the process starts. | Conductor + `TaskService` |
| **lease** | A lease is a row: this node holds this write scope and this slot until `last_beat_at + lease_s`. It is taken inside the same transaction that marks the task `starting`, so two nodes cannot take the same scope. | `_prepare_next` (server) |
| **heartbeat** | The engine's existing heartbeat line every 5 s. The Projector moves `agent_nodes.last_beat_at` (coalesced, at most once per 15 s when nothing else changed). Any event extends the lease. | node writes, Projector reads |
| **hand-off** | On a clean end the host writes `handoff.json` (a summary, the files made with their checksums, claims, status). The Conductor validates it, scrubs it, stores it as a message and releases the lease. | host (writes), Conductor (reads) |
| **finish** | `run.ended` is read as today; the task and the node go terminal. | `Projector` |
| **teardown** | Sweep the node's temp files (`choices.json`, MCP config), release the scope and slot, flush audit, keep the run folder as history. Nothing is deleted that the owner could want. | Conductor |
| **crash recovery** | At app start `reconcile` (unchanged) settles tasks. Then `reconcile_projects` rebuilds leases from rows, re-adopts live nodes, retries or fails the rest. Leases are rows, so a crash loses nothing. | server |

A node never waits for the human while its process is alive. Approvals happen **before** spawn (the plan gate) or **after** a node ends (a `needs_grant` end becomes a card
and then a new attempt). That avoids parked processes, which is the "no idle reaper" problem of F4.

### 3.4 How a project starts

```mermaid
sequenceDiagram
  autonumber
  participant O as Owner
  participant C as Org chat agent (planner)
  participant P as ProjectService
  participant G as Gatekeeper
  participant K as Conductor / start_ready
  participant S as ProcessLauncher
  participant W as Worker node (process)
  participant D as Projector / DB
  O->>C: request (client_id)
  C->>C: staged plan, TaskWorkflow validated
  C->>P: adopt(request, plan, tasks) in the same transaction
  P->>D: projects, agent_nodes, tasks(blocked/queued, lane)
  P->>G: evaluate(plan)
  alt rules need the owner
    G->>O: approval card (needs_you)
    O->>G: approve (idempotent)
  end
  G->>D: grants frozen, audit rows
  K->>K: task gate: kill switch, project state, parallel cap, budget, write lease
  K->>S: spawn ready node (FIFO, caps)
  S->>W: task.json + node block, choices.json
  W-->>D: events.jsonl (run.started, say, usage, heartbeat)
  W->>W: work in its scope
  W-->>D: handoff.json, run.ended
  D->>K: node handing_off
  K->>D: validate, scrub, message, release lease, teardown
  K->>K: dependants ready, start_ready again
  K->>D: last node done: project done, audit export
  D-->>O: project.updated, receipt card
```

## 4. Approach by area

### 4.1 Communication: messages and events

Two kinds of traffic, kept apart.

**Inside a node:** unchanged. The eight run events (`run.started`, `say`, `node`, `step`, `atom`, `usage`, `heartbeat`, `run.ended`) go to `events.jsonl`. No new run event
type is added. Structured payloads travel as **files in the node's own run folder**, the way the live view already does (D133 "a published file, not a ninth run event"):

| File | Written by | Read by | Shape |
|---|---|---|---|
| `handoff.json` | the host, at a clean end (flag on) | Conductor | `handoff/1` (section 5.3) |
| `verdict.json` | the light reviewer | Gatekeeper | `verdict/1` |
| `needs.json` | the light host when it lacks a grant | Gatekeeper | `needs/1`: `{tier, why}` |
| `agent_live.json` | engine or light host | `RunWatcher` | `agent-live/1`, unchanged (so live text uses the existing `chat.partial` path) |

**Between nodes:** only through the server, in a table `node_messages` (append-only, written only by the server). A node never reads another node's folder and never writes to
another node. Dependants receive upstream data through the **existing** `upstream` mechanism (files copied under `upstream/<run id>/`, which the host already checks for
absolute paths, `..` and links) plus the validated `handoff.json`.

Message envelope (`node-message/1`):

```
{ v:1, project_id, seq,            # seq: 1, 2, 3 ... per project, no gap (D297): the writer takes MAX(seq)+1 in its own transaction
  at, from:{node_id, role}, to:{node_id|role|"project"},
  kind: handoff | verdict | gate_request | gate_decision | control | status,
  src_ref,                         # unique per project: "handoff:<node_id>:<attempt>"; a repeat is stored once
  body, body_sha256 }              # body <= 16 KB; anything bigger is a file reference with a sha256
```

Delivery is at least once with `src_ref` de-duplication, so effectively once (the same pattern as `chat_messages.src_ref` and `usage_ledger.call_ref`).

**The `seq` guarantee (D297).** For one project, at every committed state, the stored `seq` values are exactly 1 to n. The key is `(project_id, seq)`, not a table-wide autoincrement (that would give project A the numbers 1, 3, 4). `NodeStore.post` does all of this in one write transaction: look up `(project_id, src_ref)`, and if it is there return that row and take no number; else take `MAX(seq) + 1` for the project and insert. Nothing is ever updated or deleted (triggers; a project is never deleted in v1), a rollback gives the number back, and `project.message` is published after COMMIT. So a page that has `k` and asks `?after=k` gets `k+1, k+2, ...`; a first row that is not `k+1` means a message was lost and the page refetches from its last contiguous number. The snapshot carries `last_message_seq`. There is no global sequence for the page; the bus has its own `seq`.

**To the owner (the page):** project and node changes are ordinary store events emitted after COMMIT, in the style of today's invalidation events:
`project.created`, `project.updated`, `node.updated`, `approval.opened`, `approval.decided`, `project.message`. They go through the same bus, so they get a `seq`, enter the
ring and replay by `Last-Event-ID`. The page then refetches `GET /api/projects/{id}` (a snapshot), the same "events are invalidations, the page refetches" rule as the bus
(`orchestrator/events.py`). Reuse of the streaming contract:

| Streaming contract (D201-D238) | Used for nodes |
|---|---|
| Gap-free `seq`, snapshot plus `after=` catch-up (`LiveTurn`) | `node_messages.seq` (per project, D297) and `GET /api/projects/{id}/messages?after=` |
| State words `accepted, running, stopping, done, stopped, failed` | Node states map one to one: `queued/leased` is accepted, `running`, `stopping` (stop ladder), `done`, `cancelled` is stopped, `failed` |
| `heartbeat` with real idle time and idle limit | The node's `last_beat_at` and the lease length are shown the same way ("quiet for 40 s of 90 s") |
| `chat.partial` live text of AI workers | A worker's live text is unchanged |
| Idempotent send with `client_id` (D219, D220) | `POST /api/projects` and approval answers |
| One `CancelToken` per turn (D215) | The planner's call (bound to its spawned process, D301) and a light node's calls |

### 4.2 Shared state and who owns it

The rule that keeps this safe: **every piece of state has exactly one writer.**

| State | Where | Single writer | Readers |
|---|---|---|---|
| `projects`, `agent_nodes`, `node_messages`, `node_audit`, `approvals` | SQLite | the server, always inside `db.tx()` | server, UI through the API |
| `tasks` (+ `lane`) | SQLite | `TaskService` / `Projector` (as today) | server |
| `usage_ledger` | SQLite | `UsageStore` (as today) | server |
| `task.json`, `inbox.jsonl`, `choices.json` | run folder | the server, before start (as today) | the node |
| `events.jsonl`, `handoff.json`, `verdict.json`, `needs.json`, `agent_live.json`, J2 files | run folder | the node that owns the folder | server |
| The owner's working folder | disk | only a node holding a write lease on that path, and only in its scope | owner, other nodes (read) |
| Provider slots (optional, sub-flag) | `<data>/connectors/slots/*.lock` | each router's `flock` on a slot file | all routers |
| `quota.json` | `<data>/connectors/` | routers (as today) | all |
| Kill and pause files `<data>/nodes/KILL`, `PAUSE` | disk | the owner (by hand, or `sutra-pro nodes`) or the server | `NodeControl` watcher (every 2 s) and the task gate; the Conductor tick may also look; the light host |

**SQLite approach.** Keep SQLite, WAL, one writer (D16). Nodes never open the database. New tables are additive in migration v6. To stop heartbeats from flooding the writer:

- The Projector skips the `tasks.touch` of a heartbeat-only batch when the last touch was less than 15 s ago. The offset is replay-safe (`src_ref` and `call_ref` make a replay harmless), so a crash re-reads at most 15 s of lines.
- Project and node updates happen **inside the Projector's existing transaction** for that run, not in extra ones.
- Node message and audit rows are small (body at most 16 KB, reasons at most 200 characters).
- Acceptance test (package MAN-12): 12 fake nodes for 5 minutes with `StoreBusy` count zero. If it fails, the next step is a batch window of 250 ms per project, not a new database.

### 4.3 Scheduling and parallelism from plan edges

One scheduler. The Conductor is a **gate** on it, not a second queue.

- **Plan edges** already exist: a step's `depends_on` becomes `tasks.depends_on`, and `settle_blocked` turns `blocked` into `queued` when the dependencies end well, or cancels it when one ends badly (F7 of the failure table in `orchestrator.md`). Reused as is.
- **Conflict edges** are new and implicit: two steps that write overlapping paths must not run together. The Gatekeeper computes them from write scopes at plan time and the task gate enforces them at start time with a lease check. A conflict edge **delays**; it never cancels, so a failed sibling does not cancel a step that only waited for a folder.
- **Write scope** per writing step: a list of relative paths or folders. The department's output spec decides if a step may write at all (`workspace_for`). The planner may **narrow** the scope, never widen it. No declared scope means "the whole folder", so that step runs alone among writers. If the folder is not a git work tree, writers run one at a time (the post-run check needs git).
- **Same-team parallelism** (sub-flag `SUTRA_NODES_LANES`): a node task gets `lane = node_id`. The unique index becomes `(dept_id, lane)`. Every ordinary task has lane `''`, so the rule for them is identical to today. `live_in`, `deliver_to_department` and `stop_live(dept)` look only at lane `''`: a node is addressed by node id only.
- **What may start**: `_prepare_next` already walks queued tasks in FIFO order and asks `why_waiting` and `start_gate`. A new optional `task_gate(conn, now, row)` is asked next, in the same transaction. It answers with a waiting sentence or empty. It checks, in order: master kill and pause (`NodeControl.gate`, built in MAN-4; the Conductor's gate asks it first and adds the rest, never replaces it: D303), that the node has a valid grant (a node with none is held, never started as an ordinary task: D302), project state, node state, parallel cap of the project, project budget, write lease, provider slot. A held task stays `queued` with the sentence as its detail (the `Limits` pattern) and starts by itself when the reason ends.
- **Caps** are shared. Node tasks count in `counts_in`, so `SUTRA_MAX_RUNS` and `SUTRA_MAX_LIVE` bound the whole machine. A project adds its own `max_parallel` (default 3).
- **Order** is FIFO by task creation, which is plan order. Critical-path ordering is a non-goal for v1.
- **Inside a department** the J2 engine still runs its own builders one after another. That is a known limit, not a regression. The seam for later is the Coordination function's schedule; it needs a J2 sync and is outside this design.

### 4.4 Budget and limits, per node and per project

| Level | What | How it is enforced | Existing piece reused |
|---|---|---|---|
| App | `SUTRA_MAX_RUNS`, `SUTRA_MAX_LIVE`, monthly dollars, plan-window guard | unchanged (`start_ready`, `Limits.gate`) | all of it |
| Provider | at most N Claude and M Codex CLIs for the whole machine | file-lock slots shared by every router (sub-flag `SUTRA_NODES_SLOTS`) | `policy.max_concurrency` for N and M |
| Project credits | a ceiling in work credits (default = the sum of the nodes' slices, so total spend equals today's separate tasks) | slices are carved at plan time so the sum never exceeds the ceiling; the task gate refuses a spawn when the unspent slices do not fit | `J2_BUDGET` |
| Project dollars | optional ceiling | the Conductor tick sums `usage_ledger` by the project's task ids; over the ceiling stops nodes with the stop ladder | `UsageStore.rows(task_id=)` |
| Node credits | one slice per engine node | `task.json` settings `J2_BUDGET` and `J2_BUDGET_CAP` both set to the slice. A raise is a question to the Gatekeeper and then to the owner, never self-served (P25 kept) | `TaskSettings` |
| Node calls, dollars, time | `max_calls` (default 60), `max_usd` (optional), `wall_s` (default 1800) | a `NodeMeter` in Sutra's own `engine/llm.py` shim adds `Allowance(max_calls, max_usd, deadline, envelope_id=node id)` to each call, from a running total in the process. Past a cap the host stops the run with outcome "Stopped: node limit (calls)" | `Allowance` and `Router.check_gate` |
| Retries | one per node, review loops at most 2, nodes spawned at most `max_nodes` (workers only, reviewers on top: D305) | counted in `agent_nodes` and `projects` rows | `attempts.py` |
| Plan confirm threshold | 500 work credits (D300): the plan gate asks when the estimate is over it; not asked when the owner gave their own `budget` | `caps_json["confirm_credits"]`, default in `config.py`; a step with no estimate counts as its slice | `Plan.confirm_credits` in `gatekeeper.py` |

Honest limits: the dollar cap sees only Claude's list-price figure (Codex rows carry tokens, no dollars, D37), so a Codex node is bounded by calls and time. The router's
`Allowance` was per request; the new `NodeMeter` makes it cumulative per node by passing the remaining amount each time.

### 4.5 Failure handling

| # | Failure | What happens | Result for the project |
|---|---|---|---|
| N1 | Node process crashes (`run.ended crashed`, or pid gone) | Existing path marks the task crashed. The Conductor retries once as a new attempt (`attempts.py`), with the earlier attempt's outcome told to it. | After the retry fails: node `failed`, policy applies |
| N2 | Node is silent past its lease | In project mode only, the Conductor asks the stop ladder to end it, marks `expired`, retries once. A sleeping laptop is detected (the Conductor's own tick gap is larger than half the lease). If the project has no open gate, the lease is extended once instead. If it has an open gate (approval or system permission), a closed laptop is a refusal: see N14. | as N1 |
| N14 | The laptop sleeps, or the app is closed, while a gate is open (D296) | Every open gate of the project counts as refused. Waiting nodes are `cancelled` ("the computer went to sleep before you answered" or "Sutra was closed before you answered"), running nodes of the project are stopped with the stop ladder, the project is `stopped`, and one receipt card says why. Detected by the Conductor's tick gap, and by `reconcile_projects` after a restart. | project `stopped` |
| N3 | Node hits its own cap (calls, dollars, time, credits) | The host stops the run; outcome names the limit. No retry (a retry would hit the same cap). The Gatekeeper may offer the owner a raise card. | node `failed` with reason `limit` |
| N4 | Project ceiling reached | Tick stops running nodes with the ladder; no new spawns; one card to the owner. | project `stopped` |
| N5 | Hand-off missing, too big, malformed or with a path outside the folder | Node is not `done`; one retry; then `failed`. The bad file is kept for the owner. | policy applies |
| N6 | Scope violation (a path changed that no running node owns) | All writers of the project are paused (no new spawns, running writers asked to stop), audit row, card to the owner. | project `awaiting_approval` |
| N7 | Reviewer says `changes_requested` | The worker's step gets one more attempt, at most `max_review_loops` (2). Then a card to the owner. | continues or waits for the owner |
| N8 | Reviewer says `reject` | Dependants cancelled, card to the owner. | policy applies |
| N9 | Approval never answered | Expires after 24 h; the held nodes are `cancelled` ("not approved"). No process was running. With Decide for me on there is no wait: the Gatekeeper's rule table answers at once (guardrails 5.1) and this row cannot happen. | project `stopped` (switch off only) |
| N10 | Database busy past 5 s (`StoreBusy`) | The gate returns "waiting" and the tick tries again. Nothing is half-written (single transaction). | none |
| N11 | App closed or crashed with live nodes | At start `reconcile` then `reconcile_projects` (section 3.3). | resumes or fails per node |
| N13 | The computer has not allowed a folder (macOS "Operation not permitted", Windows "Access is denied") | Found by the probe before spawn: the node waits in `awaiting_system` with one card, the rest runs. Found late, during a run: the node ends as `needs_system_permission` (no retry) and the same card appears. Never answered by Decide for me. | only the affected steps wait or are cancelled |
| N12 | Kill switch | The stop ladders of every live node run together (about 12 s in all, D303), audit row, no new spawns until cleared. Every project with a live node becomes `stopped`, its queued and blocked nodes are `cancelled`, and nothing restarts by itself after resume. Pause only holds. A node the owner or the switch stopped is never retried. | project `stopped` |

**Failure policy** per project, set at plan time, default `stop_branch`: a failed node cancels only its dependants (what a failed task does today), siblings go on. The other
choice is `stop_all`. Nothing silently continues: a project that ends with a failed node ends `done_with_open_items` or `stopped`, never `done`.

## 5. Components

| Component | New / changed | Responsibility | Files | Public interface |
|---|---|---|---|---|
| `ProjectService` | new | Create a project from a plan, own the project and node rows, adopt tasks, build the snapshot. | `sutra_app/orchestrator/projects.py` | `adopt(tx, request, plan, task_ids) -> ProjectOut`, `snapshot(id)`, `stop(id)`, `pause(id)` |
| `NodeStore` | new | Rows of `agent_nodes`, `node_messages`, `node_audit`, `approvals`; leases; state moves. | `sutra_app/orchestrator/nodes_store.py` | `put_node`, `lease(tx, node, now)`, `release(tx, node)`, `post(tx, msg)`, `audit(tx, row)` |
| `KillSwitch`, `NodeControl` | new (MAN-4, built) | The two files, the stop and pause levels, the 2-second watcher, the node stop, an audit row for each. Calls the one stop ladder through `TaskService.stop_node`. | `sutra_app/orchestrator/killswitch.py`, `sutra_app/ops/nodes.py` | `KillSwitch.held()`, `NodeControl.gate`, `stop_node`, `pause_all`, `kill_all`, `resume`, `enforce` |
| `Conductor` | new | The task gate, the tick, hand-off intake, teardown, expiry, `reconcile_projects`. | `sutra_app/orchestrator/conductor.py` | `task_gate(conn, now, row) -> str`, `tick(now)`, `on_run_ended(task_id)`, `reconcile_projects()` |
| `Gatekeeper` | new | Role table, grant calculation (an intersection), tier rules, approval cards, audit of decisions. | `sutra_app/orchestrator/gatekeeper.py`, `sutra_app/orchestrator/grants.py` | `evaluate(plan) -> Evaluation`, `grant_for(node) -> Grant`, `decide(approval_id, answer)` |
| Project routes | new | HTTP surface (token, flag-guarded). | `sutra_app/orchestrator/api/projects.py` | see section 6 |
| Light node host | new | A small run host for the reviewer: same files and events, no J2. | `sutra_app/nodes/__main__.py`, `host.py`, `reviewer.py`, `templates/reviewer.md` | `python -m sutra_app.nodes --run-dir <dir>` |
| `TaskService` | changed (small) | `lane` in the busy key; optional `task_gate`; node block in `_run_spec`; node retries. | `sutra_app/orchestrator/tasks.py`, `waiting.py` | `TaskService(..., task_gate=None)` |
| `Projector` | changed (small) | Update node rows inside its existing transaction; coalesce heartbeats; call `Conductor.on_run_ended`. | `sutra_app/orchestrator/projector.py` | unchanged public surface |
| `RunSpec` / `TaskSpec` | changed (additive) | Optional `node` block. Written only when the flag is on. | `sutra_app/orchestrator/models.py`, `sutra_app/engine/spec.py` | `RunSpec.node: NodeBlock | None = None`; excluded from the dump when `None` |
| `CallTag` | changed (additive) | Optional `node_id`, `node_role`. | `sutra_app/engine/port.py` | two new optional fields |
| `engine/llm.py` shim | changed (additive) | `NodeMeter`: cumulative calls, dollars, deadline per node. | `sutra_app/engine/llm.py` | `configure(..., meter=None)` |
| `host/finish.py` | changed (additive step) | `handoff` step: write `handoff.json`. Only when the task says it is a node. | `sutra_app/engine/host/finish.py`, `handoff.py` | `finish.run_steps` gains one step |
| Router slots | new, optional | A file-lock slot per provider, shared across processes. | `sutra_app/connectors/slots.py`, `router.py` (one hook) | `Slots.acquire(provider) -> Slot` |
| Scoped folder grant | changed (additive) | `Folder` may carry `scope`; Claude gets `Edit(<scope>/**)` rules. | `sutra_app/connectors/workdir.py`, `claude.py`, `codex.py` | `Folder(..., scope=())` |
| Egress | changed (additive, built) | The audit row also records `node` and `role` from the tag (the project is one join away, D304). | `sutra_app/connectors/egress.py` | two optional fields |
| Schema | changed (additive, built) | Migration v6: five tables, `tasks.lane`, index swap. | `sutra_app/orchestrator/schema.py` | `DDL_V6_NODES` |
| Config | changed (additive) | The flags and defaults. | `sutra_app/config.py`, `sutra_app/ops/envfile.py` | `Settings.nodes_v1` etc. |
| UI | new | A project page: node list, graph, approval card, stop, audit. Behind the flag. | `sutra_app/ui/static/js/project_*.js`, `sutra_app/ui/...` | page `/p/<id>` |

### 5.1 The `node` block in `task.json`

```
"node": { "id": "nd_<12 hex>", "project_id": "prj_<12 hex>", "role": "worker|reviewer",
          "runtime": "engine|light", "attempt": 1, "grants_id": "gr_<12 hex>",
          "caps": { "calls": 60, "usd": null, "wall_s": 1800 }, "scope": ["site/pricing/"] }
```

MAN-8 adds one more optional key, `tool_profile` (`none|sutra|github|sutra+github`, from the grant), so an engine worker's calls can carry the tools it was granted (D298); `folder` needs no key, because the router already derives it from the tag and the owner's access.

`TaskSpec` already has `extra="ignore"` ("a newer orchestrator may add some", `engine/spec.py` line 91), so an older engine reads the file as before. The block is **left out** of the
dump when the flag is off, so `task.json` is byte-identical to today (golden test).

### 5.2 The grant (frozen at spawn)

A grant is data: `{id, node_id, role, tiers: [0..4], folder: none|read|inspect|edit, scope: [...], tool_profile: none|sutra|github|sutra+github, commands: none|git_reads, run_tools: none|engine, caps}`.
It is computed once by the Gatekeeper as the **intersection** of the role table, the plan, the department's output spec and the owner's own folder access. It never changes
during the node's life. The connectors enforce it with what they already have (see the mapping table in the guardrails document).

How the parts relate (D298, D299, D304):

- `tiers` are not a ladder: a grant lists each tier it holds (a reviewer holds 0, 1 and 3, never 2).
- `folder` is what the node may do in the owner's folder. It is capped by the owner's access and by the department's output spec (`workspace_for`). `inspect` is read plus the four git reads (`Router.folder_for`).
- Tier 1 = a folder to read, or the `sutra` part of the profile. Tier 2 = folder `edit`. Tier 3 = the four git reads (`commands = git_reads`). Tier 4 = the `github` part of the profile. The owner's folder access caps the first three through `folder`; it does not cap the profile.
- `run_tools` describes J2's builder tools in the run folder: `engine` for a worker (the engine's own rule, as today), `none` otherwise. It is written in the audit and not enforced by the grant; it is not a tier and not capped by the owner's access.
- `from_json` checks a stored grant by the same rules as a new one, so a row edited by hand cannot be wider than the role table.

### 5.3 `handoff.json` (`handoff/1`)

```
{ "v":1, "node_id", "status": "done|done_with_open_items|blocked",
  "summary": "<= 2000 chars, plain text, treated as data",
  "files": [ {"path":"relative/path", "sha256":"...", "bytes": 1234} ],      # at most 200, paths checked
  "claims": [ "<= 200 chars each, at most 20" ],
  "needs": [ {"tier": 3, "why": "<= 200 chars"} ] }                           # light nodes only
```

The host builds `files` from the folder watch and the run's own files, not from what an agent says. The Conductor re-checks every path (relative, no `..`, no link,
inside the node's scope or its run folder) and every checksum before accepting.

## 6. Interfaces / APIs

Every route answers `404 not_found` while `SUTRA_NODES_V1` is off, before the token is looked at. With it on, every write needs the launch token (`require_token`); reads need none, as every read of the app (D305).

| Route | Request | Response | Errors |
|---|---|---|---|
| `POST /api/projects` | `{request_id?, client_id, text?, budget?}` | `201 ProjectOut`; a repeated `client_id` answers `200 {duplicate:true, project}` | 400 bad body; 409 `busy` (a project for that request is live); 422 plan refused; 503 `store_busy` |
| `GET /api/projects` | `?status=&limit=&offset=` | `ProjectOut[]` | |
| `GET /api/projects/{id}` | | snapshot: project, nodes, edges, caps, spend, open approvals, last message seq | 404 |
| `GET /api/projects/{id}/messages` | `?after=<seq>&limit=` | `node_message[]` (secrets redacted) | 404 |
| `GET /api/projects/{id}/audit` | `?after=<seq>&limit=` | `audit_row[]` | 404 |
| `POST /api/projects/{id}/approvals/{aid}` | `{decision: "allow_once"|"allow_project"|"deny", client_id}` | `ApprovalOut`; a repeat is a no-op `{duplicate:true}` | 404; 409 `decided`; 422 `allow_project` on tier 5 or 6 |
| `POST /api/projects/{id}/stop` | `{}` | `{stopped: n}` | 404 |
| `POST /api/projects/{id}/pause` | `{resume?: bool}` | `ProjectOut` | 404 |
| `GET /api/nodes/status` | | `{level: none|pause|kill, kill, pause}` (what the two files say; the page's way to learn the flag: 404 means off) | |
| `POST /api/nodes/pause-all` and `/kill-all` | `{reason?}` | `{affected: n}`: for pause, nodes now waiting to start; for kill, nodes stopped | |
| `POST /api/nodes/resume` | `{}` | `{resumed: bool}`: removes both files; what was held starts | |
| `POST /api/nodes/{id}/stop` | `{}` | `{stopped: bool}` (`false` for a node whose task is over) | 404 only for an id that does not exist |

Error codes reuse the app's closed set where one fits (`not_found`, `busy`, `store_busy`, `validation`). One new code: `node_limit` (a cap stopped something), carried as data, never a new HTTP status.

New card: `NodeApprovalCard {type:"node_approval", project_id, approval_id, question, options[], impact[]}` in `needs_you`, shaped like `ApprovalCard`.

## 7. Data model

Migration `DDL_V6_NODES` (one tuple, one transaction, never edited later):

```
projects        id TEXT PK ('prj_'+12 hex), request_id TEXT UNIQUE, title, status CHECK (planning, awaiting_approval, running, reviewing, done,
                done_with_open_items, stopped, failed), failure_policy ('stop_branch'|'stop_all'), decide_for_me 0|1, paused 0|1, review_loops,
                caps_json, budget_credits, budget_usd, client_id UNIQUE, created_at, ended_at, stop_reason
agent_nodes     id TEXT PK ('nd_'+12 hex), project_id FK, task_id UNIQUE FK NULL, role CHECK (planner, worker, reviewer),
                runtime CHECK (inline, engine, light), plan_ref, depends_on JSON, state CHECK (planned, awaiting_approval, awaiting_system, ready, queued, leased,
                running, handing_off, done, failed, cancelled, expired), attempt, grants_json, writes_json, slice_credits,
                lease_expires_at, last_beat_at, failure_reason, torn_down_at, created_at, ended_at
node_messages   project_id FK, seq INTEGER (>= 1), from_node, to_node, kind CHECK (...), src_ref, body, body_sha256, at,
                PRIMARY KEY (project_id, seq), UNIQUE(project_id, src_ref)   -- seq per project, no gap (D297)
                + triggers: no UPDATE, no DELETE (D264)
node_audit      seq INTEGER PK AUTOINCREMENT, at, project_id, node_id, role, actor, action, tier, target, decision, reason, ref, hash
                + triggers: no UPDATE, no DELETE (the pattern of atom_ledger)
approvals       id TEXT PK ('ap_'+12 hex), project_id FK, node_id, tier, request_json, status CHECK (open, allowed_once, allowed_project, denied,
                expired), decided_by ('owner'|'system'|'rule:<name>'), decided_at, expires_at, client_id, created_at
tasks           + lane TEXT NOT NULL DEFAULT ''
index swap      DROP INDEX tasks_one_live_per_dept; CREATE UNIQUE INDEX tasks_one_live_per_dept_lane ON tasks(dept_id, lane)
                WHERE status IN ('starting','running','waiting_user')
```

Notes from the build (D304, D305): `agent_nodes.task_id` (UNIQUE) points at the node's current attempt; an earlier attempt stays in `tasks` through `parent_task_id`, and a retry re-points the row in the same transaction that makes the new task. Projects are never deleted in v1, because the append-only tables refer to them. `paused` is a column because a paused project is still `running` in the status list.

Backward compatibility:

- Every existing task has `lane = ''`, so the new unique index forbids exactly what the old one forbids.
- Older code reading a v6 file stops with the existing message "the database is newer than this app understands: update the app" (`db.py` `migrate`). That is the same rule as v2 to v5. The pre-upgrade backup the app already makes (`ops/backup.py`) covers it.
- With the flag off, the five tables stay empty and nothing reads them.
- Disk: `<data>/projects/<project_id>/` holds the audit export (`audit.jsonl`, mode 0600) written at project close. Run folders stay where they are.

## 8. Cross-cutting

| Topic | Rule |
|---|---|
| Errors | A node failure never fails the server. Every Conductor action is wrapped; an error is logged, audited and the node is failed with a reason. |
| Logging | Ids only (`prj_`, `nd_`, `tsk_`). No prompt text, no file contents. Reasons are clipped to 200 characters and redacted. |
| Config | `SUTRA_NODES_V1` (master, default 0), `SUTRA_NODES_LANES`, `SUTRA_NODES_REVIEWER`, `SUTRA_NODES_SLOTS` (each default 0 and effective only with the master). Caps in `projects.caps_json` with defaults in `config.py`. |
| Security | See the guardrails document. Nodes never open the database or call the server. The launch token never reaches a node (`child_environment` already drops it). |
| Performance | Heartbeats coalesced; node writes ride the Projector's transaction; one watcher task per live node as today; no per-node database connection. Targets: 12 nodes, no `StoreBusy`, page update within 1 s of an event. |
| Concurrency | The task gate runs inside `_prepare_next`'s single write transaction, so the lease check and the lease take are atomic. The Conductor tick uses `run_blocking` like every store call. |
| Time | The lease uses the injected `Clock` (tests), and the sleeping-laptop check uses a monotonic gap. |
| Privacy | Everything stays under the data folder. No network service. Audit rows hold names and shapes, never content. |

## 9. Preservation: each existing behaviour and how it is kept

| Existing behaviour | Kept by |
|---|---|
| Checkpoints | Nodes are runs, so run files, `snapshot.json` and `LiveTurn` checkpoints are untouched. The planner's turn keeps its checkpoint. Project state is rows plus files, rebuilt at start. |
| Resume | `reconcile` runs first and unchanged. `reconcile_projects` is read-and-repair on top. A follow-up task and `rehydrate` work on a node's run like any run. |
| Stop and `CancelToken` | A node stop is `launcher.stop` (the same ladder). The project stop calls it per node, all together (D303). The planner and the light host use a `CancelToken` as chat turns do, bound to the spawned process, so a Stop ends the running call (D301). |
| Idempotent send | `client_id` on project start and approvals; `src_ref` on messages. |
| Egress scrub | Both modes stay. New: hand-off and messages are scrubbed in `replace` mode; light-node prompts are scrubbed by the host before the call; audit rows gain node fields. |
| Budgets | Slices become `J2_BUDGET`; raises stay the Requester's; `Limits` still gates the start; the monthly dollar limit still applies. |
| J2 provider seam | `llm.py`, `ModelPort`, `Router`, `ChatPort` unchanged in shape. Optional tag fields and an optional allowance only. |
| Local-first | All new rows and files are in the data folder. |
| Releases | No change to release scripts, workflows, packaging or version numbers. |
| Vendored J2 | No `j2*.py` change; `test_engine_vendor.py` and the prompt goldens still pass. |

## 10. Test strategy

Runs with the fake engine (`SUTRA_ENGINE=fake`, `FakeLauncher`, `ScriptedConnector`); the default suite never calls a model (`orchestrator.md` section 7). Mapped to the work packages.

| Layer | What it covers |
|---|---|
| Unit | Role table and grant intersection (never wider than the owner's access); tier rules; scope overlap; budget slicing (sum never exceeds the ceiling); `NodeMeter`; `handoff.json` validation (paths, sizes, checksums); injection wrapper; state machine moves (only allowed edges); message de-duplication. |
| Store | Migration v6 on an empty file and on a v5 file with data; the lane index keeps the old rule for lane `''`; append-only triggers; `src_ref` uniqueness. |
| Integration | A project of 4 steps with `FakeLauncher`: edges respected, parallel steps run together, a conflict edge delays, caps hold, a failed node cancels only its branch; kill and stop; crash and restart (`reconcile_projects`); lease expiry; approval allow, deny and expiry; budget ceiling stop; `StoreBusy` retry. |
| Contract | `task.json` byte-identical with the flag off (golden); `RunSpec` dump with a node block validates in `TaskSpec`; event set of `events.jsonl` is still the closed eight; the bus topics. |
| Phase 1 additions | `seq` stays 1 to n under two projects, a repeated `src_ref` and a rollback (D297); a read-only owner still gets tier 4 when approved, and never tier 2 or 3 (D298); a document run's grant has `run_tools = engine` and tiers 0 and 1 (D299); a node with no valid grant is held, never started (D302); kill-all with several nodes ends in one ladder's time (D303). |
| Safety | A planted-instruction hand-off ("ignore your rules, enable writes") changes no grant and no edge; a secret in a hand-off is redacted; a path outside scope pauses the project; no route works with the flag off. |
| Preservation | The whole existing suite with the flag off: unchanged. Vendored-file hashes unchanged. |
| e2e (beta app, by hand) | The owner runs a 3-step project in the beta and stops it. `live_smoke.py` is **not** run (it spends quota, `AGENTS.md`). |

## 11. Rollout and risk

Order: schema and flags first (inert), then identity and audit (no behaviour), then the gate and project rows, then parallel same-team lanes, reviewer, slots. Each package leaves the
build green and the flag off by default. Try each in the beta app (`~/.sutra-pro-beta`) as `AGENTS.md` says; release only when the owner asks.

Rollback: set `SUTRA_NODES_V1=0`. Running projects are stopped first by the kill switch. Rows stay and are ignored. The migration is additive, so no data is lost.

| Risk | Likelihood | Mitigation |
|---|---|---|
| Parallel writers corrupt the owner's folder | medium | Scoped leases, path attribution, pause on violation, writers serialise when no git or no scope. Default `lanes` off. |
| A node is told something that changes its behaviour (prompt injection) | medium | Data wrapper, structured hand-off, no grant changes from content, tests with planted text. |
| Hand-offs leak secrets | low | Scrub in `replace` mode before storing and before giving to the next node. |
| More processes exhaust the machine or quota | medium | Shared caps, optional provider slots, per-node call and time caps. |
| SQLite write pressure | low now, rising | Coalesced heartbeats; the MAN-12 load test; batch window as the next step. |
| Scope enforcement is weaker on Codex than on Claude | medium | Backstop is the path check. A writer with a multi-path scope is routed to Claude. Documented. |
| The Conductor tick stops while the server runs | low | Tick is also driven by `start_ready` kicks; a missed tick delays but never loses state (rows). |
| Owner confusion between "graph node" and "node" | low | UI says "agent"; docs say "runtime node". |

## 12. Alternatives considered

| Option | What it is | Why not |
|---|---|---|
| **A. Agents as threads in the server** | Run each agent as an asyncio task or thread in the one server process. | `engine/llm.py` configuration and the J2 environment are module-level, per process (`loop.py` docstring: the J2 environment is set before `engine.j2` is imported). Two J2 runs in one process would share them. No OS isolation, no kill without taking the server down. Rejected. |
| **B. Split J2's five functions into five nodes** | Identity, Adaptation, Priority, Coordination and Audit each become a process. | They share one `J2Run` object and its lock. Splitting is a rewrite of a frozen engine (D13, D249). The owner said enhance, do not replace. Rejected. |
| **C. A broker and remote workers** | Redis or a queue, workers on other machines. | A new service and dependency, breaks local-first, and the file protocol plus one SQLite writer is enough at the target of 12 to 24 nodes. Rejected; the node protocol is files, so a remote node stays possible later. |
| **D. (chosen) Node = run + identity + project** | New rows around the existing run. | Reuses scheduler, stop ladder, recovery, usage and the router. Smallest change that gives identity, limits and a project. |

## 13. Traceability

The owner's asks, with where each is answered.

| Ask | Design | Test | Package |
|---|---|---|---|
| Nodes spawned for a project and torn down | 3.3, 3.4 | integration: project of 4 steps | MAN-5, MAN-6 |
| Parallel where the plan allows | 4.3 | integration: edges, conflicts, caps | MAN-5, MAN-10 |
| Planner, workers, reviewer, gatekeeper | 3.1 | unit and integration | MAN-2, MAN-3, MAN-5, MAN-11 |
| Lifecycle: lease, heartbeat, hand-off, crash recovery | 3.3 | integration: expiry, restart | MAN-5, MAN-6, MAN-7 |
| Message and event contract | 4.1 | contract tests | MAN-6, MAN-13 |
| Shared state and SQLite | 4.2, 7 | store tests, load test | MAN-1, MAN-12 |
| Budgets and limits | 4.4 | unit and integration | MAN-9, MAN-12 |
| Failure handling | 4.5 | integration | MAN-7 |
| Guardrails, permissions, approvals, audit, kill, injection, egress | guardrails document | safety tests | MAN-2, MAN-3, MAN-4, MAN-8, MAN-14 |
| Flag off keeps today | 5.1, 7, 9 | preservation tests | every package |
| Resume of messages by `after=` | 4.1 (`seq` guarantee), 7 | store and message tests | MAN-1, MAN-6 |
| A node can reach only what its grant says, builder tools and network told truthfully | 5.2, guardrails 3 and 4 | grant tests | MAN-2, MAN-8 |
| Stop means stop, also for the planner | 4.5, 9 | kill, planner stop tests | MAN-4, MAN-5 |

## 14. Decisions

D253 to D305 in [decisions.md](decisions.md). D297 to D305 are the architect's rulings after phase 1 (seq per project, tier 4 and the folder, builder tools are not a tier, the confirm threshold, the planner's stop, no grant no start, kill switch ownership, adopted findings, small rules). D294 is Decide for me for projects (the project runs with no input; a rule table answers the gates). D295 is operating-system permissions per system, Mac and Windows (checked before a node starts; only the owner can grant them). D296: a closed laptop is a refusal. The main ones: D253 node = run plus identity, D254 flag off by default, D257 one scheduler with a task gate, D258 lanes,
D262 server is the only writer, D266 the Gatekeeper is code, D267 grants frozen at spawn, D271 budget slices.
