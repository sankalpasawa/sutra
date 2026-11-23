"""`POST /api/projects` and `GET /api/nodes/app-location` (MAN-13, D326): off is 404 before anything, a write needs the token, the body is closed, the request goes to the org chat as the owner's
line, `failure_policy` is kept for the project it becomes (default `stop_branch`; only this route sets `stop_all`), a repeated `client_id` starts nothing, and the app-location words are plain."""
import json
import time

from fastapi.testclient import TestClient
from orchestrator.test_chat_agent import add_dept, assignments, change_reply, decide, draft
from orchestrator.test_projects_adopt import BASE, HEADERS, make_app, rows, yes_to_new_teams
from orchestrator.test_scripted_conversation import ORG

CLIENT = "start-0001"


def script(connector):
    connector.push(decide(change="add", reuse=(), why="two"), change_reply(add_dept("$web", "Web", "Websites"), add_dept("$sales", "Sales", "Quotes")),
                   assignments(draft("a1", "web", title="Page"), draft("a2", "sales", title="Quote", depends_on=("a1",))), {"kind": "node_plan", "steps": []})


def wait_idle(services):
    deadline = time.time() + 10
    while services.runner.busy and time.time() < deadline:
        time.sleep(0.02)


def settle(client, services):
    """The turn ends; the owner says yes to the teams it proposes (a new team waits for that, D427) and the request finishes."""
    wait_idle(services)
    yes_to_new_teams(client, services)


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
        settle(client, services)
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
        settle(client, app.state.services)
        assert [r["failure_policy"] for r in rows(app.state.services, "SELECT failure_policy FROM projects")] == ["stop_branch"]


def test_the_default_policy_is_stop_branch(tmp_path):
    app, connector = make_app(tmp_path, nodes_v1=True)
    script(connector)
    with TestClient(app, base_url=BASE) as client:
        assert client.post("/api/projects", json={"client_id": CLIENT, "text": "A page and a quote"}, headers=HEADERS).status_code == 202
        settle(client, app.state.services)
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


def test_the_project_a_post_started_is_found_by_its_client_id(tmp_path):                                        # R6
    app, connector = make_app(tmp_path, nodes_v1=True)
    script(connector)
    with TestClient(app, base_url=BASE) as client:
        services = app.state.services
        assert client.get(f"/api/projects?client_id={CLIENT}").json() == []                                       # nothing sent yet
        assert client.post("/api/projects", json={"client_id": CLIENT, "text": "A page and a quote"}, headers=HEADERS).status_code == 202
        settle(client, services)
        found = client.get(f"/api/projects?client_id={CLIENT}").json()
        assert [p["id"] for p in found] == [r["id"] for r in rows(services, "SELECT id FROM projects")] and len(found) == 1
        assert client.get("/api/projects?client_id=other-0002").json() == []                                       # another send's project is not this one
        assert client.get("/api/projects?client_id=x").status_code == 422                                          # the id rule of the post
        assert len(client.get("/api/projects").json()) == 1


def test_a_note_about_a_project_ends_with_its_address_and_a_finished_project_says_so(tmp_path):
    app, connector = make_app(tmp_path, nodes_v1=True)
    script(connector)
    with TestClient(app, base_url=BASE) as client:
        services = app.state.services
        client.post("/api/projects", json={"client_id": CLIENT, "text": "A page and a quote"}, headers=HEADERS)
        settle(client, services)
        project = rows(services, "SELECT id FROM projects")[0]["id"]
        asyncio_stop = client.post(f"/api/projects/{project}/stop", json={}, headers=HEADERS)
        assert asyncio_stop.status_code == 200
        notes = [r["text"] for r in rows(services, "SELECT text FROM chat_messages WHERE session_id = ? AND kind = 'note' AND text LIKE ?", ORG, "%/p/%")]
        assert all(text.endswith(f"/p/{project}") for text in notes)


# ---- the reply ends with the project's address, whichever way the line came in (D382) -------------------------------------------------

def _reply_and_cards(services):
    replies = rows(services, "SELECT text FROM chat_messages WHERE session_id = ? AND role = 'agent' AND kind = 'text' ORDER BY id", ORG)
    cards = [json.loads(r["card_json"]) for r in rows(services, "SELECT card_json FROM chat_messages WHERE session_id = ? AND kind = 'card'", ORG)]
    return [r["text"] for r in replies], [c for c in cards if c.get("type") == "task"]


def _project_id(services):
    return rows(services, "SELECT id FROM projects")[0]["id"]


def test_a_request_sent_with_post_projects_gets_a_reply_that_ends_with_the_project_address_and_cards_that_link_to_it(tmp_path):
    app, connector = make_app(tmp_path, nodes_v1=True)
    script(connector)
    with TestClient(app, base_url=BASE) as client:
        services = app.state.services
        assert client.post("/api/projects", json={"client_id": CLIENT, "text": "A page and a quote"}, headers=HEADERS).status_code == 202
        settle(client, services)
        texts, tasks = _reply_and_cards(services)
        address = f"/p/{_project_id(services)}"
        assert texts[-1].endswith(f"You can follow it here: {address}") and sum("/p/" in t for t in texts) == 1
        assert len(tasks) == 2 and all(card["project_id"] == _project_id(services) for card in tasks)


