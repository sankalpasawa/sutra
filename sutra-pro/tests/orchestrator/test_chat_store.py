"""ChatStore and ChatTranscripts (ORCH-3): sessions, ordered messages, `src_ref` idempotency, questions, the division lens, the
provider chip, merge links, the router's transcript source."""
import json

import pytest
from factories_org import apply, make_chart, merge_op
from orchestrator.test_graph_store import World, tid

from sutra_app.connectors.models import Message
from sutra_app.library.gate import GATE, Checked
from sutra_app.library.org_chart import LinkPlan, carry_links
from sutra_app.orchestrator.chats import RESUME_MESSAGES, ChatStore, ChatTranscripts, parse_options
from sutra_app.orchestrator.errors import NotFound
from sutra_app.orchestrator.records import ChatMessage


@pytest.fixture
def world(db, clock):
    return World(db, clock)


@pytest.fixture
def chats(db):
    return ChatStore(db)


def msg(session: str, text: str = "hello", *, who: str = "identity", kind: str = "text", at: int = 100, **over) -> Checked:
    role = over.pop("role", "user" if who == "user" else "agent")
    return GATE.check("chat_message", ChatMessage(kind=kind, session_id=session, role=role, who=who, text=text, at=at, **over))


def post(db, chats, session: str, *args, **kw):
    with db.tx() as tx:
        return chats.post(tx, session, msg(session, *args, **kw))


def card(session: str, body: dict, **over) -> Checked:
    return GATE.check("chat_message", ChatMessage(kind="card", session_id=session, role="agent", who="sutra", card=body, at=100, **over))


ATOM_CARD = {"type": "atom", "atom_id": "a-3f9a1c2b7d-01", "outcome": "opened", "label": "WORK ATOM OPEN", "goal": "g", "rows": []}


# ---- sessions ----------------------------------------------------------------------------------------------------------------------

def test_every_node_has_exactly_one_active_session_and_the_list_is_in_creation_order(world, chats):
    found = chats.sessions()
    assert len(found) == len(world.session_of) == len({s.node_id for s in found})
    assert [s.id for s in found] == [world.session_of[n] for n in world.session_of]
    assert chats.sessions(node_id="web")[0].id == world.session_of["web"]


def test_a_session_has_the_wire_fields_and_an_unknown_one_is_not_found(world, chats):
    out = chats.session(world.session_of["web"])
    assert (out.kind, out.node_id, out.writable, out.status, out.phase) == ("department", "web", True, "active", None)
    with pytest.raises(NotFound):
        chats.session("cs_000000000fff")


def test_the_org_chat_phase_is_ready_then_working_while_a_task_is_open(world, chats):
    assert chats.session("cs_org").phase == "ready" and chats.phase("cs_org") == "ready"
    world.task(1, "web", "running")
    assert chats.phase("cs_org") == "working"
    world.sql("UPDATE tasks SET status = 'done', ended_at = 5, started_at = 2 WHERE id = ?", tid(1))
    assert chats.phase("cs_org") == "ready"


def test_a_turn_phase_set_by_the_runner_wins_until_cleared_and_only_the_org_chat_has_one(world, chats):
    world.task(1, "web", "running")
    chats.set_turn_phase("planning")
    assert chats.phase("cs_org") == "planning" and chats.session("cs_org").phase == "planning"
    assert chats.phase(world.session_of["web"]) is None and chats.session(world.session_of["web"]).phase is None
    chats.set_turn_phase(None)
    assert chats.phase("cs_org") == "working"
    with pytest.raises(ValueError):
        chats.set_turn_phase("done")


def test_archived_sessions_are_listed_only_on_request(world, chats):
    world.sql("UPDATE chat_sessions SET status = 'archived', writable = 0, filed_under = 'sales' WHERE id = ?", world.session_of["menu"])
    assert world.session_of["menu"] not in [s.id for s in chats.sessions()]
    assert world.session_of["menu"] in [s.id for s in chats.sessions(include_archived=True)]
    assert [s.id for s in chats.sessions(node_id="sales", include_archived=True)].count(world.session_of["menu"]) == 1   # filed under sales


