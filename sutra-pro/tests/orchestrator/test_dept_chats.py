"""Each department or division the org chat creates gets its own chat, end to end (GAP3 dept-chats, docs/notes/GAP3-dept-chats.md).

The turn runner runs for real over the scripted connector and the fake launcher (test_turn_runner's `RunnerEnv`): the owner asks the org chat for
two new teams in ONE turn. What these tests pin: the session rows (made with their nodes, in one transaction, titled by the team's name), who owns
every stored message, the owner's request as the first user line of each team's chat marked as passed on, and the org chat holding pointers only.
The provider sessions are proved in tests/e2e/test_dept_chats.py (the real connector router over the fake CLIs)."""
import json
import sqlite3

import pytest
from orchestrator.test_chat_agent import add_dept, add_div, assignments, change_reply, decide, draft
from orchestrator.test_turn_runner import renv  # noqa: F401  (renv is a fixture)

from sutra_app.orchestrator import chart as chart_module
from sutra_app.orchestrator.chats import _passed_on_of
from sutra_app.orchestrator.models import ChatMessageOut

ORG = "cs_org"
ASK = "I need a flyer printed and my lease reviewed"


def two_teams(renv, text=ASK):
    renv.connector.push(
        decide(change="add", reuse=()),
        change_reply(add_dept("$print", "Print", "Flyers and print jobs"), add_dept("$legal", "Legal", "Contract and lease reviews")),
        assignments(draft("a1", "print", title="Flyer", brief="Print the flyer."), draft("a2", "legal", title="Lease review", brief="Review the lease.")))
    return renv.say(text)


def session_of(renv, node_id):
    return renv.one("SELECT chat_session_id FROM graph_nodes WHERE id = ?", node_id)


# ---- (a) the session rows ------------------------------------------------------------------------------------------------------------

def test_two_new_teams_get_two_sessions_made_with_their_nodes_and_titled_by_name(renv):
    two_teams(renv)
    rows = renv.sql("SELECT id, node_id, kind, title, writable, status, connector, provider_session_id FROM chat_sessions"
                    " WHERE node_id IN ('print', 'legal') ORDER BY node_id").fetchall()
    assert [(r["node_id"], r["kind"], r["title"], r["writable"], r["status"], r["connector"], r["provider_session_id"]) for r in rows] == [
        ("legal", "department", "Legal", 1, "active", "", None), ("print", "department", "Print", 1, "active", "", None)]
    ids = [r["id"] for r in rows]
    assert len(set(ids)) == 2 and ORG not in ids
    assert {session_of(renv, "print"), session_of(renv, "legal")} == set(ids)                      # the node names its session (invariant I1)
    assert renv.sql("SELECT chat_session_id FROM graph_nodes GROUP BY chat_session_id HAVING count(*) > 1").fetchall() == []   # nobody shares one
    assert renv.sql("SELECT count(*) FROM chat_sessions WHERE node_id LIKE 'print.%' AND kind = 'function'").fetchone()[0] == 5   # and the five logs are theirs


def test_a_session_is_made_in_the_transaction_of_its_node_so_a_failure_leaves_neither_team(renv, monkeypatch):
    real = chart_module.ensure_node

    def broken(tx, spec, **kw):
        if spec.node.get("id") == "legal":                                                          # the SECOND team's node fails after the first one's was made
            raise sqlite3.OperationalError("disk I/O error")
        return real(tx, spec, **kw)

    monkeypatch.setattr(chart_module, "ensure_node", broken)
    before = {t: renv.one(f"SELECT count(*) FROM {t}") for t in ("graph_nodes", "chat_sessions", "org_nodes", "departments")}
    accepted = two_teams(renv)
    after = {t: renv.one(f"SELECT count(*) FROM {t}") for t in before}
    assert after == before                                                                           # not one node, session or department of either team
    assert renv.sql("SELECT count(*) FROM chat_sessions WHERE node_id IN ('print', 'legal') OR node_id LIKE 'print.%'").fetchone()[0] == 0
    assert renv.user_state(accepted.message_id) == "error"
    assert [m for m in renv.messages() if m.kind == "card" and m.card.type == "team_chat"] == []


# ---- who owns every message ------------------------------------------------------------------------------------------------------------

def test_every_message_belongs_to_exactly_one_chat_and_the_org_chat_holds_none_of_the_teams(renv):
    accepted = two_teams(renv)
    org, print_chat, legal_chat = ORG, session_of(renv, "print"), session_of(renv, "legal")
    owner = {r["id"]: r["session_id"] for r in renv.sql("SELECT id, session_id FROM chat_messages").fetchall()}
    for sid in (org, print_chat, legal_chat):                                                        # the API lens and the table agree, id for id
        assert {m.id for m in renv.messages(sid)} == {i for i, s in owner.items() if s == sid}
        assert all(m.session_id == sid for m in renv.messages(sid))
    assert len({i for i in owner}) == len(owner) and {org, print_chat, legal_chat} <= set(owner.values())
    # the org chat: the owner's line, Sutra's template line and cards; no line written by a team (identity, W-n) and none carrying a team's task
    org_lines = renv.messages(org)
    assert {m.who for m in org_lines} == {"sutra", "user"} and all(m.task_id is None for m in org_lines)
    assert [m.card.type for m in org_lines if m.kind == "card"] == ["chart_change", "team_chat", "team_chat", "task", "task"]
    # a team chat: its own copy of the owner's line and nothing of Sutra's template lines or of the other team
    for sid, task_title in ((print_chat, "Flyer"), (legal_chat, "Lease review")):
        lines = renv.messages(sid)
        assert [(m.role, m.who, m.text) for m in lines] == [("user", "user", ASK)]
        task = renv.sql("SELECT id, title, dept_id FROM tasks WHERE dept_id = ?", renv.one("SELECT node_id FROM chat_sessions WHERE id = ?", sid)).fetchone()
        assert task["title"] == task_title and lines[0].task_id == task["id"]
    assert renv.chats.message(accepted.message_id).session_id == org                                # the original stayed where the owner wrote it


