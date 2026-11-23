"""`task.json` and the node identity (MAN-3, D254, D283). With the flag off, and for every run that is not a node, the file is byte-identical to what it was before nodes existed (the
golden files in tests/fixtures/run_spec were written by the code of origin/main at the time of MAN-1). A node's file carries one more block, read back by the engine's `TaskSpec`; the
child environment names the node (SUTRA_NODE_ID) only for a node."""
import json
from pathlib import Path

import pytest
from orchestrator.test_tasks import tenv_with

from sutra_app.engine.spec import TaskSpec
from sutra_app.orchestrator import nodes_store, tasks
from sutra_app.orchestrator.grants import StepRequest, intersect
from sutra_app.orchestrator.models import NodeBlock, RunSpec, UpstreamRef
from sutra_app.orchestrator.runs import NODE_ID_ENV, ProcessLauncher

GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "run_spec"
PROJECT, NODE, GRANT = "prj_" + "b" * 12, "nd_" + "a" * 12, "gr_" + "c" * 12


def golden(name: str) -> str:
    return (GOLDEN / name).read_bytes().decode("utf-8").replace("\r\n", "\n")


def plain_spec() -> RunSpec:
    return RunSpec(run_id="j2-20261104-100005-7f3b", task_id="tsk_a1b2c3d4e5f7", dept_id="web", dept_label="Web", user_text="Build a landing page")


def full_spec(**extra) -> RunSpec:
    return RunSpec(run_id="j2-20261104-100004-7f3a", task_id="tsk_a1b2c3d4e5f6", dept_id="web", dept_label="Web", scope_id="web-div", scope_label="Pricing",
                   user_text="Café menu — naïve ünïcode", framing="the owner wants a menu", parent_run_id="j2-20261103-090000-aaaa", seed_from="j2-20261103-090000-aaaa",
                   upstream=[UpstreamRef(dept_id="sales", run_id="j2-20261103-080000-bbbb", title="Quote", files=["quote.md", "terms.md"])],
                   settings={"J2_OUTPUT": "hld", "J2_BUDGET": "75", "J2_BUDGET_CAP": "150", "J2_FIXES": "1", "J2_MEMORY": "0", "J2_SLIM": "1", "J2_RATES": "0",
                             "J2_DECIDE_FOR_ME": "1"}, connector="stub", **extra)


# ---- byte for byte ----------------------------------------------------------------------------------------------------------------

def test_a_run_spec_with_no_node_is_byte_identical_to_the_golden_files():
    assert plain_spec().model_dump_json(indent=2) + "\n" == golden("plain.task.json")
    assert full_spec().model_dump_json(indent=2) + "\n" == golden("full.task.json")
    assert plain_spec().model_dump_json(by_alias=True) == golden("plain.compact.json")


def test_no_node_key_is_written_not_even_as_null_in_any_dump_mode():
    spec = full_spec()
    for dump in (json.loads(spec.model_dump_json()), spec.model_dump(), spec.model_dump(mode="json"), spec.model_dump(by_alias=True), spec.model_dump(exclude_none=True)):
        assert "node" not in dump


def test_a_node_adds_one_block_at_the_end_and_changes_nothing_before_it():
    block = NodeBlock(id=NODE, project_id=PROJECT, role="worker", runtime="engine", grants_id=GRANT, scope=["site/pricing/"])
    text = full_spec(node=block).model_dump_json(indent=2) + "\n"
    assert {k: v for k, v in json.loads(text).items() if k != "node"} == json.loads(golden("full.task.json"))             # everything else is the golden file's
    assert json.loads(text)["node"] == {"id": NODE, "project_id": PROJECT, "role": "worker", "runtime": "engine", "attempt": 1, "grants_id": GRANT,
                                        "caps": {"calls": 60, "usd": None, "wall_s": 1800}, "scope": ["site/pricing/"], "tool_profile": "none", "slots": False, "tiers": [], "commands": "none"}
    assert list(json.loads(text))[-1] == "node"


def test_a_run_spec_with_a_node_is_read_back_by_the_engines_task_spec_and_by_itself():
    block = NodeBlock(id=NODE, project_id=PROJECT, role="reviewer", runtime="light", grants_id=GRANT)
    dump = json.loads(full_spec(node=block).model_dump_json(by_alias=True))
    read = TaskSpec.model_validate(dump)
    assert (read.node.id, read.node.project_id, read.node.role, read.node.runtime, read.node.grants_id) == (NODE, PROJECT, "reviewer", "light", GRANT)
    assert RunSpec.model_validate(dump).node == block
    assert RunSpec.model_validate({k: v for k, v in dump.items() if k != "node"}).node is None


# ---- the launcher's environment -----------------------------------------------------------------------------------------------------

def test_the_child_environment_names_the_node_only_for_a_node_and_never_inherits_one():
    launcher = ProcessLauncher(environ={"PATH": "/bin", "SUTRA_DATA_DIR": "/d", NODE_ID_ENV: "nd_" + "f" * 12})
    assert NODE_ID_ENV not in launcher.environment(plain_spec())                  # a stray value in the server's own environment is not passed on
    block = NodeBlock(id=NODE, project_id=PROJECT, role="worker", runtime="engine", grants_id=GRANT)
    env = launcher.environment(full_spec(node=block))
    assert env[NODE_ID_ENV] == NODE and env["SUTRA_DATA_DIR"] == "/d"
    assert NODE_ID_ENV not in ProcessLauncher(environ={"PATH": "/bin"}).environment(plain_spec())


