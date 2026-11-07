"""AtomStore and UsageStore (ORCH-3): both atom schemas through `apply_transition`, forward-only moves, `display`, the append-only Atom
log, replays; usage rows, idempotent `call_ref`, stub rows, totals and groups."""
import json
import sqlite3

import pytest
from factories_atom import abandon, close_with, open_transition
from orchestrator.test_graph_store import World, tid

from sutra_app.connectors.usage import UsageIn
from sutra_app.library.atom import AtomView, ViewCheck, ledger_row
from sutra_app.library.gate import GATE, GateError
from sutra_app.orchestrator.atoms import AtomStore
from sutra_app.orchestrator.chats import ChatStore
from sutra_app.orchestrator.errors import NotFound
from sutra_app.orchestrator.models import RunAtom
from sutra_app.orchestrator.usage import NO_KEY, UsageStore, parse_since

RUN = "j2-20261104-100001-aaaa"
NODE = "web.adaptation"
AT = "2026-11-04T10:00:00Z"


@pytest.fixture
def world(db, clock):
    return World(db, clock)


@pytest.fixture
def chats(db):
    return ChatStore(db)


@pytest.fixture
def atoms(db, world, chats):
    return AtomStore(db, chats=chats, graph=world.store)


@pytest.fixture
def usage(db, chats):
    return UsageStore(db, chats=chats)


@pytest.fixture
def task(world):
    return world.task(1, "web", "running")


# ---- events ------------------------------------------------------------------------------------------------------------------------

def fn_event(t, *, ledger="auto", card=True, outcome="auto", **over) -> RunAtom:
    """The `atom` line the function-node layer writes for a library Transition."""
    a = t.atom
    if ledger == "auto":
        ledger = ledger_row(a).model_dump(mode="json") if a.state != "open" else None
    body = {**json.loads(GATE.check("atom", a).json), **over.pop("body", {})}
    return RunAtom.model_validate({
        "t": "atom", "at": AT, "node": over.pop("node", a.node_id),
        "atom": {"id": a.id, "schema": "work-atom/0.3", "goal": a.goal, "work_kind": a.work.dispatch_kind, "verify_template": "file-exists",
                 "status": a.state, "attempt": a.attempt, "closed_by": a.closed_by, "reason": a.reason, "body": body,
                 "ts_open": a.ts_open, "ts_closed": a.ts_closed, **over},
        "outcome": t.outcome if outcome == "auto" else outcome, "card": t.card.model_dump(mode="json") if card else None, "ledger": ledger})


def view_event(node: str, status: str, *, vid: str = "W-1.a1", attempt: int = 0, ts_closed: int | None = None, **over) -> RunAtom:
    check = ViewCheck(check="exists", method="file-exists: site/index.html", met=None if status == "open" else status == "closed",
                      evidence=None if status in ("open", "closed") else "site/index.html is missing")
    view = AtomView(id=vid, workflow="W-1", name="Landing page", status=status, attempt=attempt or None, goal="The page exists", verification=[check])
    return RunAtom.model_validate({
        "t": "atom", "at": AT, "node": node,
        "atom": {"id": vid, "schema": "atom/1", "goal": "The page exists", "work_kind": "llm", "verify_template": "file-exists",
                 "status": status, "attempt": attempt, "closed_by": None, "reason": None, "body": view.model_dump(mode="json"),
                 "ts_open": 5000, "ts_closed": ts_closed, **over}})


def apply(db, atoms, event, *, run=RUN, task=None):
    with db.tx() as tx:
        return atoms.apply_transition(tx, event.node, event, run_id=run, task_id=task)


def row(world, atom_id):
    r = world.sql("SELECT * FROM atoms WHERE id = ?", atom_id).fetchone()
    return dict(r) if r is not None else None


def opened(**over):
    over.setdefault("node_id", NODE)
    return open_transition(**over)


def failed_try(t):
    return close_with(t.atom, 1)


# ---- a function atom's life --------------------------------------------------------------------------------------------------------

def test_opening_stores_the_row_posts_the_card_updates_the_node_and_emits_in_order(db, world, atoms, chats, task, events):
    events.batches.clear()
    t = opened()
    result = apply(db, atoms, fn_event(t), task=task)
    assert (result.status, result.display, result.outcome, result.ledgered) == ("applied", "open", "opened", False)
    r = row(world, t.atom.id)
    assert (r["schema"], r["state"], r["display"], r["attempt"], r["node_id"], r["task_id"], r["department_id"]) == (
        "work-atom/0.3", "open", "open", 0, NODE, task, "web")
    assert r["goal"] == t.atom.goal and r["sha256"] and r["ts_open"] == t.atom.ts_open and r["ts_closed"] is None
    [card] = chats.messages(world.session_of[NODE])
    assert (card.kind, card.who, card.card.type, card.card.outcome, card.card.label, card.task_id) == ("card", "adaptation", "atom", "opened", "WORK ATOM OPEN", task)
    assert world.sql("SELECT src_ref FROM chat_messages").fetchone()[0] == f"{RUN}#atom:{t.atom.id}:opened:0"
    body = world.store.get(NODE)
    assert (body.open_atom, body.atom_count) == (t.atom.id, 1)
    assert events.types() == ["chat.message", "graph.updated", "atom.updated"]
    updated = events.events[-1].data
    assert (updated["atom_id"], updated["node_id"], updated["outcome"], updated["state"]) == (t.atom.id, NODE, "opened", "open")
    assert updated["atom"]["schema"] == "work-atom/0.3" and updated["atom"]["state"] == "open"
    assert world.sql("SELECT count(*) FROM atom_ledger").fetchone()[0] == 0


