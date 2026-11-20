"""`POST /api/projects/{id}/approvals/{aid}` (MAN-8): flag off 404 before anything, a token for every write, a closed body, the answer rules as the app's errors, the snapshot back."""
import time

from fastapi.testclient import TestClient
from orchestrator.test_chat_agent import add_dept, assignments, change_reply, decide, draft
from orchestrator.test_projects_adopt import BASE, HEADERS, make_app, rows
from orchestrator.test_scripted_conversation import ORG


def project_asking_github(tmp_path, **flags):
    app, connector = make_app(tmp_path, **flags)
    client = TestClient(app, base_url=BASE)
    client.__enter__()
    services = app.state.services
    connector.push(decide(change="add", reuse=(), why="two"), change_reply(add_dept("$web", "Web", "Websites"), add_dept("$sales", "Sales", "Quotes")),
                   assignments(draft("a1", "web", title="Page"), draft("a2", "sales", title="Quote", depends_on=("a1",))), {"kind": "node_plan", "steps": [{"ref": "a2", "scope": [], "needs": ["github"]}]})
    client.post(f"/api/chats/{ORG}/messages", json={"text": "A page and a quote"}, headers=HEADERS)
    deadline = time.time() + 10
    while services.runner.busy and time.time() < deadline:
        time.sleep(0.02)
    return client, services


def test_the_route_answers_the_question_and_returns_the_snapshot_with_its_card(tmp_path):
    client, services = project_asking_github(tmp_path, nodes_v1=True)
    try:
        project = rows(services, "SELECT id FROM projects")[0]["id"]
        approval = rows(services, "SELECT id FROM approvals")[0]["id"]
        snapshot = client.get(f"/api/projects/{project}").json()
        assert [c["kind"] for c in snapshot["cards"]] == ["tier"] and snapshot["cards"][0]["approval_id"] == approval
        url = f"/api/projects/{project}/approvals/{approval}"
        assert client.post(url, json={"decision": "allow_once"}).status_code == 401                                    # a write needs the token
        assert client.post(url, json={"decision": "maybe"}, headers=HEADERS).status_code == 422
        assert client.post(url, json={"decision": "allow_once", "extra": 1}, headers=HEADERS).status_code == 422
        assert client.post(f"/api/projects/{project}/approvals/ap_000000000000", json={"decision": "deny"}, headers=HEADERS).status_code == 404
        done = client.post(url, json={"decision": "allow_project"}, headers=HEADERS)
        assert done.status_code == 200 and done.json()["project"]["status"] in ("running", "done") and done.json()["cards"] == []
        assert client.post(url, json={"decision": "deny"}, headers=HEADERS).status_code == 409                        # the first answer wins
    finally:
        client.__exit__(None, None, None)


def test_with_the_flag_off_the_route_is_404_before_the_token_is_looked_at(tmp_path):
    client, services = project_asking_github(tmp_path)
    try:
        assert client.post("/api/projects/prj_000000000000/approvals/ap_000000000000", json={"decision": "deny"}).status_code == 404
        assert client.post("/api/projects/prj_000000000000/approvals/ap_000000000000", json={"decision": "deny"}, headers=HEADERS).status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_the_system_routes_are_404_when_off_need_the_token_and_404_for_a_question_that_is_not_open(tmp_path):
    client, services = project_asking_github(tmp_path)
    try:
        for action in ("check", "skip"):
            assert client.post(f"/api/projects/prj_000000000000/system/files_folders/{action}", json={}, headers=HEADERS).status_code == 404         # off: the feature does not exist
    finally:
        client.__exit__(None, None, None)
    on_dir = tmp_path / "on"
    on_dir.mkdir()
    client, services = project_asking_github(on_dir, nodes_v1=True)
    try:
        project = rows(services, "SELECT id FROM projects")[0]["id"]
        for action in ("check", "skip"):
            url = f"/api/projects/{project}/system/files_folders/{action}"
            assert client.post(url, json={}).status_code == 401
            assert client.post(url, json={"x": 1}, headers=HEADERS).status_code == 422
            assert client.post(url, json={}, headers=HEADERS).status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_the_settings_switch_the_page_uses_answers_the_open_questions_of_the_teams_projects(tmp_path):
    import asyncio
    client, services = project_asking_github(tmp_path, nodes_v1=True)
    try:
        assert rows(services, "SELECT status FROM approvals")[0]["status"] == "open"
        async def switch():
            return services.send_setting("sales", {"decide_for_me": True})
        asyncio.run(switch())
        assert rows(services, "SELECT status, decided_by FROM approvals")[0]["decided_by"] == "rule:decide_for_me" and rows(services, "SELECT decide_for_me FROM projects")[0]["decide_for_me"] == 1
    finally:
        client.__exit__(None, None, None)