# ---- post and read -----------------------------------------------------------------------------------------------------------------

def test_messages_come_oldest_first_with_ids_that_rise_and_after_and_limit_page(db, world, chats):
    sid = world.session_of["web"]
    first = [post(db, chats, sid, f"line {i}", at=100 + i) for i in range(5)]
    ids = [m.id for m in first]
    assert ids == sorted(ids) and len(set(ids)) == 5
    assert [m.text for m in chats.messages(sid)] == [f"line {i}" for i in range(5)]
    assert [m.id for m in chats.messages(sid, after=ids[1])] == ids[2:]
    assert [m.id for m in chats.messages(sid, after=ids[1], limit=2)] == ids[2:4]


def test_post_stores_the_columns_returns_the_wire_message_and_moves_the_session_cursor(db, world, chats, events):
    sid = world.session_of["web"]
    out = post(db, chats, sid, "What next?", kind="question", pause="ask", at=1_793_786_400)
    assert (out.kind, out.role, out.who, out.pause, out.state, out.answered_by) == ("question", "agent", "identity", "ask", "ok", None)
    assert out.at == "2026-11-04T10:00:00Z" and out.card is None
    session = chats.session(sid)
    assert session.last_message_id == out.id
    sent = [e for e in events.events if e.type == "chat.message"]
    assert len(sent) == 1 and sent[0].data["session_id"] == sid and sent[0].data["message"]["id"] == out.id


def test_a_replayed_src_ref_is_stored_once_and_emits_nothing(db, world, chats, events):
    sid = world.session_of["web"]
    first = post(db, chats, sid, "from the run", src_ref="j2-x#chat:3")
    before = len(events.events)
    assert post(db, chats, sid, "from the run", src_ref="j2-x#chat:3") is None
    assert len(events.events) == before
    assert len(chats.messages(sid)) == 1 and chats.messages(sid)[0].id == first.id


def test_the_same_src_ref_in_another_session_is_a_different_message(db, world, chats):
    a, b = world.session_of["web"], world.session_of["sales"]
    assert post(db, chats, a, "x", src_ref="r#1") is not None and post(db, chats, b, "x", src_ref="r#1") is not None


def test_post_refuses_what_is_not_a_checked_message_for_that_session(db, world, chats):
    sid = world.session_of["web"]
    with db.tx() as tx:
        with pytest.raises(TypeError):
            chats.post(tx, sid, ChatMessage(kind="text", session_id=sid, role="agent", who="identity", text="x", at=1))
        with pytest.raises(ValueError):
            chats.post(tx, world.session_of["sales"], msg(sid))
        with pytest.raises(NotFound):
            chats.post(tx, "cs_000000000fff", msg("cs_000000000fff"))


def test_a_message_posted_in_a_rolled_back_transaction_leaves_nothing_and_no_event(db, world, chats, events):
    sid = world.session_of["web"]
    with pytest.raises(RuntimeError):
        with db.tx() as tx:
            chats.post(tx, sid, msg(sid))
            raise RuntimeError("boom")
    assert chats.messages(sid) == [] and "chat.message" not in events.types()


def test_a_card_message_keeps_its_card_as_a_typed_card(db, world, chats):
    sid = world.session_of["web.identity"]
    with db.tx() as tx:
        chats.post(tx, sid, card(sid, ATOM_CARD))
    shown = chats.messages(sid)[0]
    assert shown.kind == "card" and shown.text == "" and shown.card.type == "atom" and shown.card.atom_id == "a-3f9a1c2b7d-01"


def test_a_task_line_carries_its_task_id(db, world, chats):
    t = world.task(1, "web")
    out = post(db, chats, world.session_of["web"], "working", task_id=t)
    assert out.task_id == t