def test_a_failed_try_keeps_the_atom_open_at_a_higher_attempt_and_cards_it_without_a_ledger_row(db, world, atoms, chats, task):
    t0 = opened()
    apply(db, atoms, fn_event(t0), task=task)
    t1 = failed_try(t0)
    result = apply(db, atoms, fn_event(t1), task=task)
    assert (result.status, result.display, result.outcome) == ("applied", "open", "verify_failed")
    r = row(world, t0.atom.id)
    assert (r["state"], r["display"], r["attempt"]) == ("open", "open", 1)
    assert [c.card.outcome for c in chats.messages(world.session_of[NODE])] == ["opened", "verify_failed"]
    assert world.sql("SELECT count(*) FROM atom_ledger").fetchone()[0] == 0
    assert world.store.get(NODE).open_atom == t0.atom.id


def test_closing_ledgers_the_atom_once_and_frees_the_node(db, world, atoms, task):
    t0 = opened()
    apply(db, atoms, fn_event(t0), task=task)
    t1 = close_with(t0.atom, 0)
    result = apply(db, atoms, fn_event(t1), task=task)
    assert (result.display, result.outcome, result.ledgered) == ("closed", "closed", True)
    assert row(world, t0.atom.id)["display"] == "closed" and row(world, t0.atom.id)["ts_closed"] == t1.atom.ts_closed
    [entry] = atoms.log()
    assert (entry.atom_id, entry.node_id, entry.status, entry.seq) == (t0.atom.id, NODE, "closed", 1)
    assert entry.body["kind"] == "atom_ledger_row" and entry.body["status"] == "closed" and entry.ts.endswith("Z")
    body = world.store.get(NODE)
    assert (body.open_atom, body.atom_count) == (None, 1)


def test_an_atom_abandoned_for_failed_verification_shows_verify_failed_while_its_state_stays_abandoned(db, world, atoms, task):
    t = opened()
    apply(db, atoms, fn_event(t), task=task)
    last = t
    for _ in range(3):
        last = failed_try(last)
        apply(db, atoms, fn_event(last), task=task)
    ended = abandon(last.atom, "verify failed: file-exists: missing", code="verify_failed")
    result = apply(db, atoms, fn_event(ended), task=task)
    assert (result.display, result.outcome) == ("verify_failed", "abandoned")
    r = row(world, t.atom.id)
    assert (r["state"], r["display"], r["attempt"]) == ("abandoned", "verify_failed", 3)
    assert atoms.log()[0].status == "verify_failed"
    assert atoms.get(t.atom.id).state == "verify_failed"


def test_any_other_abandon_shows_abandoned_and_is_ledgered_as_abandoned(db, world, atoms, task):
    t = opened()
    apply(db, atoms, fn_event(t), task=task)
    result = apply(db, atoms, fn_event(abandon(t.atom, "run ended: stopped", code="run_ended")), task=task)
    assert result.display == "abandoned" and row(world, t.atom.id)["display"] == "abandoned"
    assert [e.status for e in atoms.log()] == ["abandoned"] and world.store.get(NODE).open_atom is None


def test_a_refused_atom_is_stored_ledgered_carded_and_does_not_hold_the_node(db, world, atoms, chats, task):
    t = open_transition(node_id=NODE, goal="done")
    assert t.outcome == "refused"
    result = apply(db, atoms, fn_event(t), task=task)
    assert (result.display, result.outcome, result.ledgered) == ("refused", "refused", True)
    assert row(world, t.atom.id)["state"] == "refused" and atoms.log()[0].status == "refused"
    assert chats.messages(world.session_of[NODE])[0].card.outcome == "refused"
    other = open_transition(node_id=NODE, id="a-3f9a1c2b7d-02")
    assert apply(db, atoms, fn_event(other), task=task).status == "applied"
    assert world.store.get(NODE).atom_count == 2


def test_a_terminal_event_without_a_ledger_row_gets_the_librarys_row(db, world, atoms, task):
    t = opened()
    apply(db, atoms, fn_event(t), task=task)
    result = apply(db, atoms, fn_event(close_with(t.atom, 0), ledger=None), task=task)
    assert result.ledgered and atoms.log()[0].body["status"] == "closed"


