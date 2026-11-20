"""A request with two or more steps becomes a project (MAN-5; D253, D255, D267, D291, D299, D305): through the whole app with a scripted planner, and `reserve` on its own."""
import json
import time

import pytest
from fastapi.testclient import TestClient
from orchestrator.projects_rig import PRig  # noqa: F401
from orchestrator.test_chat_agent import add_dept, assignments, change_reply, decide, draft
from orchestrator.test_scripted_conversation import ORG, TOKEN

from sutra_app.config import Settings
from sutra_app.main import create_app
from sutra_app.orchestrator.projects import ProjectStep
from sutra_app.orchestrator.testing.fake_engine import FakeLauncher, node_script
from sutra_app.orchestrator.testing.scripted import ScriptedConnector

BASE = "http://127.0.0.1:8780"
HEADERS = {"X-Sutra-Token": TOKEN}


def make_app(tmp_path, **flags):
    settings = Settings.load({}, data_dir=tmp_path / "data", token=TOKEN, env_file=tmp_path / "none.env", engine="fake", watch_ms=20, max_runs=4, max_live=8, **flags)
    connector = ScriptedConnector()
    return create_app(settings, connector=connector, launcher=FakeLauncher(node_script)), connector


def four_steps():
    return assignments(draft("a1", "web", title="Page"), draft("a2", "sales", title="Quote"), draft("a3", "web", title="Polish", depends_on=("a1",)),
                       draft("a4", "sales", title="Send", depends_on=("a2", "a3")))


def talk(client, services, connector, text, *script):
    connector.push(*script)
    response = client.post(f"/api/chats/{ORG}/messages", json={"text": text}, headers=HEADERS)
    assert response.status_code == 202, response.text
    deadline = time.time() + 10
    while services.runner.busy and time.time() < deadline:
        time.sleep(0.02)
    return response.json()["message_id"]


def rows(services, sql, *args):
    return services.db.conn().execute(sql, args).fetchall()


@pytest.fixture
def world(tmp_path):
    app, connector = make_app(tmp_path, nodes_v1=True)
    with TestClient(app, base_url=BASE) as client:
        services = app.state.services
        mid = talk(client, services, connector, "A site and a quote please",
                   decide(change="add", reuse=(), why="two new teams"), change_reply(add_dept("$web", "Web", "Websites"), add_dept("$sales", "Sales", "Quotes")), four_steps())
        yield client, services, connector, mid


def test_a_four_step_plan_makes_one_project_four_nodes_a_planner_and_four_tasks_with_the_plans_edges(world):
    client, services, connector, mid = world
    project = rows(services, "SELECT * FROM projects")
    assert len(project) == 1 and project[0]["request_id"] == f"req-{mid}" and project[0]["title"] == "Page"
    nodes = rows(services, "SELECT * FROM agent_nodes WHERE role <> 'planner' ORDER BY created_at, rowid")
    assert [n["plan_ref"] for n in nodes] == ["a1", "a2", "a3", "a4"] and all(n["task_id"] for n in nodes) and len(rows(services, "SELECT * FROM tasks")) == 4
    by_ref = {n["plan_ref"]: n for n in nodes}
    assert json.loads(by_ref["a3"]["depends_on"]) == [by_ref["a1"]["id"]] and json.loads(by_ref["a4"]["depends_on"]) == [by_ref["a2"]["id"], by_ref["a3"]["id"]]
    tasks = {r["id"]: json.loads(r["depends_on"]) for r in rows(services, "SELECT id, depends_on FROM tasks")}
    assert tasks[by_ref["a4"]["task_id"]] == [by_ref["a2"]["task_id"], by_ref["a3"]["task_id"]]          # the tasks carry the plan's own depends_on, as before


def test_each_node_has_a_frozen_grant_that_says_run_tools_and_an_audit_row(world):
    client, services, connector, mid = world
    for node in rows(services, "SELECT * FROM agent_nodes WHERE role = 'worker'"):
        grant = json.loads(node["grants_json"])
        assert grant["role"] == "worker" and grant["node_id"] == node["id"] and grant["id"].startswith("gr_") and grant["run_tools"] == "engine" and 6 not in grant["tiers"]
    issued = rows(services, "SELECT * FROM node_audit WHERE action = 'grant.issued'")
    assert len(issued) == 4 and all("run_tools engine" in r["reason"] and r["actor"] == "gatekeeper" and r["decision"] == "allow" for r in issued)
    assert {r["action"] for r in rows(services, "SELECT action FROM node_audit")} >= {"project.created", "plan.accepted", "grant.issued"}


def test_the_planner_has_a_node_and_every_planner_call_carried_its_identity(world):
    client, services, connector, mid = world
    planner_nodes = rows(services, "SELECT * FROM agent_nodes WHERE role = 'planner'")
    assert len(planner_nodes) == 1 and planner_nodes[0]["runtime"] == "inline" and planner_nodes[0]["task_id"] is None and planner_nodes[0]["state"] == "done"
    ids = {call.context.get("agent_node_id") for call in connector.calls}
    assert ids == {planner_nodes[0]["id"]} and {call.context.get("agent_role") for call in connector.calls} == {"planner"}
    assert not services.projects._planners                                                          # the token is released when the request is done