def test_the_owners_request_is_each_teams_first_line_marked_as_passed_on_from_the_org_chat(renv):
    accepted = two_teams(renv)
    for node in ("print", "legal"):
        [line] = renv.messages(session_of(renv, node))
        assert (line.role, line.text, line.passed_on) == ("user", ASK, accepted.message_id)
        assert renv.one("SELECT src_ref FROM chat_messages WHERE id = ?", line.id) == f"req:{accepted.message_id}:{line.task_id}"
        assert line.model_dump(mode="json")["passed_on"] == accepted.message_id                      # and it is on the wire
    original = renv.chats.message(accepted.message_id)
    assert original.passed_on is None and "passed_on" not in original.model_dump(mode="json")        # the original is not a copy


def test_the_task_starts_in_the_teams_chat_not_in_the_org_chat(renv):
    accepted = two_teams(renv)
    tasks = {r["dept_id"]: r for r in renv.tasks_of(f"req-{accepted.message_id}")}
    assert set(tasks) == {"print", "legal"}
    for node, task in tasks.items():
        assert renv.one("SELECT session_id FROM chat_messages WHERE task_id = ? AND role = 'user'", task["id"]) == session_of(renv, node)
        assert task["user_text"] == ASK and task["status"] in ("starting", "queued", "running")
    assert renv.one("SELECT count(*) FROM chat_messages WHERE session_id = ? AND task_id IS NOT NULL", ORG) == 0


# ---- (c) the card line in the org chat -------------------------------------------------------------------------------------------------

def test_the_org_chat_says_started_with_a_pointer_to_each_teams_own_chat(renv):
    two_teams(renv)
    cards = renv.cards("team_chat")
    assert [(c.node_id, c.name, c.kind, c.about, c.question_message_id) for c in cards] == [
        ("print", "Print", "department", "started", None), ("legal", "Legal", "department", "started", None)]
    assert [c.session_id for c in cards] == [session_of(renv, "print"), session_of(renv, "legal")]
    assert all(c.session_id != ORG for c in cards)
    assert renv.cards("needs_you") == []


def test_a_reused_team_gets_no_started_line(renv):
    renv.connector.push(decide())
    renv.say("I need a landing page for my coffee shop.")
    assert renv.cards("team_chat") == []


def test_a_new_division_has_its_own_session_and_its_chat_shows_the_passed_on_line(renv):
    renv.connector.push(decide(change="add", reuse=()), change_reply(add_div("$blog", "Blog", "web", "Posts")), assignments(draft("a1", "web", scope="blog")))
    accepted = renv.say("Start a blog")
    blog, web = session_of(renv, "blog"), session_of(renv, "web")
    assert blog != web and renv.one("SELECT kind FROM chat_sessions WHERE id = ?", blog) == "division"
    assert renv.one("SELECT title FROM chat_sessions WHERE id = ?", blog) == "Blog"
    [pointer] = renv.cards("team_chat")
    assert (pointer.node_id, pointer.kind, pointer.session_id) == ("blog", "division", blog)
    [line] = [m for m in renv.messages(blog) if m.role == "user"]                                    # the division is a lens on the team's lines for its tasks
    assert line.session_id == web and line.passed_on == accepted.message_id and line.text == "Start a blog"


# ---- the pass-on mark is read from the store, nothing else -----------------------------------------------------------------------------

@pytest.mark.parametrize("session,src_ref,expected", [
    ("cs_0123456789ab", "req:7:tsk_0123456789ab", 7),
    ("cs_0123456789ab", "req:7:choice", None),                    # the org chat's own choice card is not a copy
    ("cs_0123456789ab", "req:0:tsk_0123456789ab", None),
    ("cs_0123456789ab", "req:7:tsk_0123456789a", None),
    ("cs_0123456789ab", "x-req:7:tsk_0123456789ab", None),
    ("cs_0123456789ab", "direct:7", None),
    ("cs_0123456789ab", None, None),
    (ORG, "req:7:tsk_0123456789ab", None),                        # in the org chat that shape is never a copy
])
def test_passed_on_is_read_from_the_copy_of_a_request_in_a_team_chat_only(session, src_ref, expected):
    assert _passed_on_of(session, src_ref) == expected


def test_the_wire_shape_of_a_message_without_a_pass_on_is_what_it_was():
    out = ChatMessageOut(id=1, session_id=ORG, role="user", who="user", kind="text", text="hi", at="2026-01-01T00:00:00Z")
    assert "passed_on" not in json.loads(out.model_dump_json()) and "turn" not in json.loads(out.model_dump_json())
    assert json.loads(out.model_copy(update={"passed_on": 3}).model_dump_json())["passed_on"] == 3
