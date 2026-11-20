"""The node plan stage (MAN-8, D306): a separate small planner call, only with the flag on and only for a request that becomes a project. Its reply is a request: the paths go through the
write-scope rules, `github` asks tier 4, a reply that is not valid is asked again, and a stage that fails gives the defaults and an audit row."""
import json

from fastapi.testclient import TestClient
from orchestrator.test_chat_agent import add_dept, assignments, change_reply, decide, draft
from orchestrator.test_projects_adopt import BASE, make_app, rows, talk

TEAMS = (decide(change="add", reuse=(), why="two teams"), change_reply(add_dept("$web", "Web", "Websites"), add_dept("$sales", "Sales", "Quotes")))


def two(*extra):
    return assignments(draft("a1", "web", title="Page"), draft("a2", "sales", title="Quote", depends_on=("a1",))), *extra


def plan(*steps):
    return {"kind": "node_plan", "steps": list(steps)}


def steps_called(connector):
    return [call.step for call in connector.calls]


def run(tmp_path, reply_items, **flags):
    app, connector = make_app(tmp_path, **flags)
    client = TestClient(app, base_url=BASE)
    client.__enter__()
    services = app.state.services
    talk(client, services, connector, "A page and a quote", *TEAMS, two()[0], *reply_items)
    return client, services, connector


def test_with_the_flag_off_the_node_plan_is_never_asked(tmp_path):
    client, services, connector = run(tmp_path, [])
    try:
        assert steps_called(connector) == ["decide", "change", "assign"] and rows(services, "SELECT * FROM projects") == []
    finally:
        client.__exit__(None, None, None)


def test_with_the_flag_on_a_project_gets_one_node_plan_call_after_the_assignments_with_the_planners_identity(tmp_path):
    client, services, connector = run(tmp_path, [plan({"ref": "a1", "scope": [], "needs": []}, {"ref": "a2", "scope": [], "needs": []})], nodes_v1=True)
    try:
        assert steps_called(connector) == ["decide", "change", "assign", "nodeplan"]
        planner = rows(services, "SELECT id FROM agent_nodes WHERE role = 'planner'")[0]["id"]
        last = connector.calls[-1]
        assert last.context.get("agent_node_id") == planner and last.cancel is not None and "STEPS OF THE PROJECT" in last.prompt and "a1: Page" in last.prompt
        assert len(rows(services, "SELECT * FROM projects")) == 1 and rows(services, "SELECT * FROM approvals") == []                      # nothing asked: no gate
    finally:
        client.__exit__(None, None, None)


def test_a_step_that_needs_github_makes_the_plan_ask_tier_4_and_the_paths_are_stored_as_requests(tmp_path):
    client, services, connector = run(tmp_path, [plan({"ref": "a1", "scope": ["site/pricing", "site"], "needs": ["sutra"]}, {"ref": "a2", "scope": [], "needs": ["github"]})], nodes_v1=True)
    try:
        project = rows(services, "SELECT * FROM projects")[0]
        assert project["status"] == "awaiting_approval"
        [asked] = rows(services, "SELECT * FROM approvals")
        assert asked["tier"] == 4 and json.loads(asked["request_json"])["kind"] == "tier"
        stored = {step["ref"]: step for step in json.loads(project["caps_json"])["plan"]}
        assert stored["a1"]["scope"] == ["site"]                      # `site/pricing` is covered by `site`, as `normalize_scope` says
        assert stored["a1"]["scope"] == ["site"] and stored["a2"]["needs"] == ["github"]
        a2 = [n for n in rows(services, "SELECT * FROM agent_nodes WHERE plan_ref = 'a2'")][0]
        assert json.loads(a2["grants_json"])["tool_profile"] == "none" and all(t != "running" for t in [r["status"] for r in rows(services, "SELECT status FROM tasks")])      # not given before the owner says yes
        assert "plan" not in client.get(f"/api/projects/{project['id']}").json()["project"]["caps"]                                      # an internal key: never shown
    finally:
        client.__exit__(None, None, None)


def test_a_reply_that_is_not_valid_is_asked_again_with_the_reasons_and_the_second_is_used(tmp_path):
    bad = plan({"ref": "a5", "scope": [], "needs": []}, {"ref": "a1", "scope": ["../outside"], "needs": []})
    good = plan({"ref": "a1", "scope": [], "needs": ["github"]})
    client, services, connector = run(tmp_path, [bad, good], nodes_v1=True)
    try:
        assert steps_called(connector).count("nodeplan") == 2 and "unknown_ref" in connector.calls[-1].prompt and "bad_scope" in connector.calls[-1].prompt
        assert [r["action"] for r in rows(services, "SELECT action FROM node_audit WHERE action = 'plan.defaults'")] == []
        assert rows(services, "SELECT tier FROM approvals")[0]["tier"] == 4
    finally:
        client.__exit__(None, None, None)


def test_a_stage_that_fails_gives_the_defaults_an_audit_row_and_the_project_is_made_anyway(tmp_path):
    client, services, connector = run(tmp_path, [{"kind": "node_plan", "steps": "nonsense"}, {"kind": "node_plan", "steps": 5}], nodes_v1=True)
    try:
        assert steps_called(connector).count("nodeplan") == 2                                                                     # its own cap of two
        project = rows(services, "SELECT * FROM projects")[0]
        assert project["status"] in ("running", "done") and len(rows(services, "SELECT * FROM tasks")) == 2 and rows(services, "SELECT * FROM approvals") == []
        assert [r["action"] for r in rows(services, "SELECT action FROM node_audit WHERE action = 'plan.defaults'")] == ["plan.defaults"]
    finally:
        client.__exit__(None, None, None)


def test_a_model_that_cannot_be_reached_for_the_node_plan_gives_the_defaults_too(tmp_path):
    from sutra_app.orchestrator.agent.ports import ConnectorFailure
    client, services, connector = run(tmp_path, [ConnectorFailure("unavailable", "no model")], nodes_v1=True)
    try:
        assert [r["action"] for r in rows(services, "SELECT action FROM node_audit WHERE action = 'plan.defaults'")] == ["plan.defaults"] and len(rows(services, "SELECT * FROM projects")) == 1
    finally:
        client.__exit__(None, None, None)
