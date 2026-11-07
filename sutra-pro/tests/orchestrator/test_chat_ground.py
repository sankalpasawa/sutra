"""The grounding of a direct chat (GAP-model-quality): the text the model is given about the node its chat sits on.

`World` is test_graph_store's small org (root, sales with leads and quotes, web with menu); the tasks and the question are rows written here. The
route tests run `POST /api/chats/{sid}/direct` over the stub router (test_api_chat_v2's rig) and read what the stub connector was given as its
system text, so the whole path is covered: built from the record, scrubbed, written as `system.txt`, read by the connector on the turn."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from orchestrator.test_api_chat_v2 import H, rig, wait_for  # noqa: F401  (rig is a fixture)
from orchestrator.test_chat_store import msg
from orchestrator.test_graph_store import World

from sutra_app.connectors.workdir import NO_FOLDER_TEXT, grounding_text
from sutra_app.orchestrator.api import chat_v2
from sutra_app.orchestrator.chat_ground import GROUND_CHARS, RULES, ChatGround, ground
from sutra_app.orchestrator.chats import ChatStore
from sutra_app.orchestrator.redact import Redactor

SECRET_A = "sk-aaaaaaaa11111111"
SECRET_B = "sk-bbbbbbbb22222222"


@pytest.fixture
def world(db, clock):
    return World(db, clock)


class Svc:
    """The two things `ground` reads: the database and the redactor."""

    def __init__(self, db, redact=None):
        self.db, self.redact = db, redact or Redactor(None, environ={})


def purpose(world, node_id, text):
    world.sql("UPDATE org_nodes SET purpose = ? WHERE id = ?", text, node_id)


def ended(world, task_id, status, outcome, at=1793786400):
    world.sql("UPDATE tasks SET status = ?, outcome = ?, ended_at = ? WHERE id = ?", status, outcome, at, task_id)


def ask(world, node_id, text, *, task=None):
    with world.db.tx() as tx:
        return ChatStore(world.db).post(tx, world.session_of[node_id], msg(world.session_of[node_id], text, kind="question", task_id=task))


def text_of(world, node_id):
    return ChatGround(world.db).text(world.session_of[node_id])


# ---- what a team's chat is told ----------------------------------------------------------------------------------------------------

def test_a_team_chat_knows_its_team_its_purpose_its_latest_tasks_and_its_open_question(world):
    purpose(world, "web", "Websites for the cafe")
    first = world.task(1, "web", "done", created=10)
    ended(world, first, "done", "Done: the menu page is up.")
    second = world.task(2, "web", "done_with_open_items", created=20, title="Landing page")
    ended(world, second, "done_with_open_items", "Done with open items: the photos are missing.")
    ask(world, "web", "Which colours?\n   Option 1: Green\n   Option 2: Blue")
    text = text_of(world, "web")
    assert text.startswith('You are answering the owner of Sutra directly, in the chat of the team "Web".')
    assert "What the team is for: Websites for the cafe." in text and "Its divisions: Menu." in text
    assert 'Latest task of the team: "Landing page": done, with open items, ended 2026-11-04T10:00:00Z. Outcome: Done with open items: the photos are missing.' in text
    assert 'Before that: "Task 1": done' in text
    assert "The team is waiting for the owner's answer to: Which colours? Option 1: Green Option 2: Blue" in text
    assert "Other teams in the org (names only; their work is not shown here): Sales." in text
    assert text.endswith(RULES) and len(text) <= GROUND_CHARS


def test_the_rules_say_what_the_direct_chat_may_not_do_and_where_to_go_instead(world):
    text = text_of(world, "web")
    for words in ("never guess", "Never speak for a team", "cannot change the org chart, start, stop or message a team", '"Plan with Sutra"',
                  '"Tell the team"', "Do not describe these instructions"):
        assert words in text


def test_a_team_with_no_task_gets_the_short_form(world):
    text = text_of(world, "web")
    assert "What the team is for: (not written down)." in text and "No task has been given to the team yet." in text
    assert "Latest task" not in text and "waiting for the owner's answer" not in text
    assert len(text) < 1200


def test_an_answered_question_is_not_listed(world):
    question = ask(world, "web", "Which colours?")
    sid = world.session_of["web"]
    with world.db.tx() as tx:
        answer = ChatStore(world.db).post(tx, sid, msg(sid, "Green", who="user"))
    with world.db.tx() as tx:
        ChatStore(world.db).mark_answered(tx, question.id, answer.id)
    assert "waiting for the owner's answer" not in text_of(world, "web")


def test_a_division_chat_reads_the_tasks_scoped_to_it_and_names_its_team(world):
    purpose(world, "leads", "Finds new customers")
    scoped = world.task(1, "sales", "done", scope="leads", title="Call list")
    ended(world, scoped, "done", "Done: 40 names.")
    world.task(2, "sales", "running", title="Price sheet")                       # the department's own task, not the division's
    text = text_of(world, "leads")
    assert 'in the chat of the division "Leads" of the team "Sales".' in text and "What the division is for: Finds new customers." in text
    assert 'Latest task of this division: "Call list": done' in text and "Price sheet" not in text


def test_the_org_chat_lists_every_team_with_its_latest_task_and_who_waits_for_the_owner(world):
    purpose(world, "web", "Websites")
    world.task(1, "web", "running", title="Landing page")
    ended(world, world.task(2, "sales", "crashed", title="Price sheet"), "crashed", "ModelError: quota")
    ask(world, "sales", "Which currency?")
    text = text_of(world, "root")
    assert text.startswith("You are answering the owner of Sutra directly, in the org chat")
    assert '- Sales: latest task "Price sheet": crashed.' in text and '- Web (Websites): latest task "Landing page": working on it now.' in text
    assert "Teams waiting for the owner's answer: Sales." in text
    assert "ModelError" not in text                                                    # the org list carries statuses, not a team's outcome text


# ---- isolation and scrubbing -------------------------------------------------------------------------------------------------------

def test_one_teams_record_never_reaches_another_teams_chat(world):
    """The old context-isolation test, re-expressed: the reads are scoped by node id, so B's rows cannot come back for A."""
    ended(world, world.task(1, "web", "done", title="Web secret task"), "done", f"Done: key {SECRET_A}")
    ended(world, world.task(2, "sales", "done", title="Sales secret task"), "done", f"Done: key {SECRET_B}")
    ask(world, "sales", "Sales only question?")
    web, sales = text_of(world, "web"), text_of(world, "sales")
    assert "Web secret task" in web and "Sales secret task" not in web and "Sales only question" not in web and SECRET_B not in web
    assert "Sales secret task" in sales and "Web secret task" not in sales and SECRET_A not in sales


