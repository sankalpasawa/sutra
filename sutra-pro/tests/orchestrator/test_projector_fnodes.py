"""Function atoms and builder atoms through the Projector (ORCH-6): the transitions the function-node layer writes become `atoms`, Atom log
rows, cards in the node's own session, `open_atom` and `atom_count` on the node, `stats` and `atom.updated` events; a task that ends in any
way abandons its open atoms; the golden run of the engine replays into consistent rows, and replaying it again changes nothing."""
import json
from pathlib import Path

from factories_atom import abandon, close_with, open_transition, tried
from orchestrator.test_tasks import tenv, TEnv, ev  # noqa: F401  (tenv is a fixture)

from sutra_app.library.atom import AtomView, ViewCheck, atom_display_state, ledger_row
from sutra_app.library.types import FUNCTIONS

GOLDEN = Path(__file__).resolve().parents[1] / "engine" / "golden" / "run_events.jsonl"
AT = "2026-11-04T10:00:00Z"
NODE = "web.priority"


def atom_line(t, *, ledger="auto", **over) -> dict:
    """The `atom` line the layer writes for a library Transition (a function atom)."""
    a = t.atom
    if ledger == "auto":
        ledger = ledger_row(a).model_dump(mode="json") if a.state != "open" else None
    return {"t": "atom", "at": AT, "node": a.node_id, "outcome": t.outcome, "card": t.card.model_dump(mode="json"), "ledger": ledger,
            "atom": {"id": a.id, "schema": "work-atom/0.3", "goal": a.goal, "work_kind": a.work.dispatch_kind, "verify_template": "file-exists",
                     "status": a.state, "attempt": a.attempt, "closed_by": a.closed_by, "reason": a.reason, "body": json.loads(a.model_dump_json()),
                     "ts_open": a.ts_open, "ts_closed": a.ts_closed}, **over}


def view_line(node: str, status: str, *, vid: str = "W-1.a1", attempt: int = 0, ts_closed: int | None = None) -> dict:
    check = ViewCheck(check="exists", method="file-exists: site/index.html", met=None if status == "open" else status == "closed",
                      evidence=None if status in ("open", "closed") else "site/index.html is missing")
    view = AtomView(id=vid, workflow="W-1", name="Landing page", status=status, attempt=attempt or None, goal="The page exists", verification=[check])
    return {"t": "atom", "at": AT, "node": node, "atom": {
        "id": vid, "schema": "atom/1", "goal": "The page exists", "work_kind": "llm", "verify_template": "file-exists", "status": status,
        "attempt": attempt, "closed_by": None, "reason": None, "body": view.model_dump(mode="json"), "ts_open": 5000, "ts_closed": ts_closed}}


def fresh(t: TEnv, atom_id: str = "a-3f9a1c2b7d-01", node: str = NODE):
    return open_transition(node_id=node, id=atom_id, department_id="web")


def go(t: TEnv, task_id: str, *events: dict):
    t.write_events(task_id, *events)
    return t.drain(task_id)


def cards_of(t: TEnv, node_id: str) -> list[str]:
    return [m.card.label for m in t.chats.messages(t.graph.get(node_id).chat_session_id) if m.card is not None]


def counts(t: TEnv, node_id: str) -> dict:
    return {r["display"]: r["n"] for r in t.sql("SELECT display, count(*) AS n FROM atoms WHERE node_id = ? GROUP BY display", node_id)}


# ---- function atoms --------------------------------------------------------------------------------------------------------------