def test_the_tasks_run_through_the_ordinary_scheduler_and_the_project_ends_done(world):
    client, services, connector, mid = world
    deadline = time.time() + 15
    while time.time() < deadline and rows(services, "SELECT status FROM projects")[0]["status"] != "done":
        time.sleep(0.05)
    assert rows(services, "SELECT status FROM projects")[0]["status"] == "done"
    assert {r["state"] for r in rows(services, "SELECT state FROM agent_nodes WHERE role = 'worker'")} == {"done"}
    snapshot = client.get(f"/api/projects/{rows(services, 'SELECT id FROM projects')[0]['id']}").json()
    assert snapshot["project"]["status"] == "done" and len(snapshot["nodes"]) == 5 and len([e for e in snapshot["edges"] if e["kind"] == "depends_on"]) == 3
    assert snapshot["last_message_seq"] == 4 and snapshot["approvals"] == []                 # one hand-off message per node
    assert [p["status"] for p in client.get("/api/projects").json()] == ["done"]


def test_a_one_step_request_keeps_todays_path_no_project(tmp_path):
    app, connector = make_app(tmp_path, nodes_v1=True)
    with TestClient(app, base_url=BASE) as client:
        services = app.state.services
        talk(client, services, connector, "A page", decide(change="add", reuse=(), why="x"), change_reply(add_dept("$web", "Web", "Websites")), assignments(draft("a1", "web")))
        assert rows(services, "SELECT * FROM projects") == [] and rows(services, "SELECT * FROM agent_nodes WHERE role <> 'planner'") == []
        assert len(rows(services, "SELECT * FROM tasks")) == 1


# ---- reserve on its own ---------------------------------------------------------------------------------------------------------------

@pytest.fixture
def rig(db, settings, clock, events):
    return PRig(db, settings, clock, events)


def steps(n):
    return [ProjectStep(ref=f"a{i}", dept_id="web") for i in range(1, n + 1)]


def test_fewer_than_two_steps_is_not_a_project(rig):
    assert rig.projects.reserve("req-1", "t", steps(1)) is None and rig.projects.reserve("req-1", "t", []) is None
    assert rig.sql("SELECT count(*) FROM projects").fetchone()[0] == 0


def test_a_plan_the_gatekeeper_refuses_makes_a_failed_project_and_no_node(rig):
    result = rig.projects.reserve("req-1", "big", steps(13))
    assert result is not None and result.ok is False and "13" not in result.why and "12" in result.why and result.nodes == {}
    project = rig.project(result.project_id)
    assert project["status"] == "failed" and project["ended_at"] is not None and "12 worker" in project["stop_reason"]
    assert rig.sql("SELECT count(*) FROM agent_nodes").fetchone()[0] == 0 and [r["action"] for r in rig.audit("plan.refused")] == ["plan.refused"]


def test_a_request_that_is_planned_again_finds_its_project_and_makes_no_second_one(rig):
    first = rig.projects.reserve("req-1", "t", steps(2))
    again = rig.projects.reserve("req-1", "t", steps(2))
    assert again.project_id == first.project_id and again.nodes == first.nodes and rig.sql("SELECT count(*) FROM projects").fetchone()[0] == 1


def test_the_caps_are_copied_into_the_project_and_the_owners_own_budget_means_no_confirm_question(rig):
    plain = rig.projects.reserve("req-1", "t", steps(2))
    caps = json.loads(rig.project(plain.project_id)["caps_json"])
    assert caps["max_parallel"] == 3 and caps["confirm_credits"] == 500 and caps["depth"] == 1 and caps["lease_s"] == 90 and rig.project(plain.project_id)["status"] == "running"
    big = [ProjectStep(ref=f"a{i}", dept_id="web") for i in range(1, 9)]
    asked = rig.projects.reserve("req-2", "t", big)
    assert rig.project(asked.project_id)["status"] == "awaiting_approval" and {n["state"] for n in rig.sql("SELECT state FROM agent_nodes WHERE project_id = ?", asked.project_id)} == {"awaiting_approval"}
    own = rig.projects.reserve("req-3", "t", big, budget=2000)
    assert rig.project(own.project_id)["status"] == "running" and json.loads(rig.project(own.project_id)["caps_json"])["confirm_credits"] is None and rig.project(own.project_id)["budget_credits"] == 2000


def test_conflict_edges_are_kept_for_the_lanes_package(rig, monkeypatch):
    rig.owner = "edit"
    monkeypatch.setattr(rig.projects, "_output_of", lambda dept: "edit")                              # writers with no scope: each holds the whole folder
    result = rig.projects.reserve("req-1", "t", [ProjectStep("a1", "web"), ProjectStep("a2", "sales")])
    assert json.loads(rig.project(result.project_id)["caps_json"])["conflict_edges"] == [["a1", "a2"]]
    nodes = rig.sql("SELECT grants_json FROM agent_nodes WHERE role = 'worker'").fetchall()
    assert all(json.loads(n["grants_json"])["tiers"] == [0, 1, 2, 3] for n in nodes)


def test_a_dependency_on_an_unknown_step_is_refused_not_stored(rig):
    result = rig.projects.reserve("req-1", "t", [ProjectStep("a1", "web"), ProjectStep("a2", "sales", ("nobody",))])
    assert result.ok is False and rig.project(result.project_id)["status"] == "failed"


def test_the_projects_routes_need_no_token_to_read_and_a_token_to_stop(world):
    client, services, connector, mid = world
    project_id = rows(services, "SELECT id FROM projects")[0]["id"]
    assert client.get(f"/api/projects/{project_id}").status_code == 200 and client.get("/api/projects/prj_" + "0" * 12).status_code == 404
    assert client.post(f"/api/projects/{project_id}/stop", json={}).status_code == 401
    assert client.post(f"/api/projects/{project_id}/pause", json={"resume": True}, headers=HEADERS).status_code in (200, 409)