def test_the_servers_task_and_department_replace_what_the_body_says(db, world, atoms, task):
    t = opened()
    result = apply(db, atoms, fn_event(t, body={"task_id": "elsewhere", "department_id": "sales"}), task=task)
    assert result.applied
    r = row(world, t.atom.id)
    assert (r["task_id"], r["department_id"]) == (task, "web")
    stored = GATE.check("atom", row_body(world, t.atom.id)).model
    assert (stored.task_id, stored.department_id, stored.session_id) == (task, "web", "3f9a1c2b7d")           # the body agrees with the columns


def row_body(world, atom_id):
    return world.sql("SELECT body FROM atoms WHERE id = ?", atom_id).fetchone()[0]


# ---- forward only, one open atom, replays --------------------------------------------------------------------------------------------

def _stored(db, world, atoms, task, *steps):
    """Apply the events and return the rows' fingerprint, to prove a refusal changed nothing."""
    for event in steps:
        assert apply(db, atoms, event, task=task).status == "applied"
    return world.sql("SELECT id, state, display, attempt, sha256 FROM atoms ORDER BY id").fetchall(), world.sql("SELECT count(*) FROM chat_messages").fetchone()[0]


def test_a_final_atom_accepts_no_later_move(db, world, atoms, task, events):
    t0 = opened()
    closed = close_with(t0.atom, 0)
    before = _stored(db, world, atoms, task, fn_event(t0), fn_event(closed))
    count = len(events.events)
    for later in (fn_event(t0), fn_event(abandon(t0.atom, "late", code="manual"))):
        result = apply(db, atoms, later, task=task)
        assert result.status == "rejected" and "final" in result.reason
    assert _stored(db, world, atoms, task) == before and len(events.events) == count
    assert row(world, t0.atom.id)["display"] == "closed"


def test_the_attempt_never_goes_down(db, world, atoms, task):
    t0 = opened()
    t1 = failed_try(t0)
    t2 = failed_try(t1)
    _stored(db, world, atoms, task, fn_event(t0), fn_event(t1), fn_event(t2))
    result = apply(db, atoms, fn_event(t1), task=task)
    assert result.status == "rejected" and "back" in result.reason
    assert row(world, t0.atom.id)["attempt"] == 2


def test_a_node_holds_one_open_atom_and_the_second_is_refused_and_noted(db, world, atoms, task):
    first = opened()
    _stored(db, world, atoms, task, fn_event(first))
    second = open_transition(node_id=NODE, id="a-3f9a1c2b7d-02")
    result = apply(db, atoms, fn_event(second), task=task)
    assert result.status == "rejected" and first.atom.id in result.reason
    assert row(world, second.atom.id) is None
    elsewhere = open_transition(node_id="web.priority", id="a-3f9a1c2b7d-03")
    assert apply(db, atoms, fn_event(elsewhere), task=task).applied


def test_the_same_event_again_is_unchanged_and_writes_nothing(db, world, atoms, task, events):
    t = opened()
    closed = close_with(t.atom, 0)
    _stored(db, world, atoms, task, fn_event(t), fn_event(closed))
    count, messages = len(events.events), world.sql("SELECT count(*) FROM chat_messages").fetchone()[0]
    assert apply(db, atoms, fn_event(closed), task=task).status == "unchanged"
    assert len(events.events) == count and world.sql("SELECT count(*) FROM chat_messages").fetchone()[0] == messages
    assert world.sql("SELECT count(*) FROM atom_ledger").fetchone()[0] == 1


def test_a_replay_of_the_whole_sequence_changes_nothing(db, world, atoms, task):
    t0 = opened()
    t1 = failed_try(t0)
    t2 = close_with(t1.atom, 0)
    steps = [fn_event(t0), fn_event(t1), fn_event(t2)]
    _stored(db, world, atoms, task, *steps)
    snapshot = [world.sql(f"SELECT * FROM {t}").fetchall() for t in ("atoms", "atom_ledger", "chat_messages")]
    # the first two are earlier moves of a final atom: refused; the last is the same body: unchanged. Nothing is written.
    assert [apply(db, atoms, s, task=task).status for s in steps] == ["rejected", "rejected", "unchanged"]
    assert [world.sql(f"SELECT * FROM {t}").fetchall() for t in ("atoms", "atom_ledger", "chat_messages")] == snapshot


def test_the_card_is_posted_once_even_if_the_row_is_rewritten(db, world, atoms, chats, task):
    t0 = opened()
    apply(db, atoms, fn_event(t0), task=task)
    changed = fn_event(t0, body={"notes": "a note"})                                 # same attempt, new body: a refresh, same card key
    assert apply(db, atoms, changed, task=task).applied
    assert len(chats.messages(world.session_of[NODE])) == 1


# ---- bad events are rejected, never raised --------------------------------------------------------------------------------------------

def test_a_body_the_gate_refuses_is_rejected_with_the_reason(db, world, atoms, task):
    t = opened()
    event = fn_event(t)
    broken = event.model_copy(update={"atom": event.atom.model_copy(update={"body": {**event.atom.body, "goal": ""}})})
    result = apply(db, atoms, broken, task=task)
    assert result.status == "rejected" and "refused" in result.reason and row(world, t.atom.id) is None


