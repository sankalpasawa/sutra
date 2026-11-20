"""The shapes of the multi-agent nodes work (MAN-1): closed, strict, and the node block as `task.json` will carry it (D283). Nothing builds them while SUTRA_NODES_V1 is off."""
import pytest
from pydantic import ValidationError

from sutra_app.orchestrator.models import (
    NODE_ROLES, NODE_RUNTIMES, NODE_STATES, PROJECT_STATUSES, AgentNodeState, NodeBlock, NodeCaps, NodeOut, ProjectOut,
)

NODE = "nd_" + "a" * 12
PROJECT = "prj_" + "b" * 12
GRANT = "gr_" + "c" * 12
AT = "2026-11-20T10:00:00Z"


def block(**over):
    return NodeBlock(id=NODE, project_id=PROJECT, role="worker", runtime="engine", grants_id=GRANT, **over)


def test_a_node_block_round_trips_and_has_the_documented_keys():
    dump = block(scope=["site/pricing/"], caps=NodeCaps(calls=40, usd=1.5, wall_s=600), attempt=2).model_dump(mode="json")
    assert dump == {"id": NODE, "project_id": PROJECT, "role": "worker", "runtime": "engine", "attempt": 2, "grants_id": GRANT,
                    "caps": {"calls": 40, "usd": 1.5, "wall_s": 600}, "scope": ["site/pricing/"], "tool_profile": "none"}
    assert NodeBlock.model_validate(dump) == block(scope=["site/pricing/"], caps=NodeCaps(calls=40, usd=1.5, wall_s=600), attempt=2)


def test_the_default_caps_are_the_design_defaults():
    assert block().caps.model_dump() == {"calls": 60, "usd": None, "wall_s": 1800}


@pytest.mark.parametrize("over", [
    {"role": "planner"}, {"role": "conductor"}, {"runtime": "inline"}, {"runtime": "thread"}, {"attempt": 0}, {"id": "nd_xyz"}, {"project_id": "tsk_" + "a" * 12},
    {"grants_id": "g1"}, {"surprise": 1}, {"scope": ["a"] * 51}, {"scope": [""]}, {"caps": {"calls": 0}},
])
def test_a_node_block_is_closed_and_checked(over):
    base = {"id": NODE, "project_id": PROJECT, "role": "worker", "runtime": "engine", "grants_id": GRANT}
    with pytest.raises(ValidationError):
        NodeBlock(**{**base, **over})


def test_the_planner_is_inline_so_it_has_no_process_block():
    with pytest.raises(ValidationError):
        NodeBlock(id=NODE, project_id=PROJECT, role="planner", runtime="inline", grants_id=GRANT)


def test_a_project_and_a_node_as_the_page_reads_them():
    project = ProjectOut(id=PROJECT, status="running", created_at=AT, caps={"max_parallel": 3, "node_usd": None}, decide_for_me=True)
    assert project.model_dump(mode="json")["status"] == "running" and project.caps["max_parallel"] == 3 and project.paused is False
    node = NodeOut(id=NODE, project_id=PROJECT, role="worker", runtime="engine", state="awaiting_system", created_at=AT, depends_on=["nd_" + "d" * 12])
    assert node.state == "awaiting_system" and node.attempt == 1 and node.grants == {}


@pytest.mark.parametrize("cls,base,over", [
    (ProjectOut, {"id": PROJECT, "status": "running", "created_at": AT}, {"status": "paused"}),
    (ProjectOut, {"id": PROJECT, "status": "running", "created_at": AT}, {"failure_policy": "go_on"}),
    (ProjectOut, {"id": PROJECT, "status": "running", "created_at": AT}, {"surprise": 1}),
    (ProjectOut, {"id": PROJECT, "status": "running", "created_at": AT}, {"created_at": "yesterday"}),
    (NodeOut, {"id": NODE, "project_id": PROJECT, "role": "worker", "runtime": "engine", "state": "ready", "created_at": AT}, {"state": "paused"}),
    (NodeOut, {"id": NODE, "project_id": PROJECT, "role": "worker", "runtime": "engine", "state": "ready", "created_at": AT}, {"role": "owner"}),
    (NodeOut, {"id": NODE, "project_id": PROJECT, "role": "worker", "runtime": "engine", "state": "ready", "created_at": AT}, {"id": "nd_1"}),
])
def test_the_output_shapes_are_closed_and_checked(cls, base, over):
    with pytest.raises(ValidationError):
        cls(**{**base, **over})


def test_the_value_lists_match_the_database_checks(db):
    """The words in models.py and the CHECK lists of migration v6 are one list: a state the model knows must be one the table takes, and the other way round."""
    def check_words(table, column):
        sql = db.conn().execute("SELECT sql FROM sqlite_master WHERE name = ?", (table,)).fetchone()[0]
        body = sql.split(f"{column} TEXT", 1)[1].split("CHECK (", 1)[1].split(")", 1)[0]
        return tuple(word.strip().strip("'") for word in body.replace(f"{column} IN (", "").split(","))

    assert check_words("agent_nodes", "state") == NODE_STATES
    assert check_words("agent_nodes", "role") == NODE_ROLES
    assert check_words("agent_nodes", "runtime") == NODE_RUNTIMES
    assert check_words("projects", "status") == PROJECT_STATUSES
    assert set(AgentNodeState.__args__) == set(NODE_STATES)



def test_the_id_factory_makes_ids_the_models_accept():
    from sutra_app.orchestrator.ids import IdFactory
    from sutra_app.orchestrator.testing import FakeIds
    for ids in (IdFactory(), FakeIds()):
        block_ = NodeBlock(id=ids.node_id(), project_id=ids.project_id(), role="reviewer", runtime="light", grants_id=ids.grant_id())
        assert block_.runtime == "light" and ids.approval_id().startswith("ap_") and len(ids.approval_id()) == 15
    assert FakeIds().project_id() == "prj_000000000001"
