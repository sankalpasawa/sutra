"""The tier-4 delivery (MAN-8, D298): the app tools a node's grant gives (`sutra`, `github`) reach the run's own agent-turn calls through `PortSpec.tools` and the `RouterPort`, and
never a builder-tools call. A run without a node (`tools` empty) makes exactly the call it made before."""
from __future__ import annotations

import pytest

from sutra_app.connectors.engine_port import port_from_config
from sutra_app.connectors.errors import NoProviderError
from sutra_app.connectors.models import ConnectorConfig
from sutra_app.engine.port import CallTag, CompletionRequest, PortSpec, ToolGrant

TAG = CallTag(run_id="j2-20261104-000000-ab12", dept_id="web", task_id="tsk_aaaaaaaaaaaa", function="audit", purpose="review")


def port_of(tmp_path, **kw):
    spec = PortSpec(mock=True, run_id="j2-20261104-000000-ab12", dept_id="web", task_id="tsk_aaaaaaaaaaaa", data_dir=str(tmp_path / "data"), **kw)
    port = port_from_config(spec, ConnectorConfig(data_dir=tmp_path / "data"))
    seen = []
    real = port.router._ask

    def spy(ask, on_progress=None):
        seen.append(ask)
        return real(ask, on_progress)
    port.router._ask = spy
    return port, seen


def test_a_port_spec_has_no_tools_unless_a_node_gave_them():
    assert PortSpec(mock=True, run_id="j2-20261104-000000-ab12", dept_id="web", data_dir="d").tools == ()


def test_the_granted_tools_are_on_an_agent_turn_call_and_a_port_without_them_makes_the_call_it_always_made(tmp_path):
    port, seen = port_of(tmp_path, tools=("sutra", "github"))
    with pytest.raises(NoProviderError):                                       # the stub cannot take tools: the call is refused, after the router has seen what it carried
        port.complete(CompletionRequest(system="", user="hello", tag=TAG))
    assert seen[-1].tools == ("sutra", "github")
    plain, plain_seen = port_of(tmp_path / "plain")
    plain.complete(CompletionRequest(system="", user="hello", tag=TAG))
    assert plain_seen[-1].tools == ()


def test_a_builder_tools_call_never_gets_the_app_tools(tmp_path):
    port, seen = port_of(tmp_path, tools=("github",))
    grant = ToolGrant(tools=("Read",), allow=("Read",), cwd=".", root=".", usd=1.0, log_chars=1)
    with pytest.raises(NoProviderError):
        port.complete(CompletionRequest(system="", user="build", tag=TAG, run_tools=grant))
    assert seen[-1].tools == () and seen[-1].run_tools is grant


def test_the_node_block_carries_the_tool_profile_and_the_host_turns_it_into_tools(tmp_path):
    from sutra_app.engine.spec import NodeSpec
    block = NodeSpec.model_validate({"id": "nd_" + "a" * 12, "project_id": "prj_" + "b" * 12, "role": "worker", "runtime": "engine", "grants_id": "gr_" + "c" * 12, "tool_profile": "sutra+github"})
    assert tuple(block.tool_profile.split("+")) == ("sutra", "github") and NodeSpec.model_validate({**block.model_dump(), "tool_profile": "none"}).tool_profile == "none"
    older = {"id": "nd_" + "a" * 12, "project_id": "prj_" + "b" * 12, "role": "worker", "runtime": "engine", "grants_id": "gr_" + "c" * 12}
    assert NodeSpec.model_validate(older).tool_profile == "none"                                               # a block written before this field