# ---- questions and needs-you -------------------------------------------------------------------------------------------------------

QUESTION = "Which style do you want?\n   Option 1: Warm\n   Option 2: Clean [adds 5 work credits]"


def test_parse_options_reads_the_option_lines_in_order_and_bounds_them():
    assert parse_options(QUESTION) == ["Warm", "Clean [adds 5 work credits]"]
    assert parse_options("no options here") == []
    assert len(parse_options("\n".join(f"   Option {i}: x" for i in range(1, 30)))) == 20
    assert len(parse_options("Option 1: " + "y" * 900)[0]) == 500


def test_an_open_question_is_listed_with_its_text_options_and_department(db, world, chats, events):
    sid = world.session_of["web"]
    q = post(db, chats, sid, QUESTION, kind="question", pause="ask")
    [need] = chats.needs_you()
    assert (need.message_id, need.session_id, need.kind, need.dept_id, need.dept_name) == (q.id, sid, "question", "web", "Web")
    assert need.text == QUESTION and need.options == ["Warm", "Clean [adds 5 work credits]"] and need.asked_at.endswith("Z")
    assert events.types()[-2:] == ["chat.message", "needs_you.changed"]
    assert events.events[-1].data == {"count": 1}


def test_an_answered_question_leaves_the_list_and_the_count_event_says_so(db, world, chats, events):
    sid = world.session_of["web"]
    q = post(db, chats, sid, QUESTION, kind="question")
    answer = post(db, chats, sid, "Option 1", who="user")
    with db.tx() as tx:
        chats.mark_answered(tx, q.id, answer.id)
    assert chats.needs_you() == [] and chats.messages(sid)[0].answered_by == answer.id
    assert events.events[-1].type == "needs_you.changed" and events.events[-1].data == {"count": 0}


def test_a_question_is_answered_once_and_a_second_answer_changes_nothing(db, world, chats, events):
    sid = world.session_of["web"]
    q = post(db, chats, sid, QUESTION, kind="question")
    a1, a2 = post(db, chats, sid, "Option 1", who="user"), post(db, chats, sid, "Option 2", who="user")
    with db.tx() as tx:
        chats.mark_answered(tx, q.id, a1.id)
    count = len(events.events)
    with db.tx() as tx:
        chats.mark_answered(tx, q.id, a2.id)
    assert chats.messages(sid)[0].answered_by == a1.id and len(events.events) == count


def test_mark_answered_refuses_a_message_that_is_not_a_question_and_an_answer_that_does_not_exist(db, world, chats):
    sid = world.session_of["web"]
    q = post(db, chats, sid, QUESTION, kind="question")
    note = post(db, chats, sid, "plain")
    with db.tx() as tx:
        with pytest.raises(ValueError):
            chats.mark_answered(tx, note.id, q.id)
        with pytest.raises(ValueError):
            chats.mark_answered(tx, 9999, q.id)
        with pytest.raises(ValueError):
            chats.mark_answered(tx, q.id, 9999)


def test_only_department_questions_count_and_they_are_listed_oldest_first(db, world, chats):
    post(db, chats, world.session_of["web.identity"], "function question", kind="question")
    a = post(db, chats, world.session_of["sales"], QUESTION, kind="question")
    b = post(db, chats, world.session_of["web"], "Second?", kind="question")
    assert [n.message_id for n in chats.needs_you()] == [a.id, b.id] and chats.needs_you_count() == 2
    assert chats.needs_you()[0].dept_name == "Sales"


def _approval(change_id: str) -> dict:
    return {"type": "approval", "change_id": change_id, "question": "Merge Leads into Quotes?",
            "options": [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}]}


def _change_row(world, change_id: str, status: str) -> None:
    world.sql("INSERT INTO chart_changes(id, task_id, kind, actor, base_revision, status, summary, body, ts) VALUES (?,?,?,?,?,?,?,?,?)",
              change_id, "req-1", "rearrange", "chat_agent", 1, status, "s", "{}", 1)


