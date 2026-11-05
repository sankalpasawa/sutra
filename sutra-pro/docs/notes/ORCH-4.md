# ORCH-4 as built: workflow graph store and routes

Built: `orchestrator/graph.py` (`GraphStore(db, specs=None)`: `view`, `node`, `get`, `put_node`, `put_edge`, `aggregate`, plus `delete_node`,
`delete_edge`, `touch`) and `orchestrator/api/graph.py` (`GET /api/graph`, `GET /api/graph/nodes/{id}`, `build_router()`).
Tests: `test_graph_store.py` (with the reusable `World` builder) and `test_api_graph.py`: 78 tests, about 1 s.

## Deviations from the specification
- Extra methods ORCH-5/6 need and the spec does not name: `delete_node` (a merged-away division's node is deleted, not archived), `delete_edge`,
  `touch(tx)` (counts a transaction as a graph change once, so a reuse-only chart change still moves `graph_version`) and `get(id)`.
- NodeDetail needs rows of `chat_sessions`, `atoms`, `usage_ledger` and `tasks` whose owners (ORCH-3, ORCH-6) have not merged: graph.py reads
  them with its own private mappers (`_session_out`, `_atom` rows, `_task_out`, `_usage_totals`). ORCH-3/6 may share theirs later.

## Decisions
- The row `version` column is the node's wire version (new = 1, each change + 1). The body is stored exactly as the Checked JSON, so `sha256`
  matches it; its own `version` and `ts_updated` are ignored when deciding "unchanged".
- The store owns `edge_ids`: `put_node` always makes them the ids of the stored edges that touch the node (re-gated), and `put_edge`,
  `delete_edge`, `delete_node` re-store both ends, so `check_graph` G5 holds. A node that arrives without `chat_session_id` keeps the stored one.
- `put_edge` refuses `contains`, `has_function`, `has_step` (ValueError): I7. A step node id must equal `step_node_id(task_id, step_ref)`.
- One `graph.updated` per transaction: the first change bumps `meta.graph_version` and emits; later changes edit that event's data in
  place before COMMIT (it relies on `Tx.pending` returning the same Event objects). Atom counts in it are read at put time.
- `level=chart`: the root, every department and division, and each department's newest task step (`step_ref='task'`, newest by `created_at`).
  `level=full`: all function nodes and every step of the not-finished tasks plus the 5 newest finished tasks per department
  (`RECENT_TERMINAL_TASKS`). `task=` shows only that task's steps (chart level: its task step only). `dept=` keeps that department's
  subtree and its ancestors up to the root (so the tree stays connected); a non-department id or an unknown task is 404.
- Pre-order: children = chart children by `org_edges.position` (then id), function nodes in the fixed order, steps by `ts` (creation, kept
  across updates; the node's `ts_created`, else the write time) then id. A step may hang on a step or a division.
- `meta.run_id`: department = its live task's run, else its newest task that has a run; step = its task's run; left out while there is none.
- `aggregate`: department live task -> `waiting_on_you` (task waits for the owner, or a function node waits on you) else `running`, detail untouched;
  no live task -> `fault` if the newest task crashed else `idle`, detail `last: <title>, <how it ended>`. A division mirrors its department only
  while a task scoped to exactly that division is live (not its ancestors). Root: waiting_on_you > running > idle (a fault does not show).
- NodeDetail: `atoms` = the open atom(s) first, then the 20 newest others (so up to 21); usage and `usage_total` leave stub rows out and give
  null for a part that is null in every row; a department's `usage_total` sums by `dept_id`, every other node by `node_id`; `task` = a step's own,
  or a department's / function node's live task.
- Responses scrub through `Services.redact.scrub` when it has one, then the redacting JSON response.

## Known limits and follow-ups
- ORCH-5 must run I1 against `ensure_node` itself (here `test_every_node_has_one_session` only proves the view reports the column).
- ORCH-6 (Projector) should call `put_node` with nodes built from `store.get()`, call `aggregate(tx)` after each batch, and note that atom
  counts in `graph.updated` come from the `atoms` rows present when `put_node` runs (upsert the atom first).
- `test_api_graph.py` imports `World` from `orchestrator.test_graph_store` (the folder is a package under the tests/ path root).

## Mutation check
25 hand-made mutants (orders, recent-task bound, restamp ignore, derived-kind guard, atom counts, atoms limit, root precedence, stub exclusion,
session keep, ancestors, version bump, scope mirror, step id guard, edge ends, id pattern ...): 24 killed first; the survivor (step order by
creation time, hidden because ids agreed) became `test_creation_time_beats_the_id_when_they_disagree`. No second round.
