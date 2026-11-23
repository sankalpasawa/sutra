"""The planner's identity (MAN-3, D291): the org chat agent's calls name a planner node and carry a stop token only when the request has them; a request without them is what it was."""
import asyncio

import pytest

from sutra_app.connectors.cancel import CancelToken
from sutra_app.connectors.errors import CallCancelledError
from sutra_app.orchestrator.agent.agent import PlanRequest, call_context
from sutra_app.orchestrator.testing.scripted import ScriptedConnector

NODE = "nd_" + "a" * 12


def test_the_call_context_names_the_planner_only_when_given_a_node():
    plain = call_context(7)
    assert plain == {"purpose": "chat_plan", "session_id": "cs_org", "node_id": "root", "atom_id": plain["atom_id"]} and "agent_node_id" not in plain
    named = call_context(7, NODE)
    assert named == {**plain, "agent_node_id": NODE, "agent_role": "planner"} and named["node_id"] == "root"         # node_id is still the graph node


def test_a_plan_request_has_no_node_and_no_token_unless_it_is_given_them():
    request = PlanRequest(text="hi", message_id=3)
    assert request.node_id == "" and request.cancel is None
    token = CancelToken()
    assert PlanRequest(text="hi", message_id=3, node_id=NODE, cancel=token).cancel is token


def test_the_scripted_connector_records_the_token_and_ends_a_requested_call_without_using_a_script_item():
    connector = ScriptedConnector([{"a": 1}, {"a": 2}])
    token = CancelToken()
    assert asyncio.run(connector.call_json("p", cancel=token))[0] == {"a": 1} and connector.calls[0].cancel is token
    assert asyncio.run(connector.call_json("p"))[0] == {"a": 2} and connector.calls[1].cancel is None
    token.request()
    connector.push({"a": 3})
    with pytest.raises(CallCancelledError):
        asyncio.run(connector.call_json("p", cancel=token))
    assert connector.remaining == 1