def test_a_pending_approval_card_is_needs_you_until_the_change_is_decided(db, world, chats, events):
    _change_row(world, "chg-0002", "pending_approval")
    _change_row(world, "chg-0003", "applied")
    with db.tx() as tx:
        chats.post(tx, "cs_org", card("cs_org", _approval("chg-0002")))
        chats.post(tx, "cs_org", card("cs_org", _approval("chg-0003")))
    [need] = chats.needs_you()
    assert (need.kind, need.session_id, need.dept_id, need.dept_name, need.text) == ("approval", "cs_org", None, "", "Merge Leads into Quotes?")
    assert need.options == ["Yes", "No"]
    assert [e.data for e in events.events if e.type == "needs_you.changed"] == [{"count": 1}, {"count": 1}]
    world.sql("UPDATE chart_changes SET status = 'applied' WHERE id = 'chg-0002'")
    assert chats.needs_you() == []


# ---- the division lens -------------------------------------------------------------------------------------------------------------

def _lines(db, chats, world):
    web, menu = world.session_of["web"], world.session_of["menu"]
    scoped = world.task(1, "web", "done", scope="menu")
    plain = world.task(2, "web", "done")
    a = post(db, chats, web, "scoped line", task_id=scoped)
    b = post(db, chats, web, "department line", task_id=plain)
    c = post(db, chats, menu, "a note of the division", who="sutra", kind="note")
    d = post(db, chats, web, "scoped again", task_id=scoped)
    e = post(db, chats, web, "no task at all")
    return web, menu, scoped, [a, b, c, d, e]


def test_a_division_shows_its_own_notes_and_the_department_lines_of_its_scoped_tasks_only(db, world, chats):
    web, menu, scoped, (a, b, c, d, e) = _lines(db, chats, world)
    shown = chats.messages(menu)
    assert [m.id for m in shown] == [a.id, c.id, d.id]
    assert [m.session_id for m in shown] == [web, menu, web]                   # a line keeps the department session it lives in
    assert [m.id for m in chats.messages(menu, after=a.id, limit=1)] == [c.id]
    assert [m.text for m in chats.messages(web)] == ["scoped line", "department line", "scoped again", "no task at all"]


def test_the_division_lens_follows_the_scope_not_the_parent_so_a_move_keeps_the_lines(db, world, chats):
    web, menu, scoped, (a, b, c, d, e) = _lines(db, chats, world)
    world.sql("UPDATE org_edges SET parent_id = 'sales', position = 9 WHERE child_id = 'menu'")
    world.sql("UPDATE graph_nodes SET parent_id = 'sales', department_id = 'sales' WHERE id = 'menu'")
    later = world.task(3, "sales", "running", scope="menu")
    f = post(db, chats, world.session_of["sales"], "after the move", task_id=later)
    assert [m.id for m in chats.messages(menu)] == [a.id, c.id, d.id, f.id]


def test_an_archived_division_session_still_shows_its_scoped_task_lines(db, world, chats):
    web, menu, scoped, (a, b, c, d, e) = _lines(db, chats, world)
    world.sql("UPDATE chat_sessions SET status = 'archived', writable = 0, filed_under = 'web' WHERE id = ?", menu)
    assert [m.id for m in chats.messages(menu)] == [a.id, c.id, d.id]


def test_messages_of_an_unknown_session_are_not_found(chats):
    with pytest.raises(NotFound):
        chats.messages("cs_000000000fff")


# ---- the provider chip -------------------------------------------------------------------------------------------------------------

def test_set_provider_is_the_routers_hook_called_positionally_with_its_own_transaction(world, chats, events):
    sid = world.session_of["web"]
    chats.set_provider(sid, "claude", "sonnet", "prov-1")
    out = chats.session(sid)
    assert (out.connector, out.model, out.provider_session_id) == ("claude", "sonnet", "prov-1")
    chats.set_provider(sid, "codex", "gpt", None)
    out = chats.session(sid)
    assert (out.connector, out.model, out.provider_session_id) == ("codex", "gpt", None)
    assert events.events == []