# ---- what the task service writes ----------------------------------------------------------------------------------------------------

def seed_node(tenv, task_id: str, *, with_grant: bool = True, role: str = "worker"):
    """A project, and the `agent_nodes` row of the task, with the grant frozen on it (what MAN-5 will do at plan time)."""
    grant = intersect("worker", StepRequest(scope=("site/pricing/",)), "edit", "edit", grant_id=GRANT, node_id=NODE)
    tenv.sql("INSERT INTO projects(id, created_at) VALUES (?, 1)", PROJECT)
    tenv.sql("INSERT INTO agent_nodes(id, project_id, task_id, role, runtime, grants_json, created_at) VALUES (?,?,?,?,?,?,1)", NODE, PROJECT, task_id, role, "engine",
             json.dumps(grant.to_json()) if with_grant else "{}")


def start_and_read(tenv, task_id):
    tenv.run(tenv.service.start_ready())
    path = tenv.run_dir(task_id) / "task.json"
    return path.read_text(encoding="utf-8"), tenv.launcher


@pytest.fixture
def make(db, settings, clock, events):
    def build(**changes):
        return tenv_with(db, settings, clock, events, **changes)
    return build


def test_with_the_flag_off_a_task_that_has_a_node_row_still_gets_the_plain_file_and_the_table_is_not_read(make, monkeypatch):
    tenv = make()
    task = tenv.new("web", "Build a landing page")
    seed_node(tenv, task.id)
    monkeypatch.setattr(tasks, "node_block_of", lambda *a, **k: pytest.fail("the nodes table was read with SUTRA_NODES_V1 off"))
    text, _ = start_and_read(tenv, task.id)
    assert "node" not in json.loads(text) and text.endswith('"connector": "auto"\n}\n')
    assert TaskSpec.model_validate(json.loads(text)).node is None


def test_with_the_flag_off_the_file_is_the_golden_file_apart_from_the_ids_and_words_of_the_task(make):
    tenv = make()
    task = tenv.new("web", "Build a landing page")
    text, _ = start_and_read(tenv, task.id)
    spec = RunSpec.model_validate_json(text)
    assert spec.model_dump_json(indent=2) + "\n" == text and set(json.loads(text)) == set(json.loads(golden("plain.task.json")))


def test_with_the_flag_on_an_ordinary_task_still_gets_the_plain_file(make):
    tenv = make(nodes_v1=True)
    task = tenv.new("web", "Build a landing page")
    text, _ = start_and_read(tenv, task.id)
    assert "node" not in json.loads(text) and set(json.loads(text)) == set(json.loads(golden("plain.task.json")))


def test_with_the_flag_on_a_node_task_gets_the_block_from_its_row_and_its_grant(make):
    tenv = make(nodes_v1=True)
    task = tenv.new("web", "Build a landing page")
    seed_node(tenv, task.id)
    text, _ = start_and_read(tenv, task.id)
    doc = json.loads(text)
    assert doc["node"] == {"id": NODE, "project_id": PROJECT, "role": "worker", "runtime": "engine", "attempt": 1, "grants_id": GRANT,
                           "caps": {"calls": 60, "usd": None, "wall_s": 1800}, "scope": ["site/pricing/"], "tool_profile": "none", "slots": False, "tiers": [0, 1, 2, 3], "commands": "git_reads"}
    assert TaskSpec.model_validate(doc).node.id == NODE


def test_a_node_without_a_usable_grant_does_not_get_a_task_json_at_all_it_raises_and_the_run_folder_is_cleaned_up(make):
    """No fallback (D302): `_run_spec` never writes a plain file for a node with no grant. The task gate holds such a node, so this is only reached by a bug."""
    from sutra_app.orchestrator.nodes_store import NodeBlockError
    tenv = make(nodes_v1=True)
    task = tenv.new("web", "Build a landing page")
    seed_node(tenv, task.id, with_grant=False)
    with pytest.raises(NodeBlockError):
        tenv.run(tenv.service.start_ready())
    assert tenv.status(task.id) == "queued" and not list((tenv.settings.data_dir / "departments" / "web" / "runs").glob("j2-*"))


def test_a_grant_that_does_not_fit_the_node_row_is_not_a_usable_grant(db):
    db.conn().execute("INSERT INTO projects(id, created_at) VALUES (?, 1)", (PROJECT,))
    db.conn().execute("INSERT INTO org_nodes(id, kind, name, created_rev, ts) VALUES ('web','department','Web',1,0)")
    db.conn().execute("INSERT INTO departments(id, home_dir, body, sha256, ts) VALUES ('web','d','{}','x',0)")
    db.conn().execute("INSERT INTO tasks(id, dept_id, title, user_text, status, created_at) VALUES ('tsk_" + "1" * 12 + "','web','t','u','queued',1)")
    reviewer_grant = intersect("reviewer", None, "edit", "edit", grant_id=GRANT, node_id=NODE)
    db.conn().execute("INSERT INTO agent_nodes(id, project_id, task_id, role, runtime, grants_json, created_at) VALUES (?,?,?,?,?,?,1)", (NODE, PROJECT, "tsk_" + "1" * 12, "worker", "engine",
                                                                                                                          json.dumps(reviewer_grant.to_json())))
    with pytest.raises(nodes_store.NodeBlockError):
        nodes_store.node_block_of(db.conn(), "tsk_" + "1" * 12)
    assert nodes_store.node_block_of(db.conn(), "tsk_" + "2" * 12) is None