def test_open_failed_try_close_is_stored_carded_ledgered_and_counted(tenv):
    task = tenv.started()
    opened = fresh(tenv)
    go(tenv, task, atom_line(opened))
    node = tenv.graph.get(NODE)
    assert (node.open_atom, node.atom_count) == (opened.atom.id, 1)
    row = tenv.sql("SELECT * FROM atoms WHERE id = ?", opened.atom.id).fetchone()
    assert (row["state"], row["display"], row["attempt"], row["task_id"], row["department_id"], row["schema"]) == ("open", "open", 0, task, "web", "work-atom/0.3")
    failed = close_with(opened.atom, 1)
    assert failed.outcome == "verify_failed"
    go(tenv, task, atom_line(failed))
    assert (tenv.sql("SELECT state, display, attempt FROM atoms WHERE id = ?", opened.atom.id).fetchone()[:]) == ("open", "open", 1)
    assert tenv.one("SELECT count(*) FROM atom_ledger") == 0                     # a failed try with tries left writes no log row
    done = close_with(failed.atom, 0)
    assert done.outcome == "closed"
    result = go(tenv, task, atom_line(done))
    assert result.applied == 1
    row = tenv.sql("SELECT * FROM atoms WHERE id = ?", opened.atom.id).fetchone()
    assert (row["state"], row["display"], row["attempt"], row["ts_closed"] is not None) == ("closed", "closed", 2, True)
    node = tenv.graph.get(NODE)
    assert (node.open_atom, node.atom_count) == (None, 1)
    log = tenv.atoms.log()
    assert [(r.atom_id, r.status, r.node_id) for r in log] == [(opened.atom.id, "closed", NODE)]
    assert cards_of(tenv, NODE) == ["WORK ATOM OPEN", "VERIFY FAILED", "WORK ATOM CLOSED"]
    outcomes = [e.data["outcome"] for e in tenv.env.events.events if e.type == "atom.updated"]
    assert outcomes == ["opened", "verify_failed", "closed"]


def test_stats_count_atoms_by_display_word(tenv):
    task = tenv.started()
    a = fresh(tenv, "a-aaaaaaaaaa-01")
    b = fresh(tenv, "a-aaaaaaaaaa-02")
    c = fresh(tenv, "a-aaaaaaaaaa-03")
    lines = [atom_line(a), atom_line(close_with(a.atom, 0)), atom_line(b)]
    lines.append(atom_line(abandon(tried(b.atom, 3), "verify failed: file-exists: missing", code="verify_failed")))
    lines += [atom_line(c)]
    go(tenv, task, *lines)
    stats = [n for n in tenv.graph.view(level="full").nodes if n.id == NODE][0].meta["stats"]
    assert (stats["atoms_open"], stats["atoms_closed"], stats["atoms_failed"], stats["atoms_total"]) == (1, 1, 1, 3)
    assert counts(tenv, NODE) == {"closed": 1, "verify_failed": 1, "open": 1}


def test_a_verify_failed_atom_has_one_ledger_row_with_the_word_verify_failed(tenv):
    task = tenv.started()
    base = fresh(tenv)
    ended = abandon(tried(base.atom, 3), "verify failed: file-exists: missing", code="verify_failed")
    go(tenv, task, atom_line(base), atom_line(ended))
    assert tenv.sql("SELECT state, display FROM atoms").fetchone()[:] == ("abandoned", "verify_failed")
    log = tenv.atoms.log()
    assert [(r.status, r.body["status"], r.body["reason"]) for r in log] == [("verify_failed", "verify_failed", "verify failed: file-exists: missing")]
    assert cards_of(tenv, NODE)[-1] == "WORK ATOM ABANDONED"


def test_a_refused_open_is_stored_ledgered_and_carded_and_the_node_stays_free(tenv):
    task = tenv.started()
    refused = open_transition(node_id=NODE, id="a-3f9a1c2b7d-02", department_id="web", goal="done")
    assert refused.outcome == "refused"
    go(tenv, task, atom_line(refused))
    row = tenv.sql("SELECT state, display, attempt FROM atoms WHERE id = 'a-3f9a1c2b7d-02'").fetchone()
    assert tuple(row) == ("refused", "refused", 0)
    assert [(r.status, r.body["status"]) for r in tenv.atoms.log()] == [("refused", "refused")]
    assert cards_of(tenv, NODE) == ["ATOM REFUSED"]
    node = tenv.graph.get(NODE)
    assert (node.open_atom, node.atom_count) == (None, 1)
    go(tenv, task, atom_line(fresh(tenv, "a-3f9a1c2b7d-03")))                       # the next turn can open an atom
    assert tenv.graph.get(NODE).open_atom == "a-3f9a1c2b7d-03"


def test_a_second_open_atom_on_one_node_is_refused_and_noted(tenv):
    task = tenv.started()
    result = go(tenv, task, atom_line(fresh(tenv, "a-3f9a1c2b7d-01")), atom_line(fresh(tenv, "a-3f9a1c2b7d-02")))
    assert tenv.one("SELECT count(*) FROM atoms") == 1 and result.skipped == 0
    notes = [t for (_, kind, t) in [(m.who, m.kind, m.text) for m in tenv.chats.messages(tenv.graph.get("web.identity").chat_session_id)] if kind == "note"]
    assert len(notes) == 1 and "already has the open atom" in notes[0]