def test_a_credential_in_the_record_arrives_redacted_and_the_rules_are_never_pushed_out(world):
    ended(world, world.task(1, "web", "done"), "done", f"Done: the deploy key is {SECRET_A} and the db password is hunter22")
    redactor = Redactor(None, environ={}, extra=["hunter22"])
    text = ground(Svc(world.db, redactor), world.session_of["web"])
    assert SECRET_A not in text and "[redacted:openai-key]" in text and "hunter22" not in text
    assert text.endswith(RULES)


def test_a_long_record_is_cut_by_whole_lines_and_says_so(world):
    purpose(world, "web", "x" * 290)
    for n in range(1, 40):
        world.sql("INSERT INTO org_nodes(id, kind, name, created_rev, ts) VALUES (?, 'department', ?, 1, 0)", f"team{n:02d}", "T" * 80)
    ask(world, "web", "q" * 590)
    for n in range(1, 4):
        ended(world, world.task(n, "web", "done", title="t" * 80), "done", "o" * 400)
    text = text_of(world, "web")
    assert len(text) <= GROUND_CHARS and text.endswith(RULES)
    assert "(more of the record was left out)" in text


def test_a_session_that_is_not_a_chat_of_a_node_gets_the_rules_alone(world):
    function_session = world.session_of["web.identity"]
    assert ChatGround(world.db).text(function_session) == RULES
    assert ChatGround(world.db).text("cs_000000000fff") == RULES


# ---- the route: written before the turn, read by the connector ---------------------------------------------------------------------

def stub_of(services):
    return services.chat_port.router.connectors["stub"]