def test_the_event_must_agree_with_its_body(db, world, atoms, task):
    t = opened()
    wrong_attempt = apply(db, atoms, fn_event(t, attempt=2), task=task)
    assert wrong_attempt.status == "rejected" and "attempt 2" in wrong_attempt.reason
    wrong_state = apply(db, atoms, fn_event(t, status="closed"), task=task)
    assert wrong_state.status == "rejected" and "body says open" in wrong_state.reason
    wrong_id = apply(db, atoms, fn_event(t, id="a-3f9a1c2b7d-09"), task=task)
    assert wrong_id.status == "rejected" and "a-3f9a1c2b7d-09" in wrong_id.reason
    wrong_outcome = apply(db, atoms, fn_event(t, outcome="closed"), task=task)
    assert wrong_outcome.status == "rejected" and "does not fit" in wrong_outcome.reason
    assert world.sql("SELECT count(*) FROM atoms").fetchone()[0] == 0


def test_an_atom_of_another_node_or_for_a_node_that_does_not_exist_is_rejected(db, world, atoms, task):
    t = opened()
    event = fn_event(t)
    with db.tx() as tx:
        assert "not to web.priority" in atoms.apply_transition(tx, "web.priority", event.model_copy(update={"node": "web.priority"}), run_id=RUN).reason
        assert "does not exist" in atoms.apply_transition(tx, "web.nothing", event.model_copy(update={"node": "web.nothing"}), run_id=RUN).reason
        assert "not web.priority" in atoms.apply_transition(tx, "web.priority", event, run_id=RUN).reason
    assert world.sql("SELECT count(*) FROM atoms").fetchone()[0] == 0


def test_a_ledger_row_that_does_not_match_the_atom_or_belongs_to_an_open_one_is_rejected(db, world, atoms, task):
    t = opened()
    apply(db, atoms, fn_event(t), task=task)
    closed = close_with(t.atom, 0)
    other = ledger_row(close_with(opened(id="a-3f9a1c2b7d-07").atom, 0).atom).model_dump(mode="json")
    assert "does not match" in apply(db, atoms, fn_event(closed, ledger=other), task=task).reason
    assert "ledger row was refused" in apply(db, atoms, fn_event(closed, ledger={"kind": "atom_ledger_row"}), task=task).reason
    assert "still open" in apply(db, atoms, fn_event(failed_try(t), ledger=ledger_row(closed.atom).model_dump(mode="json")), task=task).reason
    assert row(world, t.atom.id)["display"] == "open" and world.sql("SELECT count(*) FROM atom_ledger").fetchone()[0] == 0


def test_applying_an_atom_card_needs_a_chat_store(db, world, task):
    bare = AtomStore(db, graph=world.store)
    with pytest.raises(RuntimeError, match="ChatStore"):
        apply(db, bare, fn_event(opened()), task=task)


# ---- the Atom log is append only -------------------------------------------------------------------------------------------------------

def _row(atom_id="a-3f9a1c2b7d-01", status="closed"):
    atom = close_with(opened(id=atom_id).atom, 0).atom
    return GATE.check("atom_ledger_row", ledger_row(atom))


def test_one_ledger_row_per_atom_a_second_is_ignored(db, atoms):
    with db.tx() as tx:
        assert atoms.append_ledger(tx, _row()) is True
        assert atoms.append_ledger(tx, _row()) is False
        assert atoms.append_ledger(tx, _row("a-3f9a1c2b7d-02")) is True
    assert [e.atom_id for e in atoms.log()] == ["a-3f9a1c2b7d-01", "a-3f9a1c2b7d-02"]