def test_replaying_an_atom_line_changes_nothing(tenv):
    task = tenv.started()
    opened = fresh(tenv)
    lines = [atom_line(opened), atom_line(close_with(opened.atom, 0))]
    go(tenv, task, *lines)
    before = (tenv.one("SELECT count(*) FROM atom_ledger"), tenv.one("SELECT count(*) FROM chat_messages"), tenv.sql("SELECT sha256 FROM atoms").fetchone()[0],
              len(tenv.env.events.events))
    tenv.sql("UPDATE tasks SET events_offset = 0 WHERE id = ?", task)
    tenv.drain(task)
    assert (tenv.one("SELECT count(*) FROM atom_ledger"), tenv.one("SELECT count(*) FROM chat_messages"), tenv.sql("SELECT sha256 FROM atoms").fetchone()[0]) == before[:3]
    assert not [e for e in tenv.env.events.events[before[3]:] if e.type == "atom.updated"]


def test_an_earlier_try_of_an_open_atom_is_a_silent_replay(tenv):
    task = tenv.started()
    opened = fresh(tenv)
    failed = close_with(opened.atom, 1)
    go(tenv, task, atom_line(opened), atom_line(failed))
    go(tenv, task, atom_line(opened))                                             # the opening line again, after the first failed try
    assert tenv.sql("SELECT attempt FROM atoms").fetchone()[0] == 1
    assert [m for m in tenv.chats.messages(tenv.graph.get("web.identity").chat_session_id) if m.kind == "note"] == []


def test_a_function_atom_for_another_department_or_a_made_up_node_is_skipped(tenv):
    task = tenv.started()
    elsewhere = open_transition(node_id="sales.priority", id="a-3f9a1c2b7d-01", department_id="sales")
    result = go(tenv, task, atom_line(elsewhere))
    assert (result.applied, result.skipped, tenv.one("SELECT count(*) FROM atoms")) == (0, 1, 0)


# ---- the end of a task abandons what is open ---------------------------------------------------------------------------------------

def _open_atom_task(t: TEnv):
    task = t.started()
    opened = fresh(t)
    go(t, task, atom_line(opened))
    return task, opened


def test_run_ended_abandons_the_open_function_atoms(tenv):
    task, opened = _open_atom_task(tenv)
    go(tenv, task, ev("run.ended", status="done_with_open_items", outcome="left things open"))
    row = tenv.sql("SELECT state, display FROM atoms").fetchone()
    assert tuple(row) == ("abandoned", "abandoned")
    atom = tenv.atoms.get(opened.atom.id)
    assert atom.body["reason"] == "run ended: done_with_open_items" and atom.body["abandon_code"] == "run_ended"
    assert [(r.atom_id, r.status) for r in tenv.atoms.log()] == [(opened.atom.id, "abandoned")]
    assert cards_of(tenv, NODE)[-1] == "WORK ATOM ABANDONED"
    node = tenv.graph.get(NODE)
    assert (node.open_atom, node.atom_count) == (None, 1)
    assert [e.data["outcome"] for e in tenv.env.events.events if e.type == "atom.updated"][-1] == "abandoned"


def test_a_crash_and_a_stop_abandon_open_atoms_too(tenv):
    task, opened = _open_atom_task(tenv)
    tenv.projector.mark_ended(task, "crashed", "boom")
    assert tenv.atoms.get(opened.atom.id).body["reason"] == "run ended: crashed"
    second = tenv.started(dept="sales", text="x")
    node = "sales.priority"
    go(tenv, second, atom_line(open_transition(node_id=node, id="a-3f9a1c2b7d-09", department_id="sales")))
    tenv.run(tenv.service.stop(second))
    assert tenv.atoms.get("a-3f9a1c2b7d-09").body["reason"] == "run ended: stopped"
    assert tenv.one("SELECT count(*) FROM atoms WHERE state = 'open'") == 0


# ---- builder atoms (atom/1) ---------------------------------------------------------------------------------------------------------

