"""Node identity at the connector layer (MAN-3, D282, D283, D291): the egress audit row and the usage row name the node of a multi-agent project only when the call's tag has one, the
orchestrator port builds the tag from `agent_node_id` and `agent_role`, and a planner call can carry an optional stop token that the router honours. Every call with no node writes the
row it always wrote."""
from __future__ import annotations

import asyncio
import json
import sys

import pytest

from sutra_app.connectors.cancel import CancelToken
from sutra_app.connectors.egress import Egress
from sutra_app.connectors.errors import CallCancelledError, InvalidRequestError
from sutra_app.connectors.models import ConnectorConfig
from sutra_app.connectors.orchestrator_port import AsyncConnector, build_tag
from sutra_app.connectors.router import Router
from sutra_app.connectors.usage import MemoryUsageSink
from sutra_app.engine.port import CallTag
from test_orchestrator_port import Spy, policy

NODE = "nd_" + "a" * 12
ORG = {"purpose": "chat_plan", "session_id": "cs_org", "node_id": "root"}
PLANNER = {**ORG, "agent_node_id": NODE, "agent_role": "planner"}


class Rig:
    def __init__(self, tmp_path):
        cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
        self.claude, self.codex = Spy("claude", cfg), Spy("codex", cfg)
        self.sink = MemoryUsageSink()
        self.egress_path = tmp_path / "data" / "connectors" / "egress.jsonl"
        self.router = Router({"claude": self.claude, "codex": self.codex}, policy(), usage_sink=self.sink, sleep=lambda s: None)
        self.router.egress = Egress(self.egress_path)
        self.port = AsyncConnector(self.router)

    def call(self, **kw):
        return asyncio.run(self.port.call_json("plan it", **kw))

    def rows(self):
        return [json.loads(line) for line in self.egress_path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


# ---- the egress row ---------------------------------------------------------------------------------------------------------------

def test_the_egress_row_has_node_fields_only_when_the_call_names_a_node(tmp_path):
    egress = Egress(tmp_path / "c" / "egress.jsonl")
    egress.check("hello", session="s1", provider="claude", replace=True)
    egress.check("hello", session="s1", provider="claude", replace=False, node_id=NODE, node_role="worker")
    egress.check("hello", session="s1", provider="claude", replace=True, node_id=NODE)
    plain, named, no_role = egress.rows()
    assert "node" not in plain and "role" not in plain and set(plain) == {"time", "session", "provider", "mode", "bytes", "shapes"}
    assert (named["node"], named["role"], named["mode"]) == (NODE, "worker", "observe") and set(named) == set(plain) | {"node", "role"}
    assert no_role["node"] == NODE and "role" not in no_role


def test_a_node_row_holds_ids_and_a_word_never_a_payload(tmp_path):
    egress = Egress(tmp_path / "c" / "egress.jsonl")
    egress.check("my key is sk-abcdefgh12345678", session=None, provider="codex", replace=True, node_id=NODE, node_role="reviewer")
    text = egress.path.read_text(encoding="utf-8")
    assert "sk-abcdefgh" not in text and "my key" not in text and NODE in text


def test_a_planner_call_writes_egress_rows_that_name_the_planner(rig):
    rig.call(function="chat_agent", step="decide", context=PLANNER)
    rows = rig.rows()
    assert rows and all(r["node"] == NODE and r["role"] == "planner" and r["mode"] == "replace" for r in rows)


def test_a_call_with_no_agent_node_writes_the_row_it_always_wrote(rig):
    rig.call(function="chat_agent", step="decide", context=ORG)
    assert rig.rows() and all("node" not in r and "role" not in r for r in rig.rows())


def test_an_egress_stand_in_that_does_not_know_node_fields_is_never_given_any_for_a_plain_call(tmp_path):
    seen = []

    class Old:
        def check(self, text, *, session, provider, replace, system=""):
            seen.append(text)
            return text

    rig = Rig(tmp_path)
    rig.router.egress = Old()
    rig.call(context=ORG)
    assert seen                                                                       # it was called, with the arguments it knows


# ---- the usage row ----------------------------------------------------------------------------------------------------------------

def test_the_usage_row_of_a_node_call_names_the_node_in_its_detail_and_a_plain_row_is_unchanged(rig):
    rig.call(context=PLANNER)
    rig.call(context=ORG)
    named, plain = rig.sink.rows
    assert named.detail["agent_node"] == NODE and named.detail["agent_role"] == "planner"
    assert "agent_node" not in plain.detail and "agent_role" not in plain.detail
    assert set(named.detail) - set(plain.detail) == {"agent_node", "agent_role"}
    assert (named.node_id, plain.node_id) == ("root", "root")                         # the row's own node_id is still the GRAPH node


# ---- the tag ----------------------------------------------------------------------------------------------------------------------

def test_the_tag_takes_the_agent_node_and_role_from_the_context_and_not_the_graph_node():
    tag = build_tag("chat_agent", "decide", PLANNER)
    assert (tag.node_id, tag.node_role) == (NODE, "planner") and tag.function == "chat_agent"
    assert build_tag("chat_agent", "decide", ORG) == CallTag(function="chat_agent", stage="decide", purpose="chat_plan", workspace="edit")
    assert (build_tag("audit", None, {"agent_node_id": NODE}).node_role) == ""


@pytest.mark.parametrize("context", [{"agent_node_id": "root"}, {"agent_node_id": NODE, "agent_role": "boss"}, {"agent_node_id": "nd_" + "A" * 12}])
def test_a_node_id_or_role_that_is_not_one_is_an_invalid_request(rig, context):
    with pytest.raises(InvalidRequestError):
        rig.call(context=context)
    assert rig.claude.seen == []


# ---- the planner's stop token ---------------------------------------------------------------------------------------------------

def test_a_stop_token_that_was_requested_ends_the_call_before_any_connector_is_used(rig):
    token = CancelToken()
    token.request()
    with pytest.raises(CallCancelledError):
        rig.call(context=PLANNER, cancel=token)
    assert rig.claude.seen == [] and rig.codex.seen == []


def test_a_token_that_was_not_requested_changes_nothing(rig):
    value, usd, how = rig.call(context=PLANNER, cancel=CancelToken())
    assert isinstance(value, dict) and how == "stub" and len(rig.claude.seen) == 1


def test_a_call_with_no_token_is_what_it_was(rig):
    rig.call(context=ORG)
    assert len(rig.claude.seen) == 1
