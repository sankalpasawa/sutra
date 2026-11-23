"""The project page's route (MAN-13, D326): `/p/{id}` is not mounted while SUTRA_NODES_V1 is off (404, like any unknown path, and Home is as it was), answers 200 with the boot block for a
known project when it is on, 404 for an id that is not a project and for a project that does not exist, and every file it names is served."""
import re
import time

from fastapi.testclient import TestClient
from orchestrator.test_chat_agent import add_dept, assignments, change_reply, decide, draft
from orchestrator.test_projects_adopt import BASE, HEADERS, make_app, rows, yes_to_new_teams
from orchestrator.test_scripted_conversation import ORG


def one_project(app, connector):
    connector.push(decide(change="add", reuse=(), why="two"), change_reply(add_dept("$web", "Web", "Websites"), add_dept("$sales", "Sales", "Quotes")),
                   assignments(draft("a1", "web", title="Page"), draft("a2", "sales", title="Quote", depends_on=("a1",))), {"kind": "node_plan", "steps": []})
    client = TestClient(app, base_url=BASE)
    client.__enter__()
    client.post(f"/api/chats/{ORG}/messages", json={"text": "A page and a quote"}, headers=HEADERS)
    deadline = time.time() + 10
    while app.state.services.runner.busy and time.time() < deadline:
        time.sleep(0.02)
    yes_to_new_teams(client, app.state.services)            # the two teams wait for the owner's yes (D427)
    return client


def test_off_there_is_no_project_page_and_home_has_no_link_to_one(tmp_path):
    app, _connector = make_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        assert client.get("/p/prj_0123456789ab").status_code == 404
        home = client.get("/")
        assert home.status_code == 200 and "/p/" not in home.text and "project_page" not in home.text


def test_on_a_known_project_has_its_page_and_anything_else_is_404(tmp_path):
    app, connector = make_app(tmp_path, nodes_v1=True)
    client = one_project(app, connector)
    try:
        project = rows(app.state.services, "SELECT id FROM projects")[0]["id"]
        page = client.get(f"/p/{project}")
        assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
        assert 'id="project-root"' in page.text and '"page":"project"' in page.text and "<!--SUTRA-BOOT-->" not in page.text
        assert "frame-ancestors" in page.headers["content-security-policy"]                     # the same policy as every page
        for name in re.findall(r'(?:src|href)="(/ui/[^"]+)"', page.text):
            assert client.get(name).status_code == 200, name                                      # every file the page names is served
        assert client.head(f"/p/{project}").status_code == 200
        assert client.get("/p/prj_000000000000").status_code == 404                              # well formed, not there
        for bad in ("/p/x", "/p/prj_xyz", "/p/prj_0123456789abcd"):
            assert client.get(bad).status_code == 404, bad
        assert client.get("/p/").status_code == 404
    finally:
        client.__exit__(None, None, None)