def test_set_provider_ignores_a_session_it_does_not_know_and_refuses_a_bad_provider(world, chats):
    chats.set_provider("cs_000000000fff", "claude", "m", None)
    with pytest.raises(ValueError):
        chats.set_provider(world.session_of["web"], "gemini", "m", None)


def test_note_provider_changes_connector_and_model_and_never_the_provider_session(db, world, chats):
    sid = world.session_of["web"]
    chats.set_provider(sid, "claude", "sonnet", "prov-1")
    with db.tx() as tx:
        chats.note_provider(tx, sid, "codex", "gpt-5")
    out = chats.session(sid)
    assert (out.connector, out.model, out.provider_session_id) == ("codex", "gpt-5", "prov-1")


def test_note_provider_keeps_the_model_when_the_new_one_is_empty_and_writes_nothing_when_nothing_changed(db, world, chats):
    sid = world.session_of["web"]
    chats.set_provider(sid, "claude", "sonnet", None)
    stamp = world.sql("SELECT updated_at FROM chat_sessions WHERE id = ?", sid).fetchone()[0]
    with db.tx() as tx:
        chats.note_provider(tx, sid, "claude", "sonnet")
        chats.note_provider(tx, "cs_000000000fff", "claude", "x")                 # unknown session: ignored
    assert world.sql("SELECT updated_at FROM chat_sessions WHERE id = ?", sid).fetchone()[0] == stamp
    with db.tx() as tx:
        chats.note_provider(tx, sid, "stub", "")
    out = chats.session(sid)
    assert (out.connector, out.model) == ("stub", "sonnet")
    with db.tx() as tx:
        with pytest.raises(ValueError):
            chats.note_provider(tx, sid, "gemini", "m")


# ---- the router's transcript source ------------------------------------------------------------------------------------------------

def test_the_transcript_maps_roles_keeps_text_and_questions_in_state_ok_and_returns_the_newest_in_order(db, world, chats):
    sid = world.session_of["web"]
    post(db, chats, sid, "owner asks", who="user")
    post(db, chats, sid, "identity answers")
    post(db, chats, sid, "a question", kind="question")
    post(db, chats, sid, "system line", role="system", who="system")
    post(db, chats, sid, "a note", kind="note", who="sutra")
    post(db, chats, sid, "broken", kind="error", who="sutra", state="error")
    post(db, chats, sid, "pending text", state="pending")
    with db.tx() as tx:
        chats.post(tx, sid, card(sid, ATOM_CARD))
    found = ChatTranscripts(chats).messages(sid)
    assert found == [Message(role="user", text="owner asks"), Message(role="assistant", text="identity answers"),
                     Message(role="assistant", text="a question"), Message(role="system", text="system line")]
    assert [m.text for m in ChatTranscripts(chats).messages(sid, limit=2)] == ["a question", "system line"]
    assert ChatTranscripts(chats).messages("cs_000000000fff") == []


# ---- resume_info -------------------------------------------------------------------------------------------------------------------

def test_resume_info_has_the_provider_and_the_last_twenty_messages_oldest_first(db, world, chats):
    sid = world.session_of["web"]
    chats.set_provider(sid, "claude", "sonnet", "prov-9")
    for i in range(RESUME_MESSAGES + 5):
        post(db, chats, sid, f"m{i}", at=100 + i)
    info = chats.resume_info(sid)
    assert (info.connector, info.provider_session_id) == ("claude", "prov-9")
    assert [m.text for m in info.messages] == [f"m{i}" for i in range(5, RESUME_MESSAGES + 5)]
    with pytest.raises(NotFound):
        chats.resume_info("cs_000000000fff")


# ---- merges: apply_links -----------------------------------------------------------------------------------------------------------

