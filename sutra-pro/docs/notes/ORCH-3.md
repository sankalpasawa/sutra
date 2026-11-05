# ORCH-3 as built: chats, atoms and usage stores with their read routes

Built: `orchestrator/chats.py` (`ChatStore`, `ChatTranscripts`, `parse_options`), `atoms.py` (`AtomStore`, `AtomResult`), `usage.py` (`UsageStore`,
`parse_since`); `api/chat.py` (`/api/chats`, `/api/chats/{sid}`, `.../messages`, `/api/needs-you`), `api/atoms.py` (`/api/atoms`, `/log`, `/{id}`),
`api/usage.py` (`/api/usage`, `/summary`). Tests: `test_chat_store.py`, `test_atoms_usage.py`, `test_api_chat_read.py`: 106 tests, about 4 s.

## Deviations from the specification
- `AtomStore.apply_transition(tx, node, event, *, run_id, task_id=None)` has two extra keyword arguments: the `atom/1` key needs the run, and the task id is the
  server's fact. It returns an `AtomResult` (applied / unchanged / rejected + reason) and never raises for bad event data; the Projector notes a rejection.
- Reads are `AtomStore.find` (not `list`: the name shadows the builtin in the class), `get`, `log`; `ChatStore.sessions/session/messages/last_messages`.
- `UsageStore.record(row, *, tx=None)` opens its own transaction (the router's sink) or joins the Projector's `tx`; the spec had one signature only.
- Ledger and `usage.recorded` writes use `ON CONFLICT ... DO NOTHING`, not `INSERT OR IGNORE` (which would also swallow a CHECK failure).
- `atom_ledger.atom_id` holds the stored key (`<run_id>:W-1.a1` for a builder atom), the body keeps the library id: the column is UNIQUE and J2 restarts at W-1 every run.
- `ChatStore` emits `needs_you.changed {count}` itself (on a question or approval card post, on `mark_answered`); `emit_needs_you(tx)` is public for ChartStore.decide.

## Decisions
- Forward-only rules. Work atoms: open to open with the same or a higher attempt, open to closed or abandoned; closed, abandoned, refused are final; an identical
  body again is `unchanged` (checked before the move rules, so a replay of a final event is not an error). `atom/1`: rank open < verify_failed < closed = abandoned.
- A terminal work atom whose event carries no `ledger` gets the library `ledger_row(atom)`; an open one with a ledger, or a row that disagrees with the atom, is rejected.
  A builder atom is ledgered the first time it is verify_failed, closed or abandoned; a later close adds no second row.
- Server facts win: `task_id` and the node's `department_id` replace the body's; `session_id` is filled from the atom id when missing. No card is posted when the event has none.
- `display` comes only from the checked body. Card message: kind `card`, who = the function name, in the node's own session, `src_ref '<run>#atom:<id>:<outcome>:<attempt>'`.
- `UsageStore`: a reference that points at nothing is stored NULL and kept in `detail.unlinked`; the provider chip (`note_provider`) follows successful requests only, an empty model
  keeps the old one; rows without a task dedupe on `call_ref` too. `include_stub` governs rows, totals and groups alike (default: stub out). Groups: key order, NULL key is `(none)`, days are UTC.
- `ChatStore.messages` of a division session = own rows + department-session rows whose task has `scope_node_id` = the division (lines keep the department `session_id`).
  `phase`: the turn runner sets `reading|planning|building` with `set_turn_phase` (memory only), else `working` while any task is unfinished, else `ready`.
- `needs_you`: unanswered questions of department sessions (options = the `Option N:` lines, J2's `numbered`) plus approval cards whose change is `pending_approval`.
- `apply_links` archives first, then moves; earlier archived sessions filed under a just-archived node are re-filed under the survivor; notes of those stay as they were.
- `set_provider` ignores an unknown session and refuses a provider other than claude/codex/stub/''. Route lists: chats 500 max; messages 200 default, 500 max; atoms/usage 50 default.

## Known limits and follow-ups
- ORCH-5: after `apply_links` re-point a graph node's `chat_session_id` (invariant I1) with `put_node`; this store does not touch `graph_nodes`.
- ORCH-6: call `atoms.apply_transition` after the node row exists; read `AtomResult.reason` for the note; call `usage.record(row, tx=tx)`; no need to emit `needs_you.changed`.
- Library `write_allowlist.txt` (when it lands) needs `UsageStore.record`, `ChatStore.apply_links`, `AtomStore.apply_transition`: they have no `Checked[...]` parameter by design.
- `graph.py` keeps private copies of the session/atom/usage mappers; they could import the ones here.

## Mutation check
22 hand-made mutants (idempotency, answered-once, transcript filter, phase, chip model, re-filing, finality, attempt, ledger conflict, display, second open atom, server facts,
view rank, stub exclusion, chip on failure, no-task dedupe, dangling links, cursor, needs-you scope, atom count, ledger time, none key): 21 killed first; the survivor (server task id
written to the body) became an assertion. No second round.