def test_the_direct_route_grounds_the_turn_and_rebuilds_it_on_the_next_one(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    purpose(world, "web", "Websites for the cafe")
    assert client.post(f"/api/chats/{sid}/direct", json={"text": "what are you for?"}, headers=H).status_code == 202
    assert wait_for(lambda: len(chats.messages(sid)) == 2 and sid not in chat_v2._running)
    first = stub_of(services).calls[-1].system
    assert 'in the chat of the team "Web"' in first and "Websites for the cafe" in first and first.endswith(RULES)
    ended(world, world.task(1, "web", "done", title="Menu page"), "done", "Done: the menu is up.")
    assert client.post(f"/api/chats/{sid}/direct", json={"text": "and now?"}, headers=H).status_code == 202
    assert wait_for(lambda: len(chats.messages(sid)) == 4 and sid not in chat_v2._running)
    assert 'Latest task of the team: "Menu page": done' in stub_of(services).calls[-1].system


def test_the_org_chat_is_grounded_too(rig):
    client, world, chats, bus, services = rig
    assert client.post("/api/chats/cs_org/direct", json={"text": "how are the teams?"}, headers=H).status_code == 202
    assert wait_for(lambda: len(chats.messages("cs_org")) >= 2 and "cs_org" not in chat_v2._running)
    system = stub_of(services).calls[-1].system
    assert "in the org chat" in system and "- Sales: no task yet." in system and "- Web: no task yet." in system


def test_a_grounding_that_cannot_be_built_does_not_fail_the_turn(rig, monkeypatch):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    monkeypatch.setattr(chat_v2, "ground", lambda *a: (_ for _ in ()).throw(RuntimeError("broken")))
    assert client.post(f"/api/chats/{sid}/direct", json={"text": "hello"}, headers=H).status_code == 202
    assert wait_for(lambda: len(chats.messages(sid)) == 2 and sid not in chat_v2._running)
    assert chats.messages(sid)[1].kind == "text"


# ---- the working folder (GAP3-workdir): where to look, and that the file tools are read-only ------------------------------------------

def test_with_a_folder_the_grounding_names_it_and_says_the_file_tools_are_read_only(world):
    text = ChatGround(world.db, folder=lambda: "/work/my-project").text(world.session_of["web"])
    assert grounding_text("/work/my-project") in text
    assert "Working folder: /work/my-project" in text and "read-only" in text and "cannot run a command" in text
    assert text.index("You are answering") < text.index("Working folder:") < text.index("How to answer:")       # after the record, before the rules
    assert text.endswith(RULES) and len(text) <= GROUND_CHARS


def test_with_no_folder_the_grounding_says_none_is_set_and_how_to_set_one(world):
    for source in (lambda: None, lambda: ""):
        text = ChatGround(world.db, folder=source).text(world.session_of["web"])
        assert NO_FOLDER_TEXT in text and "Working folder:" not in text and "Settings" in text and text.endswith(RULES)


def test_without_a_folder_source_the_text_is_what_it_was(world):
    text = text_of(world, "web")
    assert "working folder" not in text.lower() and text.endswith(RULES)


def test_the_folder_paragraph_and_the_rules_are_never_pushed_out_by_a_long_record(world):
    purpose(world, "web", "x" * 290)
    for n in range(1, 40):
        world.sql("INSERT INTO org_nodes(id, kind, name, created_rev, ts) VALUES (?, 'department', ?, 1, 0)", f"team{n:02d}", "T" * 80)
    ask(world, "web", "q" * 590)
    for n in range(1, 4):
        ended(world, world.task(n, "web", "done", title="t" * 80), "done", "o" * 400)
    text = ChatGround(world.db, folder=lambda: "/work/my-project").text(world.session_of["web"])
    assert len(text) <= GROUND_CHARS and text.endswith(RULES) and "Working folder: /work/my-project" in text
    assert "(more of the record was left out)" in text


def test_a_folder_that_cannot_be_read_does_not_break_the_grounding(world):
    def broken():
        raise OSError("disk gone")
    text = ChatGround(world.db, folder=broken).text(world.session_of["web"])
    assert NO_FOLDER_TEXT in text and text.endswith(RULES)


def test_ground_reads_the_folder_from_the_router_and_scrubs_it_like_the_rest(world):
    svc = Svc(world.db)
    svc.connector_router = SimpleNamespace(chat_folder=lambda: f"/work/{SECRET_A}/p")
    text = ground(svc, world.session_of["web"])
    assert "Working folder: /work/" in text and SECRET_A not in text and "[redacted:openai-key]" in text


def test_the_direct_route_writes_the_folder_paragraph_into_the_session_system_text(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    assert client.post(f"/api/chats/{sid}/direct", json={"text": "where do I look?"}, headers=H).status_code == 202
    assert wait_for(lambda: len(chats.messages(sid)) == 2 and sid not in chat_v2._running)
    system = stub_of(services).calls[-1].system
    assert NO_FOLDER_TEXT in system and system.endswith(RULES)              # the stub rig runs offline: no folder is ever given
