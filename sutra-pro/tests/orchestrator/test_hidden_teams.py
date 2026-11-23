"""Named projects, task 4: a project the owner deleted (a hidden team, D426) is invisible to the org chat: not in its digest, not a
candidate, not reusable, not assignable, not in Agent Org, not in the chat grounding. Its row, runs and files stay."""
import pytest
from factories_org import dept_op
from orchestrator.test_chart_store import Env

from sutra_app.connectors.workdir import WorkFolder
from sutra_app.orchestrator.agent.planner import candidates, fallback_plan
from sutra_app.orchestrator.chart_rules import reuse_violations, without_hidden
from sutra_app.orchestrator.team_admin import TeamAdmin


@pytest.fixture
def env(db, settings, clock, events, tmp_path):
    built = Env(db, settings, clock, events).build()
    admin = TeamAdmin(db, built.chart, built.chart.departments, settings.data_dir, clock, folders=WorkFolder(settings.data_dir),
                      documents=tmp_path / "Documents")
    admin.hide("web")
    return built


def test_digest_leaves_out_a_hidden_team(env):
    digest = env.chart.digest("make a web site")
    assert "web |" not in digest and "Sales" in digest


def test_the_planning_chart_leaves_out_a_hidden_team_and_what_is_under_it(env):
    chart = env.chart.planning_chart()
    ids = {n.id for n in chart.nodes}
    assert "web" not in ids and "menu" not in ids and "sales" in ids and "leads" in ids
    assert chart.revision == env.head().revision
    assert all(e.parent in ids and e.child in ids for e in chart.edges)


def test_candidates_and_fallback_leave_out_a_hidden_team(env):
    chart = env.chart.planning_chart()
    assert "web" not in [c.id for c in candidates(chart, "web site menu", limit=5)]
    found = fallback_plan("web site menu", chart)
    assert found is None or ("web" not in [c.id for c in found.candidates] and getattr(found.reuse, "id", None) != "web")


def test_an_assignment_to_a_hidden_team_is_refused(env):
    from types import SimpleNamespace
    draft = SimpleNamespace(dept="web", scope=None, follows=None)
    found = env.chart.check_assignments([draft], env.head())
    assert [v.message for v in found] == ["That project was deleted"]


def test_an_add_like_a_hidden_team_is_not_a_reuse(env):
    hidden_name = env.one("SELECT name FROM org_nodes WHERE id = 'web'")
    assert hidden_name.startswith("Web (deleted ")
    hidden = env.chart.departments.hidden_ids()
    assert reuse_violations(env.head(), [dept_op("$w", hidden_name)], hidden=hidden) == []
    assert reuse_violations(env.head(), [dept_op("$w", hidden_name)]) != []          # without the hidden set the old rule still fires


def test_agent_org_view_leaves_out_a_hidden_team(env):
    ids = [n.id for n in env.chart.view().nodes]
    assert "web" not in ids and "menu" not in ids and "sales" in ids


def test_chat_grounding_leaves_out_a_hidden_team(env):
    from sutra_app.orchestrator.chat_ground import ChatGround
    conn = env.db.conn()
    lines = "\n".join(ChatGround._org(ChatGround.__new__(ChatGround), conn))
    assert "Web" not in lines and "Sales" in lines


def test_without_hidden_keeps_the_chart_when_nothing_is_hidden(env):
    head = env.head()
    assert without_hidden(head, set()) is head


# ---- a deleted project takes no new work, whatever the path (review: Important 1) ----------------------------------------------

@pytest.fixture
def convo(tmp_path):
    from fastapi.testclient import TestClient
    from orchestrator.test_scripted_conversation import Scenario, make_scenario
    app, connector = make_scenario(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1:8780") as client:
        yield Scenario(client, app, connector)


def deleted_project(convo):
    from orchestrator.test_scripted_conversation import HEADERS
    team = convo.client.post("/api/teams", json={"name": "Pulse"}, headers=HEADERS).json()["team"]
    assert convo.client.delete(f"/api/teams/{team['id']}", headers=HEADERS).status_code == 200
    return team


def test_a_deleted_projects_chat_refuses_new_work(convo):
    from orchestrator.test_scripted_conversation import HEADERS
    team = deleted_project(convo)
    response = convo.client.post(f"/api/chats/{team['session_id']}/messages", json={"text": "build it"}, headers=HEADERS)
    assert response.status_code == 403 and response.json()["error"]["message"] == "This project was deleted."
    assert convo.one("SELECT count(*) FROM tasks WHERE dept_id = ?", team["id"]) == 0


def test_a_deleted_projects_direct_chat_refuses(convo):
    from orchestrator.test_scripted_conversation import HEADERS
    team = deleted_project(convo)
    response = convo.client.post(f"/api/chats/{team['session_id']}/direct", json={"text": "hello"}, headers=HEADERS)
    assert response.status_code == 403 and response.json()["error"]["message"] == "This project was deleted."


def test_a_deleted_projects_schedules_stop(env):
    from sutra_app.orchestrator.recurring import Recurring as RecurringService
    assert RecurringService._team_active(None, env.db.conn(), "sales") is True
    assert RecurringService._team_active(None, env.db.conn(), "web") is False
