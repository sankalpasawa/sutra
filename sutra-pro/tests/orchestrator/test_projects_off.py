"""With SUTRA_NODES_V1 off the same four-step plan makes plain tasks exactly as before (MAN-5): no project, no node, no audit row, no new column used, the planner's calls carry no identity,
`task.json` has no node block, the routes are 404 and the scheduler has no gate."""
import json
import time

from fastapi.testclient import TestClient
from orchestrator.test_chat_agent import add_dept, assignments, change_reply, decide
from orchestrator.test_projects_adopt import BASE, HEADERS, four_steps, make_app, rows, talk


def test_the_same_plan_with_the_flag_off_makes_plain_tasks_and_nothing_else(tmp_path):
    app, connector = make_app(tmp_path)
    services = app.state.services
    assert services.projects is None and services.node_control is None
    assert services.tasks.task_gate is None and services.tasks.spawn_guard is None and services.tasks.node_sync is None and services.projector.node_sync is None
    assert services.runner.projects is None
    with TestClient(app, base_url=BASE) as client:
        talk(client, services, connector, "A site and a quote please", decide(change="add", reuse=(), why="two new teams"),
             change_reply(add_dept("$web", "Web", "Websites"), add_dept("$sales", "Sales", "Quotes")), four_steps())
        tasks = rows(services, "SELECT * FROM tasks ORDER BY created_at, rowid")
        assert len(tasks) == 4 and [t["lane"] for t in tasks] == [""] * 4
        for table in ("projects", "agent_nodes", "node_messages", "node_audit", "approvals"):
            assert rows(services, f"SELECT count(*) AS n FROM {table}")[0]["n"] == 0, table
        assert all("agent_node_id" not in call.context and "agent_role" not in call.context for call in connector.calls)
        deadline = time.time() + 15
        while time.time() < deadline and any(r["status"] != "done" for r in rows(services, "SELECT status FROM tasks")):
            time.sleep(0.05)
        assert {r["status"] for r in rows(services, "SELECT status FROM tasks")} == {"done"}
        for task in tasks:
            if task["run_id"]:
                path = tmp_path / "data" / "departments" / task["dept_id"] / "runs" / task["run_id"] / "task.json"
                assert "node" not in json.loads(path.read_text(encoding="utf-8"))
        for path in ("/api/projects", "/api/nodes/status"):
            assert client.get(path).status_code == 404
        assert client.post("/api/projects/prj_" + "0" * 12 + "/stop", json={}, headers=HEADERS).status_code == 404


def test_the_planner_request_has_no_identity_and_no_token_with_the_flag_off(tmp_path):
    app, connector = make_app(tmp_path)
    from sutra_app.orchestrator.agent.agent import PlanRequest
    request = PlanRequest(text="x", message_id=1)
    assert app.state.services.runner._as_planner(request) is request