def test_builder_atoms_are_keyed_by_the_run_and_get_one_ledger_row_the_first_time_they_are_terminal(tenv):
    task = tenv.started()
    run = tenv.row(task).run_id
    go(tenv, task, ev("step", step="W-1", name="Landing page", status="running"), view_line("W-1", "open"))
    key = f"{run}:W-1.a1"
    node = tenv.sql("SELECT id FROM graph_nodes WHERE task_id = ? AND step_ref = 'W-1'", task).fetchone()[0]
    row = tenv.sql("SELECT * FROM atoms WHERE id = ?", key).fetchone()
    assert (row["schema"], row["node_id"], row["display"], row["task_id"]) == ("atom/1", node, "open", task)
    assert tenv.one("SELECT count(*) FROM atom_ledger") == 0
    go(tenv, task, view_line("W-1", "verify_failed", attempt=1), view_line("W-1", "closed", attempt=2, ts_closed=5100))
    assert tenv.sql("SELECT display FROM atoms WHERE id = ?", key).fetchone()[0] == "closed"
    log = tenv.atoms.log()
    assert [(r.atom_id, r.status, r.node_id) for r in log] == [(key, "verify_failed", node)]      # the first terminal word; a later close adds no row
    go(tenv, task, view_line("W-1", "closed", attempt=2, ts_closed=5100))
    assert len(tenv.atoms.log()) == 1
    assert [e.data["outcome"] for e in tenv.env.events.events if e.type == "atom.updated"] == ["opened", "verify_failed", "closed"]


def test_two_runs_with_the_same_builder_atom_id_give_two_rows(tenv):
    first = tenv.started()
    go(tenv, first, ev("step", step="W-1", name="Page", status="running"), view_line("W-1", "open"))
    tenv.projector.mark_ended(first, "done", "ok")
    second = tenv.started()
    go(tenv, second, ev("step", step="W-1", name="Page", status="running"), view_line("W-1", "open"))
    assert tenv.one("SELECT count(*) FROM atoms WHERE schema = 'atom/1'") == 2


def test_an_older_builder_line_is_a_silent_replay_but_a_conflicting_final_is_noted(tenv):
    task = tenv.started()
    go(tenv, task, view_line("W-1", "closed", attempt=1, ts_closed=5100))
    notes = lambda: [m.text for m in tenv.chats.messages(tenv.graph.get("web.identity").chat_session_id) if m.kind == "note"]
    go(tenv, task, view_line("W-1", "open"))                                              # an earlier state of the same atom: nothing to say
    assert tenv.sql("SELECT display FROM atoms").fetchone()[0] == "closed" and notes() == []
    go(tenv, task, view_line("W-1", "abandoned", attempt=1, ts_closed=5200))              # another final word: the store refuses and it is noted
    assert tenv.sql("SELECT display FROM atoms").fetchone()[0] == "closed"
    assert len(notes()) == 1 and "final" in notes()[0]


# ---- the golden run -------------------------------------------------------------------------------------------------------------------

def golden_events() -> list[dict]:
    return [json.loads(line) for line in GOLDEN.read_text().splitlines() if line.strip()]


def table_state(t: TEnv) -> dict:
    return {name: [tuple(r) for r in t.sql(sql)] for name, sql in {
        "atoms": "SELECT id, state, display, attempt, sha256 FROM atoms ORDER BY id",
        "ledger": "SELECT seq, atom_id, node_id, status, body FROM atom_ledger ORDER BY seq",
        "chat": "SELECT session_id, who, kind, text, card_json, src_ref FROM chat_messages ORDER BY id",
        "usage": "SELECT call_ref, node_id, atom_id, tokens_in FROM usage_ledger ORDER BY id",
        "nodes": "SELECT id, state, sha256 FROM graph_nodes ORDER BY id",
        "task": "SELECT status, outcome FROM tasks ORDER BY id"}.items()}


def replay_golden(t: TEnv) -> str:
    task = t.new(text="Brew Lab: a site for a craft coffee roaster")
    t.run(t.service.start_ready())
    (t.run_dir(task.id) / "events.jsonl").write_bytes(GOLDEN.read_bytes())
    while t.drain(task.id).more:
        pass
    return task.id


