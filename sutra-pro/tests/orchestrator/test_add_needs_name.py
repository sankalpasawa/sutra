"""Named projects, task 5 (Q13, D427): the org chat never makes a project by itself. When the chat agent's change would add a team, the
owner is asked first, on an approval card that carries the suggested name; the owner names it (or keeps the suggestion) and only then is the
team made, with its folder. A reuse, and the owner's own changes, stay automatic."""
import os

import pytest
from factories_org import dept_op, div_op
from fastapi.testclient import TestClient
from orchestrator.test_chart_store import Env
from orchestrator.test_chat_agent import add_dept, assignments, change_reply, decide, draft
from orchestrator.test_scripted_conversation import HEADERS, ORG, Scenario, make_scenario

from sutra_app.orchestrator.chart_rules import classify


@pytest.fixture
def convo(tmp_path):
    app, connector = make_scenario(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1:8780") as client:
        yield Scenario(client, app, connector)


def ask_for_cafe(c: Scenario) -> dict:
    """The owner asks for something no team does; the agent would add "Cafe site". Returns the approval card."""
    c.say("I need a landing page for my cafe.",
          decide(change="add", reuse=(), why="no team builds pages"),
          change_reply(add_dept("$web", "Cafe site", "Websites and landing pages")),
          assignments(draft("a1", "cafe-site", title="Cafe page", brief="Build the cafe landing page.")))
    [card] = c.cards("approval")
    return card


def documents():
    return os.environ["SUTRA_DOCUMENTS_DIR"]


def departments(c: Scenario) -> list[str]:
    return [r[0] for r in c.sql("SELECT name FROM org_nodes WHERE kind = 'department' AND state = 'active'")]


def test_a_chat_agent_add_waits_for_the_owner(convo):
    head = convo.one("SELECT max(revision) FROM org_charts")
    card = ask_for_cafe(convo)
    assert card["adds"] == [{"ref": "$web", "name": "Cafe site"}]
    assert card["question"] == "I'd start a new project for this: Cafe site. Name it to create it, or say no."
    assert convo.one("SELECT max(revision) FROM org_charts") == head and departments(convo) == []
    assert convo.one("SELECT status FROM chart_changes ORDER BY seq DESC LIMIT 1") == "pending_approval"


def test_naming_it_applies_the_add_under_that_name(convo):
    card = ask_for_cafe(convo)
    convo.connector.push(assignments(draft("a1", "cafe", title="Cafe page", brief="Build the cafe landing page.")))     # stage C repairs to the renamed id
    response = convo.client.post(f"/api/chart/changes/{card['change_id']}/decision", json={"approve": True, "names": {"$web": "Cafe"}}, headers=HEADERS)
    assert response.status_code == 200, response.text
    new_id = response.json()["ids_by_ref"]["$web"]
    assert departments(convo) == ["Cafe"]
    folder = os.path.join(documents(), "Sutra Pro", "Cafe")
    assert os.path.isdir(folder)
    from sutra_app.connectors.workdir import WorkFolder
    assert WorkFolder(convo.services.data_dir, dept_id=new_id).get() == os.path.realpath(folder)


def test_a_chosen_folder_and_access_go_with_the_name(convo, tmp_path):
    card = ask_for_cafe(convo)
    convo.connector.push(assignments(draft("a1", "cafe", title="Cafe page", brief="Build the cafe landing page.")))     # stage C repairs to the renamed id
    src = tmp_path / "src"
    src.mkdir()
    response = convo.client.post(f"/api/chart/changes/{card['change_id']}/decision",
                                 json={"approve": True, "names": {"$web": "Cafe"}, "folder": str(src), "access": "read"}, headers=HEADERS)
    assert response.status_code == 200, response.text
    from sutra_app.connectors.workdir import WorkFolder
    store = WorkFolder(convo.services.data_dir, dept_id=response.json()["ids_by_ref"]["$web"])
    assert (store.get(), store.stored_access()) == (os.path.realpath(src), "read")


def test_a_plain_yes_uses_the_suggested_name(convo):
    ask_for_cafe(convo)
    card_id = max(m["id"] for m in convo.messages() if m["kind"] == "card")
    convo.say("Yes", choice={"message_id": card_id, "option": "yes"})
    assert departments(convo) == ["Cafe site"]
    assert os.path.isdir(os.path.join(documents(), "Sutra Pro", "Cafe site"))
    convo.until("the resumed request's task", lambda: convo.one("SELECT count(*) FROM tasks WHERE dept_id = 'cafe-site'"))


def test_declining_leaves_the_chart(convo):
    card = ask_for_cafe(convo)
    response = convo.client.post(f"/api/chart/changes/{card['change_id']}/decision", json={"approve": False}, headers=HEADERS)
    assert response.status_code == 200 and response.json()["status"] == "rejected"
    assert departments(convo) == [] and not os.path.exists(os.path.join(documents(), "Sutra Pro", "Cafe site"))


def test_a_name_in_use_is_refused_at_decide(convo):
    made = convo.client.post("/api/teams", json={"name": "Pulse"}, headers=HEADERS)
    assert made.status_code == 201, made.text
    card = ask_for_cafe(convo)
    response = convo.client.post(f"/api/chart/changes/{card['change_id']}/decision", json={"approve": True, "names": {"$web": " pulse "}}, headers=HEADERS)
    assert response.status_code == 409 and response.json()["error"]["code"] == "name_taken"
    assert response.json()["error"]["message"] == "A project called Pulse already exists"
    assert convo.one("SELECT status FROM chart_changes WHERE id = ?", card["change_id"]) == "pending_approval"


def test_a_blank_name_is_refused_at_decide(convo):
    card = ask_for_cafe(convo)
    response = convo.client.post(f"/api/chart/changes/{card['change_id']}/decision", json={"approve": True, "names": {"$web": "  "}}, headers=HEADERS)
    assert response.status_code == 422 and response.json()["error"]["message"] == "Give the project a name"
    assert convo.one("SELECT status FROM chart_changes WHERE id = ?", card["change_id"]) == "pending_approval"


def test_needs_you_carries_the_change_and_adds(convo):
    card = ask_for_cafe(convo)
    [item] = [n for n in convo.client.get("/api/needs-you").json() if n["kind"] == "approval"]
    assert item["change_id"] == card["change_id"] and item["adds"] == [{"ref": "$web", "name": "Cafe site"}]


def test_a_reuse_and_an_owner_change_stay_auto(db, settings, clock, events):
    env = Env(db, settings, clock, events).build()
    head = env.head()
    from factories_org import make_change
    add = make_change(head, dept_op("$x", "Support"))
    assert classify(add) == "approve" and classify(add, actor="chat_agent") == "approve"
    assert classify(add, actor="user") == "auto"
    assert classify(make_change(head, reuses=["web"])) == "auto"
    assert classify(make_change(head, div_op("$d", "Desserts", "web"))) == "auto"          # a division is not a project