def test_the_log_cannot_be_updated_or_deleted(db, world, atoms):
    with db.tx() as tx:
        atoms.append_ledger(tx, _row())
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        world.sql("UPDATE atom_ledger SET status = 'abandoned'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        world.sql("DELETE FROM atom_ledger")


def test_the_writers_take_checked_records_only(db, atoms):
    with db.tx() as tx:
        with pytest.raises(TypeError):
            atoms.append_ledger(tx, ledger_row(close_with(opened().atom, 0).atom))
        with pytest.raises(TypeError):
            atoms.upsert(tx, opened().atom)
        with pytest.raises(TypeError):
            atoms.upsert(tx, _row())                                                 # a ledger row is not an atom
        view = GATE.check("atom_view", AtomView(id="W-1.a1", workflow="W-1", name="x", status="open"))
        with pytest.raises(ValueError):
            atoms.upsert(tx, view)                                                   # a view needs its key, node and opening time


# ---- J2 builder atoms (atom/1) --------------------------------------------------------------------------------------------------------------

@pytest.fixture
def step(world, task):
    return world.step(task, "W-1", "web")


def test_a_builder_atom_is_keyed_by_run_and_keeps_j2s_id_in_its_body(db, world, atoms, step, task, chats):
    result = apply(db, atoms, view_event(step, "open"), task=task)
    assert (result.status, result.atom_id, result.display, result.outcome) == ("applied", f"{RUN}:W-1.a1", "open", "opened")
    r = row(world, f"{RUN}:W-1.a1")
    assert (r["schema"], r["state"], r["display"], r["node_id"], r["task_id"], r["department_id"], r["ts_open"]) == (
        "atom/1", "open", "open", step, task, "web", 5000)
    assert json.loads(r["body"])["id"] == "W-1.a1"
    assert chats.messages(world.session_of[step]) == []                               # no card for a builder atom
    assert world.store.get(step).kind == "step"


def test_two_runs_with_the_same_builder_atom_id_give_two_rows(db, world, atoms, step, task):
    apply(db, atoms, view_event(step, "open"), run="j2-20261104-100001-aaaa", task=task)
    apply(db, atoms, view_event(step, "open"), run="j2-20261104-100002-bbbb", task=task)
    assert [r[0] for r in world.sql("SELECT id FROM atoms ORDER BY id").fetchall()] == [
        "j2-20261104-100001-aaaa:W-1.a1", "j2-20261104-100002-bbbb:W-1.a1"]
    assert atoms.get("j2-20261104-100002-bbbb:W-1.a1").body["id"] == "W-1.a1"


def test_a_node_may_hold_several_open_builder_atoms(db, world, atoms, step, task):
    for n in (1, 2, 3):
        assert apply(db, atoms, view_event(step, "open", vid=f"W-1.a{n}"), task=task).applied
    assert world.sql("SELECT count(*) FROM atoms WHERE display = 'open'").fetchone()[0] == 3


def test_a_builder_atom_that_closes_appends_one_ledger_row_and_a_replay_appends_none(db, world, atoms, step, task, events):
    apply(db, atoms, view_event(step, "open"), task=task)
    closed = view_event(step, "closed", attempt=1, ts_closed=5100)
    result = apply(db, atoms, closed, task=task)
    assert (result.display, result.outcome, result.ledgered) == ("closed", "closed", True)
    [entry] = atoms.log()
    assert (entry.atom_id, entry.node_id, entry.status, entry.ts) == (f"{RUN}:W-1.a1", step, "closed", "1970-01-01T01:25:00Z")   # the event's ts_closed, 5100 s
    assert entry.body["atom_id"] == "W-1.a1" and entry.body["verify"] == {"template": "file-exists", "exit_code": 0}
    count = len(events.events)
    assert apply(db, atoms, closed, task=task).status == "unchanged"
    assert world.sql("SELECT count(*) FROM atom_ledger").fetchone()[0] == 1 and len(events.events) == count


def test_a_builder_atom_that_fails_verification_is_ledgered_as_verify_failed_and_a_later_close_adds_no_second_row(db, world, atoms, step, task):
    apply(db, atoms, view_event(step, "open"), task=task)
    result = apply(db, atoms, view_event(step, "verify_failed", attempt=1), task=task)
    assert (result.display, result.ledgered) == ("verify_failed", True)
    assert atoms.get(f"{RUN}:W-1.a1").state == "verify_failed"
    assert atoms.log()[0].body["reason"] == "verify failed: site/index.html is missing"
    again = apply(db, atoms, view_event(step, "closed", attempt=2, ts_closed=5200), task=task)
    assert again.applied and not again.ledgered and [e.status for e in atoms.log()] == ["verify_failed"]


def test_builder_atoms_move_forward_only(db, world, atoms, step, task):
    apply(db, atoms, view_event(step, "open"), task=task)
    apply(db, atoms, view_event(step, "verify_failed", attempt=1), task=task)
    assert "cannot go back" in apply(db, atoms, view_event(step, "open", attempt=1), task=task).reason
    apply(db, atoms, view_event(step, "abandoned", attempt=1, ts_closed=5300), task=task)
    assert "final" in apply(db, atoms, view_event(step, "closed", attempt=1, ts_closed=5400), task=task).reason
    assert row(world, f"{RUN}:W-1.a1")["display"] == "abandoned"


def test_a_view_that_disagrees_with_its_event_or_will_not_pass_the_gate_is_rejected(db, atoms, step, task):
    event = view_event(step, "open")
    assert "its view says" in apply(db, atoms, event.model_copy(update={"atom": event.atom.model_copy(update={"status": "closed"})}), task=task).reason
    broken = event.model_copy(update={"atom": event.atom.model_copy(update={"body": {**event.atom.body, "attempt": 9}})})
    assert "atom view was refused" in apply(db, atoms, broken, task=task).reason


# ---- reads -----------------------------------------------------------------------------------------------------------------------------

def test_find_filters_and_pages_newest_first_and_get_takes_the_stored_key(db, world, atoms, step, task):
    t = opened()
    apply(db, atoms, fn_event(t), task=task)
    apply(db, atoms, fn_event(close_with(t.atom, 0)), task=task)
    apply(db, atoms, view_event(step, "open"), task=task)
    apply(db, atoms, view_event(step, "open", vid="W-1.a2"), task=task)
    everything = atoms.find(limit=10)
    assert len(everything) == 3
    assert [a.id for a in atoms.find(node_id=NODE)] == [t.atom.id]
    assert {a.id for a in atoms.find(task_id=task)} == {a.id for a in everything}
    assert [a.id for a in atoms.find(status="closed")] == [t.atom.id]
    assert {a.state for a in atoms.find(status="open")} == {"open"} and len(atoms.find(status="open")) == 2
    assert len(atoms.find(limit=2)) == 2 and len(atoms.find(limit=2, offset=2)) == 1 and atoms.find(offset=5) == []
    assert atoms.get(f"{RUN}:W-1.a2").schema_ == "atom/1"
    with pytest.raises(NotFound):
        atoms.get("nope")
    with pytest.raises(ValueError):
        atoms.find(status="verified")


def test_atoms_come_newest_opened_first(db, world, atoms, task):
    for n, ts in ((1, 300), (2, 100), (3, 200)):
        world.sql("INSERT INTO atoms(id, schema, node_id, state, display, attempt, goal, body, sha256, ts_open) VALUES (?,?,?,?,?,0,'g','{}','x',?)",
                  f"a-0000000000-{n:02d}", "work-atom/0.3", NODE, "closed", "closed", ts)
    assert [a.id for a in atoms.find()] == ["a-0000000000-01", "a-0000000000-03", "a-0000000000-02"]


def test_atom_usage_sums_by_atom_id_with_stub_rows_out_and_null_parts_left_out(world, atoms, usage, db):
    world.atom(NODE, "closed", n=1)
    key = "a-0000000001-01"
    for ref, kw in (("c1", dict(usd=0.5, tin=10, tout=5)), ("c2", dict(usd=None, tin=7, tout=None)), ("c3", dict(provider="stub", usd=9.0, tin=99, tout=99))):
        world.usage(ref, atom=key, **kw)
    out = atoms.get(key).usage
    assert (out.calls, out.usd, out.tokens_in, out.tokens_out) == (2, 0.5, 17, 5)
    world.atom(NODE, "closed", n=2)
    world.usage("c4", atom="a-0000000002-01", provider="codex", usd=None, tin=3, tout=1)
    codex = atoms.get("a-0000000002-01").usage
    assert (codex.calls, codex.usd, codex.tokens_in) == (1, None, 3)
    assert atoms.get(world.atom(NODE, "closed", n=3)).usage.calls == 0


def test_the_log_pages_in_seq_order_by_node(db, world, atoms):
    with db.tx() as tx:
        for n in (1, 2, 3):
            atoms.append_ledger(tx, _row(f"a-3f9a1c2b7d-0{n}"))
    assert [e.seq for e in atoms.log()] == [1, 2, 3]
    assert [e.seq for e in atoms.log(after=1, limit=1)] == [2]
    assert atoms.log(after=3) == [] and atoms.log(node_id="web.priority") == []
    assert len(atoms.log(node_id=NODE)) == 3


def test_the_chip_counts_equal_the_group_by_display_over_atoms(db, world, atoms, task):
    t = opened()
    apply(db, atoms, fn_event(t), task=task)
    ok = close_with(t.atom, 0)
    apply(db, atoms, fn_event(ok), task=task)
    second = opened(id="a-3f9a1c2b7d-02")
    apply(db, atoms, fn_event(second), task=task)
    third_last = second
    for _ in range(3):
        third_last = failed_try(third_last)
        apply(db, atoms, fn_event(third_last), task=task)
    apply(db, atoms, fn_event(abandon(third_last.atom, "verify failed: x", code="verify_failed")), task=task)
    apply(db, atoms, fn_event(open_transition(node_id=NODE, id="a-3f9a1c2b7d-03", goal="done")), task=task)
    stats = world.store.node(NODE).node.meta["stats"]
    assert (stats["atoms_open"], stats["atoms_closed"], stats["atoms_failed"], stats["atoms_total"]) == (0, 1, 1, 3)
    counts = dict(world.sql("SELECT display, count(*) FROM atoms WHERE node_id = ? GROUP BY display", NODE).fetchall())
    assert counts == {"closed": 1, "verify_failed": 1, "refused": 1}


# ---- usage -----------------------------------------------------------------------------------------------------------------------------

def uin(**over) -> UsageIn:
    base = dict(provider="claude", model="sonnet", purpose="agent_turn", how="native", usd=0.25, tokens_in=100, tokens_out=40, seconds=1.5,
                atom_id="a-0000000001-01", call_ref="r:abc")
    return UsageIn(**{**base, **over})


def rows_of(world):
    return [dict(r) for r in world.sql("SELECT * FROM usage_ledger ORDER BY id").fetchall()]


def test_record_stores_every_field_returns_the_id_and_emits_usage_recorded(usage, world, task, events):
    events.batches.clear()
    row_id = usage.record(uin(task_id=task, dept_id="web", node_id=NODE, session_id=world.session_of[NODE], fn="adaptation", step="W-1",
                              call_ref=f"{RUN}:3", detail={"retries": 1}, how="repaired"))
    [r] = rows_of(world)
    assert r["id"] == row_id == 1
    assert (r["provider"], r["model"], r["purpose"], r["task_id"], r["dept_id"], r["node_id"], r["fn"], r["step"], r["atom_id"]) == (
        "claude", "sonnet", "agent_turn", task, "web", NODE, "adaptation", "W-1", "a-0000000001-01")
    assert (r["usd"], r["tokens_in"], r["tokens_out"], r["seconds"], r["ok"], r["how"], r["call_ref"]) == (0.25, 100, 40, 1.5, 1, "repaired", f"{RUN}:3")
    assert r["at"] > 0 and json.loads(r["detail_json"]) == {"retries": 1}
    [event] = events.events
    assert event.type == "usage.recorded" and event.data["row"]["id"] == 1 and event.data["row"]["detail"] == {"retries": 1}
    assert event.data["task_total"] == {"calls": 1, "usd": 0.25, "tokens_in": 100, "tokens_out": 40}


def test_a_replayed_call_ref_of_a_task_is_stored_once_and_returns_the_same_id(usage, world, task, events):
    events.batches.clear()
    first = usage.record(uin(task_id=task, call_ref=f"{RUN}:1"))
    again = usage.record(uin(task_id=task, call_ref=f"{RUN}:1", usd=9.0))
    assert first == again and len(rows_of(world)) == 1 and rows_of(world)[0]["usd"] == 0.25
    assert events.types() == ["usage.recorded"]
    other_task = world.task(2, "sales", "running")
    assert usage.record(uin(task_id=other_task, call_ref=f"{RUN}:1")) != first                  # the key is (task, call_ref)
    assert usage.record(uin(task_id=task, call_ref=f"{RUN}:2")) != first
    assert len(rows_of(world)) == 3


def test_rows_without_a_call_ref_are_all_kept_and_rows_without_a_task_dedupe_on_the_call_ref(usage, world):
    usage.record(uin(call_ref=None))
    usage.record(uin(call_ref=None))
    assert len(rows_of(world)) == 2
    a, b = usage.record(uin(call_ref="r:same")), usage.record(uin(call_ref="r:same"))
    assert a == b and len(rows_of(world)) == 3


def test_a_link_to_nothing_is_stored_as_null_and_remembered_in_the_detail(usage, world, task):
    usage.record(uin(task_id="tsk_ffffffffffff", node_id="web.nothing", session_id="cs_000000000fff", dept_id="nodept", detail={"k": 1}))
    [r] = rows_of(world)
    assert (r["task_id"], r["node_id"], r["session_id"], r["dept_id"]) == (None, None, None, None)
    assert json.loads(r["detail_json"]) == {"k": 1, "unlinked": {
        "session_id": "cs_000000000fff", "node_id": "web.nothing", "task_id": "tsk_ffffffffffff", "dept_id": "nodept"}}
    usage.record(uin(call_ref="r:2", task_id=task, node_id=NODE))
    assert rows_of(world)[1]["task_id"] == task and rows_of(world)[1]["detail_json"] is None


def test_a_row_the_gate_refuses_raises_and_stores_nothing(usage, world):
    with pytest.raises(GateError):
        usage.record(uin(fn="x" * 30))
    with pytest.raises(TypeError):
        usage.record({"provider": "claude"})
    assert rows_of(world) == []


def test_the_provider_chip_follows_successful_requests_only_and_keeps_the_provider_session(usage, world, chats):
    sid = world.session_of["web"]
    chats.set_provider(sid, "claude", "sonnet", "prov-1")
    usage.record(uin(session_id=sid, provider="codex", model="gpt-5", call_ref="r:1"))
    out = chats.session(sid)
    assert (out.connector, out.model, out.provider_session_id) == ("codex", "gpt-5", "prov-1")
    usage.record(uin(session_id=sid, provider="claude", model="opus", ok=False, call_ref="r:2"))
    assert chats.session(sid).connector == "codex"
    usage.record(uin(provider="claude", model="opus", call_ref="r:3"))                 # no session: nothing to note
    assert chats.session(sid).model == "gpt-5"


def test_usd_stays_null_for_codex_and_a_total_is_null_when_every_part_is(usage, world):
    usage.record(uin(provider="codex", usd=None, tokens_in=10, tokens_out=None, call_ref="r:1"))
    usage.record(uin(provider="codex", usd=None, tokens_in=5, tokens_out=None, call_ref="r:2"))
    rows, totals = usage.rows()
    assert [r.usd for r in rows] == [None, None] and (totals.calls, totals.usd, totals.tokens_in, totals.tokens_out) == (2, None, 15, None)


def test_record_inside_a_given_transaction_joins_it_and_a_rollback_takes_it_back(usage, db, world, events):
    events.batches.clear()
    with pytest.raises(RuntimeError):
        with db.tx() as tx:
            usage.record(uin(), tx=tx)
            raise RuntimeError("boom")
    assert rows_of(world) == [] and events.events == []
    with db.tx() as tx:
        usage.record(uin(), tx=tx)
        with pytest.raises(RuntimeError):
            usage.record(uin(call_ref="r:2"))                                         # own transaction inside a transaction: refused
    assert len(rows_of(world)) == 1


def test_stub_rows_are_stored_but_left_out_of_rows_totals_and_groups_unless_asked_for(usage, world, task):
    usage.record(uin(task_id=task, call_ref="a"))
    usage.record(uin(task_id=task, provider="stub", model="", usd=None, tokens_in=1, tokens_out=1, call_ref="b", how="stub"))
    assert len(rows_of(world)) == 2
    rows, totals = usage.rows(task_id=task)
    assert [r.provider for r in rows] == ["claude"] and totals.calls == 1
    rows, totals = usage.rows(task_id=task, include_stub=True)
    assert [r.provider for r in rows] == ["claude", "stub"] and (totals.calls, totals.tokens_in) == (2, 101)
    assert usage.task_total(task).calls == 1
    assert {g["key"] for g in usage.summary("provider")} == {"claude"} and {g["key"] for g in usage.summary("provider", include_stub=True)} == {"claude", "stub"}


def test_rows_filter_by_task_department_function_and_time_and_page_while_totals_cover_every_match(usage, world, clock, task):
    stamps = []
    for n in range(5):
        usage.record(uin(task_id=task if n < 4 else None, dept_id="web" if n < 3 else None, fn="adaptation" if n % 2 == 0 else "priority",
                         call_ref=f"c{n}", usd=1.0, tokens_in=10, tokens_out=1))
        stamps.append(rows_of(world)[-1]["at"])
    ids = lambda **kw: [r.id for r in usage.rows(**kw)[0]]                           # noqa: E731
    assert ids(task_id=task) == [1, 2, 3, 4] and ids(dept_id="web") == [1, 2, 3] and ids(fn="adaptation") == [1, 3, 5]
    assert ids(since=stamps[3]) == [4, 5] and ids(since=stamps[3] + 1) == [5]
    page, totals = usage.rows(limit=2, after=1)
    assert [r.id for r in page] == [2, 3] and totals.calls == 5 and totals.usd == 5.0 and totals.tokens_in == 50
    assert usage.rows(task_id=task, dept_id="web", fn="adaptation")[1].calls == 2


def test_summary_groups_by_department_function_provider_day_and_atom_and_the_sums_agree_with_the_total(usage, world, task):
    usage.record(uin(dept_id="web", fn="adaptation", atom_id="a-0000000001-01", call_ref="1", usd=0.5, tokens_in=10, tokens_out=2))
    usage.record(uin(dept_id="web", fn="priority", atom_id="a-0000000001-01", call_ref="2", usd=0.25, tokens_in=20, tokens_out=3))
    usage.record(uin(dept_id=None, fn="chat_agent", atom_id="a-0000000009-01", provider="codex", usd=None, call_ref="3", tokens_in=5, tokens_out=1))
    by = lambda key, **kw: {g["key"]: g for g in usage.summary(key, **kw)}           # noqa: E731
    assert set(by("dept")) == {"web", NO_KEY} and by("dept")["web"]["calls"] == 2 and by("dept")["web"]["usd"] == 0.75
    assert set(by("fn")) == {"adaptation", "priority", "chat_agent"}
    assert by("provider")["codex"] == {"key": "codex", "calls": 1, "usd": None, "tokens_in": 5, "tokens_out": 1}
    assert list(by("day")) == ["2026-11-04"] and by("day")["2026-11-04"]["calls"] == 3
    atoms = by("atom")
    assert atoms["a-0000000001-01"]["tokens_in"] == 30 and atoms["a-0000000009-01"]["calls"] == 1
    total = usage.rows()[1]
    assert sum(g["calls"] for g in atoms.values()) == total.calls and sum(g["tokens_in"] for g in atoms.values()) == total.tokens_in
    assert round(sum(g["usd"] or 0 for g in atoms.values()), 6) == total.usd
    with pytest.raises(ValueError):
        usage.summary("colour")


def test_parse_since_takes_epoch_seconds_or_an_iso_time():
    assert parse_since("1793786400") == 1793786400 == parse_since("2026-11-04T10:00:00Z") == parse_since(1793786400)
    with pytest.raises(ValueError):
        parse_since("yesterday")


def test_parse_since_refuses_a_number_that_is_no_time():
    """QA: since=99999999999999999999 reached SQLite as a Python int too large for it and the route answered 500."""
    assert parse_since("253402300799") == 253402300799 == parse_since("9999-12-31T23:59:59Z")
    for text in ("253402300800", "99999999999999999999", "9" * 40, 2 ** 63, -1):
        with pytest.raises(ValueError):
            parse_since(text)


def test_every_provider_row_keeps_its_atom_and_the_node_of_a_chat_agent_call_is_root(usage, world):
    usage.record(uin(node_id="root", session_id="cs_org", fn="chat_agent", purpose="chat_plan", atom_id="a-0000000009-01", call_ref="r:q"))
    assert world.sql("SELECT count(*) FROM usage_ledger WHERE provider != 'stub' AND atom_id IS NULL").fetchone()[0] == 0
    assert world.sql("SELECT node_id, session_id FROM usage_ledger").fetchone()[:] == ("root", "cs_org")
