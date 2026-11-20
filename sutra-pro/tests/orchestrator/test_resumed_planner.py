"""A request that waited for the owner's yes (a merge) and is then resumed is a planner too (G5, D301): its calls carry the planner's identity and stop token, a stop ends the call, and the project made
from it has the planner node."""
import time

import pytest
from fastapi.testclient import TestClient
from orchestrator.test_chat_agent import add_dept, add_div, assignments, change_reply, decide, draft
from orchestrator.test_projects_adopt import BASE, HEADERS, make_app, rows, talk
from orchestrator.test_scripted_conversation import MERGE, ORG

from sutra_app.connectors.errors import CallCancelledError
from sutra_app.orchestrator.agent.planner import line


@pytest.fixture
def world(tmp_path):
    app, connector = make_app(tmp_path, nodes_v1=True)
    with TestClient(app, base_url=BASE) as client:
        services = app.state.services
        talk(client, services, connector, "Set up the teams", decide("chart_request", "add", reuse=(), assignments=[]),
             change_reply(add_dept("$web", "Web", "Websites"), add_dept("$sales", "Sales", "Quotes"), add_div("$menu", "Menu", "web"), add_div("$recipes", "Recipes", "web")))
        connector.calls.clear()
        yield client, services, connector


def ask_for_a_merge(client, services, connector):
    """The owner asks for work that needs a merge first: the card waits for the yes. Returns the card's message id."""
    talk(client, services, connector, "Merge Menu into Recipes and then do a page and a quote", decide("new_task", "rearrange", reuse=(), assignments=[]), change_reply(MERGE))
    return max(r["id"] for r in rows(services, "SELECT id FROM chat_messages WHERE kind = 'card'"))


def say_yes(client, services, connector, card_id, *script):
    connector.push(*script)
    response = client.post(f"/api/chats/{ORG}/messages", json={"text": "Yes", "choice": {"message_id": card_id, "option": "yes"}}, headers=HEADERS)
    assert response.status_code == 202, response.text
    deadline = time.time() + 10
    while services.runner.busy and time.time() < deadline:
        time.sleep(0.02)


def test_a_resumed_request_carries_the_planner_identity_and_its_project_has_the_planner_node(world):
    client, services, connector = world
    card = ask_for_a_merge(client, services, connector)
    connector.calls.clear()
    say_yes(client, services, connector, card, assignments(draft("a1", "web", title="Page"), draft("a2", "sales", title="Quote")))
    planner = rows(services, "SELECT * FROM agent_nodes WHERE role = 'planner'")
    assert len(rows(services, "SELECT * FROM projects")) == 1 and len(planner) == 1
    assert connector.calls and {call.context.get("agent_node_id") for call in connector.calls} == {planner[0]["id"]} and all(call.cancel is not None for call in connector.calls)
    assert not services.projects._planners                                                          # the token is released when the resumed request is done


def test_a_stop_during_the_assignment_stage_of_a_resumed_request_ends_the_call_and_makes_nothing(world):
    client, services, connector = world
    card = ask_for_a_merge(client, services, connector)

    def stopped_by_the_owner(call):                                                                  # the kill switch asks the planner call to stop while it runs
        assert services.projects.stop_planners() == 1 and call.cancel.requested
        raise CallCancelledError("the turn was stopped")
    say_yes(client, services, connector, card, stopped_by_the_owner)
    assert rows(services, "SELECT * FROM tasks") == [] and rows(services, "SELECT * FROM projects") == []
    last = rows(services, "SELECT state, text FROM chat_messages WHERE role = 'agent' ORDER BY id DESC LIMIT 1")[0]
    assert last["state"] == "ok" and line("stopped") in last["text"] and "went wrong" not in last["text"] and not services.projects._planners and not services.runner.busy


def test_a_stop_during_a_fresh_planning_call_ends_it_as_a_stop_not_as_a_connector_failure(world):
    """The agent used to turn the stop into a `ConnectorFailure` ("I can't reach Claude"), so the runner's own handling of it never ran."""
    client, services, connector = world

    def stopped_by_the_owner(call):
        services.projects.stop_planners()
        raise CallCancelledError("the turn was stopped")
    talk(client, services, connector, "A page and a quote", stopped_by_the_owner)
    last = rows(services, "SELECT text FROM chat_messages WHERE role = 'agent' ORDER BY id DESC LIMIT 1")[0]
    assert last["text"] == line("stopped") and "can't reach" not in last["text"] and rows(services, "SELECT * FROM tasks") == [] and not services.projects._planners
