# ORCH-5 as built: global org chart store, chart rules, departments, node linker, chart and department routes

Built: `orchestrator/chart_rules.py` (`ChartRules`, `classify`, `reuse_violations`), `chart.py` (`ChartStore`, `ChangeFailed`, `StoredChange`), `departments.py`
(`DepartmentStore`), `nodes.py` (`ensure_node`, `node_init`, `session_kind`), `api/chart.py`, `api/departments.py`. Tests: `test_chart_rules.py`, `test_chart_store.py`
(holds `Env`, which the other three import), `test_departments.py`, `test_api_chart.py`: 118 tests, about 3 s.

## Deviations from the specification
- `ChartStore(db, *, graph, chats, data_dir, departments=None, rules=None, ids=None)`: it needs the graph and chat stores (nodes, sessions, links) and the data dir (folders).
- `ensure_node(tx, spec, *, graph, new_session_id=None)`: the graph store is passed in because `put_node` batches per store and per transaction (one `graph.updated`); the node and
  the session are both gated before either is written, so a refusal leaves nothing. It reads `GraphStore._outs` and `_NODE_COLUMNS` (private, same package) to return a `GraphNodeOut`.
- `apply` assigns the row id itself (`chg-<seq>`, inside the transaction) and stores the change re-gated with that id; a caller's id is only a proposal. `next_change_id()` shows it.
- `apply` returns a `ChangeResult` for applied, pending_approval and stale; violations raise 422 `rules` and store nothing; a SQL or folder error raises `ChangeFailed` (code
  `internal`) after a second small transaction logs a `failed` row. `decide` marks a pending row `failed` the same way.
- `DepartmentStore.list` is `listing` (a method named `list` breaks the annotations of its own class). Extras: `get`, `runs`, `problems` (I4), `write_mirror`.
- Extras on `ChartStore`: `preview` (dry run, no write; used by `dry_run`), `record(change_id)` (checked change, kept plan, reasons), `check_assignments`, `pending`, `next_change_id`.
- The bootstrap row's `body` is the seed `OrgChart` (a `ChartChange` of kind add needs ops, and the root cannot be added); its `base_revision` is 0, which marks it.
- `bootstrap()` returns True when it made the chart. Greeting text: "Hello. Tell me what you need and I will give it to the right team." (the design says only "fixed").

## Decisions
- `busy` counts unfinished tasks (blocked, queued, starting, running, waiting) whose `scope_node_id` lies in the subtree of a moved, merged (each source) or split division; a queued task
  will start against it. A rename is never busy. `reuse_candidate` judges added nodes only (not split parts) against the chart before the change; it is skipped on a stale base.
- Library and our violations are returned together (library first). A change that is `stale` is logged with static plan lists (only ids the ops name that exist; new ids are not known).
- `decide(yes)` re-checks everything; any failure, a moved chart included, makes the row `rejected` with the reasons (design wording), not `stale`.
- `chart.changed` is emitted for every row (applied, pending, stale, rejected, failed) with the LIB keys plus `version`, `summary`, `archived` and `status`; `chart.approval` for a pending row;
  `needs_you.changed` when a pending row is decided. Summaries are written by code ("Added the Web team", "Merged Leads into Quotes"). `task_title` falls back to the reason cut to 60.
- Merge: sessions of merged-away divisions go through `carry_links` (new nodes of the same change included), the survivor's note is "Took in A, B" (kept across merges), steps are re-parented,
  the graph node is deleted, `org_nodes` keeps a retired row (also for a node made and merged in one change). A move writes the note "Moved from A to B"; a rename retitles sessions.
- `departments/<id>` (0700) and `runs/` are made inside the transaction; folders this attempt made are removed on failure. `department.json` is written after COMMIT, best effort.
- `GET /api/chart/changes` is oldest first with a `seq` cursor (the UI fixtures do the same). `POST /api/chart/changes`: 200 applied, 202 pending, 409 `stale_chart` (the result in
  `details.result`), 422 `validation` or `rules`; `dry_run` returns the preview. `already_decided` carries the first result in `details.result`.

## Known limits and follow-ups
- ORCH-8: set `Services.chart`, `.departments`, `.department = departments.row`; run `departments.sweep()` and `chart.bootstrap()` at startup; mount both routers; library write
  allowlist (when it lands) needs `ChartStore.apply/decide/bootstrap`, `ensure_node`, `DepartmentStore.write_mirror`.
- ORCH-7: build the `Checked` change, call `check` first, `classify`, then `apply(..., plan=...)`; read the plan back with `record(id).plan`; post the approval card with the returned id.
- ORCH-6: create step nodes with `ensure_node(tx, node_init(step_node), graph=graph)`; `refresh_function_nodes` at startup is wiring (library function + `graph.put_node`).
- The digest keeps the first 25 departments on ties; function-session titles read "<department> · <Function>".

## Mutation check
31 hand-made mutants (reuse threshold and boundary, classify, open statuses, name equality, scope rule, digest bounds, id widening, chained re-filing, notes, double decision, graph touch,
folder cleanup, mirror, title fallback, needs-you and approval events, positions, retitling, cursor, step re-parenting, stale test, move note, sweep guards, run order, id rule, writable kinds,
session reuse, token guard, stale mapping): 27 killed first; 4 survivors (boundary of 0.5, the 25/40 digest constants, the id rule of `row`) became tests and are killed. No second round.