def test_the_golden_run_replays_into_consistent_rows(tenv):
    task = replay_golden(tenv)
    events = golden_events()
    atoms = {}
    for e in events:
        if e["t"] == "atom":
            atoms[e["atom"]["id"]] = e                                                # the last line of each atom
    row = tenv.row(task)
    assert row.status == "done" and row.outcome.startswith("Done: the site is workable")
    stored = {r["id"]: r for r in tenv.sql("SELECT * FROM atoms")}
    assert set(stored) == set(atoms) and len(stored) == 31
    for atom_id, last in atoms.items():
        body = last["atom"]
        assert stored[atom_id]["state"] == body["status"] and stored[atom_id]["attempt"] == body["attempt"]
        assert stored[atom_id]["display"] == atom_display_state(body["body"])
    assert tenv.one("SELECT count(*) FROM atoms WHERE state = 'open'") == 0                    # none open at run.ended
    ledger_ids = [r.atom_id for r in tenv.atoms.log(limit=500)]
    assert sorted(ledger_ids) == sorted(atoms) and len(ledger_ids) == len(set(ledger_ids))      # the log holds every atom once
    assert {"closed"} == {r.status for r in tenv.atoms.log(limit=500)}          # GAP-TUNE: no atom of the mock run fails its checks now
    for fn in FUNCTIONS:
        node = tenv.graph.get(f"web.{fn}")
        mine = [a for a, e in atoms.items() if e["node"] == node.id]
        assert (node.open_atom, node.atom_count) == (None, len(mine))
        assert sum(counts(tenv, node.id).values()) == len(mine)
        assert len(cards_of(tenv, node.id)) >= len(mine)                                        # at least one card per transition that carries one
    expected_cards = sum(1 for e in events if e["t"] == "atom" and e.get("card"))
    assert sum(len(cards_of(tenv, f"web.{fn}")) for fn in FUNCTIONS) == expected_cards


def test_golden_usage_invariants(tenv):
    task = replay_golden(tenv)
    usage_lines = [e for e in golden_events() if e["t"] == "usage"]
    assert tenv.one("SELECT count(*) FROM usage_ledger") == len(usage_lines) == 34
    assert tenv.one("SELECT count(*) FROM usage_ledger WHERE provider != 'stub' AND atom_id IS NULL") == 0
    assert tenv.one("SELECT count(*) FROM usage_ledger WHERE atom_id IS NULL") == 0                  # stub rows carry one too
    run = tenv.row(task).run_id
    builder = tenv.sql("SELECT atom_id, node_id FROM usage_ledger WHERE call_ref LIKE '%:10'").fetchone()
    assert tuple(builder) == (f"{run}:W-1.a1", None)                                          # no step node yet: the link stays empty
    groups = tenv.usage.summary("atom", include_stub=True)
    assert sum(g["tokens_in"] for g in groups) == tenv.one("SELECT sum(tokens_in) FROM usage_ledger") and sum(g["calls"] for g in groups) == 34
    assert tenv.usage.summary("atom") == []                                                   # stub rows are out of every total


def test_replaying_the_golden_run_a_second_time_changes_nothing(tenv):
    task = replay_golden(tenv)
    before = table_state(tenv)
    versions = tenv.one("SELECT value FROM meta WHERE key = 'graph_version'")
    published = len(tenv.env.events.events)
    tenv.sql("UPDATE tasks SET events_offset = 0, status = 'running', ended_at = NULL WHERE id = ?", task)       # the file is read again from the top
    again = tenv.drain(task)
    assert again.applied > 0
    tenv.sql("UPDATE tasks SET status = 'done', ended_at = started_at, outcome = (SELECT outcome FROM tasks WHERE id = ?) WHERE id = ?", task, task)
    after = table_state(tenv)
    for name in ("atoms", "ledger", "chat", "usage"):
        assert after[name] == before[name], name
    assert tenv.one("SELECT value FROM meta WHERE key = 'graph_version'") == versions
    assert not [e for e in tenv.env.events.events[published:] if e.type in ("atom.updated", "usage.recorded", "chat.message")]


def test_the_golden_events_all_parse_strictly():
    from sutra_app.orchestrator.models import parse_event
    events = golden_events()
    assert len(events) == 155
    for line in GOLDEN.read_text().splitlines():
        parse_event(line, strict=True)
