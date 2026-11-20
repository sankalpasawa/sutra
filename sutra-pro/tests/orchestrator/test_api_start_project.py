"""`POST /api/projects` and `GET /api/nodes/app-location` (MAN-13, D326): off is 404 before anything, a write needs the token, the body is closed, the request goes to the org chat as the owner's
line, `failure_policy` is kept for the project it becomes (default `stop_branch`; only this route sets `stop_all`), a repeated `client_id` starts nothing, and the app-location words are plain."""
import time

from fastapi.testclient import TestClient
from orchestrator.test_chat_agent import add_dept, assignments, change_reply, decide, draft
from orchestrator.test_projects_adopt import BASE, HEADERS, make_app, rows
from orchestrator.test_scripted_conversation import ORG

CLIENT = "start-0001"


def script(connector):
    connector.push(decide(change="add", reuse=(), why="two"), change_reply(add_dept("$web", "Web", "Websites"), add_dept("$sales", "Sales", "Quotes")),
                   assignments(draft("a1", "web", title="Page"), draft("a2", "sales", title="Quote", depends_on=("a1",))), {"kind": "node_plan", "steps": []})


def wait_idle(services):
    deadline = time.time() + 10
    while services.runner.busy and time.time() < deadline:
        time.sleep(0.02)


def test_off_the_routes_do_not_exist_and_on_a_write_needs_the_token_and_a_closed_body(tmp_path):
    app, _connector = make_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        assert client.post("/api/projects", json={"client_id": CLIENT, "text": "x"}, headers=HEADERS).status_code == 404
        assert client.post("/api/projects", json={"client_id": CLIENT, "text": "x"}).status_code == 404                 # off looks the same to everybody
        assert client.get("/api/nodes/app-location").status_code == 404
    on = tmp_path / "on"
    on.mkdir()
    app, _connector = make_app(on, nodes_v1=True)
    with TestClient(app, base_url=BASE) as client:
        assert client.post("/api/projects", json={"client_id": CLIENT, "text": "x"}).status_code == 401
        for bad in ({"client_id": CLIENT}, {"text": "x"}, {"client_id": "short", "text": "x"}, {"client_id": CLIENT, "text": ""}, {"client_id": CLIENT, "text": "x", "extra": 1},
                    {"client_id": CLIENT, "text": "x", "failure_policy": "skip"}, {"client_id": CLIENT, "text": "x", "budget": 0}):
            assert client.post("/api/projects", json=bad, headers=HEADERS).status_code == 422, bad


def test_the_request_becomes_a_project_that_stops_all_and_the_same_send_again_starts_nothing(tmp_path):
    app, connector = make_app(tmp_path, nodes_v1=True)
    script(connector)
    with TestClient(app, base_url=BASE) as client:
        services = app.state.services
        sent = client.post("/api/projects", json={"client_id": CLIENT, "text": "A page and a quote", "failure_policy": "stop_all", "budget": 40}, headers=HEADERS)
        assert sent.status_code == 202 and sent.json()["duplicate"] is False and sent.json()["message_id"] >= 1
        wait_idle(services)
        again = client.post("/api/projects", json={"client_id": CLIENT, "text": "A page and a quote", "failure_policy": "stop_all"}, headers=HEADERS)
        assert again.status_code == 200 and again.json() == {"duplicate": True, "message_id": sent.json()["message_id"], "client_id": CLIENT}
        found = rows(services, "SELECT failure_policy, status FROM projects")
        assert [r["failure_policy"] for r in found] == ["stop_all"]                                               # one project, the owner's policy
        assert len(rows(services, "SELECT id FROM chat_messages WHERE role = 'user' AND session_id = ?", ORG)) == 1                       # one line, never two
        assert client.get("/api/projects").json()[0]["failure_policy"] == "stop_all"


def test_a_request_made_in_the_chat_is_always_stop_branch(tmp_path):
    app, connector = make_app(tmp_path, nodes_v1=True)
    script(connector)
    with TestClient(app, base_url=BASE) as client:
        client.post(f"/api/chats/{ORG}/messages", json={"text": "A page and a quote"}, headers=HEADERS)
        wait_idle(app.state.services)
        assert [r["failure_policy"] for r in rows(app.state.services, "SELECT failure_policy FROM projects")] == ["stop_branch"]


def test_the_default_policy_is_stop_branch(tmp_path):
    app, connector = make_app(tmp_path, nodes_v1=True)
    script(connector)
    with TestClient(app, base_url=BASE) as client:
        assert client.post("/api/projects", json={"client_id": CLIENT, "text": "A page and a quote"}, headers=HEADERS).status_code == 202
        wait_idle(app.state.services)
        assert [r["failure_policy"] for r in rows(app.state.services, "SELECT failure_policy FROM projects")] == ["stop_branch"]


def test_the_app_location_is_read_and_has_plain_words_only_when_it_is_not_usual(tmp_path):
    from sutra_app import oslayer
    assert oslayer.app_location("/Applications/Sutra Pro.app/Contents/MacOS/python", "darwin", {"HOME": "/h"}) == {"usual": True, "note": ""}
    assert oslayer.app_location("/h/Applications/Sutra Pro.app/Contents/MacOS/python", "darwin", {"HOME": "/h"})["usual"] is True
    off = oslayer.app_location("/Volumes/Sutra Pro/Sutra Pro.app/Contents/MacOS/python", "darwin", {"HOME": "/h"})
    assert off["usual"] is False and "Applications" in off["note"] and "/Volumes" not in off["note"] and "/h" not in off["note"]      # the words, never the path
    assert oslayer.app_location("C:\\Program Files\\Sutra Pro\\SutraPro.exe", "win32", {"ProgramFiles": "C:\\Program Files"})["usual"] is True
    assert oslayer.app_location("C:\\Users\\a\\AppData\\Local\\Programs\\Sutra Pro\\SutraPro.exe", "win32", {"LOCALAPPDATA": "C:\\Users\\a\\AppData\\Local"})["usual"] is True
    far = oslayer.app_location("D:\\Downloads\\SutraPro.exe", "win32", {"ProgramFiles": "C:\\Program Files", "LOCALAPPDATA": "C:\\Users\\a\\AppData\\Local"})
    assert far["usual"] is False and "Downloads" not in far["note"]
    assert oslayer.app_location("/usr/bin/python3", "linux", {}) == {"usual": True, "note": ""}                  # a command-line install or a checkout is never judged
    assert oslayer.app_location("/Users/a/dev/.venv/bin/python", "darwin", {"HOME": "/Users/a"}) == {"usual": True, "note": ""}
    app, _connector = make_app(tmp_path, nodes_v1=True)
    with TestClient(app, base_url=BASE) as client:
        got = client.get("/api/nodes/app-location")
        assert got.status_code == 200 and set(got.json()) == {"usual", "note"}
