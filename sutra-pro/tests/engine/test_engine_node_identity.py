"""Node identity in the engine (MAN-3, D283): the optional `node` block of `task.json` is read, the host puts the node's id and role on the base tag of every call of the process,
and a run with no block gets exactly the tag it always got. The block is read tolerantly: an older reader ignores it."""
import json
from types import SimpleNamespace

import pytest
from pydantic import ConfigDict, ValidationError, create_model

from sutra_app.engine import llm
from sutra_app.engine.host import loop
from sutra_app.engine.port import CallTag
from sutra_app.engine.spec import NodeSpec, TaskSpec

from test_engine_host import BREW_LAB, QUIET, Running, j2  # noqa: F401  (j2 is a fixture)

EXAMPLE_TASK = {"schema": "run-spec/1", "run_id": "j2-20261104-100004-7f3a", "task_id": "tsk_a1b2c3d4e5f6", "dept_id": "web", "dept_label": "Web", "user_text": "A website for my cafe",
                "settings": {"J2_BUDGET": "100"}, "connector": "auto"}           # the same run the engine conftest makes (its folder has no importable name)
NODE = {"id": "nd_" + "a" * 12, "project_id": "prj_" + "b" * 12, "role": "worker", "runtime": "engine", "attempt": 1, "grants_id": "gr_" + "c" * 12,
        "caps": {"calls": 60, "usd": None, "wall_s": 1800}, "scope": ["site/pricing/"]}


class TaggingPort(llm.ScriptedPort):
    """A scripted port that keeps the tag of every request it is given."""

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.tags: list[CallTag] = []

    def complete(self, req, on_progress=None):
        self.tags.append(req.tag)
        return super().complete(req, on_progress)


def run_with(make_run_dir, **task_fields):
    run_dir = make_run_dir(user_text=BREW_LAB, settings=QUIET, **task_fields)
    holder = {}

    def make(*, sink, mock, task, paths):
        holder["port"] = TaggingPort(usage_sink=sink)
        return holder["port"]

    assert Running(run_dir, "--mock", make_port=make).wait() == 0
    return holder["port"].tags


# ---- the spec ---------------------------------------------------------------------------------------------------------------------

def test_a_task_spec_with_a_node_block_validates_and_without_one_has_none():
    spec = TaskSpec.model_validate({**EXAMPLE_TASK, "node": NODE})
    assert isinstance(spec.node, NodeSpec) and (spec.node.id, spec.node.role, spec.node.runtime, spec.node.attempt) == (NODE["id"], "worker", "engine", 1)
    assert spec.node.caps.calls == 60 and spec.node.caps.usd is None and spec.node.caps.wall_s == 1800 and spec.node.scope == ["site/pricing/"]
    assert TaskSpec.model_validate(EXAMPLE_TASK).node is None


def test_the_node_block_is_read_tolerantly_unknown_keys_are_ignored_but_a_wrong_id_or_role_is_not_accepted():
    spec = TaskSpec.model_validate({**EXAMPLE_TASK, "node": {**NODE, "added_later": 1, "caps": {**NODE["caps"], "tokens": 5}}})
    assert spec.node.id == NODE["id"]
    for bad in ({"id": "nd_x"}, {"id": "tsk_" + "a" * 12}, {"project_id": "p1"}, {"role": "planner"}, {"role": "owner"}, {"runtime": "inline"}, {"grants_id": ""}, {"attempt": 0},
                {"caps": {"calls": 0}}, {"scope": ["a"] * 51}):
        with pytest.raises(ValidationError):
            TaskSpec.model_validate({**EXAMPLE_TASK, "node": {**NODE, **bad}})
    with pytest.raises(ValidationError):
        TaskSpec.model_validate({**EXAMPLE_TASK, "node": {"id": NODE["id"]}})


def test_an_older_reader_that_has_no_node_field_ignores_the_block():
    """An older engine's `TaskSpec` had `extra="ignore"` and no `node`: the same file reads as before."""
    older = create_model("OlderTaskSpec", __config__=ConfigDict(extra="ignore"), run_id=(str, ...), task_id=(str, ...), dept_id=(str, ...), user_text=(str, ...))
    read = older.model_validate({**EXAMPLE_TASK, "node": NODE})
    assert read.task_id == EXAMPLE_TASK["task_id"] and not hasattr(read, "node")
    assert TaskSpec.model_config["extra"] == "ignore"


# ---- the base tag -----------------------------------------------------------------------------------------------------------------

def test_the_base_tag_of_a_node_run_names_the_node_and_its_role():
    task = TaskSpec.model_validate({**EXAMPLE_TASK, "node": NODE})
    tag = loop.Host._base_tag(SimpleNamespace(task=task))
    assert (tag.run_id, tag.dept_id, tag.task_id, tag.node_id, tag.node_role) == (task.run_id, "web", task.task_id, NODE["id"], "worker")


def test_the_base_tag_of_a_run_that_is_not_a_node_is_exactly_what_it_was():
    task = TaskSpec.model_validate(EXAMPLE_TASK)
    tag = loop.Host._base_tag(SimpleNamespace(task=task))
    assert tag == CallTag(run_id=task.run_id, dept_id="web", task_id=task.task_id) and (tag.node_id, tag.node_role) == ("", "")


def test_every_call_of_a_node_run_carries_the_node_and_a_plain_run_carries_none(j2, make_run_dir):
    tags = run_with(make_run_dir, node=NODE)
    assert len(tags) > 5 and {(t.node_id, t.node_role) for t in tags} == {(NODE["id"], "worker")}
    assert all(t.run_id == EXAMPLE_TASK["run_id"] and t.task_id == EXAMPLE_TASK["task_id"] for t in tags)


def test_a_run_with_no_node_block_makes_calls_with_empty_node_fields(j2, make_run_dir):
    tags = run_with(make_run_dir)
    assert len(tags) > 5 and {(t.node_id, t.node_role) for t in tags} == {("", "")}


def test_the_node_fields_appear_in_a_tag_dump_only_with_their_empty_defaults_for_other_calls():
    dump = CallTag(function="audit").model_dump()
    assert dump["node_id"] == "" and dump["node_role"] == ""
    assert json.loads(CallTag(node_id=NODE["id"], node_role="reviewer").model_dump_json())["node_role"] == "reviewer"
    for bad in ({"node_id": "nd_1"}, {"node_id": "x" * 15}, {"node_role": "boss"}, {"node_role": "Worker"}):
        with pytest.raises(ValidationError):
            CallTag(**bad)