def _division_sessions(world, *nodes: str) -> dict[str, str]:
    """A session for each node id (the chart nodes the merge test uses are not part of World)."""
    out = {}
    for n, node in enumerate(nodes, 1):
        sid = f"cs_{0xa00 + n:012x}"
        world.sql("INSERT INTO chat_sessions(id, node_id, kind, title, writable, created_at, updated_at) VALUES (?,?,'division',?,1,0,0)", sid, node, node.title())
        out[node] = sid
    return out


def _status(world, sid):
    r = world.sql("SELECT node_id, status, writable, note, filed_under FROM chat_sessions WHERE id = ?", sid).fetchone()
    return dict(r)


def test_a_plan_with_keep_changes_nothing(db, world, chats):
    sessions = _division_sessions(world, "alpha")
    with db.tx() as tx:
        chats.apply_links(tx, LinkPlan(keep={"alpha": sessions["alpha"]}), {})
    assert _status(world, sessions["alpha"]) == {"node_id": "alpha", "status": "active", "writable": 1, "note": "", "filed_under": None}


def test_a_merge_of_three_divisions_places_three_sessions_one_active_two_archived_none_dropped(db, world, chats):
    chart = make_chart({"sales": {"alpha": {}, "beta": {}, "gamma": {}}})
    sessions = _division_sessions(world, "alpha", "beta", "gamma")
    plan = carry_links(sessions, apply(chart, merge_op("alpha", "beta", "gamma")))
    assert plan.archive == {sessions["beta"]: "alpha", sessions["gamma"]: "alpha"} and plan.keep == {"alpha": sessions["alpha"]}
    with db.tx() as tx:
        chats.apply_links(tx, plan, {"alpha": "Alpha"})
    assert _status(world, sessions["alpha"])["status"] == "active"
    for dead in ("beta", "gamma"):
        assert _status(world, sessions[dead]) == {"node_id": dead, "status": "archived", "writable": 0, "note": "Merged into Alpha", "filed_under": "alpha"}
    assert world.sql("SELECT count(*) FROM chat_sessions WHERE id IN (?,?,?)", *sessions.values()).fetchone()[0] == 3


def test_a_move_repoints_the_session_to_the_survivor_that_had_none(db, world, chats):
    sessions = _division_sessions(world, "beta")
    with db.tx() as tx:
        chats.apply_links(tx, LinkPlan(move={sessions["beta"]: "alpha"}), {})
    assert _status(world, sessions["beta"]) == {"node_id": "alpha", "status": "active", "writable": 1, "note": "", "filed_under": None}
    assert [s.id for s in chats.sessions(node_id="alpha")] == [sessions["beta"]]


def test_a_chained_merge_refiles_the_session_archived_earlier_under_the_new_survivor(db, world, chats):
    sessions = _division_sessions(world, "alpha", "beta", "gamma")
    with db.tx() as tx:
        chats.apply_links(tx, LinkPlan(archive={sessions["alpha"]: "beta"}), {"beta": "Beta"})
    assert _status(world, sessions["alpha"])["filed_under"] == "beta"
    with db.tx() as tx:
        chats.apply_links(tx, LinkPlan(archive={sessions["beta"]: "gamma"}), {"gamma": "Gamma"})
    assert _status(world, sessions["alpha"])["filed_under"] == "gamma" and _status(world, sessions["alpha"])["note"] == "Merged into Beta"
    assert _status(world, sessions["beta"])["filed_under"] == "gamma" and _status(world, sessions["gamma"])["status"] == "active"


def test_a_plan_that_names_a_session_that_does_not_exist_is_refused(db, world, chats):
    with db.tx() as tx:
        with pytest.raises(ValueError):
            chats.apply_links(tx, LinkPlan(archive={"cs_000000000fff": "alpha"}), {})
    json.dumps(chats.sessions()[0].model_dump(mode="json"))                       # the listing still works