def test_a_request_typed_in_the_org_chat_gets_the_same_address(tmp_path):
    app, connector = make_app(tmp_path, nodes_v1=True)
    script(connector)
    with TestClient(app, base_url=BASE) as client:
        services = app.state.services
        client.post(f"/api/chats/{ORG}/messages", json={"text": "A page and a quote"}, headers=HEADERS)
        settle(client, services)
        texts, tasks = _reply_and_cards(services)
        assert texts[-1].endswith(f"/p/{_project_id(services)}") and all(card["project_id"] == _project_id(services) for card in tasks)


def test_without_the_flag_the_reply_and_the_task_cards_are_what_they_were(tmp_path):
    app, connector = make_app(tmp_path)
    connector.push(decide(change="reuse", reuse=("web",), why="one"), assignments(draft("a1", "web", title="Page")))
    with TestClient(app, base_url=BASE) as client:
        services = app.state.services
        client.post(f"/api/chats/{ORG}/messages", json={"text": "A page"}, headers=HEADERS)
        settle(client, services)
        texts, tasks = _reply_and_cards(services)
        assert all("/p/" not in text for text in texts) and all("project_id" not in card for card in tasks)
        for card in rows(services, "SELECT card_json FROM chat_messages WHERE kind = 'card'"):
            assert "project_id" not in card["card_json"]


def test_only_the_apps_own_address_can_be_a_link_a_look_alike_in_a_models_word_is_made_plain(tmp_path):
    """D389: the chat page links the exact shape `/p/prj_<12 hex>`; the reply keeps the app's own address for a project that exists and breaks the shape in anything else."""
    from sutra_app.orchestrator.agent.runner import _NO_PROJECT_ADDRESS
    assert _NO_PROJECT_ADDRESS.sub("/p/ ", "see /p/prj_0123456789ab and /p/other") == "see /p/ prj_0123456789ab and /p/other"
    app, connector = make_app(tmp_path, nodes_v1=True)
    script(connector)
    with TestClient(app, base_url=BASE) as client:
        services = app.state.services
        client.post("/api/projects", json={"client_id": CLIENT, "text": "A page and a quote"}, headers=HEADERS)
        settle(client, services)
        texts, _ = _reply_and_cards(services)
        real = _project_id(services)
        assert sum(t.count("/p/prj_") for t in texts) == 1 and texts[-1].endswith(f"/p/{real}")


# ---- the two guards of the reply's address are each pinned (D408, m-10) ---------------------------------------------------------------------------------

def test_a_look_alike_address_in_a_models_word_is_broken_in_the_reply_and_only_the_real_one_is_kept(tmp_path, monkeypatch):
    from sutra_app.orchestrator.agent.runner import TurnRunner
    original = TurnRunner._sentences
    monkeypatch.setattr(TurnRunner, "_sentences", lambda self, *a, **k: [*original(self, *a, **k), "A word of the model's: /p/prj_0123456789ab."])
    app, connector = make_app(tmp_path, nodes_v1=True)
    script(connector)
    with TestClient(app, base_url=BASE) as client:
        services = app.state.services
        client.post("/api/projects", json={"client_id": CLIENT, "text": "A page and a quote"}, headers=HEADERS)
        settle(client, services)
        texts, _ = _reply_and_cards(services)
        real = _project_id(services)
        reply = texts[-1]
        assert reply.count("/p/prj_") == 1 and reply.endswith(f"/p/{real}"), reply
        assert "/p/ prj_0123456789ab" in reply, "the model's look-alike was made plain"


def test_no_address_and_no_project_key_when_the_project_is_not_there(tmp_path, monkeypatch):
    from sutra_app.orchestrator.agent.runner import TurnRunner
    monkeypatch.setattr(TurnRunner, "_project_exists", lambda self, project_id: False, raising=False)
    app, connector = make_app(tmp_path, nodes_v1=True)
    script(connector)
    with TestClient(app, base_url=BASE) as client:
        services = app.state.services
        client.post("/api/projects", json={"client_id": CLIENT, "text": "A page and a quote"}, headers=HEADERS)
        settle(client, services)
        texts, tasks = _reply_and_cards(services)
        assert all("/p/prj_" not in t for t in texts) and all("project_id" not in card for card in tasks) and tasks


def test_the_tasks_of_a_project_carry_the_do_only_your_own_job_rule_and_a_single_request_does_not(tmp_path):
    app, connector = make_app(tmp_path, nodes_v1=True)
    script(connector)
    with TestClient(app, base_url=BASE) as client:
        services = app.state.services
        client.post("/api/projects", json={"client_id": CLIENT, "text": "A page and a quote"}, headers=HEADERS)
        settle(client, services)
        framings = {r["title"]: r["framing"] for r in rows(services, "SELECT title, framing FROM tasks")}
        assert "STEP 1 OF 2" in framings["Page"] and "Do ONLY this step's own job: Page" in framings["Page"] and "Quote" in framings["Page"]
        assert "STEP 2 OF 2" in framings["Quote"] and "Do ONLY this step's own job: Quote" in framings["Quote"]


def test_an_ordinary_one_step_request_has_no_such_rule(tmp_path):
    app, connector = make_app(tmp_path)
    connector.push(decide(change="reuse", reuse=("web",), why="one"), assignments(draft("a1", "web", title="Page")))
    with TestClient(app, base_url=BASE) as client:
        services = app.state.services
        client.post(f"/api/chats/{ORG}/messages", json={"text": "A page"}, headers=HEADERS)
        settle(client, services)
        assert all("THIS IS STEP" not in r["framing"] for r in rows(services, "SELECT framing FROM tasks"))
